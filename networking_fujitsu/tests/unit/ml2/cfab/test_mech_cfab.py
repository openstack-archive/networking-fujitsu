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

import mock
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.plugins.ml2 import config as ml2_config
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin

from networking_fujitsu.ml2.cfab import cfabdriver
from networking_fujitsu.ml2.cfab import mech_cfab
from networking_fujitsu.tests.unit.ml2.common import helper

USERNAME = 'admin'
PASSWORD = 'admin'
ADDRESS = '192.168.100.1'
PHYSICAL_NET = ["physnet1:1"]


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
        ml2_config.cfg.CONF.set_override(
            'type_drivers', ['vlan'], 'ml2')

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

            with mock.patch.object(mech_cfab.CFABMechanismDriver,
                                   'initialize', new=mocked_initialize):
                super(TestFujitsuMechDriverV2, self).setUp()


class TestFujitsuMechDriverPortsV2(test_ml2_plugin.TestMl2PortsV2,
                                   TestFujitsuMechDriverV2):
    pass


class TestMechCFABIsSupported(helper.FujitsuMechanismHelper):

    def test_is_supported_type_vlan(self):
        ctx = self.prepare_dummy_context('network')
        network = ctx.current
        self.assertTrue(mech_cfab.is_supported(network))

    def test_is_supported_not_support_type_flat(self):
        ctx = self.prepare_dummy_context('network', net_type='flat')
        network = ctx.current
        self.assertFalse(mech_cfab.is_supported(network))

    def test_is_supported_not_support_type_vxlan(self):
        ctx = self.prepare_dummy_context('network', net_type='vxlan')
        network = ctx.current
        self.assertFalse(mech_cfab.is_supported(network))

    def test_is_supported_illegal_seg_id_is_none(self):
        ctx = self.prepare_dummy_context('network', net_type='vlan')
        network = ctx.current
        ctx.current['provider:segmentation_id'] = None
        self.assertFalse(mech_cfab.is_supported(network))

    def test_is_supported_illegal_seg_id_is_not_defined(self):
        ctx = self.prepare_dummy_context('network', net_type='vlan')
        network = ctx.current
        del network['provider:segmentation_id']
        self.assertFalse(mech_cfab.is_supported(network))


class TestFujitsuMechDriverBaremetalPortsV2(helper.FujitsuMechanismHelper):

    def setUp(self):
        ml2_fujitsu_opts = {
            'username': USERNAME,
            'password': PASSWORD,
            'address': ADDRESS,
            'physical_networks': PHYSICAL_NET,
            'pprofile_prefix': 'test-'
        }
        for opt, val in ml2_fujitsu_opts.items():
            ml2_config.cfg.CONF.set_override(opt, val, "fujitsu_cfab")
        self.mech = mech_cfab.CFABMechanismDriver()
        self.mech._driver = mock.Mock()
        super(TestFujitsuMechDriverBaremetalPortsV2, self).setUp()

    def test_create_port(self):
        ctx = self.prepare_dummy_context()
        self.mech.create_port_postcommit(ctx)
        self.mech._driver.associate_mac_to_network.assert_not_called()

    def test_bind_port_with_single(self):
        ctx = self.prepare_dummy_context()
        self.mech.bind_port(ctx)
        params = params_for_setup_vlan(ctx.current)
        self.mech._driver.setup_vlan.assert_called_once_with(
            params['address'],
            params['username'],
            params['password'],
            params['vfab_id'],
            params['vlanid'],
            params['ports'],
            params['mac_address'],
        )

    def test_bind_port_with_lag(self):
        ctx = self.prepare_dummy_context(nic='lag')
        self.mech.bind_port(ctx)
        params = params_for_setup_vlan(ctx.current, lag=True)
        self.mech._driver.setup_vlan_with_lag.assert_called_once_with(
            params['address'],
            params['username'],
            params['password'],
            params['vfab_id'],
            params['vlanid'],
            params['ports'],
            params['mac_address'],
        )

    def test_bind_port_with_mlag(self):
        ctx = self.prepare_dummy_context(nic='mlag')
        self.mech.bind_port(ctx)
        params = params_for_setup_vlan(ctx.current, lag=True)
        self.mech._driver.setup_vlan_with_lag.assert_called_once_with(
            params['address'],
            params['username'],
            params['password'],
            params['vfab_id'],
            params['vlanid'],
            params['ports'],
            params['mac_address'],
        )

    def test_update_port(self):
        ctx = self.prepare_dummy_context(set_original=True)
        ctx.current['binding:vif_type'] = 'other'
        self.mech.update_port_postcommit(ctx)
        self.mech._driver.associate_mac_to_network.assert_not_called()
        self.mech._driver.clear_vlan.assert_not_called()

    def test_update_port_with_unbound(self):
        ctx = self.prepare_dummy_context(set_original=True)
        params = params_for_setup_vlan(ctx.original)
        self.mech.update_port_postcommit(ctx)
        self.mech._driver.associate_mac_to_network.assert_not_called()
        self.mech._driver.clear_vlan.assert_called_with(
            params['address'],
            params['username'],
            params['password'],
            params['vfab_id'],
            params['vlanid'],
            params['ports'],
            params['mac_address'],
        )

    def test_update_port_network_type_is_not_vlan(self):
        ctx = self.prepare_dummy_context(set_original=True, net_type='vxlan')
        self.mech.update_port_postcommit(ctx)
        self.mech._driver.associate_mac_to_network.assert_not_called()
        self.mech._driver.clear_vlan.assert_not_called()

    def test_update_port_and_raises_in_clear_vlan(self):
        ctx = self.prepare_dummy_context(set_original=True)

        self.mech._driver.clear_vlan.side_effect = Exception
        self.assertRaises(ml2_exc.MechanismDriverError,
                          self.mech.update_port_postcommit, ctx)

    def test_delete_port_with_single(self):
        ctx = self.prepare_dummy_context(nic='single')
        self.mech.delete_port_postcommit(ctx)
        params = params_for_setup_vlan(ctx.current)
        self.mech._driver.clear_vlan.assert_called_with(
            params['address'],
            params['username'],
            params['password'],
            params['vfab_id'],
            params['vlanid'],
            params['ports'],
            params['mac_address'],
        )
        self.mech._driver.dissociate_mac_from_network.assert_not_called()

    def test_delete_with_lag(self):
        ctx = self.prepare_dummy_context(nic='lag')
        self.mech.delete_port_postcommit(ctx)
        params = params_for_setup_vlan(ctx.current, lag=True)
        self.mech._driver.clear_vlan_with_lag.assert_called_with(
            params['address'],
            params['username'],
            params['password'],
            params['vfab_id'],
            params['vlanid'],
            params['ports'],
            params['mac_address'],
        )
        self.mech._driver.dissociate_mac_from_network.assert_not_called()

    def test_delete_with_mlag(self):
        ctx = self.prepare_dummy_context(nic='mlag')
        self.mech.delete_port_postcommit(ctx)
        params = params_for_setup_vlan(ctx.current, lag=True)
        self.mech._driver.clear_vlan_with_lag.assert_called_with(
            params['address'],
            params['username'],
            params['password'],
            params['vfab_id'],
            params['vlanid'],
            params['ports'],
            params['mac_address'],
        )
        self.mech._driver.dissociate_mac_from_network.assert_not_called()


def params_for_setup_vlan(port, lag=False):
    lli = port['binding:profile']['local_link_information']
    return {
        'address': ADDRESS,
        'username': USERNAME,
        'password': PASSWORD,
        'vfab_id': '1',
        'vlanid': 1111,
        'ports': ','.join(p['port_id'] for p in lli),
        'mac_address': port['mac_address'],
        'lag': lag
    }
