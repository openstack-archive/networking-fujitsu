# Copyright 2015-2016 FUJITSU LIMITED
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

import copy
import re
import select
import time

import eventlet
telnetlib = eventlet.import_patched('telnetlib')

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

from networking_fujitsu._i18n import _
from networking_fujitsu._i18n import _LE
from networking_fujitsu._i18n import _LW
from networking_fujitsu.ml2.common import utils as fj_util
from neutron.common import utils
from neutron.plugins.ml2.common import exceptions as ml2_exc


LOG = logging.getLogger(__name__)
TELNET_PORT = 23

_EP = 'endpoint'
_PORT_MODE = 'cfab port-mode'
_IFGROUP = 'ifgroup'
_LAG = 'linkaggregation'
_LOCK_NAME = 'fujitsu-cfab'
_TIMEOUT = 30
_TIMEOUT_LOGIN = 5
_WAIT_FOR_BUSY = 3.0
_CRLF_RE = re.compile(r"\r\n", re.MULTILINE)
_PROMPT_LOGIN = "Login: "
_PROMPT_PASS = "Password: "
_PROMPT_ADMIN = "# "
_PROMPT_CONFIG = "(config)# "
_RETRY_PROMPTS_RE = re.compile(
    r"The system is busy|too many sessions")
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
_IFGROUP_RE = re.compile(r"^ifgroup\s+(\d+)\s+(?:ether|linkaggregation)\s+",
                         re.MULTILINE)
_LAG_RE = re.compile(
    r"^(?:linkaggregation\s+(?:\d+)\s(\d+)\s+)|"
    r"^interface\s+\d/\d/\d/\d$\n(?:(?:\s+.+\n)"
    r"*(?:\s+type\s+linkaggregation\s+(\d+))(?:\s+.+\n)*)\s+exit$",
    re.MULTILINE)
_VFAB_VLAN = r'^vfab\s+{v}\s+vlan\s+{vlan}\s+endpoint\s+{vlan_type}\s+(\d.*)'
_VFAB_VLANS = r'^vfab\s+{v}\s+vlan\s+(\d.*)\s+endpoint\s+{vlan_type}\s+(\d.*)'
_IFGROUP_BOUNDARY = re.compile(r'(\d+)-(\d+)')
_PPROFILE_INDICES = frozenset(range(0, 4096))
_IFGROUP_INDICES = frozenset(range(0, 4095))
_LAG_INDICES = frozenset(range(1, 200))
_INDICES = {_IFGROUP: _IFGROUP_INDICES, _LAG: _LAG_INDICES}
_REG = {_IFGROUP: _IFGROUP_RE, _LAG: _LAG_RE}


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
        self._max_retry = _TIMEOUT / _WAIT_FOR_BUSY
        self._retry_count = 0

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

    def get_candidate_config(self, prefix=None):
        """Get running-config of the switch."""

        terminal = self._execute("show terminal")
        match = _PAGER_ENABLE_RE.search(terminal)
        if match:
            self._execute("terminal pager disable")
        res = self._get_candidate_config_no_pager_control(prefix)
        if match:
            self._execute("terminal pager enable")
        return res

    def _get_candidate_config_no_pager_control(self, prefix=None):
        """Get running-config of the switch without pager control."""

        current = self._get_mode()
        if current not in (_MODE_ADMIN, _MODE_CONFIG, _MODE_CONFIG_IF):
            self._reconnect()
        cmd = "show candidate-config"
        if prefix:
            cmd = " ".join([cmd, prefix])
        return self._execute(cmd)

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
        self.close_session()
        # Open new TELNET connection
        try:
            self._telnet = telnetlib.Telnet(
                host=self._address, port=TELNET_PORT, timeout=self._timeout)
        except (OSError, EnvironmentError):
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("Connect failed to switch"))
        try:
            prompt = ""
            prompt = self._telnet.read_until(_PROMPT_LOGIN, _TIMEOUT_LOGIN)
            prompt.index(_PROMPT_LOGIN)
            self._telnet.write(self._username + "\n")
            prompt = self._telnet.read_until(_PROMPT_PASS, _TIMEOUT_LOGIN)
            prompt.index(_PROMPT_PASS)
            self._telnet.write(self._password + "\n")
            prompt = self._telnet.read_until(_PROMPT_ADMIN, _TIMEOUT_LOGIN)
            prompt.index(_PROMPT_ADMIN)
        except (EOFError, OSError, EnvironmentError, ValueError):
            if _RETRY_PROMPTS_RE.search(prompt.strip()):
                # Wait 3 seconds
                if self._retry_count < self._max_retry:
                    LOG.warning(_LW("Wait %(sec)s and retry. cause=%(cause)s"),
                                dict(sec=_WAIT_FOR_BUSY, cause=prompt))
                    self._retry_count += 1
                    time.sleep(_WAIT_FOR_BUSY)
                    self._reconnect()
                    return
                with excutils.save_and_reraise_exception():
                    self.close_session()
                    self._retry_count = 0
                    LOG.exception(_LE("Number of retry times has reached."))
            else:
                with excutils.save_and_reraise_exception():
                    self.close_session()
                    self._retry_count = 0
                    LOG.exception(_LE("Login failed to switch.(%s)"), prompt)

        self._retry_count = 0
        LOG.debug("Connect success to address %(address)s:%(telnet_port)s",
                  dict(address=self._address, telnet_port=TELNET_PORT))

    def close_session(self):
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
        except (OSError, EnvironmentError):
            self.close_session()
            try:
                self._reconnect()
                self._telnet.write(buffer)
            except (OSError, EnvironmentError):
                with excutils.save_and_reraise_exception():
                    LOG.exception(_LE("Write failed to switch"))

    def _read_eager(self):
        """Read readily available data."""
        if not self._telnet and self._address:
            self.connect(self._address, self._username, self._password)
        try:
            return self._telnet.read_eager()
        except (EOFError, OSError, EnvironmentError):
            self.close_session()
            try:
                self._reconnect()
                return self._telnet.read_eager()
            except (EOFError, OSError, EnvironmentError):
                with excutils.save_and_reraise_exception():
                    LOG.exception(_LE("Read failed from switch"))

    def _read_until(self, match):
        """Read until a given string is encountered or until timeout."""

        if not self._telnet and self._address:
            self.connect(self._address, self._username, self._password)
        try:
            return self._telnet.read_until(match, self._timeout)
        except (EOFError, OSError, EnvironmentError):
            self.close_session()
            try:
                self._reconnect()
                return self._telnet.read_until(match, self._timeout)
            except (EOFError, OSError, EnvironmentError):
                with excutils.save_and_reraise_exception():
                    LOG.exception(_LE("Read failed from switch"))

    def _expect(self, res):
        """Read until one from a list of a regular expressions matches."""

        if not self._telnet and self._address:
            self.connect(self._address, self._username, self._password)
        try:
            return self._telnet.expect(res, timeout=self._timeout)
        except (EOFError, OSError, EnvironmentError, select.error):
            self.close_session()
            try:
                self._reconnect()
                return self._telnet.expect(res, timeout=self._timeout)
            except (EOFError, OSError, EnvironmentError, select.error):
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

    def _create_ifgroup(self, ifgroup_id, ports, lag_id=None, commit=False):
        """Create ifgroup."""

        common_def = "ifgroup {if_id} {port_type} "
        if lag_id:
            port_type = _LAG
            com = common_def + "{domain} {lag}"
            cmds = [com.format(if_id=ifgroup_id, port_type=port_type,
                               domain=_get_domain_id(ports), lag=lag_id)]
        else:
            port_type = "ether"
            com = common_def + "{ports}"
            cmds = [com.format(if_id=ifgroup_id, port_type=port_type,
                               ports=ports)]
        self.mgr.configure(cmds, commit=commit)

    def _setup_interfaces(self, ports, definitions, commit=False):
        """Add definitions for specified interfaces(ports)."""

        commands = []
        # interface range {ports}
        commands.append("interface range {ports}".format(ports=ports))
        # type endpoint and cfab port-mode external
        for key in sorted(definitions):
            commands.append("{k} {v}".format(k=key, v=definitions[key]))
        commands.append("exit")
        self.mgr.configure(commands, commit=commit)

    def _setup_vfab_vlan(self, vfab_id, vlanid, ifgroup_id, config, ifg=None,
                         port_type=_EP, vlan_type='untag', commit=False):
        """Setup VFAB VLAN configuration."""

        # Judge the result of cleanup process.
        #     ifg is None
        #         'ifgroup' for vfab vlan hasn't changed at all.
        #     ifg is ''(Empty string)
        #         The definition of vfab vlan has been deleted in cleanup.
        #     ifg is String(Not empty)
        #         'ifgroup' for vfab vlan has been changed in cleanup.
        modified = True if ifg is not None else False
        ifgroups = ifg if modified else _get_ifgroups_of_vfab_vlan(
            vfab_id, vlanid, config)
        # Need to re-define for the vfab vlan.
        if modified and ifg is '':
            ifgroups = None
        if _is_ifgroup_included(ifgroup_id, ifgroups):
            LOG.debug(_("ifgroup %(if_id)s has already configured"
                        "in %(ifgs)s"), dict(if_id=ifgroup_id, ifgs=ifgroups))
        elif ifgroups is None:
            ifgroups = str(ifgroup_id)
        else:
            ifgroups += "," + str(ifgroup_id)

        cmds = [
            "vfab {vfab} vlan {vlan} {port_type} {vlan_type} {ifgroup}".format(
                vfab=vfab_id, vlan=vlanid, port_type=port_type,
                vlan_type=vlan_type, ifgroup=ifgroups)]
        self.mgr.configure(cmds, commit=commit)

    def _setup_vlan(self, vfab_id, vlanid, ports, config, ifg=None,
                    commit=False):
        """Setup untagged VLAN configuration."""

        indices = search_ifgroup_indices(ports, config)
        if not indices:
            ifgroup_id = _get_available_index(_IFGROUP, config)
            if ifgroup_id is None:
                raise ml2_exc.MechanismDriverError(method="_setup_vlan")
            self._create_ifgroup(ifgroup_id, ports)
        else:
            ifgroup_id = indices[0]
        self._setup_interfaces(ports, {'type': _EP, _PORT_MODE: 'external'})
        self._setup_vfab_vlan(vfab_id, vlanid, ifgroup_id, config, ifg=ifg,
                              commit=commit)

    def _setup_vlan_with_lag(self, vfab_id, vlanid, ports, config,
                             ifg=None, commit=False):
        """Setup untagged VLAN and LAG configuration."""

        lag_id = self._setup_lag(ports, config)
        indices = search_ifgroup_indices(ports, config, lag_id=lag_id)
        if not indices:
            ifgroup_id = _get_available_index(_IFGROUP, config)
            if ifgroup_id is None:
                raise ml2_exc.MechanismDriverError(
                    method="_setup_vlan_with_lag")
            self._create_ifgroup(ifgroup_id, ports, lag_id=lag_id)
        else:
            ifgroup_id = indices[0]
        defs = {'type': "{p_type} {lag_id}".format(p_type=_LAG, lag_id=lag_id)}
        self._setup_interfaces(ports, defs)
        self._setup_vfab_vlan(vfab_id, vlanid, ifgroup_id, config, ifg=ifg,
                              commit=commit)

    def _setup_lag(self, ports, config):
        """Setup LAG configuration.

        @param self  CFABdriver's instance
        @param ports  a string of the ports which is separated by ','
        @param config  a string of candidate-config for C-Fabric.
        @return lag_id(int)
        """

        lag_id = _get_available_index(_LAG, config)
        if lag_id is None:
            raise ml2_exc.MechanismDriverError(method="_setup_lag")
        # TODO(yushiro) LAG mode 'static', 'active' or 'passive'
        #               Currently, only support 'active'
        mode_opts = {'type': _EP, _PORT_MODE: 'external', 'mode': 'active'}
        self._configure_lag_mode(_get_domain_id(ports), lag_id, mode_opts)
        return lag_id

    def _configure_lag_mode(self, domain_id, lag_id, mode_opts, commit=False):
        """Add LAG definitions.

        @param self  CFABdriver's instance
        @param domain_id  the string of domain_id to which the port belongs
        @param lag_id  the string of LAG definiton ID
        @param mode_opts  the string of LAG mode options
        @param commit  the boolean whether executes commit or not
        @return None
        """

        commands = []
        lag = "linkaggregation {domain_id} {lag_id}".format(
            domain_id=domain_id, lag_id=lag_id)
        for key in sorted(mode_opts):
            commands.append("{lag} {k} {v}".format(lag=lag, k=key,
                                                   v=mode_opts[key]))
        self.mgr.configure(commands, commit=commit)

    def _clear_vlans(self, vfab_id, ports, config, port_type=_EP,
                     vlan_type='untag', lag_id=None, commit=False):
        """Clear all VLAN definitions with specified ports.

        @param self  CFABdriver's instance
        @param vfab_id  the string of VFAB ID
        @param ports  a string of the ports which is separated by ','
        @param config a string of a candidate-config
        @return None or string of the modified ifgroups separated by ','
        """

        # (yushiro): ifgroup won't delete because it can not determine
        #            whether ifgroup is created by plugin or not.
        indices = search_ifgroup_indices(ports, config, lag_id=lag_id)
        vlan_ifgs = _get_all_vfab_vlans_and_ifgroups(vfab_id, config,
                                                     vlan_type='untag')
        updated_vlan_ifgs = copy.deepcopy(vlan_ifgs)
        cmds = []
        for vlanid in sorted(vlan_ifgs.keys()):
            vlan = str(vlanid)
            is_delete = False
            # Target ifgroup_ids exists but vfab vlan definition does not exist
            # or ifgroup_id doesn't exist but vfab vlan definition exists.
            if None in [vlan_ifgs[vlan]] or not indices:
                LOG.debug(_("ifgroup with %(p)s for VLAN(%(v)s)has already"
                            "deleted. Skip clear_vlan."), dict(p=ports,
                                                               v=vlanid))
                continue
            eliminated = fj_util.eliminate_val(vlan_ifgs[vlan], indices)
            updated_vlan_ifgs[vlan] = eliminated
            # VLAN is configured with the only ifgroup_id
            if not eliminated:
                is_delete = True

            common_def = "vfab {vfab} vlan {vlan} {port_type} {vlan_type}"
            # Delete VFAB VLAN definition
            if is_delete:
                command = "no" + " " + common_def
                cmds.append(command.format(vfab=vfab_id, vlan=vlanid,
                                           port_type=port_type,
                                           vlan_type=vlan_type))
            # Reject ifgroup_id from VFAB VLAN definition
            else:
                command = common_def + " " + "{ifgroup}"
                cmds.append(command.format(vfab=vfab_id, vlan=vlanid,
                                           port_type=port_type,
                                           vlan_type=vlan_type,
                                           ifgroup=eliminated))
        self.mgr.configure(cmds, commit=commit)
        return updated_vlan_ifgs

    def _clear_interfaces(self, ports, commit=False):
        """Clear port type definitions with specified interfaces.

        @param self  CFABdriver's instance
        @param ports  a string of the ports which is separated by ','
        @param ether a boolean to judge ether port or linkaggregation
        @param commit a boolean to judge use "commit" or not
        @return None
        """

        cmds = ["interface range {ports}".format(ports=ports)]
        cmds.append("no type")
        cmds.append("no cfab port-mode")
        cmds.append("exit")
        self.mgr.configure(cmds, commit=commit)

    def _clear_lag(self, vfab_id, lag_id, ports, config, commit=False):
        """Clear linkaggregation definition with specified ports.

        @param self  CFABdriver's instance
        @param vfab_id a string of VFAB ID
        @param lag_id a string of LAG ID
        @param ports a string of the ports which is separated by ','
        @param config a string of candidate-config
        @return None
        """

        prefix = 'no linkaggregation {domain_id} {lag_id}'.format(
                 domain_id=_get_domain_id(ports), lag_id=lag_id)
        cmds = []
        cmds.append('{prefix} {p_mode}'.format(prefix=prefix,
                                               p_mode=_PORT_MODE))
        cmds.append('{prefix} mode'.format(prefix=prefix))
        cmds.append('{prefix} type'.format(prefix=prefix))
        self.mgr.configure(cmds, commit=commit)

    @utils.synchronized(_LOCK_NAME, external=True)
    def setup_vlan(self, address, username, password,
                   vfab_id, vlanid, ports, mac):
        """Setup untagged VLAN with specified ports.

        @param self CFABdriver's instance
        @param address the string of C-Fabric IP address
        @param username the string of C-Fabric username
        @param password the string of C-Fabric password
        @param vfab_id the string of VFAB ID
        @param vlanid the string of VLAN ID
        @param ports string of the ports which is separated by ','
        @param mac  string of the MAC address
        @return None
        """
        try:
            self.mgr.connect(address, username, password)
            config = self.mgr.get_candidate_config()
            modified = self._cleanup_definitions(vfab_id, vlanid, ports,
                                                 config, mac)
            self._setup_vlan(vfab_id, vlanid, ports, config, ifg=modified,
                             commit=True)
            self.mgr.close_session()
        except (EOFError, OSError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            self.mgr.close_session()
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    @utils.synchronized(_LOCK_NAME, external=True)
    def setup_vlan_with_lag(self, address, username, password,
                            vfab_id, vlanid, ports, mac):
        """Setup untagged VLAN and linkaggregation.

        @param self CFABdriver's instance
        @param address the string of C-Fabric IP address
        @param username the string of C-Fabric username
        @param password the string of C-Fabric password
        @param vfab_id the string of VFAB ID
        @param vlanid the string of VLAN ID
        @param ports  string of the ports which is separated by ','
        @param mac  string of the MAC address
        @return None
        """
        try:
            self.mgr.connect(address, username, password)
            config = self.mgr.get_candidate_config()
            modified = self._cleanup_definitions(vfab_id, vlanid, ports,
                                                 config, mac)
            self._setup_vlan_with_lag(vfab_id, vlanid, ports, config,
                                      ifg=modified, commit=True)
            self.mgr.close_session()
        except (EOFError, OSError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            self.mgr.close_session()
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    @utils.synchronized(_LOCK_NAME, external=True)
    def clear_vlan(self, address, username, password,
                   vfab_id, vlanid, ports, mac):
        """Clear untagged VLAN.

        @param self  CFABdriver's instance
        @param address  the string of C-Fabric IP address
        @param username  the string of C-Fabric username
        @param password  the string of C-Fabric password
        @param vfab_id  the string of VFAB ID
        @param vlanid  the string of VLAN ID
        @param ports   string of the ports which is separated by ','
        @param mac  string of the MAC address
        @return None
        """
        try:
            self.mgr.connect(address, username, password)
            config = self.mgr.get_candidate_config()
            self._dissociate_mac_from_port_profile(vfab_id, vlanid, mac,
                                                   config=config,
                                                   do_not_commit=True)
            self._clear_vlans(vfab_id, ports, config)
            self._clear_interfaces(ports, commit=True)
            self.mgr.close_session()
        except (EOFError, OSError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            self.mgr.close_session()
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    def _cleanup_definitions(self, vfab_id, vlanid, ports, config, mac,
                             commit=False):
        """Cleanup existing LAG/VLAN/interface definitions.

        @param self  CFABdriver's instance
        @param vfab_id  the string of VFAB ID
        @param vlanid  the string of VLAN ID
        @param ports   string of the ports which is separated by ','
        @param config  string of candidate-config
        @param mac  string of the MAC address
        @param commit  the boolean whether executes commit or not
        @return  A string of modified ifgroups for vfab vlan or None
        """

        self._dissociate_mac_from_port_profile(vfab_id, vlanid, mac,
                                               config=config,
                                               do_not_commit=True)
        lag_id = _get_associated_lag_id(ports, config)
        commit_interface = True if (commit and not lag_id) else False
        self._clear_interfaces(ports, commit=commit_interface)
        if commit_interface:
            LOG.debug(_('Skip clearing VLAN and LAG.'))
            return None
        modified = self._clear_vlans(vfab_id, ports, config, lag_id=lag_id)
        if lag_id:
            LOG.debug(_('Found LAG%s definiton and clear.'), lag_id)
            self._clear_lag(vfab_id, lag_id, ports, config, commit=commit)
        return modified.get(str(vlanid), None)

    @utils.synchronized(_LOCK_NAME, external=True)
    def clear_vlan_with_lag(self, address, username, password,
                            vfab_id, vlanid, ports, mac):
        """Clear untagged VLAN with linkaggregation.

        @param self  CFABdriver's instance
        @param address  the string of C-Fabric IP address
        @param username  the string of C-Fabric username
        @param password  the string of C-Fabric password
        @param vfab_id  the string of VFAB ID
        @param vlanid  the string of VLAN ID
        @param ports   string of the ports which is separated by ','
        @param mac  string of the MAC address
        @return None
        """

        try:
            self.mgr.connect(address, username, password)
            config = self.mgr.get_candidate_config()
            self._cleanup_definitions(vfab_id, vlanid, ports,
                                      config, mac, commit=True)
            self.mgr.close_session()
        except (EOFError, OSError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            self.mgr.close_session()
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    @utils.synchronized(_LOCK_NAME, external=True)
    def associate_mac_to_network(self, address, username, password,
                                 vfab_id, net_id, mac):
        """Associates a MAC address to virtual network.

        @param self  CFABdriver's instance
        @param address  the string of C-Fabric IP address
        @param username  the string of C-Fabric username
        @param password  the string of C-Fabric password
        @param vfab_id  the string of VFAB ID
        @param net_id  the string of VLAN ID(segmentation_id for network)
        @param mac the string of MAC address
        @return None
        """

        try:
            self.mgr.connect(address, username, password)
            self._associate_mac_to_port_profile(vfab_id, net_id, mac)
            self.mgr.close_session()
        except (EOFError, OSError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            self.mgr.close_session()
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    @utils.synchronized(_LOCK_NAME, external=True)
    def dissociate_mac_from_network(self, address, username, password,
                                    vfab_id, net_id, mac):
        """Dissociates a MAC address from virtual network.

        @param self  CFABdriver's instance
        @param address  the string of C-Fabric IP address
        @param username  the string of C-Fabric username
        @param password  the string of C-Fabric password
        @param vfab_id  the string of VFAB ID
        @param net_id  the string of VLAN ID(segmentation_id for network)
        @param mac the string of MAC address
        @return None
        """

        try:
            self.mgr.connect(address, username, password)
            self._dissociate_mac_from_port_profile(vfab_id, net_id, mac)
            self.mgr.close_session()
        except (EOFError, OSError, EnvironmentError, select.error,
                ml2_exc.MechanismDriverError):
            self.mgr.close_session()
            with excutils.save_and_reraise_exception():
                LOG.exception(_LE("CLI error"))

    def _create_port_profile(self, vlanid, mac_address, running_config=None,
                             commit=True):
        """Creates a port profile."""

        if running_config is None:
            running_config = self.mgr.get_running_config()
        if self._share_pprofile:
            pprofile = self._get_pprofile(vlanid, mac_address, running_config)
            if pprofile is None:
                pprofile = self._get_new_pprofile(
                    vlanid, mac_address, running_config)
                self._configure_pprofile(pprofile, vlanid, commit)
        else:
            pprofile = self._get_new_pprofile(
                vlanid, mac_address, running_config)
            match = re.search(
                r"^pprofile\s+{pid}\s+vlan\s+tag\s+([0-9,-]+)".format(
                    pid=re.escape(pprofile)), running_config, re.MULTILINE)
            if match:
                if match.group(1) != str(vlanid):
                    LOG.warning(
                        _LW('Override "pprofile %(pid)s vlan tag %(vids)s" '
                            'to "vlan tag %(vlanid)s"'),
                        dict(pid=pprofile, vids=match.group(1),
                             vlanid=vlanid))
                    self._configure_pprofile(pprofile, vlanid, commit)
            else:
                self._configure_pprofile(pprofile, vlanid, commit)
        return pprofile

    def _configure_pprofile(self, profile, vlanid, commit=True):
        """Configures pprofile."""

        self.mgr.configure(
            ["pprofile {pid} vlan tag {vid}".format(
                pid=profile, vid=vlanid)], commit=commit)

    def _get_pprofile(self, vlanid, mac_address, running_config):
        """Gets the name of existing pprofile."""

        if self._share_pprofile:
            pprofile = None
            match = re.search(
                r"^pprofile\s+({prefix}\S+)\s+vlan\s+tag\s+{vid}$".format(
                    prefix=re.escape(self._pprofile_prefix), vid=vlanid),
                running_config, re.MULTILINE)
            if match:
                pprofile = match.group(1)
        else:
            pprofile = self._get_new_pprofile(
                vlanid, mac_address, running_config)
            match = re.search(
                r"^pprofile\s+{pid}\s+vlan\s+tag\s+{vid}$".format(
                    pid=re.escape(pprofile), vid=vlanid),
                running_config, re.MULTILINE)
            if not match:
                pprofile = None
        return pprofile

    def _get_new_pprofile(self, vlanid, mac_address, running_config):
        """Gets a name of new pprofile for the MAC address or the vlan id."""

        if self._share_pprofile:
            used = re.findall(
                r"^pprofile\s+(\S+)\s+", running_config, re.MULTILINE)
            while True:
                pprofile = self._pprofile_name.format(
                    prefix=self._pprofile_prefix, pid=vlanid)
                if pprofile not in used:
                    return pprofile
                vlanid += 1
        else:
            return self._pprofile_name.format(
                prefix=self._pprofile_prefix, pid=mac_address)

    def _associate_mac_to_port_profile(self, vfab_id, vlanid, mac_address):
        """Associates a MAC address to a port profile."""

        running_config = self.mgr.get_running_config()
        pprofile = self._create_port_profile(
            vlanid, mac_address, running_config, commit=False)
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

    def _dissociate_mac_from_port_profile(self, vfab_id, vlanid, mac_address,
                                          config=None, do_not_commit=False):
        """Dissociates a MAC address from a port profile."""

        config = config if config else self.mgr.get_running_config()
        pprofile = self._get_pprofile(vlanid, mac_address, config)
        if pprofile is None:
            return
        index = _get_vfab_pprofile_index(
            vfab_id, pprofile, mac_address, config)
        if index is not None:
            delete_port_profile = True
            for m in _VFAB_PPROFILE_RE.finditer(config):
                if m.group(3) == pprofile and not (
                        m.group(1) == vfab_id and m.group(2) == index):
                    delete_port_profile = False
                    break
            commit = False if do_not_commit else (not delete_port_profile)
            self.mgr.configure(
                ["no vfab {vfab_id} pprofile {index}".format(
                    vfab_id=vfab_id, index=index)], commit=commit)
            if delete_port_profile:
                commit = False if do_not_commit else delete_port_profile
                self.mgr.configure(["no pprofile {pid}".format(pid=pprofile)],
                                   commit=commit)
        else:
            LOG.warning(
                _LW("No corresponding vfab pprofile for %(vid)s, %(mac)s"),
                dict(vid=vlanid, mac=mac_address))


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


def search_ifgroup_indices(ports, candidate_config, lag_id=None):
    """Search ifgroup ids with specified ports."""

    reg = r"^ifgroup\s+(\d+)\s+ether\s+{ports}$".format(ports=ports)
    if lag_id:
        domain_id = _get_domain_id(ports)
        reg = r"^ifgroup\s+(\d+)\s+{if_type}\s+{domain_id}\s+{lag_id}$".format(
            if_type=_LAG, domain_id=domain_id, lag_id=lag_id)
    match = re.findall(reg, candidate_config, re.MULTILINE)
    if match:
        ifgroup_indices = sorted([int(m) for m in match])
        LOG.debug(_('Found ifgroup for port(%(p)s):%(ifg)s'),
                  dict(p=ports, ifg=ifgroup_indices))
        return ifgroup_indices
    return []


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


def _get_ifgroups_of_vfab_vlan(vfab_id, vlanid, config, vlan_type='untag'):
    """Gets ifgroup definitions for specified vfab vlan.

        @param vfab_id  the string of VFAB ID
        @param vlanid  the string of VLAN ID
        @param config the string of candidate-config
        @param vlan_type 'untag(default)' or 'tag'.
        @return the string of ifgroups otherwise None
    """
    match = re.search(
        _VFAB_VLAN.format(v=vfab_id, vlan=vlanid, vlan_type=vlan_type),
        config, re.MULTILINE)
    if match:
        return match.group(1)
    else:
        return None


def _get_all_vfab_vlans_and_ifgroups(vfab_id, config, vlan_type='untag'):
    """Gets all VFAB VLAN definitions and ifgroups.

        @param vfab_id  the string of VFAB ID
        @param config the string of candidate-config
        @param vlan_type 'untag(default)' or 'tag'.
        @return the string of ifgroups otherwise None
    """
    match = re.findall(_VFAB_VLANS.format(v=vfab_id, vlan_type=vlan_type),
                       config, re.MULTILINE)
    result = dict(match)
    if result:
        LOG.debug(_('VFAB(%(vfab)s){VLANID: ifgroups}:%(result)s'),
                  dict(vfab=vfab_id, result=result))
    else:
        LOG.debug(_('VLAN and ifgroups not found.'))
    return result


def _get_available_index(target, config):
    """Gets an available index for specified target resource."""

    indices = _INDICES[target]
    reg = _REG[target]
    available = indices - set([int(''.join(x)) for x in reg.findall(config)])
    if len(available) > 0:
        return sorted(available)[0]
    else:
        LOG.error(_LE("No unused %s index."), target)
        return None


def _get_associated_lag_id(ports, config):
    """Get lag_id which is associated to the ports."""

    ids = []
    interfaces = ports.split(",")
    for port in interfaces:
        match = re.search(
            r'^interface\s+{port}$\n((?:\s+.+\n)'
            r'*(\s+type\s+{port_type}\s+(\d+))(?:\s+.+\n)*)\s+exit$'.format(
                port=port, port_type='linkaggregation'), config, re.MULTILINE)
        if match:
            ids.append(match.group(3))
    lag_ids = list(set(ids))
    if not lag_ids:
        return None
    if len(lag_ids) > 1:
        LOG.warning(
            _LW("Each port%(ports)s has different LAG ids(%(lag_ids)s)"),
            dict(ports=ports, lag_ids=lag_ids))
    LOG.debug(_("Associated LAG%(lag_ids)s with interfaces:%(ports)s"),
              dict(lag_ids=lag_ids, ports=ports))
    return sorted(lag_ids)[0]


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


def _get_domain_id(physical_ports):
    """Get CFAB domain_id from port."""

    # TODO(yushiro) Consider how to get domain_id
    return physical_ports[0]


def _is_ifgroup_included(ifgroup_id, ifgroups):
    """Judge a specified ifgorup is included into ifgroups or not."""

    if ifgroups is None:
        return False
    if str(ifgroup_id) in ifgroups:
        return True
    match = _IFGROUP_BOUNDARY.findall(ifgroups)
    if match:
        for ifg in match:
            if (int(ifg[0]) <= ifgroup_id and ifgroup_id <= int(ifg[1])):
                return True
    return False
