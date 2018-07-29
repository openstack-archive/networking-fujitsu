# Copyright 2017-2018 FUJITSU LIMITED
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

from neutron.plugins.ml2 import managers
from neutron.plugins.ml2 import rpc
from neutron_lib.agent import topics


class TunnelCaller(object):
    """Common tunnel calls for FOSSW agent."""
    def __init__(self):
        self._construct_rpc_stuff()

    def _construct_rpc_stuff(self):
        self.notifier = rpc.AgentNotifierApi(topics.AGENT)
        self.type_manager = managers.TypeManager()
        self.tunnel_rpc = rpc.RpcCallbacks(self.notifier, self.type_manager)

    def trigger_tunnel_sync(self, context, tunnel_ip):
        """Sends tunnel sync RPC message to the neutron L2 agent.

        :param context: A context of request.
        :type context: A Neutron context object.
        :param tunnel_ip: An endpoint IP address of vxlan.
        :type tunnel_ip: string
        :returns: None
        """

        tunnel_dict = {'tunnel_ip': tunnel_ip, 'tunnel_type': 'vxlan'}
        self.tunnel_rpc.tunnel_sync(context, **tunnel_dict)
