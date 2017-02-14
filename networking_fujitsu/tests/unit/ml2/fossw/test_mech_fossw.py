# Copyright 2017 FUJITSU LIMITED
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock

from oslo_utils import uuidutils

from networking_fujitsu.ml2.fossw import mech_fossw
from neutron.plugins.ml2 import config as ml2_config
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin

LLI = {'single': [{"switch_id": "00:00:4c:ee:e5:39", " port_id": "0/1",
                   "switch_info": "ET-7648BRA-FOS"}],
       'lag': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "0/2",
                "switch_info": "ET-7648BRA-FOS"},
               {"switch_id": "00:00:4c:ee:e5:39", "port_id": "0/3",
                "switch_info": "ET-764BRA-FOS"}],
       'mlag': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "0/2",
                 "switch_info": "ET-764BRA-FOS"},
                {"switch_id": "00:00:4c:ee:e5:40", "port_id": "0/2",
                 "switch_info": "ET-764BRA-FOS"}]}


class TestFujitsuMechDriverV2(test_ml2_plugin.Ml2PluginV2TestCase):
    """Test Fujitsu mechanism driver.

    """

    _mechanism_drivers = ['fujitsu_fossw']

    _skip = ["test_create_router_port_and_fail_create_postcommit"]

    def setup(self):

        ml2_config.cfg.CONF.set_override(
            'tenant_network_types', ['vlan', 'vxlan'], 'ml2')

        if self._testMethodName in self._skip:
            self.skipTest("This test has already verified at neutron's test.")

        def mocked_initialize(self):
            self._list_switch_info = [{"ip": "192.168.3.123", "port": 22,
                                       "username": "admin", "password": "",
                                       "timeout": 30},
                                      {"ip": "192.168.3.124", "port": 22,
                                       "username": "admin", "password": "",
                                       "timeout": 30}]
            self._driver = mock.MagicMock()

            with mock.patch.object(mech_fossw.FujitsuMechanism,
                                   'initialize', new=mocked_initialize):
                super(TestFujitsuMechDriverV2, self).setUp()


class TestFujitsuMechDriverNetworksV2(test_ml2_plugin.TestMl2NetworksV2,
                                      TestFujitsuMechDriverV2):
    pass


class TestFujitsuMechDriverPortsV2(test_ml2_plugin.TestMl2PortsV2,
                                   TestFujitsuMechDriverV2):
    pass


class TestFujitsuMechDriverBaremetalPortsV2(TestFujitsuMechDriverV2):

    def setup_net_and_port(self, method='create', net={}, port={},
                           phy_port='single'):
        def call_method(arg):
            return 'new_' + arg + '_request'
        target = call_method(method)

        with self.network() as network:
            net_id = network['network']['id']
            self._create_subnet(self.fmt, net_id, '172.16.1.0/24')
            port_data = {'port': {'network_id': network['network']['id'],
                                  'tenant_id':
                                  network['network']['tenant_id'],
                                  'name': 'prov-port', 'admin_state_up': 1,
                                  'binding:vnic_type': 'baremetal',
                                  'binding:profile':
                                  {'local_link_information':
                                      LLI[phy_port]}}}
            if method in ['update', 'delete']:
                port = self.deserialize(
                    self.fmt,
                    self.new_create_request(
                        'ports',
                        port_data
                    ).get_response(self.api)
                )
                p_id = port['port']['id']
                call_target = getattr(self, target)
                if method is 'update':
                    body = {
                        'port': {
                            'binding:host_id': uuidutils.generate_uuid()
                        }
                    }
                    call_target('ports', p_id,
                                str(body)).get_response(self.api)
                else:
                    call_target('ports', p_id).get_response(self.api)
            else:
                call_target = getattr(self, target)
                call_target('ports', port_data).get_response(self.api)

    def test_create_with_single_NIC(self):
        self.setup_net_and_port()

    def test_create_with_lag(self):
        self.setup_net_and_port(phy_port='lag')

    def test_create_with_mlag(self):
        self.setup_net_and_port(phy_port='mlag')

    def test_update_with_single_NIC(self):
        self.setup_net_and_port(method='update')

    def test_update_with_lag(self):
        self.setup_net_and_port(method='update', phy_port='lag')

    def test_update_with_mlag(self):
        self.setup_net_and_port(method='update', phy_port='mlag')

    def test_delete_with_single_NIC(self):
        self.setup_net_and_port(method='delete')

    def test_delete_with_lag(self):
        self.setup_net_and_port(method='delete', phy_port='lag')

    def test_delete_with_mlag(self):
        self.setup_net_and_port(method='delete', phy_port='mlag')
