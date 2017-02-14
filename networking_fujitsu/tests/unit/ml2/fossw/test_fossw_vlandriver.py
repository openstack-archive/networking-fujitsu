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
from networking_fujitsu.ml2.fossw import fossw_vlandriver
from neutron.tests import base

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

SWITCHES = [{"address": "192.168.0.1", "username": "admin", "password": ""},
            {"address": "192.168.0.2", "username": "admin", "password": ""}]


class BaseTestFOSSWVlanDriver(base.BaseTestCase):
    """Base class to test Fujitsu FOSSW driver."""

    def setUp(self):
        super(BaseTestFOSSWVlanDriver, self).setUp()
        self.driver = fossw_vlandriver.FOSSWVlanDriver()


class TestFOSSWVlanDriverCreateVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu fossw driver for create VLAN"""

    def test_create_vlan(self):
        pass

        # TODO(t_miyagishi) Update unit test to through latest source code.
        # ip = '192.168.0.1'
        # vlan_id = '2'
        # with mock.patch('self.driver.client') as mocked_client:
        #     mocked_client.connect.return_value = None
        #     mocked_client.create_vlan.return_value = None
        #     self.assertIsNone(self.driver.create_vlan, ip, vlan_id)
        #     self.driver.client.disconnect.assert_called_with()


class TestFOSSWVlanDriverDeleteVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver for delete VLAN"""
    def setUp(self):
        super(TestFOSSWVlanDriverDeleteVlan, self).setUp()

    def test_vlan_not_exist(self):
        pass
        # TODO(t_miyagishi) Update unit test to through latest source code.
        # switch = SWITCHES[0]
        # vlan_id = 2
        # with mock.patch.object(self.driver.client,
        #                        'is_exist_vlan',
        #                        return_value=False), \
        #     mock.patch.object(self.driver.client,
        #                       'delete_vlan'):
        #     self.driver.delete_vlan(switch, vlan_id)
        #     self.assertEqual(self.driver.client.delete_vlan.called, 0)

    def test_delete_vlan(self):
        pass
        # TODO(t_miyagishi) Update unit test to through latest source code.
        # switch = SWITCHES[0]
        # vlan_id = 2
        # with mock.patch.object(self.driver.client,
        #                        'is_exist_vlan',
        #                        return_value=True), \
        #     mock.patch.object(self.driver.client,
        #                       'delete_vlan',
        #                       return_value=None):
        #     self.assertIsNone(self.driver.delete_vlan(switch, vlan_id))
        #     self.assertEqual(self.driver.client.delete_vlan.called, 1)


class TestFOSSWVlanDriverSetupVlan(BaseTestFOSSWVlanDriver):
    """Test Fujitsu FOSSW vlan driver."""
    pass
    # TODO(t_miyagishi) Update unit test to through latest source code.

    #    def setUp(self):
    #        super(TestFosswdriverSetupVlan, self).setUp()
    #
    #    def test_not_matched_switch(self):
    #        pass
    #
    #    def test_setup_vlan(self):
    #        self.driver.setup_vlan(self, SWITCHES, vlan_id, lli)
    #        pass


class TestFOSSWVlanDriverClearVlan(BaseTestFOSSWVlanDriver):
    pass
    # TODO(t_miyagishi) Update unit test to through latest source code.
