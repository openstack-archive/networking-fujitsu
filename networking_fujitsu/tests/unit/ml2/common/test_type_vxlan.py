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

from neutron.plugins.common import constants as p_const
from neutron.tests.unit.plugins.ml2.drivers import base_type_tunnel
from neutron.tests.unit import testlib_api

from networking_fujitsu.ml2.common import type_vxlan


class TestTypeVxlan(base_type_tunnel.TunnelTypeTestMixin,
                    testlib_api.SqlTestCase):
    DRIVER_MODULE = type_vxlan
    DRIVER_CLASS = type_vxlan.TypeVxlan
    TYPE = p_const.TYPE_VXLAN

    def add_endpoint(self, ip=base_type_tunnel.TUNNEL_IP_ONE,
                     host=base_type_tunnel.HOST_ONE,
                     port=4789):
        return self.driver.add_endpoint(ip, host, port)

    def test_add_endpoint(self):
        endpoint = super(TestTypeVxlan, self).test_add_endpoint()
        self.assertEqual(4789, endpoint.udp_port)

    def test_get_endpoints(self):
        self.add_endpoint()
        self.add_endpoint(base_type_tunnel.TUNNEL_IP_TWO,
                          base_type_tunnel.HOST_TWO)

        endpoints = self.driver.get_endpoints()
        for endpoint in endpoints:
            if endpoint['ip_address'] == base_type_tunnel.TUNNEL_IP_ONE:
                self.assertEqual(4789, endpoint['udp_port'])
                self.assertEqual(base_type_tunnel.HOST_ONE, endpoint['host'])
            elif endpoint['ip_address'] == base_type_tunnel.TUNNEL_IP_TWO:
                self.assertEqual(4789, endpoint['udp_port'])
                self.assertEqual(base_type_tunnel.HOST_TWO, endpoint['host'])

    def test_db_get_endpoint_by_ip(self):
        self.add_endpoint()
        endpoint = self.driver.db_get_endpoint_by_ip(
            base_type_tunnel.TUNNEL_IP_ONE)
        self.assertEqual(4789, endpoint['udp_port'])
        self.assertEqual(base_type_tunnel.HOST_ONE, endpoint['host'])

    def test_db_delete_endpoint(self):
        self.add_endpoint()

        self.assertIsNone(self.driver.db_delete_endpoint(
            base_type_tunnel.TUNNEL_IP_ONE))
        # Get all the endpoints and verify its empty
        endpoints = self.driver.get_endpoints()
        self.assertNotIn(base_type_tunnel.TUNNEL_IP_ONE, endpoints)

    def test_db_get_endpoint_ip_by_host(self):
        self.add_endpoint()
        endpoint_ip = self.driver.db_get_endpoint_ip_by_host(
            base_type_tunnel.HOST_ONE)
        self.assertEqual(base_type_tunnel.TUNNEL_IP_ONE, endpoint_ip)
