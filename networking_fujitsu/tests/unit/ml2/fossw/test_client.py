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

import paramiko
import socket
import time

import mock

from networking_fujitsu.ml2.fossw import client
from networking_fujitsu.ml2.fossw import mech_fossw
from neutron.tests import base
from oslo_config import cfg

DUMMY_FOSSW_IPS = ['192.168.0.1']
DUMMY_USERNAME = 'username'
MAX_LOGICAL_PORT_NUM = 64


class BaseTestFOSSWClient(base.BaseTestCase):
    """Base class to test Fujitsu Fossw driver."""

    def setUp(self):
        super(BaseTestFOSSWClient, self).setUp()
        cfg.CONF.register_opts(
            mech_fossw.ML2_FUJITSU,
            mech_fossw.ML2_FUJITSU_GROUP
        )
        cfg.CONF.set_override(
            'username', DUMMY_USERNAME, 'fujitsu_fossw'
        )
        cfg.CONF.set_override(
            'fossw_ips', DUMMY_FOSSW_IPS, 'fujitsu_fossw'
        )
        self.cli = client.FOSSWClient(cfg.CONF)
        self.cli.ssh = mock.Mock()
        self.cli.console = mock.Mock()


class TestFOSSWClientConnect(BaseTestFOSSWClient):
    """Test FOSSW client for connect to FOS switch."""

    def test_connect(self):
        with mock.patch.object(paramiko, 'SSHClient') as p_ssh:
            p_ssh.connect.return_value = None
            self.cli.connect(cfg.CONF.fujitsu_fossw.fossw_ips[0])
            p_ssh.return_value.connect.assert_called_once_with(
                cfg.CONF.fujitsu_fossw.fossw_ips[0],
                password=cfg.CONF.fujitsu_fossw.password,
                port=cfg.CONF.fujitsu_fossw.port,
                timeout=cfg.CONF.fujitsu_fossw.timeout,
                username=cfg.CONF.fujitsu_fossw.username
            )

    def test_connect_fail(self):
        with mock.patch(__name__ + ".client.paramiko.SSHClient") as p_ssh:
            err_io = IOError
            err_hostkey = paramiko.ssh_exception.BadHostKeyException
            err_auth = paramiko.ssh_exception.AuthenticationException
            err_ssh = paramiko.ssh_exception.SSHException
            err_socket = socket.error(9999, "fake_error")
            errors = [err_io, err_hostkey, err_auth, err_ssh, err_socket]
            p_ssh.return_value.connect.side_effect = errors
            self.assertRaises(
                client.FOSSWClientException,
                self.cli.connect,
                cfg.CONF.fujitsu_fossw.fossw_ips[0]
            )
            self.assertIsNone(self.cli.ssh)


class TestFOSSWClientDisconnect(BaseTestFOSSWClient):
    """Test FOSSW client for diconnect from FOS switch."""

    def test_disconnect(self):
        with mock.patch.object(paramiko, 'SSHClient') as p_ssh:
            p_ssh.connect.return_value = None
            self.cli.connect(cfg.CONF.fujitsu_fossw.fossw_ips[0])
            self.cli.disconnect()
            self.assertIsNone(self.cli.ssh)


class TestFOSSWClientExecCommand(BaseTestFOSSWClient):
    """Test FOSSW client for execute command to FOS switch."""

    def setUp(self):
        super(TestFOSSWClientExecCommand, self).setUp()
        time.sleep = mock.Mock()
        self.cli.console.recv_ready.side_effect = [True, False]
        self.cli.disconnect = mock.Mock()

    def test_normal(self):
        cmd = 'configure'
        self.cli.console.recv.return_value = (
            '\r\n(ET-7648BRA-FOS) #%s\r\n(ET-7648BRA-FOS) (Config)#' % cmd)
        result = self.cli._exec_command(cmd)
        self.cli.console.send.assert_called_with(cmd + '\n')
        self.cli.console.recv_ready.assert_called_with()
        self.cli.console.recv.assert_called_once_with(1024)
        self.assertEqual('(ET-7648BRA-FOS) (Config)#', result)

    def test_socket_timeout_with_send(self):
        cmd = 'configure'
        self.cli.console.send.side_effect = socket.timeout
        self.assertRaises(
            client.FOSSWClientException, self.cli._exec_command, cmd)
        self.cli.disconnect.assert_called_once_with()

    def test_socket_timeout_with_maximum_retry(self):
        self.cli.console.recv_ready = mock.Mock(return_value=False)
        cmd = 'configure'
        self.assertRaises(
            client.FOSSWClientException, self.cli._exec_command, cmd)
        self.cli.disconnect.assert_called_once_with()


class TestFOSSWClientFormatCommand(BaseTestFOSSWClient):
    """Test FOSSW client for format command"""

    def setUp(self):
        super(TestFOSSWClientFormatCommand, self).setUp()

    def test__format_command(self):
        self.assertEqual(
            "vlan 2", self.cli._format_command("vlan {vlan_id}", vlan_id=2))

    def test__format_command_fails(self):
        raw_cmd = "vlan {vlan_id}"
        self.assertRaises(
            client.FOSSWClientException, self.cli._format_command, raw_cmd)
        self.assertRaises(
            client.FOSSWClientException, self.cli._format_command, raw_cmd,
            vlan=2)
        self.assertRaises(
            client.FOSSWClientException, self.cli._format_command, raw_cmd,
            vlan_id=None)


class TestFOSSWClientCreateVlan(BaseTestFOSSWClient):
    """Test Fossw client for create VLAN"""
    def setUp(self):
        super(TestFOSSWClientCreateVlan, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock()

    def test_create_vlan(self):
        result = "(ET-7648BRA-FOS) (Vlan)#"
        self.cli._exec_command.return_value = "(ET-7648BRA-FOS) (Vlan)#"
        self.assertEqual(result, self.cli.create_vlan(10))


class TestFOSSWClientDeleteVlan(BaseTestFOSSWClient):
    """Test Fossw client for delete VLAN"""
    def setUp(self):
        super(TestFOSSWClientDeleteVlan, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock()

    def test_delete_vlan(self):
        ret = "(ET-7648BRA-FOS) (Vlan)#"
        self.cli._exec_command.return_value = ret
        self.assertIsNone(self.cli.delete_vlan(10))
        ret = ("Failed to delete one or more VLAN's. Please refer system log "
               "for more information.")
        self.cli._exec_command.return_value = ret


class TestFOSSWClientSetVlan(BaseTestFOSSWClient):
    """Test Fossw client for set VLAN"""
    def setUp(self):
        super(TestFOSSWClientSetVlan, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock()

    def test_set_vlan(self):
        ret = ["(ET-7648BRA-FOS) (Interface 0/1)#",
               "(ET-7648BRA-FOS) (Interface 0/1)#"]
        self.cli._exec_command.side_effect = ret
        self.assertIsNone(self.cli.set_vlan(10, 1))

    def test_set_vlan_fail(self):
        ret = ["(ET-7648BRA-FOS) (Interface 0/1)#",
               "VLAN ID not found.(ET-7648BRA-FOS) (Interface 0/1)#"]
        self.cli._exec_command.side_effect = ret
        self.assertRaises(
            client.FOSSWClientException, self.cli.set_vlan, 10, 1)


class TestFOSSWClientClearVlan(BaseTestFOSSWClient):
    """Test Fossw client for clear VLAN"""
    def setUp(self):
        super(TestFOSSWClientClearVlan, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock()

    def test_clear_vlan(self):
        ret = "(ET-7648BRA-FOS) (Interface 0/1)#"
        self.cli._exec_command.side_effect = ret
        self.assertIsNone(self.cli.clear_vlan(10, 1))


class TestFOSSWClientGetFreeLogicalPort(BaseTestFOSSWClient):
    """Test FOSSW Client for get free logical port"""
    def setUp(self):
        super(TestFOSSWClientGetFreeLogicalPort, self).setUp()
        self.cli._exec_command = mock.Mock(return_value=None)

    def test_get_free_logical_port(self):
        ret = ("3/1       ch1              1   Down       Disabled Static"
               "3/2       ch2              1   Down       Disabled Static"
               "3/3       ch3              1   Down       Disabled Static"
               "3/4       ch4              1   Down       Disabled Static"
               "3/5       ch5              1   Down       Disabled Static"
               "3/6       ch6              1   Down       Disabled Static"
               "3/7       ch7              1   Down       Disabled Static"
               "3/8       ch8              1   Down       Disabled Static"
               "3/9       ch9              1   Down       Disabled Static"
               "3/10      ch10             1   Down       Disabled Static"
               ""
               "(ET-7648BRA-FOS) #")
        self.cli._exec_command.return_value = ret
        self.assertEqual("3/1", self.cli.get_free_logical_port())


class TestFOSSWClientJoinToLag(BaseTestFOSSWClient):
    """Test FOSSW Client for join to lag"""
    def setUp(self):
        super(TestFOSSWClientJoinToLag, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock(return_value=None)

    def test_join_to_lag(self):
        ret = ["(ET-7648BRA-FOS) (Interface 3/1)#",
               "(ET-7648BRA-FOS) (Interface 0/1)#"]
        self.cli._exec_command.side_effect = ret
        self.assertIsNone(self.cli.join_to_lag("0/1", "3/1"))


class TestFOSSWClientGetVPCId(BaseTestFOSSWClient):
    """TEst FOSSW Client for get vpc id"""
    def setUp(self):
        super(TestFOSSWClientGetVPCId, self).setUp()
        self.cli._exec_command = mock.Mock()

    def test_get_vpc_specified_id(self):
        ret = [
            "Port channel................................... none",
            "Port channel................................... none",
            "Port channel................................... none",
            "Port channel................................... 3/1",
            "Port channel................................... 3/2",
            "Port channel................................... none"]
        self.cli._exec_command.side_effect = ret
        self.assertEqual("5", self.cli.get_vpcid(logicalport="3/2"))

    def test_get_vpc_free_id(self):
        ret = [
            "Port channel................................... none",
            "Port channel................................... none",
            "Port channel................................... none"]
        self.cli._exec_command.side_effect = ret
        self.assertEqual("1", self.cli.get_vpcid())

        ret[0] = "Port channel................................... 3/1"
        self.cli._exec_command.side_effect = ret
        self.assertEqual("2", self.cli.get_vpcid())

    def test_get_vpc_id_no_free_vpc(self):
        ret = []
        for i in iter(range(1, MAX_LOGICAL_PORT_NUM + 1)):
            ret.append(
                ("Port channel................................... "
                 "3/{no}").format(no=i))
        self.cli._exec_command.side_effect = ret
        self.assertIsNone(self.cli.get_vpcid())

    def test_get_vpc_specidied_id_not_found(self):
        ret = "Port channel................................... none"
        self.cli._exec_command.return_value = ret
        self.assertIsNone(self.cli.get_vpcid("3/1"))


class TestFOSSWClientJoinToVPC(BaseTestFOSSWClient):
    """Test FOSSW Client for join to vpc"""
    def setUp(self):
        super(TestFOSSWClientJoinToVPC, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock(return_value=None)

    def test_join_to_lag(self):
        ret = ["(ET-7648BRA-FOS) (Interface 3/1)#",
               "(ET-7648BRA-FOS) (Interface 0/1)#"]
        self.cli._exec_command.side_effect = ret
        self.assertIsNone(self.cli.join_to_lag("0/1", "3/1"))


class TestFOSSWClientGetPeerlinkPartner(BaseTestFOSSWClient):
    """Test FOSSW Client for get peerlink partner ip"""
    def setUp(self):
        super(TestFOSSWClientGetPeerlinkPartner, self).setUp()
        self.cli._exec_command = mock.Mock()

    def test_get_peerlink_partner(self):
        self.cli._exec_command.return_value = (
            "Peer IP address................................ 192.168.1.1")
        self.assertEqual("192.168.1.1", self.cli.get_peerlink_partner())


class TestFOSSWClientGetLAGPort(BaseTestFOSSWClient):
    """Test FOSSW Client for get port-wqmemberport of port-channel."""
    def setUp(self):
        super(TestFOSSWClientGetLAGPort, self).setUp()
        self.cli._exec_command = mock.Mock()

    def test_get_lag_port(self):
        self.cli._exec_command.return_value = (
            "")
        self.assertIsNone(self.cli.get_lag_port("0/1"))

        self.cli._exec_command.return_value = (
            "")
        self.assertIsNone(self.cli.get_lag_port("0/1"))


class TestFOSSWClientGetSwitchMAC(BaseTestFOSSWClient):
    """Test FOSSW Client for get FOS switch's MAC address"""
    def setUp(self):
        super(TestFOSSWClientGetSwitchMAC, self).setUp()
        self.cli._exec_command = mock.Mock()

    def test_get_switch_mac(self):
        ret = ("Base MAC Address............................... "
               "00:30:AB:F4:CA:DA(ET-7648BRA-FOS) #")
        self.cli._exec_command.return_value = ret
        self.assertEqual(ret, self.cli.get_switch_mac())


class TestFOSSWClientLeaveFromLAG(BaseTestFOSSWClient):
    """Test FOSSW Client for leave physical port from logical port"""
    def setUp(self):
        super(TestFOSSWClientLeaveFromLAG, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock()

    def test_leave_from_lag(self):
        ret = "(ET-7648BRA-FOS) (Interface 0/10)#"
        self.cli._exec_command.return_value = ret
        self.assertIsNone(self.cli.leave_from_lag("0/10", "3/1"))


class TestFOSSWClientLeaveFromVPC(BaseTestFOSSWClient):
    """Test FOSSW Client for leave logical port from VPC(mLAG)"""
    def setUp(self):
        super(TestFOSSWClientLeaveFromVPC, self).setUp()
        self.cli.change_mode = mock.Mock(return_value=None)
        self.cli._exec_command = mock.Mock()

    def test_leave_from_vpc(self):
        ret = ["(ET-7648BRA-FOS) (Interface 3/1)#",
               "          Failure Information"
               "---------------------------------------"
               "Interfaces failed to be configured : 1"
               "---------------------------------------"
               "Interface             Error"
               "---------------------------------------"
               "3/1           Failed to remove."
               "(ET-7648BRA-FOS) (Interface 3/1)#"]
        self.cli._exec_command.side_effect = ret
        self.assertIsNone(self.cli.leave_from_vpc("3/1", "1"))
        self.assertIsNone(self.cli.leave_from_vpc("3/1", "2"))


class TestFOSSWClientSaveRunningConfig(BaseTestFOSSWClient):
    """Test FOSSW client for save running config."""
    def setUp(self):
        super(TestFOSSWClientSaveRunningConfig, self).setUp()
        self.cli._exec_command = mock.Mock(return_value="(ET-7648BRA-FOS) #")

    def test_save_running_config(self):
        self.assertIsNone(self.cli.save_running_config())
