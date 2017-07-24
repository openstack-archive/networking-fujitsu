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
import socket
import time

from neutron.tests import base
from oslo_log import log as logging

from networking_fujitsu.ml2.common.ovsdb import base_connection

LOG = logging.getLogger(__name__)


class FakeDecodeClass(object):
    def __init__(self, fake_data):
        self.fake_data = fake_data

    def decode(self, utf8):
        return self.fake_data


class SocketClass(object):
    def __init__(self,
                 connect_error=None,
                 send_error=None,
                 recv_error=None,
                 rcv_data=None):
        self.connect_error = connect_error
        self.rcv_data = rcv_data
        self.send_error = send_error
        self.recv_error = recv_error

    def connect(self, ip_port):
        if self.connect_error:
            raise self.connect_error

    def send(self, data):
        if self.send_error:
            raise self.send_error
        return len(data)

    def recv(self, length):
        if self.recv_error:
            raise self.recv_error
        return self.rcv_data

    def close(self):
        pass


class TestBaseConnection(base.BaseTestCase):
    def setUp(self):
        super(TestBaseConnection, self).setUp()

        self.fake_ovsdb_ip = "192.168.1.1"
        self.fake_ovsdb_port = 6640

        self.sock = mock.patch('socket.socket').start()
        self.fake_ovsdb = base_connection.BaseConnection(
            self.fake_ovsdb_ip, self.fake_ovsdb_port)
        self.fake_ovsdb.s = mock.patch('socket.socket').start()
        self.op_id = 'abcd'
        self.fake_message = {'id': self.op_id,
                             'fake_key': 'fake_value'}

        self.fake_ovsdb.responses = [self.fake_message]

        self.fake_ip = 'fake_ip'

    def test_init(self):
        fakesocket = SocketClass()
        with mock.patch.object(base_connection.LOG, 'debug') as logger_call, \
                mock.patch.object(socket, 'socket',
                                  return_value=fakesocket):
            self.fake_ovsdb.__init__(self.fake_ovsdb_ip, self.fake_ovsdb_port)
            self.assertTrue(logger_call.called)
            self.assertTrue(self.sock.called)

    def test_init_with_socket_error(self):
        fakesocket = SocketClass(socket.error)
        with mock.patch.object(base_connection.LOG, 'exception') as logger_exc, \
                mock.patch.object(base_connection.LOG, 'warning') as logger_warn, \
                mock.patch.object(socket, 'socket', return_value=fakesocket) as sock_connect, \
                mock.patch.object(time, 'sleep'):
            self.assertRaises(socket.error, base_connection.BaseConnection,
                              self.fake_ovsdb_ip, self.fake_ovsdb_port)
            self.assertTrue(logger_warn.called)
            self.assertTrue(logger_exc.called)
            self.assertTrue(sock_connect.called)

    def test_init_with_timeout(self):
        fakesocket = SocketClass(socket.timeout)
        with mock.patch.object(base_connection.LOG, 'exception') as logger_exc, \
                mock.patch.object(base_connection.LOG, 'warning') as logger_warn, \
                mock.patch.object(socket, 'socket', return_value=fakesocket) as sock_connect, \
                mock.patch.object(time, 'sleep'):
            self.assertRaises(socket.timeout, base_connection.BaseConnection,
                              self.fake_ovsdb_ip, self.fake_ovsdb_port)
            self.assertTrue(logger_warn.called)
            self.assertTrue(logger_exc.called)
            self.assertTrue(sock_connect.called)

    def test_send(self):
        with mock.patch.object(self.fake_ovsdb.socket, 'send',
                               return_value=1):
            return_value = self.fake_ovsdb.send(mock.Mock())
            self.assertEqual(return_value, True)

    def test_send_exception(self):
        with mock.patch.object(self.fake_ovsdb.socket, 'send',
                               side_effect=Exception) as send:
            with mock.patch.object(base_connection.LOG,
                                   'exception'):
                with mock.patch.object(self.fake_ovsdb,
                                       'disconnect') as mock_disconnect:
                    with mock.patch.object(base_connection.LOG,
                                           'warning'):
                        self.fake_ovsdb.send(mock.Mock())
                        self.assertTrue(send.called)
                        self.assertTrue(mock_disconnect.called)

    def test_disconnect(self):
        with mock.patch.object(self.fake_ovsdb.socket, 'close') as sock_close:
            self.fake_ovsdb.disconnect()
            self.assertTrue(sock_close.called)
