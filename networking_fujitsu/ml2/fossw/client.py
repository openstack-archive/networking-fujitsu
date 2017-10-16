# Copyright 2017 FUJITSU LIMITED
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#

import re
import socket
import time

from oslo_log import log as logging
import paramiko

from networking_fujitsu._i18n import _

LOG = logging.getLogger(__name__)

MODE_GLOBAL = 'configure'
MODE_VLAN = 'vlan database'
MODE_INTERFACE = 'interface'
ENABLE = 'enable'
END = 'end'
READ_TIMEOUT = 5.0
MAX_LOOP = 50
MAX_VPC_ID = 63
SHOW_PC_BRIEF = 'show port-channel brief'
TERMINAL_LENGTH_0 = 'terminal length 0'
RECV_BUF = 32768


class FOSSWClient(object):

    def __init__(self, conf):
        self._conf = conf
        self.ssh = None
        self.console = None

    def connect(self, ip):
        """Establish ssh connection for FOS switch.

        If exists session for specified target, reuse it otherwise reconnect.
        In order to get command result correctly, execute 'terminal length 0'
        at the beginning of the session.
        :param ip: a ip address of FOS switch
        :type ip: string
        :returns: None
        :rtype: None

        """
        if not self.lookup(ip):
            self._reconnect(ip)
            self._exec_command(TERMINAL_LENGTH_0)

    def _reconnect(self, ip):
        """Reconnect a new SSH session

        :param ip: a ip address of FOS switch
        :type ip: string
        :returns: None
        :rtypes: None

        """
        self.disconnect()
        method = "connect"
        retry_count = 0
        while retry_count < 5:
            try:
                self.ssh = paramiko.SSHClient()
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh.connect(
                    ip,
                    port=self._conf.fujitsu_fossw.port,
                    username=self._conf.fujitsu_fossw.username,
                    password=self._conf.fujitsu_fossw.password,
                    timeout=self._conf.fujitsu_fossw.timeout
                )
                self.console = self.ssh.invoke_shell()
                self.console.settimeout(READ_TIMEOUT)
                return
            except socket.error as e:
                LOG.warning('A socket error occurred while connecting. %s', e)
            except IOError as e:
                LOG.warning('Could not initialize SSH client. %s', e)
            except (paramiko.ssh_exception.BadHostKeyException,
                    paramiko.ssh_exception.AuthenticationException,
                    paramiko.ssh_exception.SSHException) as e:
                LOG.warning('Could not connect to FOS switch. An error'
                            'occurred while connecting. %s', e)
            except Exception as e:
                LOG.warning('Unexpected error occurred while connecting. '
                            '%s', e)
            retry_count += 1
            self.disconnect()
            LOG.warning('Connect attempt %s failed.', retry_count)
        if retry_count >= 5:
            self.disconnect()
            LOG.exception('Max retries exceeded. Failed to connect to '
                          'FOS switch.')
            raise FOSSWClientException(method)

    def disconnect(self):
        """Close ssh connection with FOS switch.

        :returns: None
        :rtypes: None

        """
        if self.ssh:
            self.ssh.close()
            self.ssh = None
            self.console = None
        else:
            LOG.debug("SSH connection already closed.")

    def _exec_command(self, command):
        try:
            raw_res = ""
            self.console.send(command + "\n")
            LOG.info("FOSSW client sent: %s", command)
            i = 0
            while i < MAX_LOOP:
                time.sleep(0.1)
                if self.console.recv_ready():
                    raw_res += self.console.recv(RECV_BUF)
                elif raw_res:
                    break
                i += 1
            if i == MAX_LOOP:
                LOG.error("No reply from FOS switch.")
                raise socket.timeout
            index = raw_res.find(command)
            received = raw_res[(index + len(command) + 1):]
        except socket.timeout:
            self.disconnect()
            LOG.exception('Socket timeout occurred while executing '
                          'commands to FOS Switch.')
            raise FOSSWClientException(method='_exec_command')
        else:
            LOG.debug("FOSSW client received: %s", received)
            # NOTE(yushiro) Validate received message here
            return received.replace('\r\n', '\n')

    def _format_command(self, command, **kwargs):
        method = "_format_command"
        if not all(kwargs.values()):
            raise FOSSWClientException(method)
        try:
            formatted = command.format(**kwargs)
        except (KeyError, TypeError):
            raise FOSSWClientException(method)
        return formatted

    def lookup(self, target):
        """Check exist session for specified IP.

        :param target: IP address of a target host
        :type target: string

        :returns: exist(True) or not exist(False)
        :rtype: bool

        """
        if self.ssh:
            if self.ssh._host_keys:
                if self.ssh._host_keys.lookup(target):
                    LOG.debug('Reuse existing session for %s.', target)
                    return True
        return False

    def create_vlan(self, segmentation_id):
        """Define VLAN with specified VLAN ID to FOS switch.

        :param segmentation_id: id of VLAN to be created.
        :type segmentation_id: string

        :returns: received message from FOS switch
        :rtype: string

        """
        self.change_mode(MODE_VLAN)
        cmd = self._format_command("vlan {vlanid}", vlanid=segmentation_id)
        return self._exec_command(cmd)

    def delete_vlan(self, segmentation_id):
        """Undefine VLAN with specified VLAN ID from FOS switch.

        :param segmentation_id: id of VLAN to be deleted.
        :type segmentation_id: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_VLAN)
        cmd = self._format_command("no vlan {vlanid}", vlanid=segmentation_id)
        if "Failed to delete" in self._exec_command(cmd):
            LOG.warning("VLAN(%s) has already deleted.", segmentation_id)

    def set_vlan(self, segmentation_id, port_id):
        """Associate VLAN to specified physical port on FOS switch.

        :param segmentation_id: id of VLAN to be associated
        :type segmentation_id: string
        :param port_id: the number of physical port on FOS switch
        :type port_id: string

        :returns: None
        :rtype: None

        """
        method = "set_vlan"
        self.change_mode(MODE_INTERFACE, port_id)
        self._exec_command("switchport mode access")
        cmd = self._format_command("switchport access vlan {vlanid}",
                                   vlanid=segmentation_id)
        if "VLAN ID not found." in self._exec_command(cmd):
            LOG.exception("VLAN(%s) does not exist on FOS switch. "
                          "Please check vlan setting.", segmentation_id)
            raise FOSSWClientException(method)

    def clear_vlan(self, port_id):
        """Disassociate VLAN from specified physical port on FOS switch.

        :param port_id: the number of physical port on FOS switch
        :type port_id: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_INTERFACE, port_id)
        self._exec_command("no switchport access vlan")
        self._exec_command("no switchport mode")

    def join_to_lag(self, port, logicalport):
        """Join specified port to LAG configuration.

        :param port: the number of physical port on FOS switch
        :type port: string
        :param logicalport: the number of logical port on FOS switch
        :type logicalport: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_INTERFACE, ifname=logicalport)
        self._exec_command("no port-channel static")

        self.change_mode(MODE_INTERFACE, ifname=port)
        self._exec_command("addport {lo_port}".format(lo_port=logicalport))

    def get_vpcid(self, logicalport="none"):
        """Get VPC ID which is associated with specified logical port.

        If this method is called without logicalport, this method returns a
        VPC ID which is not associated with any logicalport.

        :param logicalport: the number of logicalport
            (optional, default: "none")
        :type logicalport: string

        :returns: the ID of VPC or None.
        :rtype: string
        """
        # TODO(yushiro): Replace regexp
        for i in iter(range(1, MAX_VPC_ID + 1)):
            cmd = 'show vpc {vid} | include "Port channel"'.format(vid=str(i))
            tmp_text = self._exec_command(cmd)
            switch_logicalport = tmp_text[tmp_text.find('. ') + 2:]
            if switch_logicalport == logicalport:
                return str(i)
        if logicalport is "none":
            # NOTE(miyagishi_t): All vpc is already associated to any logical
            # port. Therefore, the FOS switch cannot to define a new vpc.
            LOG.error("There is no free vpc. All vpc is already configured.")
        else:
            # NOTE(miyagishi_t): There is no VPC id which is related to
            # specified logicalport. It maybe the vpc already cleared or
            # originally not defined on the FOS switch.
            LOG.warning("A vpc which related to logicalport(%s) on FOS "
                        "switch not found.", logicalport)

    def join_to_vpc(self, logicalport, vpcid):
        """Join a specified logical port to member of VPC.

        :param logicalport: the number of logical port on FOS switch
        :type logicalport: string
        :param vpcid: id of VPC
        :type vpcid: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_INTERFACE, ifname=logicalport)
        self._exec_command("vpc {vpcid}".format(vpcid=vpcid))

    def get_peerlink_partner(self):
        """Get peerlink partner switch's IP address.

        :returns: IP address of peerlink partner
        :rtype: string

        """
        # TODO(yushiro): Replace regexp
        ret = self._exec_command('show vpc peer-keepalive | include "Peer '
                                 'IP address"')
        return ret[ret.find('. ') + 2:]

    def get_lag_port(self, portname=None):
        """Get logicalport from FOS switch.

        If portname is specified, returns logicalport which is associated
        with portname. If portname is not specified, returns available
        logicalport in FOS switch. 'available' means as follows:
            1. Status is not 'Dynamic'
            2. Portname Begins '3/'
            3. No member port exists
        :param portname: the number of physical port on FOS switch
        :type portname: string
        :returns: the number of logical port which associated with specified
                  physical port
        :rtype: string

        """
        # Find related lag_port with specified portname
        if portname:
            cmd = "show running-config interface %s" % portname
            query = r'addport\s+(?:(\d+/(?:(\d+))))'
        # Find free lag_port from all port-channel
        else:
            cmd = SHOW_PC_BRIEF + " | exclude Dynamic begin 3/"
            query = r'(?:(3/(?:(\d+))).+Static(?!\s+\d+\/\d+,\d+\/\d+))'
        ret = re.search(query, self._exec_command(cmd))
        return ret.group(1) if ret else None

    def get_switch_mac(self):
        """Get MAC address of FOS switch.

        :returns: MAC address of FOS switch
        :rtype: string

        """
        cmd = 'show hardware eeprom | include "Base MAC Address"'
        res = self._exec_command(cmd)
        if res:
            mac = re.search(r'([0-9A-F]{2}(:[0-9A-F]{2}){5})', res)
            return mac.group(0).lower() if mac else None

    def leave_from_lag(self, port, logicalport):
        """Leave a specified port from LAG configuration.

        :param port: the number of physical port on FOS switch
        :type port: string
        :param logicalport: the number of logical port on FOS switch
        :type logicalport: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_INTERFACE, ifname=port)
        res = self._exec_command(
            "deleteport {lo_port}".format(lo_port=logicalport))
        self.change_mode(MODE_INTERFACE, ifname=logicalport)
        self._exec_command("port-channel static")
        if "is not a member of port-channel" in res:
            LOG.warning("Specified port(%(port)s) has already removed "
                        "from logical port(%(log_po)s)",
                        {"port": port, "log_po": logicalport})

    def leave_from_vpc(self, logicalport, vpcid):
        """Leave a specified logical port from member of VPC.

        :param logicalport: the number of logical port on FOS switch
        :type logicalport: string
        :param vpcid: id of VPC
        :type vpcid: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_INTERFACE, ifname=logicalport)
        res = self._exec_command("no vpc {vpcid}".format(vpcid=vpcid))
        if "Failed to remove" in res:
            LOG.warning("Specified logical port(%(log_po)s) has already "
                        "removed from VPC(%(vpc)s).",
                        {"log_po": logicalport, "vpc": vpcid})

    def save_running_config(self):
        """Save running config of FOS switch.

        :returns: None
        :rtypes: None

        """
        self._exec_command("copy system:running-config nvram:startup-config")
        self._exec_command("y")
        self._exec_command("")

    def change_mode(self, mode, ifname=None):
        """Change CLI mode of FOS switch.

        :param mode: the name of the mode to be moved.
        :type mode: string
        :param ifname: the number of physical port on FOS switch
            (optional, default: None)
        :type ifname: string

        :returns: None
        :rtype: None

        """
        # Move to Privileged EXEC mode.
        prompt = self._exec_command(END)
        if ") >" in prompt:
            self._exec_command(ENABLE)
        if mode in [MODE_GLOBAL, MODE_VLAN]:
            self._exec_command(mode)
        elif mode == MODE_INTERFACE:
            self._exec_command(MODE_GLOBAL)
            cmd = self._format_command(
                MODE_INTERFACE + " {ifname}", ifname=ifname)
            self._exec_command(cmd)


class FOSSWClientException(Exception):

    def __init__(self, method):
        self.message = _("FOSSW client caught an error at %s") % method

    def __str__(self):
        return(self.message)
