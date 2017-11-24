# Copyright 2015-2017 FUJITSU LIMITED
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

from collections import defaultdict
import copy

import mock
from neutron.tests import base
from neutron_lib.api.definitions import portbindings

from networking_fujitsu.ml2.common import utils


class FujitsuCommonUtilsTestCase(base.BaseTestCase):
    """Base class to test Fujitsu Common Utils"""

    def setUp(self):
        super(FujitsuCommonUtilsTestCase, self).setUp()
        self.net = mock.MagicMock()

        self.net.network_segments = [{
            "provider:network_type": "vlan",
            "provider:physical_network": 'physnet1',
            "provider:segmentation_id": 100
        }]
        self.port = defaultdict(lambda: {})
        self.port[portbindings.VNIC_TYPE] = portbindings.VNIC_BAREMETAL
        self.lli = [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "1/1/0/1",
                     "switch_info": "CFX2000R"},
                    {"switch_id": "00:00:4c:ee:e5:40", "port_id": "1/1/0/2",
                     "switch_info": "CFX2000R"}]
        self.port['binding:profile']['local_link_information'] = self.lli
        self.ctx = mock.MagicMock()
        self.ctx.current = defaultdict(lambda: {})
        self.ctx.original = defaultdict(lambda: {})
        self.ctx.current[portbindings.VIF_TYPE] = portbindings.VIF_TYPE_UNBOUND
        self.ctx.original[portbindings.VIF_TYPE] = portbindings.VIF_TYPE_OTHER


class TestEliminateVal(FujitsuCommonUtilsTestCase):
    """Test class for eliminate_val"""

    def test_definition_is_None(self):
        definition = None
        target = [1]
        result = utils.eliminate_val(definition, target)
        self.assertIsNone(result)

    def test_found_the_lowest(self):
        definition = "1,2,3"
        target = [1]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("2,3", result)

    def test_found_the_highest(self):
        definition = "1,2,3"
        target = [3]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("1,2", result)

    def test_found_range_of_low(self):
        definition = "1-10"
        target = [1]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("2-10", result)

    def test_found_range_of_highest_next_to_lowest(self):
        definition = "1-2"
        target = [2]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("1", result)

    def test_found_range_of_lowest_next_to_highest(self):
        definition = "1-2"
        target = [1]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("2", result)

    def test_found_range_of_high(self):
        definition = "1-10"
        target = [10]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("1-9", result)

    def test_found_between_ranges(self):
        definition = "1-10"
        target = [5]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("1-4,6-10", result)

    def test_found_between_ranges_next_to_the_lowest(self):
        definition = "1-10"
        target = [2]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("1,3-10", result)

    def test_found_between_ranges_next_to_the_highest(self):
        definition = "1-10"
        target = [9]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("10,1-8", result)

    def test_found_between_ranges_next_to_the_lowest_and_highest(self):
        definition = "1-3"
        target = [2]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("1,3", result)

    def test_matches_only_one(self):
        definition = "100"
        target = [100]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("", result)

    def test_no_matched(self):
        definition = "10,11"
        target = [100]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("10,11", result)

    def test_no_matched_with_boundary(self):
        definition = "1-10"
        target = [100]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("1-10", result)

    def test_specify_target_with_list_and_include_1(self):
        definition = "1-5"
        target = [1, 10]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("2-5", result)

    def test_specify_target_with_list_and_include_2(self):
        definition = "1-5"
        target = [1, 2]
        result = utils.eliminate_val(definition, target)
        self.assertEqual("3-5", result)


class DummyNetwork(object):

    def __init__(self, segments):
        self.network_segments = segments


class TestGetNetworkSegments(FujitsuCommonUtilsTestCase):
    """Test class for following methods

       * get_network_type
       * get_segmentation_id
       * get_physical_network
    """

    def setUp(self):
        super(TestGetNetworkSegments, self).setUp()

        self.vlan_segments = [{
            "network_type": "vlan",
            "physical_network": 'physnet1',
            "segmentation_id": 100}]
        self.vxlan_segments = [{
            "network_type": "vxlan",
            "segmentation_id": 10000}]
        self.flat_segments = [{
            "network_type": "flat",
            "physical_network": 'flatnet'}]
        self.ctx_vlan = DummyNetwork(self.vlan_segments)
        self.ctx_vxlan = DummyNetwork(self.vxlan_segments)
        self.ctx_flat = DummyNetwork(self.flat_segments)
        self.attrs = ['NETWORK_TYPE', 'PHYSICAL_NETWORK', 'SEGMENTATION_ID']

    def test_get_from_network_dict(self):
        network = {
            "provider:network_type": "vlan",
            "provider:physical_network": 'physnet1',
            "provider:segmentation_id": 100
        }
        retvals = [
            utils._get_provider_attribute(network, attr) for attr in self.attrs
        ]
        self.assertEqual("vlan", retvals[0])
        self.assertEqual('physnet1', retvals[1])
        self.assertEqual(100, retvals[2])

    def test_get_from_network_dict_with_segments(self):
        net_dict = {
            "segments": [{
                "provider:network_type": "vlan",
                "provider:physical_network": 'physnet1',
                "provider:segmentation_id": 100
            }]
        }
        retvals = [
            utils._get_provider_attribute(
                net_dict, attr) for attr in self.attrs]
        self.assertEqual("vlan", retvals[0])
        self.assertEqual('physnet1', retvals[1])
        self.assertEqual(100, retvals[2])

    def test_get_from_network_context_with_segments(self):
        retvals = [
            utils._get_provider_attribute(
                self.ctx_vlan, attr) for attr in self.attrs]
        self.assertEqual("vlan", retvals[0])
        self.assertEqual('physnet1', retvals[1])
        self.assertEqual(100, retvals[2])

    def test_get_from_network_context_with_segments_provider(self):
        retvals = [
            utils._get_provider_attribute(
                self.ctx_vlan, attr) for attr in self.attrs]
        self.assertEqual("vlan", retvals[0])
        self.assertEqual('physnet1', retvals[1])
        self.assertEqual(100, retvals[2])

    def test_get_from_network_context_vxlan(self):
        self.assertEqual('vxlan', utils.get_network_type(self.ctx_vxlan))
        self.assertEqual(10000, utils.get_segmentation_id(self.ctx_vxlan))
        self.assertIsNone(utils.get_physical_network(self.ctx_vxlan))

    def test_get_from_network_context_flat(self):
        self.assertEqual('flat', utils.get_network_type(self.ctx_flat))
        self.assertEqual('flatnet', utils.get_physical_network(self.ctx_flat))
        self.assertIsNone(utils.get_segmentation_id(self.ctx_flat))

    def test_illegal_attrs_not_exist(self):
        net_dict = {}
        self.assertIsNone(utils.get_network_type(net_dict))
        self.assertIsNone(utils.get_physical_network(net_dict))
        self.assertIsNone(utils.get_segmentation_id(net_dict))

    def test_illegal_unable_to_load_attributes(self):
        for attr in [self.ctx_vlan, self.ctx_vxlan, self.ctx_flat]:
            self.assertRaises(
                AttributeError,
                utils._get_provider_attribute,
                attr,
                'non_exist_attribute')


class TestGetPhysicalConnectivity(FujitsuCommonUtilsTestCase):
    """Test class for get_physical_connectivity"""

    def test_get_correct_data(self):
        local_link_info = utils.get_physical_connectivity(self.port)
        self.assertEqual(self.lli, local_link_info)

    def test_local_link_info_is_undefined(self):
        del self.port['binding:profile']['local_link_information']
        local_link_info = utils.get_physical_connectivity(self.port)
        self.assertEqual([], local_link_info)

    def test_local_link_info_is_empty(self):
        self.port['binding:profile']['local_link_information'] = []
        local_link_info = utils.get_physical_connectivity(self.port)
        self.assertEqual([], local_link_info)

    def test_some_key_in_local_link_info_is_missing(self):
        for missing in self.lli[1]:
            tmp = copy.copy(self.lli[1])
            del tmp[missing]
            self.port['binding:profile']['local_link_information'] = [tmp]
            local_link_info = utils.get_physical_connectivity(self.port)
            self.assertEqual([], local_link_info)

    def test_some_value_in_local_link_info_is_missing(self):
        for missing in self.lli[0]:
            tmp = copy.copy(self.lli[0])
            tmp[missing] = ""
            self.port['binding:profile']['local_link_information'] = [tmp]
            local_link_info = utils.get_physical_connectivity(self.port)
            self.assertEqual([], local_link_info)


class TestIsBaremetalDeploy(FujitsuCommonUtilsTestCase):
    """Test class for is_baremetal_deploy"""

    def test_vnic_type_is_baremetal(self):
        self.assertTrue(utils.is_baremetal(self.port))

    def test_vnic_type_is_not_baremetal(self):
        self.port[portbindings.VNIC_TYPE] = portbindings.VNIC_NORMAL
        self.assertFalse(utils.is_baremetal(self.port))

        self.port[portbindings.VNIC_TYPE] = None
        self.assertFalse(utils.is_baremetal(self.port))

    def test_illegal_port_without_vnic_type(self):
        self.assertFalse(utils.is_baremetal({}))

    def test_illegal_argument_is_none(self):
        self.assertRaises(AttributeError, utils.is_baremetal, None)

    def test_illegal_argument_is_empty_list(self):
        self.assertRaises(AttributeError, utils.is_baremetal, [])


class TestIsLag(FujitsuCommonUtilsTestCase):
    """Test class for is_lag"""

    def test_lli_is_one(self):
        self.assertFalse(utils.is_lag([self.lli[0]]))

    def test_lli_is_more_than_2(self):
        self.assertTrue(utils.is_lag(self.lli))

    def test_lli_is_empty(self):
        self.assertFalse(utils.is_lag([]))


class TestIsUnbound(FujitsuCommonUtilsTestCase):
    """Test class for is_local_link_info_clear"""

    def test_is_unbound(self):
        self.assertTrue(utils.is_unbound(self.ctx))

    def test_is_not_unbound(self):
        self.ctx.current[portbindings.VIF_TYPE] = portbindings.VIF_TYPE_OTHER
        self.assertFalse(utils.is_unbound(self.ctx))


class TestHasLLI(FujitsuCommonUtilsTestCase):
    """Test class for has_lli"""

    def test_has_lli(self):
        self.assertTrue(utils.has_lli(self.port))

    def test_lli_not_exist(self):
        self.port['binding:profile'] = {}
        self.assertFalse(utils.has_lli(self.port))
