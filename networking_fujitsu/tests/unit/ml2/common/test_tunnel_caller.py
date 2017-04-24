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

from neutron.plugins.ml2.drivers import type_tunnel
from neutron.plugins.ml2 import managers
from neutron.plugins.ml2 import rpc
from neutron.tests import base

from networking_fujitsu.ml2.common import tunnel_caller


class TestTunnelCaller(base.BaseTestCase):

    def setUp(self):
        super(TestTunnelCaller, self).setUp()
        mock.patch.object(managers, 'TypeManager').start()
        self.tunnel_caller = tunnel_caller.TunnelCaller()
        self.context = mock.MagicMock()

    def test_trigger_tunnel_sync(self):
        with mock.patch.object(rpc, 'RpcCallbacks'), \
                mock.patch.object(type_tunnel.TunnelRpcCallbackMixin,
                                  'tunnel_sync') as mock_tunnel_sync:
            self.tunnel_caller.trigger_tunnel_sync(self.context, 'fake_ip')
            mock_tunnel_sync.assert_called_with(
                self.context, tunnel_ip='fake_ip', tunnel_type='vxlan')
