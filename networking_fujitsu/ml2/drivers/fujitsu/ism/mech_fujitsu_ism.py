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

from networking_fujitsu.i18n import _LW
from networking_fujitsu.ml2.drivers.fujitsu.common import utils as fj_util
from neutron.plugins.common import constants as p_const
from neutron.plugins.ml2 import driver_api
from oslo_log import helpers as log_helpers
from oslo_log import log as logging


LOG = logging.getLogger(__name__)
ISM_DRIVER = 'networking_fujitsu.ml2.drivers.fujitsu.ism.ism_base'
_SUPPORTED_NET_TYPES = ['vlan']


class FujitsuIsmDriver(driver_api.MechanismDriver):
    """Ml2 Mechanism driver for Fujitsu ISM. """

    def __init__(self):
        self._driver = None
        self.initialize()

    def initialize(self):
        self._driver = ISM_DRIVER

    @classmethod
    def create_ism_base(self, network_type, segmentation_id):

        if (network_type == p_const.TYPE_VLAN):
            ism = self._driver.IsmVlanBase(network_type, segmentation_id)
            return ism
        elif (network_type == p_const.TYPE_VXLAN):
            ism = self._driver.IsmVxlanBase(network_type, segmentation_id)
            return ism

    @log_helpers.log_method_call
    def create_port_postcommit(self, context):
        """Call ISM API to set VLAN configuration."""

        port = context.current
        if not fj_util.is_baremetal(port):
            LOG.warning("This plugin is under developing and "
                        "not doing at all.")
            return

    @log_helpers.log_method_call
    def update_port_postcommit(self, context):
        """Call ISM API to set VLAN configuration."""

        port = context.current
        if not fj_util.is_baremetal(port):
            LOG.warning("This plugin is under developing and "
                        "not doing at all.")
            return

    @log_helpers.log_method_call
    def delete_port_postcommit(self, context):
        """Call ISM API to reset VLAN configuration."""

        port = context.current
        if not fj_util.is_baremetal(port):
            LOG.warning("This plugin is under developing and "
                        "not doing at all.")
            return

    def validate_network(network):
        """Validate network parameter(network_type and segmentation_id).

        @param a network object
        @return True if network_type is 'VLAN' and segmentation_id is included
                otherwise False
        """

        segment = network.network_segments[0]
        seg_id = segment[driver_api.SEGMENTATION_ID]
        net_type = segment[driver_api.NETWORK_TYPE]
        if (net_type in _SUPPORTED_NET_TYPES and seg_id):
            return True
        LOG.warning(_LW("Only network type vlan is supported."))
        return False
