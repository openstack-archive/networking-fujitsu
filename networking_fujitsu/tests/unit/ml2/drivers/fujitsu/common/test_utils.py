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

from collections import defaultdict
import copy
import mock
from networking_fujitsu.ml2.drivers.fujitsu.common import utils as fj_util
from neutron.extensions import portbindings
from neutron.tests import base
#from neutron.tests.unit.db import test_db_base_plugin_v2 as test_plugin


class FujitsuCommonUtilsTestCase(base.BaseTestCase):
    """Base class to test Fujitsu Common Utils"""

    def setUp(self):
        super(FujitsuCommonUtilsTestCase, self).setUp()
        self.net = mock.MagicMock()

        self.net.network_segments = [{"network_type": "vlan",
                                      "segmentation_id": 100}]


class TestEliminateVal(FujitsuCommonUtilsTestCase):
    """Test class for eliminate_val"""

    def test_definition_is_None(self):
        definition = None
        target = [1]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual(None, result)

    def test_found_the_lowest(self):
        definition = "1,2,3"
        target = [1]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("2,3", result)

    def test_found_the_highest(self):
        definition = "1,2,3"
        target = [3]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("1,2", result)

    def test_found_range_of_low(self):
        definition = "1-10"
        target = [1]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("2-10", result)

    def test_found_range_of_highest_next_to_lowest(self):
        definition = "1-2"
        target = [2]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("1", result)

    def test_found_range_of_lowest_next_to_highest(self):
        definition = "1-2"
        target = [1]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("2", result)

    def test_found_range_of_high(self):
        definition = "1-10"
        target = [10]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("1-9", result)

    def test_found_between_ranges(self):
        definition = "1-10"
        target = [5]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("1-4,6-10", result)

    def test_found_between_ranges_next_to_the_lowest(self):
        definition = "1-10"
        target = [2]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("1,3-10", result)

    def test_found_between_ranges_next_to_the_highest(self):
        definition = "1-10"
        target = [9]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("10,1-8", result)

    def test_found_between_ranges_next_to_the_lowest_and_highest(self):
        definition = "1-3"
        target = [2]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("1,3", result)

    def test_matches_only_one(self):
        definition = "100"
        target = [100]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("", result)

    def test_no_matched(self):
        definition = "10,11"
        target = [100]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("10,11", result)

    def test_no_matched_with_boundary(self):
        definition = "1-10"
        target = [100]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("1-10", result)

    def test_specify_target_with_list_and_include_1(self):
        definition = "1-5"
        target = [1, 10]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("2-5", result)

    def test_specify_target_with_list_and_include_2(self):
        definition = "1-5"
        target = [1, 2]
        result = fj_util.eliminate_val(definition, target)
        self.assertEqual("3-5", result)


class TestGetNetworkSegments(FujitsuCommonUtilsTestCase):
    """Test class for get_network_segments and _validate_network"""

    def test_normal_case(self):
        network_type, vlan_id = fj_util.get_network_segments(self.net)
        self.assertEqual("vlan", network_type)
        self.assertEqual(100, vlan_id)

    def test_segmentation_id_is_nothing(self):
        self.net.network_segments[0]["segmentation_id"] = None
        network_type, vlan_id = fj_util.get_network_segments(self.net)
        self.assertEqual('vlan', network_type)
        self.assertEqual(None, vlan_id)

    def test_network_type_is_not_vlan(self):
        self.net.network_segments[0]["network_type"] = "vxlan"
        network_type, vlan_id = fj_util.get_network_segments(self.net)
        self.assertEqual('vxlan', network_type)
        self.assertEqual(100, vlan_id)


class TestGetPhysicalConnectivity(FujitsuCommonUtilsTestCase):
    """Test class for get_physical_connectivity"""

    def setUp(self):
        super(TestGetPhysicalConnectivity, self).setUp()
        # Mock
        self.port = defaultdict(lambda: {})
        self.port[portbindings.VNIC_TYPE] = portbindings.VNIC_BAREMETAL
        self.lli = [{"switch_id": "00:00:4c:ee:e5:39", "port_id": "1/1/0/1",
                     "switch_info": "CFX2000R"},
                    {"switch_id": "00:00:4c:ee:e5:40", "port_id": "1/1/0/2",
                     "switch_info": "CFX2000R"}]
        self.port['binding:profile']['local_link_information'] = self.lli

    def test_get_correct_data(self):
        self.port['binding:profile']['local_link_information'] = self.lli
        expect = self.lli
        local_link_info = fj_util.get_physical_connectivity(self.port)
        self.assertEqual(expect, local_link_info)

    def test_local_link_info_is_undefined(self):
        del self.port['binding:profile']['local_link_information']
        local_link_info = fj_util.get_physical_connectivity(self.port)
        self.assertEqual({}, local_link_info)

    def test_local_link_info_is_empty(self):
        self.port['binding:profile']['local_link_information'] = []
        local_link_info = fj_util.get_physical_connectivity(self.port)
        self.assertEqual({}, local_link_info)

    def test_some_key_in_local_link_info_is_missing(self):
        for missing in self.lli[1]:
            tmp = copy.copy(self.lli[1])
            del tmp[missing]
            self.port['binding:profile']['local_link_information'] = [tmp]
            local_link_info = fj_util.get_physical_connectivity(self.port)
            self.assertEqual({}, local_link_info)

    def test_some_value_in_local_link_info_is_missing(self):
        for missing in self.lli[0]:
            tmp = copy.copy(self.lli[0])
            tmp[missing] = ""
            self.port['binding:profile']['local_link_information'] = [tmp]
            local_link_info = fj_util.get_physical_connectivity(self.port)
            self.assertEqual({}, local_link_info)


class TestIsBaremetalDeploy(FujitsuCommonUtilsTestCase):
    """Test class for is_baremetal_deploy"""


class TestIsLag(FujitsuCommonUtilsTestCase):
    """Test class for is_lag"""
