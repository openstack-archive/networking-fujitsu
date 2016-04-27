# Copyright 2015-2016 FUJITSU LIMITED
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
import os
from oslo_utils import uuidutils

import mock

try:
    from oslo_log import log as logging
except ImportError:
    from neutron.openstack.common import log as logging

from networking_fujitsu.ml2.drivers.fujitsu.cfab import cfabdriver
from networking_fujitsu.ml2.drivers.fujitsu.cfab import mechanism_fujitsu
from neutron.plugins.ml2 import config as ml2_config
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin

LOG = logging.getLogger(__name__)
LLI = {'single': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "1/1/0/1",
          "switch_info": "CFX2000R"}],
       'lag': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "1/1/0/2",
           "switch_info": "CFX2000R"},
               {"switch_id": "00:00:4c:ee:e5:39", "port_id": "1/1/0/3",
                   "switch_info": "CFX2000R"}],
       'mlag': [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "1/1/0/2",
           "switch_info": "CFX2000R"},
               {"switch_id": "00:00:4c:ee:e5:40", "port_id": "1/1/0/2",
                   "switch_info": "CFX2000R"}]}


class TestFujitsuMechDriverV2(test_ml2_plugin.Ml2PluginV2TestCase):
    """Test Fujitsu mechanism driver.

    If the environment variable OS_FUJITSU_CFAB_ADDRESS is defined, tests will
    be performed using the C-Fabric driver, and a telnet connection to the
    address OS_FUJITSU_CFAB_ADDRESS and the port OS_FUJITSU_CFAB_PORT (defaults
    to 23) will be established. The username will be taken from
    OS_FUJITSU_CFAB_USERNAME (defaults to "admin") and the password will be
    taken from OS_FUJITSU_CFAB_PASSWORD (defaults to "password").
    If the environment variable OS_FUJITSU_CFAB_ADDRESS is NOT defined, tests
    will be performed using the mock driver instead of the C-Fabric driver, and
    no real telnet connection will be used.
    """

    _mechanism_drivers = ['fujitsu_cfab']
    # test_create_router_port_and_fail_create_postcommit:
    #     This one is mocked 'fake_driver' only. So, our plugin's instance
    #     hasn't mocked and fail definitely. Therefore, skips this test.
    _skip = ["test_create_router_port_and_fail_create_postcommit"]

    def setUp(self):

        ml2_config.cfg.CONF.set_override(
            'tenant_network_types', ['vlan'], 'ml2')

        if self._testMethodName in self._skip:
            self.skipTest("This test has already verified at neutron's test.")

        address = os.environ.get('OS_FUJITSU_CFAB_ADDRESS')
        if address:
            ml2_fujitsu_opts = {
                'username': os.environ.get('OS_FUJITSU_CFAB_USERNAME') or
                "admin",
                'password': os.environ.get('OS_FUJITSU_CFAB_PASSWORD') or
                "password",
                'address': address,
                'physical_networks': ["physnet1:1", "physnet2:2"],
                'pprofile_prefix': "test-"}

            for opt, val in ml2_fujitsu_opts.items():
                ml2_config.cfg.CONF.set_override(opt, val, "fujitsu_cfab")

            try:
                cfabdriver.TELNET_PORT = int(
                    os.environ['OS_FUJITSU_CFAB_PORT'])
            except KeyError:
                pass
            super(TestFujitsuMechDriverV2, self).setUp()
        else:
            def mocked_initialize(self):
                self._switch = {'address': "", 'username': "", 'password': ""}
                self._driver = mock.MagicMock()
                self._physical_networks = {'physnet1': "1", 'physnet2': "2"}

            with mock.patch.object(mechanism_fujitsu.FujitsuMechanism,
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
        #network_type = 'vlan'
        #segmentation_id = 100
        #physical_network = 'physnet1'
        #if net.get(pnet.NETWORK_TYPE):
        #    network_type = net.get(pnet.NETWORK_TYPE)
        #if net.get(pnet.SEGMENTATION_ID):
        #    segmentation_id = net.get(pnet.SEGMENTATION_ID)
        #if net.get(pnet.PHYSICAL_NETWORK):
        #    physical_network = net.get(pnet.PHYSICAL_NETWORK)

        #kwargs = {'name': 'prov-net',
        #          'tenant_id': 'tenant_one',
        #          'segments':[{
        #              pnet.NETWORK_TYPE: network_type,
        #              pnet.SEGMENTATION_ID: segmentation_id,
        #              pnet.PHYSICAL_NETWORK: physical_network}]}
        with self.network() as network:
            net_id = network['network']['id']
            self._create_subnet(self.fmt, net_id, '172.16.1.0/24')
            port_data = {'port': {'network_id': network['network']['id'],
                                  'tenant_id': network['network']['tenant_id'],
                                  'name': 'prov-port', 'admin_state_up': 1,
                                  'binding:vnic_type': 'baremetal',
                                  'binding:profile': {'local_link_information':
                                      LLI[phy_port]}}}
            if method in ['update', 'delete']:
                port = self.deserialize(self.fmt,
                                        self.new_create_request('ports',
                                            port_data).get_response(self.api))
                p_id = port['port']['id']
                #return network['network'], port
                call_target = getattr(self, target)
                if method is 'update':
                    body = {'port': {'binding:host_id':
                                uuidutils.generate_uuid()}}
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
        self.setup_net_and_port(method="update")

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
