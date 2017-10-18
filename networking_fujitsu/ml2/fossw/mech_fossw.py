# Copyright 2017 FUJITSU LIMITED
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
#

from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron_lib.api.definitions import portbindings as pb_def
from neutron_lib import constants as nl_const
from neutron_lib.plugins.ml2 import api
from oslo_config import cfg
from oslo_log import helpers as log_helpers
from oslo_log import log as logging
from oslo_utils import importutils

from networking_fujitsu._i18n import _
from networking_fujitsu.ml2.common import utils

LOG = logging.getLogger(__name__)
DRIVER = 'networking_fujitsu.ml2.'
FOSSW_VLAN_DRIVER = DRIVER + 'fossw.fossw_vlandriver.FOSSWVlanDriver'
FOSSW_VXLAN_DRIVER = DRIVER + 'fossw.fossw_vxlandriver.FOSSWVxlanDriver'
DEFAULT_VLAN = 1

_SUPPORTED_NET_TYPES = [nl_const.TYPE_VLAN, nl_const.TYPE_VXLAN]

ML2_FUJITSU_GROUP = "fujitsu_fossw"
ML2_FUJITSU = [
    cfg.ListOpt(
        'fossw_ips', default='[]',
        help=_("List of IP addresses of all FOS switches.")),
    cfg.StrOpt(
        'username', default='',
        help=_("Username of FOS switches.")),
    cfg.StrOpt(
        'password', default='',
        help=_("Password of FOS switches.")),
    cfg.IntOpt(
        'port', default=22,
        help=_("The port number which is used for SSH connection.")),
    cfg.IntOpt(
        'timeout', default=30,
        help=_("The timeout of SSH connection.")),
    cfg.IntOpt(
        'udp_dest_port', default=4789,
        help=_("The port number of VXLAN UDP destionation on the FOS "
               "switch. All VXLANs on the switches use this UDP port as the "
               "UDP destination port in the UDP header when encapsulating.")),
    cfg.IntOpt(
        'ovsdb_vlanid_range_min', default=2,
        help=_("The minimum VLAN ID in the range that is used for binding "
               "VNI and physical port. The range of 78 VLAN IDs (starts from "
               "this value) will be reserved. Default is 2 (VLAN ID from 2 "
               "to 79 will be reserved).")),
    cfg.IntOpt(
        'ovsdb_port', default=6640,
        help=_("The port number which OVSDB server on the FOS switches "
               "lisetn."))]

cfg.CONF.register_opts(ML2_FUJITSU, ML2_FUJITSU_GROUP)


class FOSSWMechanismDriver(api.MechanismDriver):
    """ML2 Mechanism driver for Fujitsu FOS switches.

    This is the upper layer driver class that interfaces to lower layer (CLI)
    below.
    """

    def __init__(self):
        self._vlan_driver = None
        self._vxlan_driver = None
        self.switches_mac_ip_pair = None
        self.ips = None
        self.initialize()

    def initialize(self):
        """Initialize of variables needed by this class."""

        self.ips = cfg.CONF.fujitsu_fossw.fossw_ips
        LOG.debug("loaded switch IP is: %s", self.ips)
        if len(self.ips) == 0:
            raise cfg.RequiredOptError(
                'fossw_ips', cfg.OptGroup(ML2_FUJITSU_GROUP))
        self.username = cfg.CONF.fujitsu_fossw.username
        self.password = cfg.CONF.fujitsu_fossw.password
        self._vlan_driver = importutils.import_object(
            FOSSW_VLAN_DRIVER, cfg.CONF)
        self._vxlan_driver = importutils.import_object(
            FOSSW_VXLAN_DRIVER, cfg.CONF)
        self.switches_mac_ip_pair = self._vlan_driver.get_switch_mac_ip_pair(
            self.ips)
        LOG.debug("Registered FOS switch's IP and MAC pairs: %s",
                  self.switches_mac_ip_pair)

    @log_helpers.log_method_call
    def create_network_postcommit(self, net_context):
        """Calls setup process for FOS switch.

        Case1: Create VLAN network
                   Create VLAN with specified VLAN ID.
        Case2: Create VXLAN network
                   Create DCVPN with specified VNI.
        Case3: Otherwise
                   Do nothing.

        :param mech_context: context of network
        :type mech_context: NetworkContext

        :returns: None
        :rtype: None

        """

        network = net_context.current
        network_id = network['id']
        tenant_id = network['tenant_id']
        network_type = utils.get_network_type(network)
        seg_id = utils.get_segmentation_id(network)

        if network_type == nl_const.TYPE_VLAN and seg_id:
            self.create_network_postcommit_vlan(seg_id)
        elif network_type == nl_const.TYPE_VXLAN and seg_id:
            self.create_network_postcommit_vxlan(network_id, seg_id)

        LOG.info(
            "created network (postcommit): network_id=%(network_id)s "
            "tenant_id=%(tenant_id)s",
            {'network_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def create_network_postcommit_vlan(self, vlanid):
        """Create VLAN to FOS switch.

        :param vlanid: the ID of VLAN to be created
        :type vlanid: string

        :returns: None
        :rtype: None

        """
        method = 'create_network_postcommit'
        for ip in self.ips:
            try:
                self._vlan_driver.create_vlan(ip, vlanid)
            except Exception:
                LOG.exception("Failed to create vlan(%(vid)s) on switch"
                              "(%(ip)s).", {'vid': vlanid, 'ip': ip})
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def create_network_postcommit_vxlan(self, net_uuid, seg_id):
        method = 'create_network_postcommit'
        try:
            self._vxlan_driver.create_logical_switch(net_uuid, seg_id)
        except Exception:
            LOG.exception(
                "Failed to create vxlan(%(seg_id)s) on switch(%(ip)s)",
                {'seg_id': seg_id, 'ip': self.ips})
            raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_network_postcommit(self, net_context):
        """Calls clean process for FOS switch.

        Case1: Baremetal deploy with VLAN network
                   Delete VLAN definition.
        Case2: Baremetal deploy with VXLAN network
                   Delete DCVPN definition.
        Case3: Otherwise:
                   Do nothing.

        :param net_context: context of network
        :type net_context: NetworkContext

        :returns: None
        :rtype: None
        """

        network = net_context.current
        net_id = network['id']
        tenant_id = network['tenant_id']
        network_type = utils.get_network_type(network)
        seg_id = utils.get_segmentation_id(network)

        if network_type == nl_const.TYPE_VLAN and seg_id:
            self.delete_network_postcommit_vlan(seg_id)
        if network_type == nl_const.TYPE_VXLAN and seg_id:
            self.delete_network_postcommit_vxlan(net_id)
        LOG.info(
            "Deleted network (postcommit): network_id=%(net)s "
            "tenant_id=%(tenant)s", {'net': net_id, 'tenant': tenant_id})

    @log_helpers.log_method_call
    def delete_network_postcommit_vlan(self, vlanid):
        """Calls clean vlan process for FOS switch.

        :param vlanid: the ID of VLAN to be deleted
        :type vlanid: string

        :returns: None
        :rtypes: None

        """
        method = 'delete_network_postcommit'
        for ip in self.ips:
            try:
                self._vlan_driver.delete_vlan(ip, vlanid)
            except Exception:
                LOG.exception(
                    "Failed to validate on switch(%(ip)s).", {'ip': ip})
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_network_postcommit_vxlan(self, net_uuid):
        method = 'delete_network_postcommit'
        try:
            self._vxlan_driver.delete_logical_switch(net_uuid)
        except Exception:
            LOG.exception(
                "Failed to validate on switch(%(ip)s).", {'ip': self.ips})
            raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_port_postcommit(self, mech_context):
        """Calls cleanup process for FOS switch.

        Case1: Baremetal deploy with VLAN
                   Clear VLAN/LAG for specified physical port.
        Case2:
                   Clear VXLAN/LAG for specified physical port.
        Case3: Otherwise
                   Do nothing.

        :param mech_context: context of port
        :type mech_context: PortContext

        :returns: None
        :rtype: None
        """

        port = mech_context.current
        network = mech_context.network
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']
        network_type = utils.get_network_type(network)
        if network_type == nl_const.TYPE_VLAN and utils.is_baremetal(port):
            self.clear_vlan(mech_context)
        if network_type == nl_const.TYPE_VXLAN:
            self.clear_vxlan(mech_context)
        LOG.info(
            "Delete port (postcommit): port_id=%(port_id)s "
            "network_id=%(net_id)s tenant_id=%(tenant_id)s",
            {'port_id': port_id, 'net_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def update_port_postcommit(self, context):
        """Update specified physical port on switch."""
        method = 'update_port_postcommit'
        port = context.current
        network = context.network
        vif_type = port[pb_def.VIF_TYPE]
        network_type = utils.get_network_type(network)
        seg_id = utils.get_segmentation_id(network)
        if utils.is_baremetal(port):
            if utils.is_unbound(context):
                try:
                    # Clear vlan or vxlan from physical port for unbound port
                    if network_type == nl_const.TYPE_VLAN:
                        self.clear_vlan(context, use_original=True)
                    if network_type == nl_const.TYPE_VXLAN:
                        self.clear_vxlan(context, use_original=True)
                except Exception:
                    LOG.exception("Failed to clear %(network_type)s"
                                  "(%(seg_id)s).",
                                  {'network_type': network_type,
                                   'seg_id': seg_id})
                    raise ml2_exc.MechanismDriverError(method=method)
        else:
            # Setup vxlan from specified physical port on switch.
            if (network_type != nl_const.TYPE_VXLAN or
                    vif_type == pb_def.VIF_TYPE_UNBOUND):
                return
            # currently supports only one segment per network
            # Setup VXLAN for port which bound with DHCP, router, and vms.
            try:
                self._vxlan_driver.update_physical_port(
                    seg_id, [], port, self.switches_mac_ip_pair)
            except Exception:
                LOG.exception("Failed to setup VNI(%s).", seg_id)
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def setup_vlan(self, params):
        """Provision VLAN with specified port(s).

        This method will select driver's method.
        Case1: param['lag'] is True
            This method calls 'setup_lag' and clears VLAN and LAG.
        Case2: param['lag'] is False
            This method calls 'setup_vlan' and setup only VLAN.

        :param params: a dictionary of the return value for
                        get_physical_net_params
        :type params: dictionary

        :returns: None
        :rtype: None
        """

        target = 'setup_lag' if params['lag'] else 'setup_vlan'
        LOG.info("Call %(target)s.  params: %(params)s",
                 {'target': target, 'params': params})
        try:
            if params['lag']:
                self._vlan_driver.setup_lag(
                    params['local_link_info'],
                    self.switches_mac_ip_pair,
                    vlanid=params['vlanid'])
            else:
                self._vlan_driver.setup_vlan(
                    params['vlanid'],
                    params['local_link_info'],
                    self.switches_mac_ip_pair)
        except Exception:
            # TODO(yushiro): Separate each exceptions.
            LOG.exception("Failed to setup vlan(%s)", params['vlanid'])
            raise ml2_exc.MechanismDriverError(method=target)

    @log_helpers.log_method_call
    def clear_vlan(self, context, use_original=False):
        """Clear VLAN with specified port(s).

        This method will select driver's method.
        Case1: param['lag'] is True
            This method calls 'clear_lag' and clears VLAN and LAG.
        Case2: param['lag'] is False
            This method calls 'clear_vlan' and clears only VLAN.

        :param params: a dictionary of the return value for
                       get_physical_net_params
        :type params: dictionary
        :returns: None
        :rtype: None
        """
        if not validate_baremetal_deploy(context, use_original):
            return
        params = self.get_physical_net_params(context, use_original)
        target = 'clear_lag'
        try:
            call_target = target if params['lag'] else 'clear_vlan'
            clear_method = getattr(self._vlan_driver, call_target)
            LOG.info("call %(target)s. params: %(params)s",
                     {'target': call_target, 'params': params})
            clear_method(params['local_link_info'], self.switches_mac_ip_pair)
        except Exception:
            LOG.exception("Failed to clear vlan(%s)", params['vlanid'])
            raise ml2_exc.MechanismDriverError(method=target)

    @log_helpers.log_method_call
    def clear_vxlan(self, context, use_original=False):
        """Clear VXLAN from specified physical port on switch."""
        method = "clear_vxlan"
        port = context.original if use_original else context.current
        network = context.network
        vif_type = port[pb_def.VIF_TYPE]
        if (vif_type == pb_def.VIF_TYPE_UNBOUND or
                utils.get_network_type(network) == nl_const.TYPE_FLAT):
            return
        lli = utils.get_physical_connectivity(port)
        try:
            if utils.is_lag(lli):
                mac_lag_map = self._vlan_driver.clear_lag(
                    lli, self.switches_mac_ip_pair)
                self._vxlan_driver.reset_physical_port_with_lag(
                    lli, port, self.switches_mac_ip_pair,
                    mac_lag_map=mac_lag_map)
            else:
                self._vxlan_driver.reset_physical_port(
                    lli, port, self.switches_mac_ip_pair)
        except Exception:
            seg_id = utils.get_segmentation_id(network)
            LOG.exception("Failed to clear VNI(%s).", seg_id)
            raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def get_physical_net_params(self, context, use_original=False):
        """Validate physical network parameters for baremetal deployment.

        Validates network & port params and returns dictionary.
        'local_link_information' is a dictionary from Ironic-port.  This value
        includes as follows:
            'switch_id': A string of switch's MAC address
                         This value is equal to 'chassis_id' from LLDP TLV.
            'port_id': A string of switch interface name.
                         This value is equal to 'port_id' from LLDP TLV.
            'switch_info': A string of switch name.
                         This value is equal to 'system_name' from LLDP TLV.

        :param port: a dictionary of port
        :type port: dictionary
        :param network: a network object
        :type network: NetworkContext

        :returns: A dictionary parameters for baremetal deploy
        :rtype: dictionary
        """
        port = context.original if use_original else context.current
        network = context.network
        vlanid = utils.get_segmentation_id(network)
        local_link_info = utils.get_physical_connectivity(port)
        return {
            "local_link_info": local_link_info,
            "vlanid": vlanid,
            "mac": port['mac_address'],
            "lag": utils.is_lag(local_link_info)
        }

    @log_helpers.log_method_call
    def bind_port(self, context):

        port = context.current
        network = context.network
        if not is_supported(network):
            return
        LOG.debug("Attempting to bind port %(port)s with vnic_type "
                  "%(vnic_type)s on network %(network)s",
                  {'port': port['id'], 'vnic_type': port[pb_def.VNIC_TYPE],
                   'network': port['network_id']})

        network_type = utils.get_network_type(network)
        to_bind = False

        if network_type == nl_const.TYPE_VXLAN:
            # vxlan driver handles not only baremetal port, but vm, dhcp,
            # router ports.
            self.setup_vxlan(context)
            to_bind = True
        if utils.is_baremetal(port) and network_type == nl_const.TYPE_VLAN:
            self.setup_vlan(self.get_physical_net_params(context))
            to_bind = True
        if to_bind:
            context.set_binding(context.segments_to_bind[0][api.ID],
                                pb_def.VIF_TYPE_OTHER, {},
                                status=nl_const.PORT_STATUS_ACTIVE)

    @log_helpers.log_method_call
    def setup_vxlan(self, context):
        """Update VXLAN from specified physical port on switch."""
        # currently supports only one segment per network
        port = context.current
        seg_id = utils.get_segmentation_id(context.network)
        lli = utils.get_physical_connectivity(port)
        req_id = context.network._plugin_context.request_id
        try:
            if utils.is_lag(lli):
                mac_lag_map = self._vlan_driver.setup_lag(
                    lli, self.switches_mac_ip_pair)
                self._vxlan_driver.update_physical_port_with_lag(
                    seg_id, lli, port, self.switches_mac_ip_pair, req_id,
                    mac_lag_map=mac_lag_map)
            else:
                self._vxlan_driver.update_physical_port(
                    seg_id, lli, port, self.switches_mac_ip_pair, req_id)
        except Exception:
            LOG.exception("Failed to setup VNI(%s).", seg_id)
            raise ml2_exc.MechanismDriverError(method='setup_vxlan')


def is_supported(network):
    """Validate network parameter(network_type and segmentation_id).

    :param network: a network object
    :type network: NetworkContext

    :returns: True if network_type is supported and segmentation_id is included
              otherwise False
    :rtype: boolean
    """

    net_type = utils.get_network_type(network)
    if net_type not in _SUPPORTED_NET_TYPES:
        LOG.warning("Network type(%s) is not supported. Skip it.", net_type)
        return False
    return True if utils.get_segmentation_id(network) else False


def validate_baremetal_deploy(port_context, use_original=False):
    """Validate baremetal deploy.

    :param port_context: a PortContext object
    :type port_context: PortContext

    :returns: True if enable to baremetal deploy otherwise False
    :rtype: boolean
    """

    port = port_context.original if use_original else port_context.current
    network = port_context.network
    return utils.is_baremetal(port) and is_supported(network)
