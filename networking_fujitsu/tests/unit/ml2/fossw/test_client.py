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

# import mock
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
        self.client = client.FOSSWClient(cfg.CONF)


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
