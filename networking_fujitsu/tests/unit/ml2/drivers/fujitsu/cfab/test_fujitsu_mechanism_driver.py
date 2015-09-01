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
import os

import mock

try:
    from oslo_log import log as logging
except ImportError:
    from neutron.openstack.common import log as logging

from networking_fujitsu.ml2.drivers.fujitsu.cfab\
    import (mechanism_fujitsu as fujitsumechanism)
from networking_fujitsu.ml2.drivers.fujitsu.cfab import cfabdriver
from neutron.plugins.ml2 import config as ml2_config
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin

LOG = logging.getLogger(__name__)


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

    def setUp(self):

        ml2_config.cfg.CONF.set_override(
            'tenant_network_types', ['vlan'], 'ml2')

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

            with mock.patch.object(fujitsumechanism.FujitsuMechanism,
                                   'initialize', new=mocked_initialize):
                super(TestFujitsuMechDriverV2, self).setUp()


class TestFujitsuMechDriverNetworksV2(test_ml2_plugin.TestMl2NetworksV2,
                                      TestFujitsuMechDriverV2):
    pass


class TestFujitsuMechDriverPortsV2(test_ml2_plugin.TestMl2PortsV2,
                                   TestFujitsuMechDriverV2):
    pass
