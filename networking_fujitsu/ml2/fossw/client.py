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

import paramiko
import socket
import time

from oslo_log import log as logging

from networking_fujitsu._i18n import _
from networking_fujitsu._i18n import _LE
from networking_fujitsu._i18n import _LW

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


class FOSSWClient(object):

    def __init__(self, conf):
        self._conf = conf
        self.ssh = None
        self.console = None

    def connect(self, ip):
        """Establish ssh connection for FOS switch.

        :param ip: a ip address of FOS switch
        :type ip: string

        :returns: None
        :rtype: None

        """
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
            except IOError as e:
                LOG.warning(_LW('Could not initialize SSH client. %s'), e)
            except (paramiko.ssh_exception.BadHostKeyException,
                    paramiko.ssh_exception.AuthenticationException,
                    paramiko.ssh_exception.SSHException) as e:
                LOG.warning(_LW('Could not connect to FOS switch. An error'
                                'occurred while connecting. %s'), e)
            except socket.error as e:
                e_no, e_str = e
                LOG.warning(_LW('A socket error occurred while connecting.\n'
                                '[Errno %(e_no)s] %(e_str)s'),
                            {'e_no': e_no, 'e_str': e_str})
            except Exception as e:
                LOG.warning(_LW('Unexpected error occurred while connecting. '
                                '%s'), e)
            retry_count += 1
            self.disconnect()
            LOG.warning(_LW('Connect attempt %s failed.'), retry_count)
        if retry_count >= 5:
            self.disconnect()
            LOG.exception(_LE('Max retries exceeded. Failed to connect to '
                              'FOS switch.'))
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
            LOG.debug(_("SSH connection already closed."))

    def _exec_command(self, command):
        try:
            raw_res = ""
            self.console.send(command + "\n")
            LOG.debug(_("FOSSW client sending command: %s"), command)
            i = 0
            while i < MAX_LOOP:
                time.sleep(0.1)
                if self.console.recv_ready():
                    raw_res += self.console.recv(1024)
                elif raw_res:
                    break
                i += 1
            if (i == MAX_LOOP):
                LOG.error(_LE("No reply from FOS switch."))
                raise socket.timeout
            res = raw_res.replace('\r\n', '')
            received = res[(res.find(command) + len(command)):]
        except socket.timeout:
            self.disconnect()
            LOG.exception(_LE('Socket timeout occured while executing '
                              'commands to FOS Switch.'))
            raise FOSSWClientException('_exec_command')
        else:
            LOG.debug(_("FOSSW client received: %s"), received)
            # NOTE(yushiro) Validate received message here
            return received

    def _format_command(self, command, **kwargs):
        method = "_format_command"
        if not all(kwargs.values()):
            raise FOSSWClientException(method)
        try:
            formatted = command.format(**kwargs)
        except (KeyError, TypeError):
            raise FOSSWClientException(method)
        return formatted

    def create_vlan(self, segmentation_id):
        """Define VLAN with specified VLAN ID to FOS switch.

        :param segmentation_id: id of VLAN to be created.
        :type segmentation_id: string

        :returns: received message from FOS switch
        :rtype: string

        """
        self.change_mode(MODE_VLAN)
        cmd = self._format_command("vlan {vlan_id}", vlan_id=segmentation_id)
        return self._exec_command(cmd)

    def delete_vlan(self, segmentation_id):
        """Undefine VLAN with specified VLAN ID from FOS switch.

        :param segmentation_id: id of VLAN to be deleted.
        :type segmentation_id: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_VLAN)
        cmd = self._format_command("no vlan {vlan_id}",
                                   vlan_id=segmentation_id)
        if "Failed to delete" in self._exec_command(cmd):
            LOG.warning(_LW("VLAN(%s) has already deleted."), segmentation_id)

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
        LOG.debug(_("FOSSW client received: %s"),
                  self._exec_command("switchport mode access"))
        cmd = self._format_command("switchport access vlan {vlan_id}",
                                   vlan_id=segmentation_id)
        if "VLAN ID not found." in self._exec_command(cmd):
            LOG.exception(_LE("VLAN(%s) does not exist on FOS switch. "
                              "Please check vlan setting."), segmentation_id)
            raise FOSSWClientException(method)

    def clear_vlan(self, segmentaion_id, port_id):
        """Disassociate VLAN from specified physical port on FOS switch.

        :param segmentation_id: id of VLAN to be disassociated
        :type segmentation_id: string
        :param port_id: the number of physical port on FOS switch
        :type port_id: string

        :returns: None
        :rtype: None

        """
        self.change_mode(MODE_INTERFACE, port_id)
        self._exec_command("no switchport access vlan")
        self._exec_command("no switchport mode")

    def get_free_logical_port(self):
        """Get logical port number which not used by any LAG configuration.

        :returns: the number of logical port
        :rtype: string

        """
        cmd = SHOW_PC_BRIEF + " | exclude Dynamic begin 3/"
        res = self._exec_command(cmd)
        return res[res.find('3/'):].split(" ")[0]

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
        for i in iter(range(1, MAX_VPC_ID + 1)):
            cmd = 'show vpc {vid} | include "Port channel"'.format(vid=str(i))
            tmp_text = self._exec_command(cmd)
            switch_logicalport = tmp_text[tmp_text.find('. ') + 2:]
            if switch_logicalport == logicalport:
                return str(i)
        if logicalport is "none":
            # NOTE(miyagishi_t): All vpc is already associated to any logical
            # port. Therefore, the FOS switch cannot to define a new vpc.
            LOG.error(_LE("There is no free vpc. All vpc is already "
                          "configured."))
        else:
            # NOTE(miyagishi_t): There is no VPC id which is related to
            # specified logicalport. It maybe the vpc already cleard or
            # originaly not defined on the FOS switch.
            LOG.warning(_LW("A vpc which related to logicalport(%s) on FOS "
                            "switch not found."), logicalport)

    def join_to_vpc(self, logicalport, vpcid):
        """Join a specified logical port to member of VPC.

        :param logicalport: the number of logical port on FOS switch
        :type logicalport: string
        :param vpcid: id of VPC
        :type vpcid: string

        :returns: None
        :rtype: None

        """
        self.changemode(MODE_INTERFACE, ifname=logicalport)
        self._exec_commmand("vpc {vpcid}".format(vpcid=vpcid))

    def get_peerlink_partner(self):
        """Get peerlink partner switch's IP address.

        :returns: IP address of peerlink partner
        :rtype: string

        """
        ret = self._exec_command('show vpc peer-keepalive | include "Peer '
                                 'IP address"')
        return ret[ret.find('. ') + 2:]

    def get_lag_port(self, portname):
        """Get logicalport from FOS switch.

        :param portname: the number of physical port on FOS switch
        :type portname: string

        :returns: the number of logical port which associated with specified
                  physical port
        :rtype: string

        """
        key_charactors = [',', ' ']
        for key in key_charactors:
            cmd = SHOW_PC_BRIEF + " | include " + '"' + portname + key + '"'
            res = self._exec_command(cmd)
            if portname in res:
                return res[:res.find(" ")]

    def get_switch_mac(self):
        """Get MAC address of FOS switch.

        :returns: MAC address of FOS switch
        :rtype: string

        """
        return self._exec_command(
            'show hardware eeprom | include "Base MAC Address"')

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
            LOG.warning(_LW("specified port(%(port)s) has already removed "
                            "from logical port(%(log_po)s)"),
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
            LOG.warning(_LW("specified logical port(%(log_po)s) has already "
                            "removed from VPC(%(vpc)s)."),
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
            prompt = self._exec_command(ENABLE)

        if mode == MODE_GLOBAL:
            prompt = self._exec_command(MODE_GLOBAL)
        if mode == MODE_VLAN:
            prompt = self._exec_command(MODE_VLAN)
        if mode == MODE_INTERFACE:
            prompt = self._exec_command(MODE_GLOBAL)
            command = self._format_command(MODE_INTERFACE + " {ifname}",
                                           ifname=ifname)
            prompt = self._exec_command(command)


class FOSSWClientException(Exception):

    def __init__(self, method):
        self.message = _("FOSSW client caught an error at %s") % method

    def __str__(self):
        return(self.message)
