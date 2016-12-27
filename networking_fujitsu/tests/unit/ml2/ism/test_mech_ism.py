# -*- coding: utf-8 -*-

# Copyright 2015-2016 FUJITSU LIMITED
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
test_networking_fujitsu
----------------------------------

Tests for `networking_fujitsu` module.
"""
from networking_fujitsu.ml2.ism import mech_ism
from neutron.tests.unit.plugins.ml2 import test_plugin as test_ml2_plugin


class FujitsuIsmDriverTestCase(test_ml2_plugin.Ml2PluginV2TestCase):

    _mechanism_drivers = ['fujitsu_ism']
    # test_create_router_port_and_fail_create_postcommit:
    #     This one is mocked 'fake_driver' only. So, our plugin's instance
    #     hasn't mocked and fail definitely. Therefore, skips this test.
    _skip = ["test_create_router_port_and_fail_create_postcommit"]

    def setUp(self):

        if self._testMethodName in self._skip:
            self.skipTest("This test has already verified at neutron's test.")
        self._driver = mech_ism.ISMMechanismDriver()
        super(FujitsuIsmDriverTestCase, self).setUp()

    def tearDown(self):
        super(FujitsuIsmDriverTestCase, self).tearDown()


class TestFujitsuMechDriverPortsV2(test_ml2_plugin.TestMl2PortsV2,
                                   FujitsuIsmDriverTestCase):
    pass
