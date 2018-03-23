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

import socket

import mock
from neutron.tests import base
from oslo_config import cfg

from networking_fujitsu.ml2.common.ovsdb import ovsdb_writer
from networking_fujitsu.ml2.common import tunnel_caller
from networking_fujitsu.ml2.common import type_vxlan
from networking_fujitsu.ml2.fossw import fossw_vxlandriver
from networking_fujitsu.ml2.fossw import mech_fossw
from networking_fujitsu.tests.unit.ml2.common.ovsdb import (
    test_base_connection as base_test)

FOSSW_IPS = ["fake_sw_ip1", "fake_sw_ip2"]
FAKE_SOCKET = base_test.SocketClass(None, None, None, '{"f_key":"f_value"}')


# TODO(yushiro): Refactor to use test helper
class TestFOSSWVxlanDriver(base.BaseTestCase):
    def setUp(self):
        super(TestFOSSWVxlanDriver, self).setUp()
        cfg.CONF.register_opts(
            mech_fossw.ML2_FUJITSU,
            mech_fossw.ML2_FUJITSU_GROUP
        )
        cfg.CONF.set_override(
            'ovsdb_vlanid_range_min', 2, group='fujitsu_fossw')
        cfg.CONF.set_override('fossw_ips', FOSSW_IPS, group='fujitsu_fossw')
        cfg.CONF.set_override('tenant_network_types', ['vlan', 'vxlan'], 'ml2')

        self.fake_ip_mac_pairs = {
            'fake_switch_mac1': FOSSW_IPS[0],
            'fake_switch_mac2': FOSSW_IPS[1]
        }
        self.fake_lli = [{
            'switch_id': 'fake_switch_mac1',
            'port_id': '0/2',
            'switch_info': 'fake_switch_name1'
        }]
        self.fake_llis = [{'switch_id': 'fake_switch_mac1',
                           'port_id': '0/2',
                           'switch_info': 'fake_switch_name1'},
                          {'switch_id': 'fake_switch_mac1',
                           'port_id': '0/3',
                           'switch_info': 'fake_switch_name1'}]
        self.fake_vni = 11111
        self.fake_network_id = '708cc7a2-4e9e-44f7-8bda-f36468b36d6d'
        self.fake_ls_name = '708cc7a24e9e44f78bdaf36468b36d6d'
        self.port_mac_address = 'fa:16:3e:50:b6:45'
        self.tunnel_ip = '10.0.0.1'
        self.fixed_ips = [
            '172.16.1.1',
            '172.16.1.2',
        ]
        self.fake_port_context = {
            'network_id': self.fake_network_id,
            'mac_address': self.port_mac_address,
            'binding:host_id': 'fake_host_id',
            'fixed_ips': [
                {'ip_address': self.fixed_ips[0]},
                {'ip_address': self.fixed_ips[1]}
            ]
        }
        self.type_vxlan_endpoints = [
            {
                'ip_address': 'fake_ep_ip1',
                'udp_port': 4789,
                'host': 'fake_hostname1'
            },
            {
                'ip_address': 'fake_ep_ip2',
                'udp_port': 4789,
                'host': 'fake_hostname2'
            }
        ]
        self.fake_ctx = mock.Mock()
        self.fake_req_id = "req-00000000-0000-0000-0000-000000000000"

        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_sw_ep_info',
                              return_value=('fake_endpoint_ip',
                                            'fake_endpoint_hostname')), \
            mock.patch.object(type_vxlan.TypeVxlan, 'get_endpoints',
                              return_value=self.type_vxlan_endpoints), \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              '_update_neutron_db',
                              return_value=None):
            self.vxlan = fossw_vxlandriver.FOSSWVxlanDriver()

    def test_save_all_fossw(self):
        """Test case to test save_all_fossw."""
        self.vxlan.client = mock.Mock(return_value=None)
        self.assertIsNone(self.vxlan.save_all_fossw())
        self.assertEqual(len(FOSSW_IPS),
                         self.vxlan.client.save_running_config.call_count)

    def test_update_neutron_db_insert(self):
        """Test case to test _update_neutron_db.

        In the case that FOS switch endpoint has not been inserted.
        """

        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_sw_ep_info',
                              return_value=('fake_endpoint_ip',
                                            'fake_endpoint_hostname')), \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'get_endpoint_by_ip',
                              return_value={}) as get_epbi, \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'add_endpoint') as add_ep:
            self.vxlan._update_neutron_db()
            get_epbi.assert_called_with('fake_endpoint_ip')
            add_ep.assert_called_with('fake_endpoint_ip',
                                      'fake_endpoint_hostname', 4789)

    def test_update_neutron_db_update(self):
        """Test case to test _update_neutron_db.

        In the case that FOS switch endpoint hostname has been changed.
        """

        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_sw_ep_info',
                              return_value=('fake_endpoint_ip',
                                            'fake_endpoint_hostname')), \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'get_endpoint_by_ip',
                              return_value={'ip_address': 'fake_endpoint_ip',
                                            'udp_port': 4789,
                                            'host': 'fake_ep_host'}
                              ) as get_epbi, \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'delete_endpoint') as del_ep, \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'add_endpoint') as add_ep:
                self.vxlan._update_neutron_db()
                get_epbi.assert_called_with('fake_endpoint_ip')
                del_ep.assert_called_with('fake_endpoint_ip')
                add_ep.assert_called_with('fake_endpoint_ip',
                                          'fake_endpoint_hostname', 4789)

    def test_update_neutron_db_none(self):
        """Test case to test _update_neutron_db.

        In the case that FOS switch endpoint has not been inserted.
        """

        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_sw_ep_info',
                              return_value=('fake_endpoint_ip',
                                            'fake_endpoint_hostname')), \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'get_endpoint_by_ip',
                              return_value={'ip_address': 'fake_endpoint_ip',
                                            'udp_port': 4789,
                                            'host': 'fake_endpoint_hostname'}
                              ) as get_epbi:
                self.vxlan._update_neutron_db()
                get_epbi.assert_called_with('fake_endpoint_ip')

    def test_create_logical_switch(self):
        """Test case to test create_logical_switch."""
        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_logical_switch') as ins_ls, \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              'save_all_fossw') as save_all:
            self.vxlan.create_logical_switch(
                self.fake_network_id, self.fake_vni)
            ins_ls.assert_called_with(self.fake_vni, self.fake_ls_name)
            self.assertEqual(1, save_all.call_count)

    def test_delete_logical_switch(self):
        """Test case to test delete_logical_switch."""
        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_logical_switch_uuid',
                              return_value="fake_uuid") as get_lsuuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'delete_logical_switch') as del_ls, \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              'save_all_fossw') as save_all:
            self.vxlan.delete_logical_switch(self.fake_network_id)
            get_lsuuid.assert_called_with(self.fake_ls_name)
            del_ls.assert_called_with("fake_uuid")
            self.assertEqual(1, save_all.call_count)

    def test_update_physical_port(self):
        """Test case to test update_physical_port."""
        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'db_get_endpoint_ip_by_host',
                              return_value=self.tunnel_ip
                              ) as get_epbh, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_logical_switch_uuid',
                              return_value="fake_uuid") as get_ls_uuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_binding_vid',
                              return_value=3) as get_bvid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'update_physical_port') as up_pp, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_ucast_macs_local',
                              return_value=['fake_ucast_macs_local_rows']
                              ) as get_uml, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'delete_ucast_macs_local') as del_uml, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_sw_ep_info',
                              return_value=('fake_locator_ip_local',
                                            'fake_endpoint_hostname')
                              ) as get_sepi, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_physical_locator_uuid',
                              return_value='fake_locator_uuid_local'
                              ) as get_pluuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_local'
                              ) as ins_uml, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_local_and_locator'
                              ) as ins_umlal, \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              '_update_ucast_macs_remote') as _up_umr, \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              'save_all_fossw') as _save, \
            mock.patch.object(tunnel_caller.TunnelCaller,
                              'trigger_tunnel_sync') as tun_sync, \
                mock.patch(
                    'networking_fujitsu.ml2.fossw.fossw_vxlandriver.context.'
                    'Context', return_value=self.fake_ctx):
            self.vxlan.update_physical_port(self.fake_vni, self.fake_lli,
                                            self.fake_port_context,
                                            self.fake_ip_mac_pairs,
                                            req_id=self.fake_req_id)
            get_epbh.assert_called_with('fake_switch_name1')
            get_ls_uuid.assert_called_with(self.fake_ls_name)
            get_bvid.assert_called_with("fake_uuid")
            up_pp.assert_called_with("0/2", 3, "fake_uuid")
            get_uml.assert_called_with(self.port_mac_address)
            del_uml.assert_called_with(self.port_mac_address)
            get_sepi.assert_called_once()
            get_pluuid.assert_called_with("fake_locator_ip_local")
            ins_uml.assert_called_with("fake_uuid",
                                       "fake_locator_uuid_local",
                                       self.port_mac_address)
            ins_umlal.assert_not_called()
            _up_umr.assert_called_with(
                self.fake_ls_name,
                self.port_mac_address,
                self.tunnel_ip,
                self.fixed_ips,
                ignore=FOSSW_IPS[0]
            )
            _save.assert_called_once()
            tun_sync.assert_called_once_with(self.fake_ctx, self.tunnel_ip)

    def test_update_physical_port_without_request_id(self):
        """Test case to test update_physical_port."""
        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(type_vxlan.TypeVxlan,
                              'db_get_endpoint_ip_by_host',
                              return_value=self.tunnel_ip
                              ) as get_epbh, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_logical_switch_uuid',
                              return_value="fake_uuid") as get_ls_uuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_binding_vid',
                              return_value=3) as get_bvid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'update_physical_port') as up_pp, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_ucast_macs_local',
                              return_value=['fake_ucast_macs_local_rows']
                              ) as get_uml, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'delete_ucast_macs_local') as del_uml, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_sw_ep_info',
                              return_value=('fake_locator_ip_local',
                                            'fake_endpoint_hostname')
                              ) as get_sepi, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_physical_locator_uuid',
                              return_value='fake_locator_uuid_local'
                              ) as get_pluuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_local'
                              ) as ins_uml, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_local_and_locator'
                              ) as ins_umlal, \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              '_update_ucast_macs_remote') as _up_umr, \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              'save_all_fossw') as _save, \
            mock.patch.object(tunnel_caller.TunnelCaller,
                              'trigger_tunnel_sync') as tun_sync, \
                mock.patch(
                    'networking_fujitsu.ml2.fossw.fossw_vxlandriver.context.'
                    'Context', return_value=self.fake_ctx):
            self.vxlan.update_physical_port(self.fake_vni, self.fake_lli,
                                            self.fake_port_context,
                                            self.fake_ip_mac_pairs)
            get_epbh.assert_called_with('fake_switch_name1')
            get_ls_uuid.assert_called_with(self.fake_ls_name)
            get_bvid.assert_called_with("fake_uuid")
            up_pp.assert_called_with("0/2", 3, "fake_uuid")
            get_uml.assert_called_with(self.port_mac_address)
            del_uml.assert_called_with(self.port_mac_address)
            get_sepi.assert_called_once()
            get_pluuid.assert_called_with("fake_locator_ip_local")
            ins_uml.assert_called_with("fake_uuid",
                                       "fake_locator_uuid_local",
                                       self.port_mac_address)
            ins_umlal.assert_not_called()
            _up_umr.assert_called_with(
                self.fake_ls_name,
                self.port_mac_address,
                self.tunnel_ip,
                self.fixed_ips,
                ignore=FOSSW_IPS[0]
            )
            _save.assert_called_once()
            tun_sync.assert_not_called()

    def test_update_ucast_macs_remote(self):
        """Test case to test _update_ucast_macs_remote."""
        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_logical_switch_uuid',
                              return_value='fake_ls_uuid') as get_lsuuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_ucast_macs_remote',
                              return_value=['fake_umr_rows']) as get_umr, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'delete_ucast_macs_remote') as del_umr, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_physical_locator_uuid',
                              return_value='fake_locator_uuid'
                              ) as get_pluuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_remote') as ins_umr, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_remote_and_locator'
                              ) as ins_umral:

            self.vxlan._update_ucast_macs_remote(
                self.fake_ls_name,
                self.port_mac_address,
                self.tunnel_ip,
                self.fixed_ips
            )
            get_lsuuid.assert_called_with(self.fake_ls_name)
            get_umr.assert_called_with(self.port_mac_address)
            del_umr.assert_called_with(self.port_mac_address)
            get_pluuid.assert_called_with(self.tunnel_ip)
            ins_umr.assert_called_with('fake_ls_uuid', self.port_mac_address,
                                       self.fixed_ips, 'fake_locator_uuid')
            ins_umral.assert_not_called()

    def test_update_ucast_macs_remote_with_locator(self):
        """Test case to test _update_ucast_macs_remote.

        With related locator need to get insert, too.
        """

        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_logical_switch_uuid',
                              return_value='fake_ls_uuid') as get_lsuuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_ucast_macs_remote',
                              return_value=['fake_umr_rows']) as get_umr, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'delete_ucast_macs_remote') as del_umr, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'get_physical_locator_uuid',
                              return_value=''
                              ) as get_pluuid, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_remote') as ins_umr, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'insert_ucast_macs_remote_and_locator'
                              ) as ins_umral:

            self.vxlan._update_ucast_macs_remote(
                'fake_sw_ip1',
                self.port_mac_address,
                self.tunnel_ip,
                ['fake_port_ips']
            )
            get_lsuuid.assert_called_with('fake_sw_ip1')
            get_umr.assert_called_with(self.port_mac_address)
            del_umr.assert_called_with(self.port_mac_address)
            get_pluuid.assert_called_with(self.tunnel_ip)
            ins_umr.assert_not_called()
            ins_umral.assert_called_with('fake_ls_uuid', self.port_mac_address,
                                         ['fake_port_ips'],
                                         self.tunnel_ip)

    def test_reset_physical_port(self):
        """Test case to test reset_physical_port."""
        with mock.patch.object(socket, 'socket', return_value=FAKE_SOCKET), \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'reset_physical_port') as res_pp, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'delete_ucast_macs_local') as del_uml, \
            mock.patch.object(ovsdb_writer.OVSDBWriter,
                              'delete_ucast_macs_remote') as del_umr, \
            mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                              'save_all_fossw') as _save:
            self.vxlan.reset_physical_port(self.fake_lli,
                                           self.fake_port_context,
                                           self.fake_ip_mac_pairs)
            res_pp.assert_called_with("0/2")
            del_uml.assert_called_with(self.port_mac_address)
            del_umr.assert_called_with(self.port_mac_address)
            _save.assert_called_once()

    def test_update_physical_port_with_lag(self):
        """Test case to test update_physical_port_with_lag."""
        with mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                               'update_physical_port') as up_pp:
            self.vxlan.update_physical_port_with_lag('fake_vnid',
                                                     self.fake_llis,
                                                     self.fake_port_context,
                                                     self.fake_ip_mac_pairs,
                                                     self.fake_req_id,
                                                     mac_lag_map={})
            self.assertEqual(2, up_pp.call_count)
            for idx, arg in enumerate(up_pp.call_args_list):
                self.assertEqual('fake_vnid', arg[0][0])
                self.assertEqual([self.fake_llis[idx]], arg[0][1])
                self.assertEqual(self.fake_port_context, arg[0][2])
                self.assertEqual(self.fake_ip_mac_pairs, arg[0][3])
                self.assertEqual(self.fake_req_id, arg[0][4])
                self.assertEqual({'mac_lag_map': {}}, arg[1])

    def test_reset_physical_port_with_lag(self):
        """Test case to test reset_physical_port_with_lag."""
        with mock.patch.object(fossw_vxlandriver.FOSSWVxlanDriver,
                               'reset_physical_port') as res_pp:
            self.vxlan.reset_physical_port_with_lag(self.fake_llis,
                                                    self.fake_port_context,
                                                    self.fake_ip_mac_pairs,
                                                    mac_lag_map={})
            self.assertEqual(2, res_pp.call_count)
            for idx, arg in enumerate(res_pp.call_args_list):
                self.assertEqual([self.fake_llis[idx]], arg[0][0])
                self.assertEqual(self.fake_port_context, arg[0][1])
                self.assertEqual(self.fake_ip_mac_pairs, arg[0][2])
