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
from neutron.extensions import portbindings
from neutron.i18n import _LE
from neutron.i18n import _LI
from neutron.plugins.common import constants as p_const
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.plugins.ml2 import driver_api
from oslo_log import helpers as log_helpers
from oslo_log import log as logging


LOG = logging.getLogger(__name__)
ISM_DRIVER = 'networking_fujitsu.ml2.drivers.fujitsu.ism.ism_base'


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

    def get_network_info(self, context, net_id):
        segments = context.network.network_segments
        segment = segments[0]
        network_type = segment[driver_api.NETWORK_TYPE]
        segmentation_id = segment[driver_api.SEGMENTATION_ID]
        LOG.info(_LI("network_type = %s") % network_type)
        LOG.info(_LI("segmentation_id = %s") % segmentation_id)
        return network_type, segmentation_id

    def get_physical_connectivity(self, port):
        # TODO(yushiro) replace following characters to constant value
        binding_profile = port.get("binding:profile", None)
        if not binding_profile:
            return None

        local_link_info = binding_profile.get("local_link_information", [])
        if (local_link_info == [] or local_link_info is None
           or local_link_info == {}):
            return None
        return local_link_info

    def validate_vnic_type(self, port):
        vnic_type = port.get(portbindings.VNIC_TYPE, portbindings.VNIC_NORMAL)
        if (vnic_type != portbindings.VNIC_BAREMETAL):
            LOG.warn("This plugin is doing nothing before ironic-neutron\
                      integration will be merged.")
            return False
        return True

    @log_helpers.log_method_call
    def create_port_postcommit(self, context):
        """Call ISM API to set VLAN configuration."""
        port = context.current
        if not self.validate_vnic_type(port):
            return

        net_type, seg_id = self.get_network_info(context, port['network_id'])
        phy_connections = self.get_physical_connectivity(port)

        # TODO(yushiro) Call LAG setup function of ISM

        for phy_con in phy_connections:
            try:
                ism = FujitsuIsmDriver.create_ism_base(net_type, seg_id)
                current = ism.get_current_config(phy_con)
                req_param = ism.generate_req_param_for_port(current)
                ism.setup_for_port(req_param, phy_con)
            except Exception as er:
                LOG.exception(
                    _LE("failed to setup %(net_type)s. detail=%(er)s"),
                    {'net_type': net_type, 'er': er})
                raise ml2_exc.MechanismDriverError(method="%s" % __name__)
        return

    @log_helpers.log_method_call
    def update_port_postcommit(self, context):
        """Call ISM API to set VLAN configuration."""
        port = context.current
        if not self.validate_vnic_type(port):
            return

        net_type, seg_id = self.get_network_info(context, port['network_id'])
        phy_connections = self.get_physical_connectivity(port)

        for phy_con in phy_connections:
            try:
                ism = FujitsuIsmDriver.create_ism_base(net_type, seg_id)
                current = ism.get_current_config(phy_con)
                req_param = ism.generate_req_param_for_port(current)
                ism.setup_for_port(req_param, phy_con)
            except Exception as er:
                LOG.exception(
                    _LE("failed to setup %(net_type)s. detail=%(er)s"),
                    {'net_type': net_type, 'er': er})
                raise ml2_exc.MechanismDriverError(method="%s" % __name__)
        return

    @log_helpers.log_method_call
    def delete_port_postcommit(self, context):
        """Call ISM API to reset VLAN configuration."""
        port = context.current
        if not self.validate_vnic_type:
            return
        net_type, seg_id = self.get_network_info(context, port['network_id'])
        phy_connections = self.get_physical_connectivity(port)

        # TODO(yushiro) Call LAG un-setup function of ISM

        for phy_con in phy_connections:
            # TODO(yushiro): Consider try position
            try:
                ism = self.create_ism_base(net_type, '')
                current = ism.get_current_config(phy_con)
                req_param = ism.generate_req_param_for_port(current)
                ism.setup_for_port(req_param, phy_con)
            except Exception as er:
                LOG.exception(
                    _LE("failed to setup %(net_type)s. detail=%(er)s"),
                    {'net_type': net_type, 'er': er})
                raise ml2_exc.MechanismDriverError(method="%s" % __name__)
