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

import mock
# import paramiko
# import socket

from networking_fujitsu.ml2.fossw import client
from networking_fujitsu.ml2.fossw import mech_fossw
from neutron.tests import base
from oslo_config import cfg

DUMMY_FOSSW_IPS = ['192.168.0.1']
DUMMY_USERNAME = 'username'


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
    """Test Fossw client for connect to FOS switch."""

    def test_connect(self):
        pass

        # TODO(t_miyagishi) Update unit test to through latest source code.
        # with mock.patch.object(paramiko, 'SSHClient') as p_ssh:
        #     p_ssh.connect.return_value = None
        #     self.client.connect(cfg.CONF.fujitsu_fossw.fossw_ips[0])
        #     p_ssh.return_value.connect.assert_called_once_with(
        #         cfg.CONF.fujitsu_fossw.fossw_ips[0],
        #         password=cfg.CONF.fujitsu_fossw.password,
        #         port=cfg.CONF.fujitsu_fossw.port,
        #         timeout=cfg.CONF.fujitsu_fossw.timeout,
        #         username=cfg.CONF.fujitsu_fossw.username
        #     )
        #     self.assertEqual(p_ssh(), self.client.ssh)

    def test_connect_fail_with_connect(self):
        pass

        # TODO(t_miyagishi) Update unit test to through latest source code.
        # with mock.patch.object(paramiko, 'SSHClient') as p_ssh:
        #     p_ssh.return_value = Mocked_SSH()
        #     errors = [
        #         paramiko.ssh_exception.BadHostKeyException,
        #         paramiko.ssh_exception.AuthenticationException,
        #         paramiko.ssh_exception.SSHException,
        #         socket.error
        #     ]
        #     for error in errors:
        #        p_ssh.return_value.connect.side_effect = error
        #         self.assertRaises(
        #             client.FOSSWClientException,
        #             self.client.connect,
        #             cfg.CONF.fujitsu_fossw.fossw_ips[0]
        #         )
        #         self.client.ssh.close.assert_called_with()
        #         self.assertEqual(p_ssh.call_count, 5)
        #         self.client.ssh.invoke_shell.assert_not_called()

    def test_connect_fail_with_invoke_shell(self):
        pass

        # TODO(t_miyagishi) Update unit test to through latest source code.
        # with mock.patch.object(paramiko, 'SSHClient') as p_ssh:
        #     p_ssh.return_value = Mocked_SSH()
        #     error = paramiko.ssh_exception.SSHException
        #     p_ssh.return_value.invoke_shell.side_effect = error
        #     self.assertRaises(
        #         client.FOSSWClientException,
        #         self.client.connect,
        #         cfg.CONF.fujitsu_fossw.fossw_ips[0]
        #     )
        #     self.client.ssh.close.assert_called_with()
        #     self.assertEqual(p_ssh.call_count, 5)


class TestFOSSWClientExecCommand(BaseTestFOSSWClient):
    """Test Fossw client for execute command to FOS switch."""

    def test__exec_command(self):
        pass
        # TODO(t_miyagishi) Update unit test to through latest source code.

    def test__exec_command_fail(self):
        pass
        # TODO(t_miyagishi) Update unit test to through latest source code.


class TestFOSSWClientCreateVlan(BaseTestFOSSWClient):
    """Test Fossw client for create VLAN"""
    pass
    # TODO(t_miyagishi) Update unit test to through latest source code.


class TestFOSSWClientDeleteVlan(BaseTestFOSSWClient):
    """Test Fossw client for delete VLAN"""
    pass
    # TODO(t_miyagishi) Update unit test to through latest source code.


class TestFOSSWClientGetVlan(BaseTestFOSSWClient):
    """Test Fossw client for get VLAN"""
    pass
    # TODO(t_miyagishi) Update unit test to through latest source code.


class TestFOSSWClientIsExistVLAN(BaseTestFOSSWClient):
    """Test Fossw client for validate vlan is exist or not"""
    pass
    # TODO(t_miyagishi) Update unit test to through latest source code.


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
        for i in iter(range(1, 65)):
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

