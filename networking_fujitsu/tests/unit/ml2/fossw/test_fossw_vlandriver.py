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
                 "switch_info ": "ET-7648BRA-FOS"},
                {"switch_id": "00:00:4c:ee:e5:40", "port_id": "0/1",
                 "switch_info": "ET-7648BRA-FOS"}]}

DUMMY_FOSSW_IPS = ['192.168.0.1']


class BaseTestFOSSWVlanDriver(base.BaseTestCase):
    """Base class to test Fujitsu FOSSW driver."""

    def setUp(self):
        super(BaseTestFOSSWVlanDriver, self).setUp()
        cfg.CONF.register_opts(
            mech_fossw.ML2_FUJITSU,
            mech_fossw.ML2_FUJITSU_GROUP
        )
        self.driver = fossw_vlandriver.FOSSWVlanDriver(cfg.CONF)


class TestFOSSWVlanDriverCreateVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu fossw driver for create VLAN"""

    def setUp(self):
        super(TestFOSSWVlanDriverCreateVlan, self).setUp()
        self.driver.client.connect = mock.Mock(return_value=None)
        self.driver.client.create_vlan = mock.Mock(return_value=None)
        self.driver.client.disconnect = mock.Mock(return_value=None)

    def test_create_vlan(self):
        self.driver.create_vlan(DUMMY_FOSSW_IPS[0], 2)
        self.assertIsNone(self.driver.client.ssh)

    def test_create_vlan_fail(self):
        error = client.FOSSWClientException('create_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.create_vlan,
            DUMMY_FOSSW_IPS[0],
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
        self.driver.delete_vlan(DUMMY_FOSSW_IPS[0], 2)
        self.assertIsNone(self.driver.client.ssh)

    def test_delete_vlan_fail(self):
        error = client.FOSSWClientException('delete_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.delete_vlan,
            DUMMY_FOSSW_IPS[0],
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

    def test_setup_vlan_fail(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:40': '192.168.1.1'}
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.setup_vlan,
            2,
            LLI['single'],
            ip_mac_pairs
        )
        ip_mac_pairs = {'00:00:4c:ee:e5:40': '192.168.1.1'}
        error = client.FOSSWClientException('set_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.setup_vlan,
            2,
            LLI['single'],
            ip_mac_pairs
        )


class TestFOSSWVlanDriverClearVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver for clear vlan"""
    def setUp(self):
        super(TestFOSSWVlanDriverClearVlan, self).setUp()
        self.driver.client.connect = mock.Mock(return_value=None)
        self.driver.client.clear_vlan = mock.Mock(return_value=None)
        self.driver.client.disconnect = mock.Mock(return_value=None)

    def test_clear_vlan(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:39': '192.168.1.1'}
        self.driver.clear_vlan(2, LLI['single'], ip_mac_pairs)
        self.assertIsNone(self.driver.client.ssh)

    def test_clear_vlan_fail(self):
        ip_mac_pairs = {'00:00:4c:ee:e5:40': '192.168.1.1'}
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.clear_vlan,
            2,
            LLI['single'],
            ip_mac_pairs
        )
        ip_mac_pairs = {'00:00:4c:ee:e5:40': '192.168.1.1'}
        error = client.FOSSWClientException('set_vlan')
        self.driver.client.connect.side_effect = error
        self.assertRaises(
            client.FOSSWClientException,
            self.driver.clear_vlan,
            2,
            LLI['single'],
            ip_mac_pairs
        )
