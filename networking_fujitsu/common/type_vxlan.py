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

from neutron.db.models.plugins.ml2 import vxlanallocation as vxlan_model
from neutron.plugins.ml2.drivers import type_tunnel
from neutron_lib import constants


class TypeVxlan(type_tunnel.EndpointTunnelTypeDriver):
    def __init__(self):
        super(TypeVxlan, self).__init__(vxlan_model.VxlanAllocation,
                                        vxlan_model.VxlanEndpoints)

    def get_type(self):
        return constants.TYPE_VXLAN

    def initialize(self):
        pass

    def get_endpoints(self):
        """Get every vxlan endpoints from Neutron DB."""
        vxlan_endpoints = self._get_endpoints()
        return [{'ip_address': vxlan_endpoint.ip_address,
                 'udp_port': vxlan_endpoint.udp_port,
                 'host': vxlan_endpoint.host}
                for vxlan_endpoint in vxlan_endpoints]

    def add_endpoint(self, ip, host, udp_port):
        """Add switch endpoint information to Neutron DB."""
        return self._add_endpoint(ip, host, udp_port=udp_port)

    def db_get_endpoint_by_ip(self, ip):
        """Get vxlan endpoint with given IPaddress from DB."""
        vxlan_endpoint = self.get_endpoint_by_ip(ip)
        return {'ip_address': vxlan_endpoint.ip_address,
                'udp_port': vxlan_endpoint.udp_port,
                'host': vxlan_endpoint.host}

    def db_delete_endpoint(self, ip):
        """Delete switch endpoint information from DB."""
        self.delete_endpoint(ip)

    def db_get_endpoint_ip_by_host(self, host):
        """Get vxlan endpoint IP address with given host name from DB."""
        vxlan_endpoint = self.get_endpoint_by_host(host)
        return vxlan_endpoint.ip_address
