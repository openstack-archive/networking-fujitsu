# Copyright 2015 FUJITSU LIMITED
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#


"""Fujitsu C-Fabric Driver implements CLI over telnet for
Neutron network life-cycle management.
"""

import re
import select

import eventlet
telnetlib = eventlet.import_patched('telnetlib')

from oslo_config import cfg
try:
    from oslo_log import log as logging
except ImportError:
    from neutron.openstack.common import log as logging
try:
    from oslo_utils import excutils
except ImportError:
    from neutron.openstack.common import excutils

from neutron.common import utils
try:
    from neutron.i18n import _LE
    from neutron.i18n import _LW
except ImportError:
    try:
        from neutron.openstack.common._i18n import _LE
        from neutron.openstack.common._i18n import _LW
    except ImportError:
        from neutron.openstack.common.gettextutils import _LE
        from neutron.openstack.common.gettextutils import _LW
from neutron.plugins.ml2.common import exceptions as ml2_exc


LOG = logging.getLogger(__name__)
TELNET_PORT = 23

_LOCK_NAME = 'fujitsu'
_TIMEOUT = 30
_TIMEOUT_LOGIN = 5
_CRLF_RE = re.compile(r"\r\n", re.MULTILINE)
_PROMPT_LOGIN = "Login: "
_PROMPT_PASS = "Password: "
_PROMPT_ADMIN = "# "
_PROMPT_CONFIG = "(config)# "
_PROMPTS_RE = re.compile(
    r"(((\(config(-if)?\))?#)|((?<!<ERROR)>)|((Login|Password):)) $")
_ADMIN_PROMPTS_RE = re.compile(r"((\(config(-if)?\))?#) $")

_MODE_LOGIN = 'login'
_MODE_ADMIN = 'admin'
_MODE_CONFIG = 'config'
_MODE_CONFIG_IF = 'config-if'
_MODE_USER = 'user'

_PAGER_ENABLE_RE = re.compile(r"^pager\s+enable", re.MULTILINE)
_INDEX_RE = re.compile(r"^(\d+)\s+", re.MULTILINE)
_VFAB_PPROFILE_RE = re.compile(
    r"^vfab\s+(default|\d+)\s+pprofile\s+(\d+)\s+"
    r"vsiid\s+(?:mac|uuid)\s+\S+\s+(\S+)", re.MULTILINE)
_PPROFILE_INDICES = frozenset(range(0, 4096))


class _CFABManager(object):
    """C-Fabric CLI manager.

    Manages C-Fabric using a single telnet connection.
    """

    def __init__(self):
        self._address = None
        self._username = None
        self._password = None
        self._telnet = None
        self._timeout = _TIMEOUT
        self.save_config = True

    def connect(self, address, username, password):
        """Connect via TELNET and initialize the CLI session."""

        # Use the persisted TELNET connection
        if ((self._telnet and address == self._address and
             username == self._username and password == self._password)):
            return

        # Connect using saved information
        self._address = address
        self._username = username
        self._password = password
        self._reconnect()

    def get_running_config(self, prefix=None):
        """Get running-config of the switch."""

        terminal = self._execute("show terminal")
        match = _PAGER_ENABLE_RE.search(terminal)
        if match:
            self._execute("terminal pager disable")
        res = self._get_running_config_no_pager_control(prefix)
        if match:
            self._execute("terminal pager enable")
        return res

    def _get_running_config_no_pager_control(self, prefix=None):
        """Get running-config of the switch without pager control."""

        current = self._get_mode()
        if current not in (_MODE_ADMIN, _MODE_CONFIG, _MODE_CONFIG_IF):
            self._reconnect()
        cmd = "show running-config"
        if prefix:
            cmd = " ".join([cmd, prefix])
        return self._execute(cmd)

    def configure(self, cmds, commit=True):
        """Configures the switch."""

        self._set_mode_config()
        for cmd in cmds:
            self._execute(cmd)
        if commit:
            self._execute("commit")
            if self.save_config:
                self._execute("save")

    def _set_mode_config(self):
        """Sets the configure mode of the switch."""

        current = self._get_mode()
        if current == _MODE_CONFIG:
            return
        if current == _MODE_ADMIN:
            self._write("configure\n")
            prompt = self._read_until(_PROMPT_CONFIG)
        elif current == _MODE_CONFIG_IF:
            self._write("exit\n")
            prompt = self._read_until(_PROMPT_CONFIG)
        else:
            self._reconnect()
            self._write("configure\n")
            prompt = self._read_until(_PROMPT_CONFIG)
        if prompt.find(_PROMPT_CONFIG) < 0:
            LOG.error(_LE("Failed to set configure mode."))
            raise ml2_exc.MechanismDriverError(method="_set_mode_config")

    def _get_mode(self):
        """Gets the current mode of the switch."""

        self._read_eager()
        self._write("\n")
        idx, match, s = self._expect([_PROMPTS_RE])
        if idx < 0 or match is None:
            LOG.error(_LE("Unexpected response from switch: %s"), s)
            raise ml2_exc.MechanismDriverError(method="_get_mode")
        return _get_mode_from_match(match)

    def _execute(self, cmd):
        """Execute the command on the switch."""

        self._write(cmd + "\n")
        idx, match, s = self._expect([_PROMPTS_RE])
        if idx < 0 or match is None:
            LOG.error(_LE("Unexpected response from switch: %s"), s)
            raise ml2_exc.MechanismDriverError(method="_execute")
        if s.find("<ERROR>") >= 0:
            LOG.error(_LE("Error is returned from switch: %s"), s)
            raise ml2_exc.MechanismDriverError(method="_execute")
        s = _CRLF_RE.sub(r"\n", s)
        # Remove command and prompt
        return s[s.find("\n") + 1:s.rfind("\n") + 1]

    def _reconnect(self):
        """Re-connect and initialize the CLI session."""

        # Close the old connection
        self._close_session()

        # Open new TELNET connection
        try:
            self._telnet = telnetlib.Telnet(
                host=self._address, port=TELNET_PORT, timeout=self._timeout)
        except EnvironmentError:
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("Connect failed to switch"))
        try:
            prompt = self._telnet.read_until(_PROMPT_LOGIN, _TIMEOUT_LOGIN)
            prompt.index(_PROMPT_LOGIN)
            self._telnet.write(self._username + "\n")
            prompt = self._telnet.read_until(_PROMPT_PASS, _TIMEOUT_LOGIN)
            prompt.index(_PROMPT_PASS)
            self._telnet.write(self._password + "\n")
            prompt = self._telnet.read_until(_PROMPT_ADMIN, _TIMEOUT_LOGIN)
            prompt.index(_PROMPT_ADMIN)
        except (EOFError, EnvironmentError, ValueError):
            self._telnet.close()
            self._telnet = None
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("Login failed to switch"))

        LOG.debug("Connect success to address %(address)s:%(telnet_port)d",
                  dict(address=self._address, telnet_port=TELNET_PORT))

    def _close_session(self):
        """Close TELNET session."""

        if self._telnet:
            self._telnet.close()
            self._telnet = None

    def _write(self, buffer):
        """Write a string to the switch."""

        if not self._telnet and self._address:
            self.connect(self._address, self._username, self._password)
        try:
            self._telnet.write(buffer)
        except EnvironmentError:
            self._close_session()
            try:
                self._reconnect()
                self._telnet.write(buffer)
            except EnvironmentError:
                with excutils.save_and_reraise_exception():
                    LOG.exception(_LE("Write failed to switch"))

    def _read_eager(self):
        """Read readily available data."""
        if not self._telnet and self._address:
            self.connect(self._address, self._username, self._password)
        try:
            return self._telnet.read_eager()
        except (EOFError, EnvironmentError):
            self._close_session()
            try:
                self._reconnect()
                return self._telnet.read_eager()
            except (EOFError, EnvironmentError):
                with excutils.save_and_reraise_exception():
                    LOG.exception(_LE("Read failed from switch"))

    def _read_until(self, match):
        """Read until a given string is encountered or until timeout."""

        if not self._telnet and self._address:
            self.connect(self._address, self._username, self._password)
        try:
            return self._telnet.read_until(match, self._timeout)
        except (EOFError, EnvironmentError):
            self._close_session()
            try:
                self._reconnect()
                return self._telnet.read_until(match, self._timeout)
            except (EOFError, EnvironmentError):
                with excutils.save_and_reraise_exception():
                    LOG.exception(_LE("Read failed from switch"))

    def _expect(self, res):
        """Read until one from a list of a regular expressions matches."""

        if not self._telnet and self._address:
            self.connect(self._address, self._username, self._password)
        try:
            return self._telnet.expect(res, timeout=self._timeout)
        except (EOFError, EnvironmentError, select.error):
            self._close_session()
            try:
                self._reconnect()
                return self._telnet.expect(res, timeout=self._timeout)
            except (EOFError, EnvironmentError, select.error):
                with excutils.save_and_reraise_exception():
                    LOG.exception(_LE("Read failed from switch"))


def _get_mode_from_match(match):
    """Determines the mode from the match object."""

    mode = None
    if match.group(4):
        mode = _MODE_CONFIG_IF
    elif match.group(3):
        mode = _MODE_CONFIG
    elif match.group(2):
        mode = _MODE_ADMIN
    elif match.group(5):
        mode = _MODE_USER
    elif match.group(6):
        mode = _MODE_LOGIN
    return mode

CFAB_MANAGER = _CFABManager()


class CFABdriver(object):
    """C-Fabric CLI interface driver for Neutron network.

    Handles life-cycle management of Neutron network (leverages AMPP on C-Fab)
    """

    def __init__(self, conf=None):
        if conf:
            self._conf = conf
        else:
            self._conf = cfg.CONF
        self._share_pprofile = self._conf.fujitsu_cfab.share_pprofile
        self._pprofile_prefix = self._conf.fujitsu_cfab.pprofile_prefix
        self._validate_pprofile_prefix()
        self._pprofile_name = "{prefix}{pid}"
        self._save_config = self._conf.fujitsu_cfab.save_config
        self.mgr = CFAB_MANAGER
        self.mgr.save_config = self._save_config

    def _validate_pprofile_prefix(self):
        if len(self._pprofile_prefix) > (28 if self._share_pprofile else 15):
            raise ValueError(_("pprofile_prefix is too long."))
        if (self._pprofile_prefix.find('"') >= 0 or
                self._pprofile_prefix.find("|") >= 0 or
                self._pprofile_prefix.find("?") >= 0):
            raise ValueError(_("pprofile_prefix contains illegal character."))

    @utils.synchronized(_LOCK_NAME)
    def associate_mac_to_network(self, address, username, password,
                                 vfab_id, net_id, mac):
        """Associates a MAC address to virtual network."""

        try:
            self.mgr.connect(address, username, password)
            self._associate_mac_to_port_profile(vfab_id, net_id, mac)
        except (EOFError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    @utils.synchronized(_LOCK_NAME)
    def dissociate_mac_from_network(self, address, username, password,
                                    vfab_id, net_id, mac):
        """Dissociates a MAC address from virtual network."""

        try:
            self.mgr.connect(address, username, password)
            self._dissociate_mac_from_port_profile(vfab_id, net_id, mac)
        except (EOFError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    def _create_port_profile(self, vlan_id, mac_address, running_config=None,
                             commit=True):
        """Creates a port profile."""

        if running_config is None:
            running_config = self.mgr.get_running_config()
        if self._share_pprofile:
            pprofile = self._get_pprofile(vlan_id, mac_address, running_config)
            if pprofile is None:
                pprofile = self._get_new_pprofile(
                    vlan_id, mac_address, running_config)
                self._configure_pprofile(pprofile, vlan_id, commit)
        else:
            pprofile = self._get_new_pprofile(
                vlan_id, mac_address, running_config)
            match = re.search(
                r"^pprofile\s+{pid}\s+vlan\s+tag\s+([0-9,-]+)".format(
                    pid=re.escape(pprofile)), running_config, re.MULTILINE)
            if match:
                if match.group(1) != str(vlan_id):
                    LOG.warning(
                        _LW('Override "pprofile %(pid)s vlan tag %(vids)s" '
                            'to "vlan tag %(vlan_id)s"'),
                        dict(pid=pprofile, vids=match.group(1),
                             vlan_id=vlan_id))
                    self._configure_pprofile(pprofile, vlan_id, commit)
            else:
                self._configure_pprofile(pprofile, vlan_id, commit)
        return pprofile

    def _configure_pprofile(self, profile, vlan_id, commit=True):
        """Configures pprofile."""

        self.mgr.configure(
            ["pprofile {pid} vlan tag {vid}".format(
                pid=profile, vid=vlan_id)], commit=commit)

    def _get_pprofile(self, vlan_id, mac_address, running_config):
        """Gets the name of existing pprofile."""

        if self._share_pprofile:
            pprofile = None
            match = re.search(
                r"^pprofile\s+({prefix}\S+)\s+vlan\s+tag\s+{vid}$".format(
                    prefix=re.escape(self._pprofile_prefix), vid=vlan_id),
                running_config, re.MULTILINE)
            if match:
                pprofile = match.group(1)
        else:
            pprofile = self._get_new_pprofile(
                vlan_id, mac_address, running_config)
            match = re.search(
                r"^pprofile\s+{pid}\s+vlan\s+tag\s+{vid}$".format(
                    pid=re.escape(pprofile), vid=vlan_id),
                running_config, re.MULTILINE)
            if not match:
                pprofile = None
        return pprofile

    def _get_new_pprofile(self, vlan_id, mac_address, running_config):
        """Gets a name of new pprofile for the MAC address or the vlan id."""

        if self._share_pprofile:
            used = re.findall(
                r"^pprofile\s+(\S+)\s+", running_config, re.MULTILINE)
            while True:
                pprofile = self._pprofile_name.format(
                    prefix=self._pprofile_prefix, pid=vlan_id)
                if pprofile not in used:
                    return pprofile
                vlan_id += 1
        else:
            return self._pprofile_name.format(
                prefix=self._pprofile_prefix, pid=mac_address)

    def _associate_mac_to_port_profile(self, vfab_id, vlan_id, mac_address):
        """Associates a MAC address to a port profile."""

        running_config = self.mgr.get_running_config()
        pprofile = self._create_port_profile(
            vlan_id, mac_address, running_config, commit=False)
        index, profile_name = _search_vfab_pprofile(
            vfab_id, mac_address, running_config)
        if index is None:
            index = _get_available_vfab_pprofile_index(
                vfab_id, running_config)
            if index is None:
                LOG.error(_LE("No unused vfab pprofile index"))
                raise ml2_exc.MechanismDriverError(
                    method="_associate_mac_to_port_profile")
        else:
            if pprofile == profile_name:
                return
            else:
                LOG.warning(
                    _LW('Override "vfab %(vfab_id)s pprofile %(index)d vsiid '
                        'mac %(mac)s %(profile_name)s" to "vsiid mac %(mac)s '
                        '%(pprofile)s"'),
                    dict(vfab_id=vfab_id, index=index, mac=mac_address,
                         profile_name=profile_name, pprofile=pprofile))
        self.mgr.configure(
            ["vfab {vfab_id} pprofile {index} vsiid mac {mac} "
             "{pid}".format(
                 vfab_id=vfab_id, index=index, mac=mac_address, pid=pprofile)])

    def _dissociate_mac_from_port_profile(self, vfab_id, vlan_id, mac_address):
        """Dissociates a MAC address from a port profile."""

        running_config = self.mgr.get_running_config()
        pprofile = self._get_pprofile(vlan_id, mac_address, running_config)
        if pprofile is None:
            return
        index = _get_vfab_pprofile_index(
            vfab_id, pprofile, mac_address, running_config)
        if index is not None:
            delete_port_profile = True
            for m in _VFAB_PPROFILE_RE.finditer(running_config):
                if m.group(3) == pprofile and not (
                        m.group(1) == vfab_id and m.group(2) == index):
                    delete_port_profile = False
                    break
            self.mgr.configure(
                ["no vfab {vfab_id} pprofile {index}".format(
                    vfab_id=vfab_id, index=index)],
                commit=not delete_port_profile)
            if delete_port_profile:
                self.mgr.configure(["no pprofile {pid}".format(pid=pprofile)])
        else:
            LOG.warning(
                _LW("No corresponding vfab pprofile for %(vid)s, %(mac)s"),
                dict(vid=vlan_id, mac=mac_address))


def _search_vfab_pprofile(vfab_id, mac_address, running_config):
    """Search for the vfab pprofile. Returns (index, pprofile) if found."""

    match = re.search(
        r"^vfab\s+{vfab_id}\s+pprofile\s+(\d+)\s+"
        r"vsiid\s+mac\s+{mac}\s+(\S+)$".format(
            vfab_id=vfab_id, mac=mac_address),
        running_config, re.MULTILINE)
    if match:
        return int(match.group(1)), match.group(2)
    else:
        return None, None


def _get_vfab_pprofile_index(vfab_id, pprofile, mac_address, running_config):
    """Gets the index for vfab pprofile."""

    index = None
    match = re.search(
        r"^vfab\s+{vfab_id}\s+pprofile\s+(\d+)\s+"
        r"vsiid\s+mac\s+{mac}\s+{pid}\b".format(
            vfab_id=vfab_id, mac=mac_address, pid=pprofile),
        running_config, re.MULTILINE)
    if match:
        index = match.group(1)
    return index


def _get_available_vfab_pprofile_index(vfab_id, running_config):
    """Gets an available index for vfab pprofile."""

    available = _PPROFILE_INDICES - set(
        [int(x) for x in
         re.findall(
             r"^vfab\s+{vfab_id}\s+pprofile\s+(\d+)\s+".format(
                 vfab_id=vfab_id), running_config, re.MULTILINE)])
    if len(available) > 0:
        return sorted(available)[0]
    else:
        return None
