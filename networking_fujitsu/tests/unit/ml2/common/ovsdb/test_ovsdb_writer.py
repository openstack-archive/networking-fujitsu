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

import ast
import random
import socket

import mock
from neutron.tests import base
from oslo_log import log as logging
from oslo_serialization import jsonutils

from networking_fujitsu.ml2.common.ovsdb import base_connection
from networking_fujitsu.ml2.common.ovsdb import constants as n_const
from networking_fujitsu.ml2.common.ovsdb import ovsdb_writer
from networking_fujitsu.tests.unit.ml2.common.ovsdb import (
    test_base_connection as base_test)

LOG = logging.getLogger(__name__)


class TestOVSDBWriter(base.BaseTestCase):
    def setUp(self):
        super(TestOVSDBWriter, self).setUp()

        self.op_id = 'abcd'
        self.ovsdb_ip = "1.1.1.1"
        self.ovsdb_port = 6640
        self.sock = mock.patch('socket.socket').start()
        self.fake_ovsdb = ovsdb_writer.OVSDBWriter(self.ovsdb_ip,
                                                   self.ovsdb_port)
        self.fake_message = {'id': self.op_id,
                             'fake_key': 'fake_value'}
        self.fake_ipaddrs = ["fake_ipaddr1", "fake_ipaddr2"]
        self.fake_ovsdb.responses = [self.fake_message]

    def test_process_response(self):
        """Test case to test _process_response."""
        expected_result = {'fake_key': 'fake_value'}
        with mock.patch.object(ovsdb_writer.OVSDBWriter,
                               '_response',
                               return_value={'fake_key': 'fake_value'}
                               ) as resp:
            result = self.fake_ovsdb._process_response(self.op_id)
            self.assertEqual(result, expected_result)
            resp.assert_called_with(self.op_id)

    def test_process_response_with_error(self):
        """Test case to test _process_response with error."""
        foo_dict = {'fake_key': 'fake_value',
                    'error': 'fake_error'}
        with mock.patch.object(ovsdb_writer.OVSDBWriter,
                               '_response',
                               return_value=foo_dict) as resp:
            self.assertRaises(base_connection.OVSDBError,
                              self.fake_ovsdb._process_response,
                              self.op_id)
            resp.assert_called_with(self.op_id)

    def test_process_response_with_error1(self):
        """Test case to test _process_response with errors in the

           subqueries.
        """
        fake_dict = {'id': '295366252499790541931626006259650283530',
                     'result':
                     [{'uuid':
                       ['uuid', 'be236bbf-8f83-4bf0-816b-629c7e5b5609'
                        ]},
                      {},
                      {'error': 'referential integrity violation',
                       'details': 'Table Ucast_Macs_Remote column '
                                  'locator row '
                                  'be236bbf-8f83-4bf0-816b-629c7e5b5609 '
                                  'references nonexistent row '
                                  '1b143819-45a6-44ec-826a-ac75243a07ce in '
                                  'table Physical_Locator.'
                       }],
                     'error': None}
        with mock.patch.object(ovsdb_writer.OVSDBWriter,
                               '_response',
                               return_value=fake_dict) as resp:
            self.assertRaises(base_connection.OVSDBError,
                              self.fake_ovsdb._process_response,
                              self.op_id)
            resp.assert_called_with(self.op_id)

    def test_send_and_receive(self):
        """Test case to test _send_and_receive."""
        with mock.patch.object(base_connection.BaseConnection,
                               'send', return_value=True
                               ) as mock_send:
            with mock.patch.object(ovsdb_writer.OVSDBWriter,
                                   '_get_reply') as mock_reply:
                self.fake_ovsdb._send_and_receive('some_query',
                                                  self.op_id, True)
                mock_send.assert_called_with('some_query')
                mock_reply.assert_called_with(self.op_id)

    def test_send_and_receive_with_rcv_required_false(self):
        """Test case to test _send_and_receive."""
        with mock.patch.object(base_connection.BaseConnection,
                               'send', return_value=True
                               ) as mock_send:
            with mock.patch.object(ovsdb_writer.OVSDBWriter,
                                   '_get_reply') as mock_reply:
                self.fake_ovsdb._send_and_receive('some_query',
                                                  self.op_id, False)
                mock_send.assert_called_with('some_query')
                mock_reply.assert_not_called()

    def test_get_reply(self):
        """Test case to test _get_reply."""
        ret_value = jsonutils.dumps({self.op_id:
                                     'foo_value'})
        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=jsonutils.dumps({
                                   self.op_id: 'foo_value'})) as recv_data, \
            mock.patch.object(ovsdb_writer.OVSDBWriter, '_process_response',
                              return_value=(ret_value, None)) as proc_response, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb._get_reply(self.op_id)
            self.assertTrue(recv_data.called)
            self.assertTrue(proc_response.called)

    def test_get_reply_exception(self):
        """Test case to test _get_reply.

        However, something unknow exception occuered when getting response.
        """

        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=jsonutils.dumps({
                                   self.op_id: 'foo_value'})), \
            mock.patch.object(ovsdb_writer.OVSDBWriter, '_process_response',
                              return_value=''), \
            mock.patch.object(ast, 'literal_eval', side_effect=RuntimeError), \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.assertRaises(RuntimeError,
                              self.fake_ovsdb._get_reply,
                              self.op_id)

    def test_get_reply_max_retried(self):
        """Test case to test _get_reply when MAX_RETRIES has been tried."""
        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=''), \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.assertRaises(RuntimeError,
                              self.fake_ovsdb._get_reply,
                              self.op_id)

    def test_recv_data(self):
        """Test case to test _recv_data with a valid data."""
        n_const.BUFFER_SIZE = 5
        fake_data_raw = '{"fake_key": "fake_value"}'
        fake_socket = base_test.SocketClass(None,
                                            None,
                                            None,
                                            fake_data_raw)
        with mock.patch.object(socket, 'socket', return_value=fake_socket):
                fake_obj = ovsdb_writer.OVSDBWriter(
                    self.ovsdb_ip, self.ovsdb_port)
                result = fake_obj._recv_data()
                self.assertEqual(fake_data_raw, result)

    def test_recv_data_with_empty_data(self):
        """Test case to test _recv_data with empty data."""
        fake_socket = base_test.SocketClass(None,
                                            None,
                                            None,
                                            '')
        with mock.patch.object(socket, 'socket',
                               return_value=fake_socket):
            with mock.patch.object(ovsdb_writer.LOG, 'warning'):
                fake_obj = ovsdb_writer.OVSDBWriter(
                    self.ovsdb_ip, self.ovsdb_port)
                result = fake_obj._recv_data()
                self.assertIsNone(result)

    def test_recv_data_with_socket_error(self):
        """Test case to test _recv_data with socket error."""

        fake_socket = base_test.SocketClass(None,
                                            None,
                                            socket.error)
        with mock.patch.object(socket, 'socket', return_value=fake_socket):
            with mock.patch.object(ovsdb_writer.LOG,
                                   'warning') as fake_warn:
                fake_obj = ovsdb_writer.OVSDBWriter(
                    self.ovsdb_ip, self.ovsdb_port)
                result = fake_obj._recv_data()
                self.assertIsNone(result)
                fake_warn.assert_called_with("Did not receive any reply from "
                                             "the OVSDB server")

    def test_get_sw_ep_info(self):
        """Test case to test get_sw_ep_info."""
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Physical_Switch',
                             'where': [],
                             'columns': ['tunnel_ips', 'name']}],
                 'id': self.op_id}
        return_value_raw = '{"id":1,"result":[{"rows":[{"name":' \
                           '"fake_host_name","tunnel_ips":' \
                           '"fake_endpoint_ip"}]}],"error":null}'
        return_value = return_value_raw.replace(':null', ':None')
        self.fake_ovsdb.response = ast.literal_eval(return_value)
        expected_result = ('fake_endpoint_ip', 'fake_host_name')
        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=return_value_raw), \
            mock.patch.object(random, 'getrandbits',
                              return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            result = self.fake_ovsdb.get_sw_ep_info()
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)
            self.assertEqual(result, expected_result)
        self.fake_ovsdb.responses = [self.fake_message]

    def test_insert_logical_switch(self):
        """Test case to test insert_logical_switch."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Logical_Switch',
                             'row': {'name': 'fake_logical_switch_name',
                                     'tunnel_key': 'fake_tunnel_key'}},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.insert_logical_switch(
                'fake_tunnel_key', 'fake_logical_switch_name', mock.ANY)
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_get_logical_switch_uuid(self):
        """Test case to test get_logical_switch_uuid."""
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Logical_Switch',
                             'where': [['name', '==',
                                        'fake_logical_switch_name']]}],
                 'id': self.op_id}
        return_value_raw = '{"id":1,"result":[{"rows":[{"_version":' \
                           '["uuid","abcd"],"name":' \
                           '"fake_logical_switch_name",' \
                           '"description":"","tunnel_key":1,"_uuid":["uuid",' \
                           '"fake_logical_switch_uuid"]}]}],"error":null}'
        return_value = return_value_raw.replace(':null', ':None')
        self.fake_ovsdb.response = ast.literal_eval(return_value)
        expected_result = 'fake_logical_switch_uuid'
        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=return_value_raw), \
            mock.patch.object(random, 'getrandbits',
                              return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            result = self.fake_ovsdb.get_logical_switch_uuid(
                'fake_logical_switch_name')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)
            self.assertEqual(result, expected_result)
        self.fake_ovsdb.responses = [self.fake_message]

    def test_delete_logical_switch(self):
        """Test case to test delete_logical_switch."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'delete',
                             'table': 'Mcast_Macs_Local',
                             'where': [['logical_switch', '==',
                                        ['uuid', 'fake_ls_uuid']]]},
                            {'op': 'delete',
                             'table': 'Logical_Switch',
                             'where': [['_uuid', '==',
                                        ['uuid', 'fake_ls_uuid']]]},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.delete_logical_switch(
                'fake_ls_uuid', mock.ANY)
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_get_binding_vid(self):
        """Test case to test get_binding_vid."""
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Physical_Port',
                             'where': [['vlan_bindings', '!=', ['map', []]]],
                             'columns': ['vlan_bindings']}],
                 'id': self.op_id}
        return_value_raw = '{"id":1,"result":[{"rows":[{"vlan_bindings":[' \
                           '"map",[[21,["uuid","fake_logical_switch_uuid_21"' \
                           ']]]]},{"vlan_bindings":["map",[[22,["uuid",' \
                           '"fake_logical_switch_uuid_22"]]]]}]}],' \
                           '"error":null}'
        return_value = return_value_raw.replace(':null', ':None')
        self.fake_ovsdb.response = ast.literal_eval(return_value)
        expected_result = 21
        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=return_value_raw), \
            mock.patch.object(random, 'getrandbits',
                              return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            result = self.fake_ovsdb.get_binding_vid(
                'fake_logical_switch_uuid_21')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)
            self.assertEqual(result, expected_result)
        self.fake_ovsdb.responses = [self.fake_message]

    def test_update_physical_port(self):
        """Test case to test update_physical_port."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'update',
                             'table': 'Physical_Port',
                             'where': [['name', '==', 'fake_port_name']],
                             'row': {
                                 'vlan_bindings': [
                                     'map',
                                     [['fake_vlanid', [
                                         'uuid',
                                         'fake_logical_switch_uuid']]]]}},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.update_physical_port(
                'fake_port_name', 'fake_vlanid',
                'fake_logical_switch_uuid')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_get_ucast_macs_local(self):
        """Test case to test get_ucast_macs_local."""
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Ucast_Macs_Local',
                             'where': [['MAC', '==', 'fake_port_mac']]}],
                 'id': self.op_id}
        return_value_raw = '{"id":1,"result":[{"rows":[{"_version":["uuid",' \
                           '"fake_v_uuid"],"locator":["uuid",' \
                           '"fake_locator_uuid"],"logical_switch":["uuid",' \
                           '"fake_ls_uuid"],"_uuid":["uuid","fake_uuid"],' \
                           '"MAC":"fake_port_mac","ipaddr":""}]}],"error":' \
                           'null}'
        return_value = return_value_raw.replace(':null', ':None')
        self.fake_ovsdb.response = ast.literal_eval(return_value)
        expected_result = [{'MAC': 'fake_port_mac',
                            '_uuid': ['uuid', 'fake_uuid'],
                            '_version': ['uuid', 'fake_v_uuid'],
                            'ipaddr': '',
                            'locator': ['uuid', 'fake_locator_uuid'],
                            'logical_switch': ['uuid', 'fake_ls_uuid']}]
        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=return_value_raw), \
            mock.patch.object(random, 'getrandbits',
                              return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            result = self.fake_ovsdb.get_ucast_macs_local('fake_port_mac')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)
            self.assertEqual(result, expected_result)
        self.fake_ovsdb.responses = [self.fake_message]

    def test_delete_ucast_macs_local(self):
        """Test case to test delete_ucast_macs_local."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'delete',
                             'table': 'Ucast_Macs_Local',
                             'where': [['MAC', '==', 'fake_MAC_value']]},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.delete_ucast_macs_local('fake_MAC_value')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_get_physical_locator_uuid(self):
        """Test case to test get_physical_locator_uuid."""
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Physical_Locator',
                             'where': [['dst_ip', '==', 'fake_dst_ip']]}],
                 'id': self.op_id}
        return_value_raw = '{"id":1,"result":[{"rows":[{"_version":' \
                           '["uuid","abcd"],"_uuid":["uuid",' \
                           '"fake_physical_locator_uuid"],"dst_ip":' \
                           '"fake_dst_ip","encapsulation_type":' \
                           '"vxlan_over_ipv4"}]}],"error":null}'
        return_value = return_value_raw.replace(':null', ':None')
        self.fake_ovsdb.response = ast.literal_eval(return_value)
        expected_result = 'fake_physical_locator_uuid'
        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=return_value_raw), \
            mock.patch.object(random, 'getrandbits',
                              return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            result = self.fake_ovsdb.get_physical_locator_uuid(
                'fake_dst_ip')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)
            self.assertEqual(result, expected_result)
        self.fake_ovsdb.responses = [self.fake_message]

    def test_insert_ucast_macs_local(self):
        """Test case to test insert_ucast_macs_local."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Local',
                             'row': {'MAC': 'fake_MAC_value',
                                     'logical_switch': [
                                         'uuid',
                                         'fake_logical_switch_uuid'],
                                     'locator': ['uuid',
                                                 'fake_locator_uuid']}},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.insert_ucast_macs_local(
                'fake_logical_switch_uuid', 'fake_locator_uuid',
                'fake_MAC_value')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_insert_ucast_macs_local_and_locator(self):
        """Test case to test insert_ucast_macs_local_and_locator."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Physical_Locator',
                             'row': {'dst_ip': 'fake_locator_ip',
                                     'encapsulation_type': 'vxlan_over_ipv4'
                                     }, 'uuid-name': 'RVTEP'},
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Local',
                             'row': {'MAC': 'fake_MAC_value',
                                     'logical_switch': [
                                         'uuid',
                                         'fake_logical_switch_uuid'],
                                     'locator': ['named-uuid', 'RVTEP']}},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.insert_ucast_macs_local_and_locator(
                'fake_logical_switch_uuid', 'fake_locator_ip',
                'fake_MAC_value')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_get_ucast_macs_remote(self):
        """Test case to test get_ucast_macs_remote."""
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Ucast_Macs_Remote',
                             'where': [['MAC', '==', 'fake_port_mac']]}],
                 'id': self.op_id}

        return_value_raw = '{"id":1,"result":[{"rows":[{"_version":["uuid",' \
                           '"fake_v_uuid"],"locator":["uuid",' \
                           '"fake_locator_uuid"],"logical_switch":["uuid",' \
                           '"fake_ls_uuid"],"_uuid":["uuid","fake_uuid"],' \
                           '"MAC":"fake_port_mac","ipaddr":"fake_ipaddr"' \
                           '}]}],"error":null}'

        return_value = return_value_raw.replace(':null', ':None')
        self.fake_ovsdb.response = ast.literal_eval(return_value)
        expected_result = [{'MAC': 'fake_port_mac',
                            '_uuid': ['uuid', 'fake_uuid'],
                            '_version': ['uuid', 'fake_v_uuid'],
                            'ipaddr': 'fake_ipaddr',
                            'locator': ['uuid', 'fake_locator_uuid'],
                            'logical_switch': ['uuid', 'fake_ls_uuid']}]

        with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
                               return_value=return_value_raw), \
            mock.patch.object(random, 'getrandbits',
                              return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            result = self.fake_ovsdb.get_ucast_macs_remote(
                'fake_port_mac')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)
            self.assertEqual(result, expected_result)
        self.fake_ovsdb.responses = [self.fake_message]

    def test_delete_ucast_macs_remote(self):
        """Test case to test delete_ucast_macs_remote."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'delete',
                             'table': 'Ucast_Macs_Remote',
                             'where': [['MAC', '==', 'fake_MAC_value']]},
                            commit_dict],
                 'id': self.op_id}

        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.delete_ucast_macs_remote(
                'fake_MAC_value')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_insert_ucast_macs_remote(self):
        """Test case to test insert_ucast_macs_remote."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Remote',
                             'row': {'MAC': 'fake_MAC_value',
                                     'logical_switch': [
                                         'uuid',
                                         'fake_logical_switch_uuid'],
                                     'locator': ['uuid', 'fake_locator_uuid'],
                                     'ipaddr': 'fake_ipaddr1'}},
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Remote',
                             'row': {'MAC': 'fake_MAC_value',
                                     'logical_switch': [
                                         'uuid',
                                         'fake_logical_switch_uuid'],
                                     'locator': ['uuid', 'fake_locator_uuid'],
                                     'ipaddr': 'fake_ipaddr2'}},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.insert_ucast_macs_remote(
                'fake_logical_switch_uuid', 'fake_MAC_value',
                self.fake_ipaddrs, 'fake_locator_uuid', mock.ANY)
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_insert_ucast_macs_remote_and_locator(self):
        """Test case to test insert_ucast_macs_remote_and_locator."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Physical_Locator',
                             'row': {'dst_ip': 'fake_locator_ip',
                                     'encapsulation_type': 'vxlan_over_ipv4'
                                     }, 'uuid-name': 'RVTEP'},
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Remote',
                             'row': {'MAC': 'fake_MAC_value',
                                     'logical_switch': [
                                         'uuid',
                                         'fake_logical_switch_uuid'],
                                     'locator': ['named-uuid', 'RVTEP'],
                                     'ipaddr': 'fake_ipaddr1'}},
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Remote',
                             'row': {'MAC': 'fake_MAC_value',
                                     'logical_switch': [
                                         'uuid',
                                         'fake_logical_switch_uuid'],
                                     'locator': ['named-uuid', 'RVTEP'],
                                     'ipaddr': 'fake_ipaddr2'}},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.insert_ucast_macs_remote_and_locator(
                'fake_logical_switch_uuid', 'fake_MAC_value',
                self.fake_ipaddrs, 'fake_locator_ip', mock.ANY)
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    def test_reset_physical_port(self):
        """Test case to test reset_physical_port."""
        commit_dict = {'op': 'commit', 'durable': True}
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'update',
                             'table': 'Physical_Port',
                             'where': [['name', '==', 'fake_port_name']],
                             'row': {'vlan_bindings': ['map', []]}},
                            commit_dict],
                 'id': self.op_id}
        with mock.patch.object(random, 'getrandbits',
                               return_value=self.op_id) as get_rand, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              '_send_and_receive') as send_n_receive, \
            mock.patch.object(ovsdb_writer.LOG,
                              'debug'):
            self.fake_ovsdb.reset_physical_port(
                'fake_port_name')
            get_rand.assert_called_with(128)
            send_n_receive.assert_called_with(query, self.op_id, True)

    # def test_get_logical_switch_uuid_return_none(self):
    #    """Test case to test get_logical_switch_uuid but none returned."""
    #    return_value_raw = '{"id":1,"result":[{"rows":[]}],"error":null}'
    #    return_value_raw = return_value_raw.replace(':null', ':None')
    #    return_value_dict = ast.literal_eval(return_value_raw)
    #    self.fake_ovsdb.responses = [return_value_dict]
    #    with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
    #                           return_value=return_value_raw):
    #        with mock.patch.object(random, 'getrandbits',
    #                               return_value=self.op_id):
    #            with mock.patch.object(ovsdb_writer.OVSDBWriter,
    #                                   '_send_and_receive'):
    #                with mock.patch.object(ovsdb_writer.LOG, 'debug'):
    #                    self.assertRaises(
    #                        IndexError,
    #                        self.fake_ovsdb.get_logical_switch_uuid,
    #                        self.op_id)
    #    self.fake_ovsdb.responses = [self.fake_message]

    # def test_get_physical_locator_uuid_return_none(self):
    #    """Test case to test get_physical_locator_uuid but none returned."""
    #    return_value_raw = '{"id":1,"result":[{"rows":[]}],"error":null}'
    #    return_value_raw = return_value_raw.replace(':null', ':None')
    #    return_value_dict = ast.literal_eval(return_value_raw)
    #    self.fake_ovsdb.responses = [return_value_dict]
    #    with mock.patch.object(ovsdb_writer.OVSDBWriter, '_recv_data',
    #                           return_value=return_value_raw):
    #        with mock.patch.object(random, 'getrandbits',
    #                               return_value=self.op_id):
    #            with mock.patch.object(ovsdb_writer.OVSDBWriter,
    #                                   '_send_and_receive'):
    #                with mock.patch.object(ovsdb_writer.LOG, 'debug'):
    #                    self.assertRaises(
    #                        IndexError,
    #                        self.fake_ovsdb.get_logical_switch_uuid,
    #                        self.op_id)
    #    self.fake_ovsdb.responses = [self.fake_message]
