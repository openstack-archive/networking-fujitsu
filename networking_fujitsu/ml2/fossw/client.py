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
CTRL_Z = '\x1A'


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
        try:
            self.ssh = paramiko.SSHClient()
        except (IOError, paramiko.ssh_exception.SSHException) as e:
            self.disconnect()
            LOG.exception(_LE("an error occurred while initializing SSH "
                              "client. %s"), e)
            raise FOSSWClientException(method)
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        retry_count = 0
        while retry_count < 5:
            try:
                self.ssh.connect(
                    ip,
                    port=self._conf.fujitsu_fossw.port,
                    username=self._conf.fujitsu_fossw.username,
                    password=self._conf.fujitsu_fossw.password,
                    timeout=self._conf.fujitsu_fossw.timeout
                )
                self.console = self.ssh.invoke_shell()
                return
            except (paramiko.ssh_exception.BadHostKeyException,
                    paramiko.ssh_exception.AuthenticationException,
                    paramiko.ssh_exception.SSHException) as e:
                retry_count += 1
                self.disconnect()
                LOG.warning(_LW('Connect attempt %(retry)s failed.'))
                LOG.exception(_LE('could not connect to FOS switch. An error'
                                  'occurred while connecting. %s'), e)
            except socket.error as e:
                retry_count += 1
                self.disconnect()
                e_no, e_str = e
                LOG.warning(_LW('Connect attempt %(err)s failed.'))
                LOG.exception(_LE('a socket error occurred while connecting.\n'
                                  '[Errno %(e_no)s] %(e_str)s'),
                              {'e_no': str(e_no), 'e_str': e_str})
            except Exception as e:
                retry_count += 1
                self.disconnect()
                LOG.exception(_LE('Connect attempt %(retry)s failed. %(err)s'),
                              {'retry': str(retry_count), 'err': e})
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
            res = ""
            i = 0
            command = command + "\n"
            LOG.debug(_("fossw client sending command: %s"), command)
            self.console.send(command)
            while i <= 5000:
                time.sleep(0.1)
                if self.console.recv_ready():
                    res += self.console.recv(1024)
                    break
                i += 1
            index = res.find(command)
            return res[(index + len(command) + 1):]
        except Exception as e:
            self.disconnect
            LOG.exception(_LE('an error occured while executing commands to '
                              'FOS Switch. %s'), e)

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
        LOG.debug(_("fossw client received: %s"),
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
        tmp_text = self._exec_command("show port-channel brief | exclude Up "
                                      "begin 3/")
        return tmp_text[tmp_text.find('3/'):].split(" ")[0]

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

        self.chenge_mode(MODE_INTERFACE, ifname=port)
        self._exec_command("addport {lo_port}".format(lo_port=logicalport))

    def get_vpcid(self, logicalport="none"):
        """Get VPC ID from FOS switch.

        This method has two behavior according to whether argument is
        specified or not.
        logicalport is:
        * not specified: Get free VPC id.
        * specified    : Get VPC id which associate with specified logicalpot.
        """
        method = "get_vpcid"
        for i in iter(range(64)):
            cmd = 'show vpc {vid} | include "Port channel"'.format(vid=str(i))
            tmp_text = self._exec_command(cmd)
            switch_logicalport = tmp_text[tmp_text.find('. '):]
            if switch_logicalport is logicalport:
                return str(i)
        if logicalport is "none":
            LOG.exception(_LE("There is no free vpc. All vpc is already "
                              "configured."))
            raise FOSSWClientException(method)
        else:
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
        return ret[ret.find('. '):]

    def get_lag_port(self, portname):
        """Get logicalport from FOS switch.

        :param portname: the number of physical port on FOS switch
        :type portname: string

        :returns: the number of logical port which associated with specified
                  physical port
        :rtype: string

        """
        show_pc = 'show port-channel brief | include'
        key_charactors = [',', ' ']
        for key in key_charactors:
            res = self._exec_command(show_pc + '"' + portname + key + '"')
            if portname in res:
                lag_port = res[res.lfind():]
                return lag_port

    def get_switch_mac(self):
        """Get MAC address of FOS switch.

        :returns: MAC address of FOS switch
        :rtype: string

        """
        return self._exec_command(
            'show hardware eeprom | include "Base MAC Address"')

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
        prompt = self._exec_command(CTRL_Z)
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
