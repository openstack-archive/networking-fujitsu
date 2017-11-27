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
from neutron.conf.plugins.ml2 import config
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin
from oslo_config import cfg
from oslo_utils import importutils

from networking_fujitsu.ml2.fossw import fossw_vlandriver
from networking_fujitsu.ml2.fossw import mech_fossw
from networking_fujitsu.tests.unit.ml2.common import helper

ADDRESS = '192.168.100.1'
ADDRESS2 = '192.168.100.2'
USERNAME = 'fossw_user'
PASSWORD = 'fossw_password'


class TestFujitsuMechDriverV2(helper.FujitsuMechanismHelper):
    """Test Fujitsu mechanism driver.

    """

    _mechanism_drivers = ['fujitsu_fossw']
    _skip = ["test_create_router_port_and_fail_create_postcommit"]

    def setUp(self):
        config.cfg.CONF.set_override(
            'tenant_network_types', ['vlan', 'vxlan'], 'ml2')

        if self._testMethodName in self._skip:
            self.skipTest("This test has already verified at neutron's test.")

        def mocked_initialize(self):
            self.ips = [ADDRESS, ADDRESS2]
            self.username = USERNAME
            self.password = PASSWORD
            self._vlan_driver = mock.Mock()
            self._vxlan_driver = mock.Mock()
            self.switches_mac_ip_pair = {
                "00:00:4c:ee:e5:39": ADDRESS,
                "00:00:4c:ee:e5:40": ADDRESS2,
            }
        with mock.patch.object(mech_fossw.FOSSWMechanismDriver,
                               'initialize', new=mocked_initialize):
            self.mech = mech_fossw.FOSSWMechanismDriver()
            super(TestFujitsuMechDriverV2, self).setUp()


class TestFujitsuMechDriverPortsV2(test_ml2_plugin.TestMl2PortsV2):
    pass


class TestFOSSWInitialize(helper.FujitsuMechanismHelper):

    def setUp(self):
        super(TestFOSSWInitialize, self).setUp()
        config.cfg.CONF.set_override(
            'tenant_network_types', ['vlan', 'vxlan'], 'ml2')
        config.cfg.CONF.set_override(
            'username', 'admin', 'fujitsu_fossw')
        config.cfg.CONF.set_override(
            'password', 'password', 'fujitsu_fossw')
        config.cfg.CONF.set_override(
            'fossw_ips', [ADDRESS, ADDRESS2], 'fujitsu_fossw')
        importutils.import_object = mock.Mock()
        fossw_vlandriver.FOSSWVlanDriver().get_switch_mac_ip_pair = mock.Mock()

    def test_initialize_success(self):
        self.mech = mech_fossw.FOSSWMechanismDriver()
        self.assertEqual('admin', self.mech.username)
        self.assertEqual('password', self.mech.password)
        self.assertEqual('password', self.mech.password)
        self.assertEqual(
            mech_fossw.FOSSW_VLAN_DRIVER,
            importutils.import_object.call_args_list[0][0][0])
        self.assertEqual(
            config.cfg.CONF,
            importutils.import_object.call_args_list[0][0][1])
        self.assertEqual(
            mech_fossw.FOSSW_VXLAN_DRIVER,
            importutils.import_object.call_args_list[1][0][0])
        self.assertEqual(
            config.cfg.CONF,
            importutils.import_object.call_args_list[1][0][1])
        self.mech._vlan_driver.get_switch_mac_ip_pair.assert_called_once_with(
            [ADDRESS, ADDRESS2])

    def test_initialize_with_no_ips(self):
        config.cfg.CONF.set_override(
            'fossw_ips', [], 'fujitsu_fossw')
        self.assertRaises(
            cfg.RequiredOptError,
            mech_fossw.FOSSWMechanismDriver)


class TestFOSSWNetwork(TestFujitsuMechDriverV2):

    def setUp(self):
        super(TestFOSSWNetwork, self).setUp()

    def test_create_network(self):
        ctx = self.prepare_dummy_context('network')
        self.mech.create_network_postcommit(ctx)
        self.mech._vlan_driver.create_vlan.assert_called()
        self.mech._vxlan_driver.create_logical_switch.assert_not_called()
        self.assertEqual(2, self.mech._vlan_driver.create_vlan.call_count)

    def test_delete_network(self):
        ctx = self.prepare_dummy_context('network')
        self.mech.delete_network_postcommit(ctx)
        self.mech._vlan_driver.delete_vlan.assert_called()
        self.mech._vxlan_driver.delete_logical_switch.assert_not_called()
        self.assertEqual(2, self.mech._vlan_driver.delete_vlan.call_count)

    def test_create_network_raises_create_vlan(self):
        ctx = self.prepare_dummy_context('network')
        self.mech._vlan_driver.create_vlan.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.create_network_postcommit, ctx
        )

    def test_delete_network_raises_delete_vlan(self):
        ctx = self.prepare_dummy_context('network')
        self.mech._vlan_driver.delete_vlan.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.delete_network_postcommit, ctx
        )


class TestFOSSWBaremetalPortsVlan(TestFujitsuMechDriverV2):

    def setUp(self):
        super(TestFOSSWBaremetalPortsVlan, self).setUp()

    def test_create_port(self):
        ctx = self.prepare_dummy_context()
        self.mech.create_port_postcommit(ctx)
        self.mech._vxlan_driver.update_physical_port.assert_not_called()
        self.mech._vlan_driver.setup_vlan.assert_not_called()

    def test_bind_port_with_single(self):
        ctx = self.prepare_dummy_context()
        self.mech.bind_port(ctx)
        params = params_for_driver(ctx.current)
        self.mech._vlan_driver.setup_vlan.assert_called_once_with(
            params['segmentation_id'],
            params['local_link_info'],
            self.mech.switches_mac_ip_pair
        )

    def test_bind_port_with_single_raises_setup_vlan(self):
        ctx = self.prepare_dummy_context()
        self.mech._vlan_driver.setup_vlan.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.bind_port, ctx)

    def test_bind_port_with_lag(self):
        ctx = self.prepare_dummy_context(nic='lag')
        self.mech.bind_port(ctx)
        params = params_for_driver(ctx.current, lag=True)
        self.mech._vlan_driver.setup_lag.assert_called_once_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair,
            vlanid=params['segmentation_id'],
        )

    def test_bind_port_with_lag_raises_setup_lag(self):
        ctx = self.prepare_dummy_context(nic='lag')
        self.mech._vlan_driver.setup_lag.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.bind_port, ctx)

    def test_bind_port_with_mlag(self):
        ctx = self.prepare_dummy_context(nic='mlag')
        self.mech.bind_port(ctx)
        params = params_for_driver(ctx.current, lag=True)
        self.mech._vlan_driver.setup_lag.assert_called_once_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair,
            vlanid=params['segmentation_id'],
        )

    def test_bind_port_with_flat(self):
        ctx = self.prepare_dummy_context(net_type='flat')
        self.mech.bind_port(ctx)
        self.mech._vlan_driver.setup_vlan.assert_not_called()
        self.mech._vxlan_driver.update_physical_port.assert_not_called()

    def test_update_port(self):
        ctx = self.prepare_dummy_context(vif_type='other')
        self.mech.update_port_postcommit(ctx)
        self.mech._vlan_driver.clear_vlan.assert_not_called()

    def test_update_port_for_baremetal_with_unbound(self):
        ctx = self.prepare_dummy_context(vif_type='unbound', set_original=True)
        self.mech.update_port_postcommit(ctx)
        params = params_for_driver(ctx.original)
        self.mech._vlan_driver.clear_vlan.assert_called_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair
        )

    def test_update_port_for_baremetal_with_unbound_and_lag(self):
        ctx = self.prepare_dummy_context(
            vif_type='unbound', set_original=True, nic='lag')
        self.mech.update_port_postcommit(ctx)
        params = params_for_driver(ctx.original)

        self.mech._vlan_driver.clear_lag.assert_called_once_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair)

    def test_update_port_for_baremetal_with_unbound_flat(self):
        ctx = self.prepare_dummy_context(net_type='flat', vif_type='other',
                                         set_original=True)
        self.mech.update_port_postcommit(ctx)
        self.mech._vlan_driver.clear_vlan.assert_not_called()

    def test_update_port_with_bound_not_baremetal(self):
        ctx = self.prepare_dummy_context(vif_type='normal', vnic_type='ovs')
        self.mech.update_port_postcommit(ctx)
        self.mech._vlan_driver.associate_mac_to_network.assert_not_called()

    def test_delete_port_with_no_local_link_information(self):
        ctx = self.prepare_dummy_context(nic='single')
        ctx.current['binding:profile'] = {}
        self.mech.delete_port_postcommit(ctx)
        self.mech._vlan_driver.clear_vlan.assert_not_called()

    def test_delete_port_with_single(self):
        ctx = self.prepare_dummy_context(nic='single')
        self.mech.delete_port_postcommit(ctx)
        params = params_for_driver(ctx.current)
        self.mech._vlan_driver.clear_vlan.assert_called_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair
        )

    def test_delete_with_lag(self):
        ctx = self.prepare_dummy_context(nic='lag')
        self.mech.delete_port_postcommit(ctx)
        params = params_for_driver(ctx.current, lag=True)
        self.mech._vlan_driver.clear_lag.assert_called_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair
        )

    def test_delete_with_mlag(self):
        ctx = self.prepare_dummy_context(nic='mlag')
        self.mech.delete_port_postcommit(ctx)
        params = params_for_driver(ctx.current, lag=True)
        self.mech._vlan_driver.clear_lag.assert_called_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair
        )

    def test_delete_port_with_normal(self):
        ctx = self.prepare_dummy_context(vnic_type='normal')
        self.mech.delete_port_postcommit(ctx)
        self.mech._vlan_driver.clear_vlan.assert_not_called()

    def test_delete_port_raises_driver_clear_vlan(self):
        self.mech._vlan_driver.clear_vlan.side_effect = Exception
        ctx = self.prepare_dummy_context(nic='single')
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.delete_port_postcommit, ctx)
        self.mech._vxlan_driver.reset_physical_port.assert_not_called()

    def test_delete_with_lag_raises_clear_lag(self):
        self.mech._vlan_driver.clear_lag.side_effect = Exception
        ctx = self.prepare_dummy_context(nic='lag')
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.delete_port_postcommit, ctx)
        self.mech._vxlan_driver.reset_physical_port.assert_not_called()


def params_for_driver(port, lag=False):
    return {
        'local_link_info': port['binding:profile']['local_link_information'],
        'segmentation_id': 1111,
        'mac': port['mac_address'],
        'lag': lag
    }


class TestFOSSWIsSupported(TestFujitsuMechDriverV2):
    def setUp(self):
        super(TestFOSSWIsSupported, self).setUp()

    def test_is_supported_not_support_type(self):
        ctx = self.prepare_dummy_context('network', net_type='flat')
        network = ctx.current
        self.assertFalse(mech_fossw.is_supported(network))

    def test_is_supported_illegal_seg_id_is_none(self):
        ctx = self.prepare_dummy_context('network', net_type='vlan')
        network = ctx.current
        ctx.current['provider:segmentation_id'] = None
        self.assertFalse(mech_fossw.is_supported(network))

    def test_is_supported_illegal_seg_id_is_not_defined(self):
        ctx = self.prepare_dummy_context('network', net_type='vlan')
        network = ctx.current
        del network['provider:segmentation_id']
        self.assertFalse(mech_fossw.is_supported(network))


class TestFOSSWBaremetalPortsVxlan(TestFujitsuMechDriverV2):

    def setUp(self):
        super(TestFOSSWBaremetalPortsVxlan, self).setUp()

    def test_is_supported_not_support_type(self):
        ctx = self.prepare_dummy_context('network', net_type='flat')
        network = ctx.current
        self.assertFalse(mech_fossw.is_supported(network))

    def test_is_supported_illegal_seg_id_is_none(self):
        ctx = self.prepare_dummy_context('network', net_type='flat')
        network = ctx.current
        ctx.current['provider:segmentation_id'] = None
        self.assertFalse(mech_fossw.is_supported(network))

    def test_is_supported_illegal_seg_id_is_not_defined(self):
        ctx = self.prepare_dummy_context('network', net_type='flat')
        network = ctx.current
        self.assertFalse(mech_fossw.is_supported(network))

    def test_create_network(self):
        ctx = self.prepare_dummy_context('network', net_type='vxlan')
        self.mech.create_network_postcommit(ctx)
        self.mech._vlan_driver.create_vlan.assert_not_called()
        net_id = ctx.current['id']
        vni = ctx.current['provider:segmentation_id']
        self.mech._vxlan_driver.create_logical_switch.assert_called_with(
            net_id, vni)

    def test_delete_network(self):
        ctx = self.prepare_dummy_context('network', net_type='vxlan')
        self.mech.delete_network_postcommit(ctx)
        net_id = ctx.current['id']
        self.mech._vlan_driver.delete_vlan.assert_not_called()
        self.mech._vxlan_driver.delete_logical_switch.assert_called_with(
            net_id)

    def test_create_network_raises_create_logical_switch(self):
        ctx = self.prepare_dummy_context('network', net_type='vxlan')
        self.mech._vxlan_driver.create_logical_switch.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.create_network_postcommit, ctx
        )

    def test_delete_network_raises_delete_logical_switch(self):
        ctx = self.prepare_dummy_context('network', net_type='vxlan')
        self.mech._vxlan_driver.delete_logical_switch.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.delete_network_postcommit, ctx
        )

    def test_create_port(self):
        ctx = self.prepare_dummy_context(net_type='vxlan')
        self.mech.create_port_postcommit(ctx)
        self.mech._vlan_driver.setup_vlan.assert_not_called()
        self.mech._vxlan_driver.update_physical_port.assert_not_called()

    def test_bind_port_with_single(self):
        ctx = self.prepare_dummy_context(net_type='vxlan')
        self.mech.bind_port(ctx)
        params = params_for_driver(ctx.current)
        self.mech._vxlan_driver.update_physical_port.assert_called_once_with(
            params['segmentation_id'],
            params['local_link_info'],
            ctx.current,
            self.mech.switches_mac_ip_pair,
            ctx.network._plugin_context.request_id
        )

    def test_bind_port_with_lag(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', nic='lag')
        self.mech._vlan_driver.setup_lag.return_value = {}
        params = params_for_driver(ctx.current, lag=True)

        self.mech.bind_port(ctx)
        self.mech._vlan_driver.setup_lag.assert_called_once_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair)
        target = self.mech._vxlan_driver.update_physical_port_with_lag
        target.assert_called_once_with(
            params['segmentation_id'],
            params['local_link_info'],
            ctx.current,
            self.mech.switches_mac_ip_pair,
            ctx.network._plugin_context.request_id,
            mac_lag_map={})

    def test_bind_port_with_mlag(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', nic='mlag')
        self.mech._vlan_driver.setup_lag.return_value = {}
        params = params_for_driver(ctx.current, lag=True)

        self.mech.bind_port(ctx)
        self.mech._vlan_driver.setup_lag.assert_called_once_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair)
        target = self.mech._vxlan_driver.update_physical_port_with_lag
        target.assert_called_once_with(
            params['segmentation_id'],
            params['local_link_info'],
            ctx.current,
            self.mech.switches_mac_ip_pair,
            ctx.network._plugin_context.request_id,
            mac_lag_map={})

    def test_bind_port_with_lag_raises_driver_method(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', nic='lag')
        self.mech._vxlan_driver.update_physical_port_with_lag.side_effect = \
            Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.bind_port, ctx)

    def test_update_port(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', vif_type='other')
        self.mech.update_port_postcommit(ctx)
        self.mech._vxlan_driver.reset_physical_port.assert_not_called()

    def test_update_port_with_flat(self):
        ctx = self.prepare_dummy_context(net_type='flat', vif_type='other')
        self.mech.update_port_postcommit(ctx)
        self.mech._vxlan_driver.update_physical_port.assert_not_called()

    def test_update_port_with_bound(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', vif_type='normal')
        self.mech.update_port_postcommit(ctx)
        self.mech._vxlan_driver.update_physical_port.assert_not_called()

    def test_update_port_for_baremetal_with_unbound(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', vif_type='unbound',
                                         set_original=True)
        self.mech.update_port_postcommit(ctx)
        params = params_for_driver(ctx.original)
        self.mech._vxlan_driver.reset_physical_port.assert_called_with(
            params['local_link_info'],
            ctx.original,
            self.mech.switches_mac_ip_pair
        )

    def test_update_port_for_baremetal_with_unbound_and_lag(self):
        ctx = self.prepare_dummy_context(
            net_type='vxlan', vif_type='unbound', set_original=True, nic='lag')
        self.mech._vlan_driver.clear_lag.return_value = {}
        params = params_for_driver(ctx.original)

        self.mech.update_port_postcommit(ctx)

        self.mech._vlan_driver.clear_lag.assert_called_once_with(
            params['local_link_info'],
            self.mech.switches_mac_ip_pair)
        target = self.mech._vxlan_driver.reset_physical_port_with_lag
        target.assert_called_with(
            params['local_link_info'],
            ctx.original,
            self.mech.switches_mac_ip_pair, mac_lag_map={})

    def test_update_port_for_baremetal_with_unbound_flat(self):
        ctx = self.prepare_dummy_context(net_type='flat', vif_type='other',
                                         set_original=True)
        self.mech.clear_vxlan = mock.Mock()
        self.mech.update_port_postcommit(ctx)
        self.mech.clear_vxlan.assert_not_called()

    def test_update_port_with_bound_not_baremetal(self):
        ctx = self.prepare_dummy_context(
            net_type='vxlan', vif_type='normal', vnic_type='ovs')
        self.mech.update_port_postcommit(ctx)
        params = params_for_driver(ctx.current)
        self.mech._vxlan_driver.update_physical_port.assert_called_with(
            params['segmentation_id'],
            [],
            ctx.current,
            self.mech.switches_mac_ip_pair
        )

    def test_update_port_raises_update_physical_port(self):
        ctx = self.prepare_dummy_context(
            net_type='vxlan', vif_type='normal', vnic_type='ovs')
        self.mech._vxlan_driver.update_physical_port.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.update_port_postcommit, ctx)

    def test_delete_port(self):
        ctx = self.prepare_dummy_context(net_type='vxlan')
        self.mech.delete_port_postcommit(ctx)
        self.mech._vxlan_driver.reset_physical_port.assert_not_called()

    def test_delete_port_with_no_local_link_information(self):
        ctx = self.prepare_dummy_context(net_type='vxlan')
        ctx.current['binding:profile'] = {}
        self.mech.delete_port_postcommit(ctx)
        self.mech._vxlan_driver.reset_physical_port.assert_not_called()

    def test_delete_port_with_bound(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', vif_type='normal')
        self.mech.delete_port_postcommit(ctx)
        params = params_for_driver(ctx.current)
        self.mech._vxlan_driver.reset_physical_port.assert_called_with(
            params['local_link_info'],
            ctx.current,
            self.mech.switches_mac_ip_pair
        )

    def test_delete_port_raises_reset_physical_port(self):
        ctx = self.prepare_dummy_context(net_type='vxlan', vif_type='normal')
        self.mech._vxlan_driver.reset_physical_port.side_effect = Exception
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.delete_port_postcommit, ctx)

    def test_delete_port_with_lag_raises_reset_physical_port_with_lag(self):
        ctx = self.prepare_dummy_context(
            net_type='vxlan', vif_type='normal', nic='lag')
        self.mech._vlan_driver.clear_lag.side_effect = [
            Exception, None]
        self.mech._vxlan_driver.reset_physical_port_with_lag.side_effect = [
            Exception, Exception]
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.delete_port_postcommit, ctx)
        self.assertRaises(
            ml2_exc.MechanismDriverError,
            self.mech.delete_port_postcommit, ctx)

    def test_delete_port_with_flat(self):
        ctx = self.prepare_dummy_context(net_type='flat')
        self.mech.delete_port_postcommit(ctx)
        self.mech._vxlan_driver.reset_physical_port.assert_not_called()

    def test_delete_with_lag(self):
        ctx = self.prepare_dummy_context(
            net_type='vxlan', vif_type='normal', nic='lag')
        self.mech._vlan_driver.clear_lag.return_value = {}
        self.mech.delete_port_postcommit(ctx)
        params = params_for_driver(ctx.current)
        target = self.mech._vxlan_driver.reset_physical_port_with_lag
        target.assert_called_with(
            params['local_link_info'],
            ctx.current,
            self.mech.switches_mac_ip_pair,
            mac_lag_map={})

    def test_delete_with_mlag(self):
        ctx = self.prepare_dummy_context(
            net_type='vxlan', vif_type='normal', nic='mlag')
        self.mech._vlan_driver.clear_lag.return_value = {}
        self.mech.delete_port_postcommit(ctx)
        params = params_for_driver(ctx.current)
        target = self.mech._vxlan_driver.reset_physical_port_with_lag
        target.assert_called_with(
            params['local_link_info'],
            ctx.current, self.mech.switches_mac_ip_pair, mac_lag_map={})
