# Copyright 2015 FUJITSU LIMITED
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

from mock import MagicMock
from networking_fujitsu.ml2.drivers.fujitsu.ism import ism_base
from neutron.extensions import portbindings
from oslo_utils import uuidutils
import random

VERSION = 'ism/api/v1'
APIS = {'get_node': 'ism/api/v1/core/nodes/%(node)s',
        'list_ports': 'ism/api/v1/topology/nodes/%(node)s/%(port)s',
        'get_port': 'ism/api/v1/topology/nodes/%(node)s/ports/%(port)s',
        'get_vlan': 'ism/api/v1/topology/nodes/%(node)s/ports/%(port)s/vlan',
        'patch_vlan': 'ism/api/v1/topology/nodes/%(node)s/ports/%(port)s/vlan',
        'get_vxlan_with_port': '',
        }

RES = {'get_node': {'IsmBody': {
                    'Node': {
                        'TimeStampInfo': {
                            'Delete': '',
                            'Update': '2015-04-14T15:30:45.250Z',
                            'Register': '2015-04-14T15:30:45.250Z'},
                        'IpVersion': 'V4',
                        'IpAddress': '192.168.123.15',
                        'NodeId': '%(node)s',
                        'Name': 'blade-server1-switch1',
                        'Model': 'PY CB Eth Switch/IBP 10Gb 18/8',
                        'Status': 'Normal',
                        'AlarmStatus': 'Normal',
                        'Type': 'server',
                        'WebUrl': 'https://192.168.123.15',
                        'Description': ''},
                    'SchemaType': 'http://get_node.json'
                    }},
       'list_ports': {'IsmBody': {
                      'PortInfo': [{
                          'NeighborPort': [{
                              'PortName': 'ether 2',
                              'NodeId': '2'}],
                          'PortNumber': '2',
                          'ControllerName': '',
                          'Category': 'LAN',
                          'PortName': 'ether 2'}, {
                          'NeighborPort': [{
                              'PortName': 'eth0',
                              'NodeId': '6'}],
                          'PortNumber': '3',
                          'ControllerName': '',
                          'Category': 'LAN',
                          'PortName': 'ether 3'}, {
                          'NeighborPort': [],
                          'PortNumber': '4',
                          'ControllerName': '',
                          'Category': 'LAN',
                          'PortName': 'ether 4'}],
                      'SchemaType': 'http://list_ports.json'}},
       'get_port': {'IsmBody': {
                    'ControllerName': '',
                    'DetailedInfo': {
                        'IpAddressSet': {
                            'V4': '',
                            'V6': ''},
                        'MacAddress': '00:0C:29:31:88:EF',
                        'PortAddress': '',
                        'Slot': '',
                        'Speed': {
                            'Unit': 'Mpbs',
                            'Value': 1000
                            },
                        'Wwpn': ''},
                    'NeighborPort': [{
                        'NodeId': '2',
                        'PortName': 'ether 2'}],
                    'PortCategory': 'LAN',
                    'PortName': 'ether 1',
                    'PortNumber': '1',
                    'SchemaType': 'http://get_port.json'}},
       'get_vlan': {'IsmBody': {
                    'TaggedVLanId': '100,200,40-50',
                    'UntaggedVLanId': '300',
                    'SchemaType': 'http://get_vlan.json'}},
       'patch_vlan': {'IsmBody': {
                      'TaggedVLanId': '100,200,40-50',
                      'UntaggedVLanId': '300',
                      'SchemaType': 'http://get_vlan.json'}},
       'get_vxlan_with_port': '',
       }


class Factory(object):
    def __init__(self):
        pass


class IsmMockFactory(Factory):
    def __init__(self, network_type, seg_id):
        ism_base.IsmVlanBase = MagicMock()
        ism_base.IsmVxlanBase = MagicMock()
        self.initialize(network_type, seg_id)

    def initialize(self, network_type, seg_id):
        self.create_ism_base = MagicMock()
        if (network_type == 'vlan'):
            self.create_ism_base.return_value = ism_base.IsmVlanBase
        else:
            self.create_ism_base.return_value = ism_base.IsmVxlanBase

    def _ret_ism_info(self, params=None):
        params = params
        # TODO(yushiro) prepare response body from ISM
        return {'IsmBody': 'dummy'}

    def _req_param(self, tags=None, untags=None):
        tagged_vlan = tags or ''
        untagged_vlan = untags or '200'
        return {'TaggedVLanId': tagged_vlan, 'UntaggedVLanId': untagged_vlan}

    def _header_and_body(self, headers=None, body={}):
        headers = headers or {'sample': 'of', 'http': 'header'}
        body = body or {'IsmBody': {'key': 'value'}}
        return headers, body


class NeutronFactory(Factory):
    def __init__(self):
        self.tenant_id = '7e02058126cc4950b75f9970368ba177'
        # TODO(yushiro): delete if Ironic-Neutron Integration patch is merged.
        portbindings.VNIC_BAREMETAL = 'baremetal'

    def build_network(self, params={}):
        network_type = params.get('provider:network_type') or 'vlan'
        seg_id = params.get('provider:segmentation_id') or 1234
        return {'id': uuidutils.generate_uuid(),
                'name': 'test-network',
                'subnets': [],
                'admin_state_up': True,
                'status': 'ACTIVE',
                'tenant_id': self.tenant_id,
                'shared': False,
                'provider:network_type': network_type,
                'provider:segmentation_id': seg_id,
                }

    def build_port(self, network, params={}):
        vnic_type = (params.get('binding:vnic_type') or
                     portbindings.VNIC_BAREMETAL)
        local_link_info = self.__default_link_local_info()
        if hasattr(params, 'local_link_information'):
            local_link_info = params['local_link_information']
        return {'id': uuidutils.generate_uuid(),
                'name': 'test-port',
                'network_id': network['id'],
                'admin_state_up': True,
                'mac_address': self.__randomMAC(),
                'fixed_ips': None,
                'device_id': '',
                'device_owner': '',
                'tenant_id': network['tenant_id'],
                'status': 'ACTIVE',
                'binding:vnic_type': vnic_type,
                'binding:profile': {'local_link_information': local_link_info}
                }

    def __default_link_local_info(self):
        return [{'switch_id': '5',
                 'switch_info': 'switch_1',
                 'port_id': 'ether 1',
                 }]

    def __randomMAC(self):
        _mac = [0x00, 0x16, 0x3e,
                random.randint(0x00, 0x7f),
                random.randint(0x00, 0xff),
                random.randint(0x00, 0xff)]
        mac = ':'.join(map(lambda x: "%02x" % x, _mac))
        return mac


class DummyContext(object):

    def __init__(self, mock_net, mock_port):
        self.network = mock_net
        self.port = mock_port
        self.current = mock_port
