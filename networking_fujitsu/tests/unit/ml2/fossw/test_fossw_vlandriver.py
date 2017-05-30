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

import copy
import mock
from networking_fujitsu.ml2.fossw import client
from networking_fujitsu.ml2.fossw import fossw_vlandriver
from networking_fujitsu.ml2.fossw import mech_fossw
from neutron.tests import base
from oslo_config import cfg

LLI = {'single': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "0/1",
                   "switch_info": "ET-7648BRA-FOS"}],
       'lag': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "0/1",
                "switch_info": "ET-7648BRA-FOS"},
               {"switch_id": "00:00:4c:ee:e5:39", "port_id": "0/2",
                "switch_info": "ET-7648BRA-FOS"}],
       'mlag': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "0/1",
                 "switch_info": "ET-7648BRA-FOS"},
                {"switch_id": "00:00:4c:ee:e5:40", "port_id": "0/1",
                 "switch_info": "ET-7648BRA-FOS"}]}
DUMMY_IP = '192.168.0.1'
DUMMY_IPS = ['192.168.0.1', '192.168.0.2']


class BaseTestFOSSWVlanDriver(base.BaseTestCase):
    """Base class to test Fujitsu FOSSW driver."""

    def setUp(self):
        super(BaseTestFOSSWVlanDriver, self).setUp()
        cfg.CONF.register_opts(
            mech_fossw.ML2_FUJITSU,
            mech_fossw.ML2_FUJITSU_GROUP
        )
        self.driver = fossw_vlandriver.FOSSWVlanDriver(cfg.CONF)


class TestFOSSWVlanDriverGetSwitchMacIpPair(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver for get_switch_mac_ip_pair"""
    def setUp(self):
        super(TestFOSSWVlanDriverGetSwitchMacIpPair, self).setUp()
        self.driver.client = mock.Mock()
        self.driver.client.get_switch_mac.return_value = 'aa:aa:aa:aa:aa:aa'

    def test_returns_mac_address_with_single_ip(self):
        ret = self.driver.get_switch_mac_ip_pair([DUMMY_IP])
        self.assertEqual({'aa:aa:aa:aa:aa:aa': DUMMY_IP}, ret)

    def test_returns_mac_address_with_multiple_ips(self):
        self.driver.client.get_switch_mac.side_effect = [
            'aa:aa:aa:aa:aa:aa',
            'ff:ff:ff:ff:ff:ff']
        expect = {
            'aa:aa:aa:aa:aa:aa': '192.168.0.1',
            'ff:ff:ff:ff:ff:ff': '192.168.0.2'}
        ret = self.driver.get_switch_mac_ip_pair(DUMMY_IPS)
        self.assertEqual(expect, ret)

    def test_mac_cannot_get(self):
        self.driver.client.get_switch_mac.return_value = None
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.get_switch_mac_ip_pair, [DUMMY_IP])

    def test_mac_cannot_get_with_multiple_ips(self):
        self.driver.client.get_switch_mac.return_value = None
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.get_switch_mac_ip_pair, DUMMY_IPS)


class TestFOSSWVlanDriverCreateVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu fossw driver for create VLAN"""

    def setUp(self):
        super(TestFOSSWVlanDriverCreateVlan, self).setUp()
        self.driver.client.connect = mock.Mock(return_value=None)
        self.driver.client.create_vlan = mock.Mock(return_value=None)
        self.driver.client.disconnect = mock.Mock(return_value=None)

    def test_create_vlan(self):
        self.driver.create_vlan(DUMMY_IP, 2)
        self.assertIsNone(self.driver.client.ssh)

    def test_create_vlan_fail(self):
        error = client.FOSSWClientException('create_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.create_vlan,
            DUMMY_IP,
            2
        )


class TestFOSSWVlanDriverDeleteVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver for delete VLAN"""
    def setUp(self):
        super(TestFOSSWVlanDriverDeleteVlan, self).setUp()
        self.driver.client.connect = mock.Mock(return_value=None)
        self.driver.client.delete_vlan = mock.Mock(return_value=None)
        self.driver.client.disconnect = mock.Mock(return_value=None)

    def test_delete_vlan(self):
        self.driver.delete_vlan(DUMMY_IP, 2)
        self.assertIsNone(self.driver.client.ssh)

    def test_delete_vlan_fail(self):
        error = client.FOSSWClientException('delete_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.delete_vlan,
            DUMMY_IP,
            2
        )


class TestFOSSWVlanDriverSetupVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver."""
    def setUp(self):
        super(TestFOSSWVlanDriverSetupVlan, self).setUp()
        self.driver.client.connect = mock.Mock(return_value=None)
        self.driver.client.set_vlan = mock.Mock(return_value=None)
        self.driver.client.disconnect = mock.Mock(return_value=None)

    def test_setup_vlan(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:39': '192.168.1.1'}
        self.driver.setup_vlan(2, LLI['single'], ip_mac_pairs)
        self.assertIsNone(self.driver.client.ssh)

    def test_setup_vlan_fail_with_keyerror(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:40': '192.168.1.1'}
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.setup_vlan,
            2,
            LLI['single'],
            ip_mac_pairs
        )
        self.driver.client.disconnect.assert_not_called()

    def test_setup_vlan_fail_with_connect_fail(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:39': '192.168.1.1'}
        error = client.FOSSWClientException('set_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.setup_vlan,
            2,
            LLI['single'],
            ip_mac_pairs
        )
        self.driver.client.set_vlan.assert_not_called()
        self.driver.client.disconnect.assert_called_once()


class TestFOSSWVlanDriverIsValidMLAG(BaseTestFOSSWVlanDriver):
    """Test FujitsuFOSSW vlan driver for setup vlan with lag"""
    def setUp(self):
        super(TestFOSSWVlanDriverIsValidMLAG, self).setUp()
        self.driver.client = mock.Mock()

    def test_valid(self):
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        macs = ["00:00:4c:ee:e5:39", "00:00:4c:ee:e5:40"]
        self.driver.client.get_peerlink_partner.return_value = '192.168.1.1'
        self.assertTrue(self.driver.is_valid_mlag(macs, ip_mac_pairs))

    def test_invalid_with_non_exist_mac(self):
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        macs = ["00:00:4c:ee:e5:39", "ff:ff:ff:ff:ff:ff"]
        self.assertFalse(self.driver.is_valid_mlag(macs, ip_mac_pairs))

    def test_raises_with_get_peerlink_partner(self):
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        macs = ["00:00:4c:ee:e5:39", "ff:ff:ff:ff:ff:ff"]
        self.driver.client.get_peerlink_partner.side_effect = Exception
        self.assertFalse(self.driver.is_valid_mlag(macs, ip_mac_pairs))


class TestFOSSWVlanDriverSetupVlanWithLAG(BaseTestFOSSWVlanDriver):
    """Test FujitsuFOSSW vlan driver for setup vlan with lag"""
    def setUp(self):
        super(TestFOSSWVlanDriverSetupVlanWithLAG, self).setUp()
        self.driver.is_valid_mlag = mock.Mock(return_value=False)
        self.driver.setup_vlan = mock.Mock()
        self.driver.client = mock.Mock()
        self.driver.client.get_lag_port.return_value = "3/1"
        self.driver.client.get_vpcid.return_value = 1
        self.vlanid = 2

    def test_lag_normal(self):
        llis = LLI['lag']
        lag_lli = copy.deepcopy(llis[0])
        lag_lli['port_id'] = '3/1'
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        self.assertIsNone(self.driver.setup_vlan_with_lag(
            self.vlanid, llis, ip_mac_pairs))

        self.driver.is_valid_mlag.assert_not_called()
        self.driver.client.connect.assert_called_once_with(
            ip_mac_pairs[llis[0]['switch_id']])
        self.driver.client.get_lag_port.assert_called_once()
        self.assertEqual(2, self.driver.client.join_to_lag.call_count)
        for lli in llis:
            self.driver.client.join_to_lag.assert_called_with(mock.ANY, '3/1')
        self.driver.setup_vlan.assert_called_once_with(
            self.vlanid, [lag_lli], ip_mac_pairs)
        self.driver.client.get_vpcid.assert_not_called()
        self.driver.client.join_to_vpc.assert_not_called()
        self.driver.client.disconnect.assert_called_once()

    def test_lag_lagport_not_found(self):
        self.driver.client.get_lag_port.return_value = None
        llis = LLI['lag']
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.setup_vlan_with_lag,
            self.vlanid, llis, ip_mac_pairs)
        self.driver.client.disconnect.assert_called_once()
        self.driver.client.join_to_vpc.assert_not_called()
        self.driver.client.get_vpcid.assert_not_called()
        self.driver.client.join_to_lag.assert_not_called()
        self.driver.setup_vlan.assert_not_called()

    def test_mlag_normal(self):
        llis = LLI['mlag']
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        self.driver.is_valid_mlag.return_value = True
        self.driver.client.join_to_vpc = mock.Mock(return_value=None)
        self.assertIsNone(self.driver.setup_vlan_with_lag(
            self.vlanid, llis, ip_mac_pairs))
        unique_mac_list = sorted(["00:00:4c:ee:e5:39", "00:00:4c:ee:e5:40"])
        self.driver.is_valid_mlag.assert_called_once()

        self.assertEqual(
            unique_mac_list, self.driver.is_valid_mlag.call_args[0][0])
        self.assertEqual(
            ip_mac_pairs, self.driver.is_valid_mlag.call_args[0][1])
        self.assertEqual(2, self.driver.client.join_to_vpc.call_count)

        lag_p = [{
            'switch_id': unique_mac_list[0],
            'port_id': '3/1',
            'switch_info': 'ET-7648BRA-FOS'}, {
            'switch_id': unique_mac_list[1],
            'port_id': '3/1',
            'switch_info': 'ET-7648BRA-FOS',
        }]
        for idx, arg in enumerate(self.driver.setup_vlan.call_args_list):
            self.assertEqual(self.vlanid, arg[0][0])
            self.assertEqual([lag_p[idx]], arg[0][1])
            self.assertEqual(ip_mac_pairs, arg[0][2])

        for arg in self.driver.client.join_to_vpc.call_args_list:
            self.assertEqual(('3/1', 1), arg[0])

    def test_mlag_not_valid_pair(self):
        llis = LLI['mlag']
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        self.assertRaises(client.FOSSWClientException,
                          self.driver.setup_vlan_with_lag,
                          self.vlanid,
                          llis,
                          ip_mac_pairs)
        self.driver.client.setup_vlan.assert_not_called()

    def test_mlag_vpcid_already_used(self):
        llis = LLI['mlag']
        ip_mac_pairs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        self.driver.is_valid_mlag.return_value = True
        self.driver.client.get_vpcid = mock.Mock(return_value=None)
        self.assertRaises(client.FOSSWClientException,
                          self.driver.setup_vlan_with_lag,
                          self.vlanid,
                          llis,
                          ip_mac_pairs)
        self.driver.client.disconnect.assert_called_once()


class TestFOSSWVlanDriverClearVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver for clear vlan"""
    def setUp(self):
        super(TestFOSSWVlanDriverClearVlan, self).setUp()
        self.driver.client = mock.Mock()
        self.driver.client.connect.return_value = None
        self.driver.client.clear_vlan.return_value = None
        self.driver.client.disconnect.return_value = None

    def test_clear_vlan(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:39': '192.168.1.1'}
        self.driver.clear_vlan(LLI['single'], ip_mac_pairs)
        self.driver.client.disconnect.assert_called_once()

    def test_clear_vlan_fail_with_keyerror(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:40': '192.168.1.1'}
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.clear_vlan, LLI['single'], ip_mac_pairs)
        self.driver.client.disconnect.assert_not_called()

    def test_clear_vlan_fail_with_connect_fail(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:39': '192.168.1.1'}
        error = client.FOSSWClientException('clear_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.clear_vlan, LLI['single'], ip_mac_pairs)
        self.driver.client.clear_vlan.assert_not_called()
        self.driver.client.disconnect.assert_called_once()


class TestFOSSWVlanDriverClearVlanWithLAG(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver for clear vlan with LAG"""
    def setUp(self):
        super(TestFOSSWVlanDriverClearVlanWithLAG, self).setUp()
        self.driver.client = mock.Mock()
        self.driver.is_valid_mlag = mock.Mock()
        self.driver.clear_vlan = mock.Mock(return_value=None)
        self.ip_macs = {"00:00:4c:ee:e5:39": "192.168.1.1",
                        "00:00:4c:ee:e5:40": "192.168.1.2"}
        self.ports = ','.join(list(sorted(
            [lli['port_id'] for lli in LLI['lag']])))

    def test_lag_normal(self):
        llis = LLI['lag']
        lag_lli = copy.deepcopy(llis[0])
        lag_lli['port_id'] = '3/1'
        self.driver.client.get_lag_port.return_value = "3/1"
        self.assertIsNone(
            self.driver.clear_vlan_with_lag(llis, self.ip_macs))
        self.driver.is_valid_mlag.assert_not_called()
        self.driver.client.connect.assert_called_once_with(
            self.ip_macs[llis[0]['switch_id']])
        self.driver.client.get_lag_port.assert_called_once_with(
            llis[0]['port_id'])
        for lli in llis:
            self.driver.client.leave_from_lag.assert_called_with(
                mock.ANY, '3/1')
        self.driver.clear_vlan.assert_called_once_with([lag_lli], self.ip_macs)
        # Not called because following methods are for MLAG
        self.driver.client.leave_from_vpc.assert_not_called()
        self.driver.client.get_vpcid.assert_not_called()
        self.driver.client.disconnect.assert_called_once()

    def test_lagport_already_cleared(self):
        llis = LLI['lag']
        self.driver.client.get_lag_port.return_value = None
        self.assertIsNone(
            self.driver.clear_vlan_with_lag(llis, self.ip_macs))

        self.driver.client.connect.assert_called_once_with(
            self.ip_macs[llis[0]['switch_id']])
        self.driver.client.get_lag_port.assert_called_once_with(
            llis[0]['port_id'])
        self.driver.client.disconnect.assert_called_once()
        # Not called because following methods are for MLAG
        self.driver.client.leave_from_lag.assert_not_called()
        self.driver.clear_vlan.assert_not_called()
        self.driver.client.leave_from_vpc.assert_not_called()
        self.driver.client.get_vpcid.assert_not_called()

    def test_mlag(self):
        llis = LLI['mlag']
        self.driver.is_valid_mlag.return_value = True
        self.driver.client.get_lag_port.return_value = "3/1"
        self.driver.client.get_vpcid.return_value = "1"
        self.assertIsNone(self.driver.clear_vlan_with_lag(llis, self.ip_macs))
        self.driver.is_valid_mlag.assert_called_once_with(
            list(sorted(list(self.ip_macs.keys()))), self.ip_macs)
        self.driver.client.leave_from_vpc.assert_called_with("3/1", "1")
        self.assertEqual(2, self.driver.client.leave_from_vpc.call_count)
        lag_p = [{
            'switch_id': llis[0]['switch_id'],
            'port_id': '3/1',
            'switch_info': 'ET-7648BRA-FOS'}, {
            'switch_id': llis[1]['switch_id'],
            'port_id': '3/1',
            'switch_info': 'ET-7648BRA-FOS',
        }]
        for idx, arg in enumerate(self.driver.clear_vlan.call_args_list):
            self.assertEqual([lag_p[idx]], arg[0][0])
            self.assertEqual(self.ip_macs, arg[0][1])

    def test_mlag_is_invalid(self):
        llis = LLI['mlag']
        self.driver.is_valid_mlag.return_value = False
        self.assertRaises(client.FOSSWClientException,
                          self.driver.clear_vlan_with_lag, llis, self.ip_macs)

    def test_mlag_vpcid_already_cleared(self):
        llis = LLI['mlag']
        self.driver.is_valid_mlag.return_value = True
        self.driver.client.get_lag_port.return_value = "3/1"
        self.driver.client.get_vpcid.return_value = None
        self.assertIsNone(self.driver.clear_vlan_with_lag(llis, self.ip_macs))
        self.assertEqual(2, self.driver.client.disconnect.call_count)

    def test_lagport_and_vpcid_already_cleared(self):
        llis = LLI['mlag']
        self.driver.is_valid_mlag.return_value = True
        self.driver.client.get_lag_port.return_value = None
        self.driver.client.get_vpcid.return_value = None
        self.driver.clear_vlan_with_lag(llis, self.ip_macs)

        self.assertEqual(2, self.driver.client.connect.call_count)
        self.assertEqual(2, self.driver.client.get_lag_port.call_count)
        self.driver.client.leave_from_lag.assert_not_called()
        self.driver.client.leave_from_vpc.assert_not_called()
        self.driver.client.get_vpcid.assert_not_called()
        self.assertEqual(2, self.driver.client.disconnect.call_count)
