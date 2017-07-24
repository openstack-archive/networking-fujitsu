# Copyright 207 FUJITSU LIMITED
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

import copy

import mock
from neutron.plugins.ml2 import driver_context
from neutron.plugins.ml2 import models
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin
from oslo_utils import uuidutils

LLI = {
    'single': [{
        "switch_id": "00:00:4c:ee:e5:39",
        "port_id": "0/1",
        "switch_info": "dummy_switch1"}],
    'lag': [{
        "switch_id": "00:00:4c:ee:e5:39",
        "port_id": "0/2",
        "switch_info": "dummy_switch1"}, {
        "switch_id": "00:00:4c:ee:e5:39",
        "port_id": "0/3",
        "switch_info": "dummy_switch1"}],
    'mlag': [{
        "switch_id": "00:00:4c:ee:e5:39",
        "port_id": "0/4",
        "switch_info": "dummy_switch1"}, {
        "switch_id": "00:00:4c:ee:e5:40",
        "port_id": "0/4",
        "switch_info": "dummy_switch2"}]
}


class FujitsuMechanismHelper(test_ml2_plugin.Ml2PluginV2TestCase):
    """Fujitsu Mechanism Driver Helper.

    """

    def setUp(self):
        super(FujitsuMechanismHelper, self).setUp()

    def prepare_dummy_context(self, target='port', **kwargs):
        """Prepare dummy PortContext or NetworkContext

        """
        return (self._dummy_port_ctx(**kwargs) if target == 'port' else
                self._dummy_network_ctx(**kwargs))

    def net_seg(self, network_type):
        segment = {'provider:network_type': network_type}
        if network_type == 'flat':
            segment.update({'provider:physical_network': 'physnet1'})
        if network_type == 'vlan':
            segment.update({'provider:segmentation_id': 1111})
            segment.update({'provider:physical_network': 'physnet1'})
        if network_type == 'vxlan':
            segment.update({'provider:segmentation_id': 1111})
        return segment

    def _dummy_port_ctx(self, **kwargs):
        # 'verb', 'port', and 'nic'
        nic = kwargs.get('nic', 'single')
        network_type = kwargs.get('net_type', 'vlan')
        vif_type = kwargs.get('vif_type', None)
        vnic_type = kwargs.get('vnic_type', 'baremetal')
        project_id = uuidutils.generate_uuid()
        set_original = kwargs.get('set_original', False)

        net_params = {
            'network': {
                'name': 'dummy-net',
                'project_id': project_id,
                'segments': [self.net_seg(network_type)],
            }
        }
        req = self.new_create_request('networks', net_params, self.fmt)
        network = self.deserialize(self.fmt, req.get_response(self.api))
        net = network['network']
        project_id = network['network']['project_id']
        self._create_subnet(self.fmt, net['id'], '172.16.1.0/24')
        baremetal = {
            'binding:vnic_type': vnic_type,
            'binding:host_id': uuidutils.generate_uuid(),
            'binding:profile': {'local_link_information': LLI[nic]}
        }
        data = {
            'port': {
                'network_id': net['id'],
                'project_id': project_id,
                'name': 'dummy-port',
                'admin_state_up': 1,
            }
        }

        req = self.new_create_request('ports', data, self.fmt)
        port = self.deserialize(self.fmt, req.get_response(self.api))
        port_data = port['port']
        port_data.update(baremetal)
        if vif_type:
            port_data.update({'binding:vif_type': vif_type})
        if set_original:
            original_port = copy.deepcopy(port_data)
            original_port.update({'binding:vif_type': 'other'})
        else:
            original_port = None
        plugin = mock.Mock()
        plugin_context = mock.Mock()
        binding = models.PortBinding()
        with mock.patch.object(driver_context.segments_db,
                               'get_network_segments') as segments:
            segments.return_value = [self.net_seg(network_type)]
            mock_ctx = driver_context.PortContext(
                plugin, plugin_context, port_data, net, binding, None,
                original_port=original_port)
            mock_ctx._segments_to_bind = [mock_ctx.network.current]
            return mock_ctx

    def _dummy_network_ctx(self, **kwargs):
        """Prepare Dummy NetworkContext

        """
        network_type = kwargs.get('net_type', 'vlan')
        project_id = uuidutils.generate_uuid()
        net_params = {
            'network': {
                'tenant_id': project_id,
                'ipv4_address_scope': None,
                'admin_state_up': True,
                'name': 'dummy-net',
                'project_id': project_id,
                'status': 'ACTIVE',
                'description': '',
                'router:external': False,
                'subnets': [],
                'shared': False,
                'availability_zone_hints': [],
                'ipv6_address_scope': None,
                'availability_zones': [],
                'mtu': 1500,
                'id': '75959a8b-8321-41f9-b11f-f15fcb47b8e3'
            }
        }
        net_params['network'].update(self.net_seg(network_type))
        net = net_params['network']
        plugin = mock.Mock()
        plugin_context = mock.Mock()
        with mock.patch.object(driver_context.segments_db,
                               'get_network_segments'):
            return driver_context.NetworkContext(plugin, plugin_context, net)
