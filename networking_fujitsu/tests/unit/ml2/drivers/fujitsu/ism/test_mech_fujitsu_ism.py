# -*- coding: utf-8 -*-

# Copyright 2015-2016 FUJITSU LIMITED
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
test_networking_fujitsu
----------------------------------

Tests for `networking_fujitsu` module.
"""
from mock import MagicMock

from networking_fujitsu.ml2.drivers.fujitsu.ism import mech_fujitsu_ism
from networking_fujitsu.tests.unit.ml2.drivers.fujitsu.ism import ism_common
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class FujitsuIsmDriverTestCase(test_ml2_plugin.Ml2PluginV2TestCase):

    _mechanism_drivers = ['fujitsu_ism']
    # test_create_router_port_and_fail_create_postcommit:
    #     This one is mocked 'fake_driver' only. So, our plugin's instance
    #     hasn't mocked and fail definitely. Therefore, skips this test.
    _skip = ["test_create_router_port_and_fail_create_postcommit"]

    def setUp(self):

        if self._testMethodName in self._skip:
            self.skipTest("This test has already verified at neutron's test.")
        self._driver = mech_fujitsu_ism.FujitsuIsmDriver()
        super(FujitsuIsmDriverTestCase, self).setUp()

    def tearDown(self):
        super(FujitsuIsmDriverTestCase, self).tearDown()

    def prepare(self, net={}, port={}):
        mock_net, mock_port = self.prepare_net_and_port(net, port)
        network_type = mock_net['provider:network_type']
        seg_id = mock_net['provider:segmentation_id']
        ism_common.IsmMockFactory(network_type, seg_id)
        return self.prepare_dummy_context(mock_net, mock_port)

    def prepare_net_and_port(self, net_params={}, port_params={}):
        neutron = ism_common.NeutronFactory()
        mock_net = neutron.build_network(net_params)
        mock_port = neutron.build_port(mock_net, port_params)
        return mock_net, mock_port

    def prepare_dummy_context(self, mock_net, mock_port):
        context = ism_common.DummyContext(mock_net, mock_port)
        self.driver.get_network = MagicMock(return_value=mock_net)
        return context

    # Test Start
    # def test_create_port_vnic_type_is_not_baremetal(self):
    #    port = {'binding:vnic_type': 'hogemetal'}
    #    context = self.prepare(net={}, port=port)
    #    result = self._driver.create_port_postcommit(context)
    #    self.assertFalse(result)

    # def test_create_port_local_link_is_empty_list(self):
    #    port = {'local_link_information': {}}
    #    context = self.prepare(net={}, port=port)
    #    result = self._driver.create_port_postcommit(context)
    #    self.assertFalse(result)

    # def test_create_port_success(self):
    #    context = self.prepare(net={}, port={})
    #    result = self._driver.create_port_postcommit(context)
    #    self.assertFalse(result)


class TestFujitsuMechDriverPortsV2(test_ml2_plugin.TestMl2PortsV2,
                                   FujitsuIsmDriverTestCase):
    pass
