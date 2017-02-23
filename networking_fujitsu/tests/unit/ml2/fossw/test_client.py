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
# from unittest import mock

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
