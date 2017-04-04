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


"""Implementation of Fujitsu ML2 Mechanism driver for ML2 Plugin."""

from oslo_config import cfg
from oslo_log import helpers as log_helpers
from oslo_log import log as logging
from oslo_utils import importutils

from networking_fujitsu._i18n import _
from networking_fujitsu._i18n import _LE
from networking_fujitsu._i18n import _LI
from networking_fujitsu._i18n import _LW
from networking_fujitsu.ml2.common import utils

from neutron_lib.api.definitions import portbindings
from neutron_lib import constants
from neutron_lib.plugins.ml2 import api

from neutron.plugins.ml2.common import exceptions as ml2_exc


LOG = logging.getLogger(__name__)
DRIVER = 'networking_fujitsu.ml2.'
FOSSW_VLAN_DRIVER = DRIVER + 'fossw.fossw_vlandriver.FOSSWVlanDriver'
FOSSW_VXLAN_DRIVER = DRIVER + 'fossw.fossw_vxlandriver.FOSSWVxlanDriver'
DEFAULT_VLAN = 1

_SUPPORTED_NET_TYPES = ['vlan', 'vxlan']

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
        LOG.debug(_("loaded switch IP is: %s"), self.ips)
        if len(self.ips) == 0:
            raise cfg.RequiredOptError(
                'fossw_ips', cfg.OptGroup(ML2_FUJITSU_GROUP))
        self.username = cfg.CONF.fujitsu_fossw.username
        self.password = cfg.CONF.fujitsu_fossw.password
        self._vlan_driver = importutils.import_object(FOSSW_VLAN_DRIVER,
                                                      cfg.CONF)
        self._vxlan_driver = importutils.import_object(FOSSW_VXLAN_DRIVER,
                                                       cfg.CONF)
        self.switches_mac_ip_pair = self._vlan_driver.get_switch_mac_ip_pair(
            self.ips
        )
        LOG.debug(_("Registered FOS switch's IP and MAC pairs: %s"),
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
        segmentation_id = utils.get_segmentation_id(network)

        if network_type == 'vlan' and segmentation_id:
            self.create_network_postcommit_vlan(segmentation_id)
        elif network_type == 'vxlan' and segmentation_id:
            self.create_network_postcommit_vxlan(network_id, segmentation_id)

        LOG.info(
            _LI("created network (postcommit): network_id=%(network_id)s "
                "tenant_id=%(tenant_id)s"),
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
                LOG.exception(_LE("Failed to create vlan(%(vid)s) on switch"
                                  "(%(ip)s)."), {'vid': vlanid, 'ip': ip})
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def create_network_postcommit_vxlan(self, net_uuid, vni):
        method = 'create_network_postcommit'
        try:
            self._vxlan_driver.create_logical_switch(net_uuid, vni)
        except Exception:
            LOG.exception(
                _LE("Failed to create vxlan(%(vni)s) on switch(%(ip)s)"),
                {'vni': vni, 'ip': self.ips})
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
        network_id = network['id']
        tenant_id = network['tenant_id']
        network_type = utils.get_network_type(network)
        segmentation_id = utils.get_segmentation_id(network)

        if network_type == 'vlan' and segmentation_id:
            self.delete_network_postcommit_vlan(segmentation_id)
        elif network_type == 'vxlan' and segmentation_id:
            self.delete_network_postcommit_vxlan(network_id)
        else:
            return

        LOG.info(
            _LI("Deleted network (postcommit): network_id=%(network_id)s "
                "tenant_id=%(tenant_id)s"),
            {'network_id': network_id, 'tenant_id': tenant_id})

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
                    _LE("Failed to validate on switch(%(ip)s)."), {'ip': ip})
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_network_postcommit_vxlan(self, net_uuid):
        method = 'delete_network_postcommit'
        try:
            self._vxlan_driver.delete_logical_switch(net_uuid)
        except Exception:
            LOG.exception(
                _LE("Failed to validate on switch(%(ip)s)."), {'ip': self.ips})
            raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_port_postcommit(self, mech_context):
        """Calls cleanup process for C-Fabric.

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

        method = 'delete_port_postcommit'
        port = mech_context.current
        network = mech_context.network
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']
        network_type = utils.get_network_type(network)
        if (network_type == 'vlan' and utils.is_baremetal(port)):
            self.delete_port_postcommit_vlan(mech_context, method)
        elif network_type == 'vxlan':
            self.delete_port_postcommit_vxlan(mech_context, method)
        else:
            return
        LOG.info(
            _LI("Delete port (postcommit): port_id=%(port_id)s "
                "network_id=%(net_id)s tenant_id=%(tenant_id)s"),
            {'port_id': port_id, 'net_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def delete_port_postcommit_vlan(self, context, method):
        """Clear VLAN from specified physical port on switch.

        :param context: context of port
        :type context: PortContext
        :param method: the name of method
        :type method: string

        :returns: None
        :rtype: None

         """
        if validate_baremetal_deploy(context):
            params = self.get_physical_net_params(context)
            try:
                self.clear_vlan(params)
            except Exception:
                LOG.exception(
                    _LE("Failed to clear vlan(%s)."), params['vlanid'])
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def update_port_postcommit(self, context):
        """Update VXLAN from specified physical port on switch."""
        port = context.current
        if utils.is_baremetal(port):
            return
        network = context.network
        vif_type = port['binding:vif_type']
        network_type = utils.get_network_type(network)
        if network_type != 'vxlan' or vif_type == 'unbound':
            return
        vni = utils.get_segmentation_id(network)
        try:
            self._vxlan_driver.update_physical_port(
                vni, [], port, self.switches_mac_ip_pair
            )
        except Exception:
            LOG.exception(_LE("Failed to create VNI(%s)."), vni)
            raise ml2_exc.MechanismDriverError(method='create_port_postcommit')

    @log_helpers.log_method_call
    def delete_port_postcommit_vxlan(self, context, method):
        """Clear VXLAN from specified physical port on switch."""
        port = context.current
        network = context.network
        vif_type = port['binding:vif_type']
        if vif_type == 'unbound' or utils.get_network_type(network) == 'flat':
            return
        lli = utils.get_physical_connectivity(port)
        try:
            if utils.is_lag(lli):
                self._vlan_driver.clear_vlan_with_lag(
                    DEFAULT_VLAN, lli, self.switches_mac_ip_pair)
                self._vxlan_driver.reset_physical_port_with_lag(
                    lli, port, self.switches_mac_ip_pair)
            else:
                self._vxlan_driver.reset_physical_port(
                    lli, port, self.switches_mac_ip_pair)
        except Exception:
            vni = utils.get_segmentation_id(network)
            LOG.exception(_LE("Failed to clear VNI(%s)."), vni)
            raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def setup_vlan(self, params):
        """Provision VLAN with specified port(s).

        This method will select driver's method.
        Case1: param['lag'] is True
            This method calls 'setup_vlan_with_lag' and clears VLAN and LAG.
        Case2: param['lag'] is False
            This method calls 'setup_vlan' and setup only VLAN.

        :param params: a dictionary of the return value for
                        get_physical_net_params
        :type params: dictionary

        :returns: None
        :rtype: None
        """

        target = 'setup_vlan_with_lag' if params['lag'] else 'setup_vlan'
        try:
            setup_method = getattr(self._vlan_driver, target)
        except AttributeError:
            LOG.exception(_LE("Unexpected error happend."))
            raise ml2_exc.MechanismDriverError(method='setup_vlan')
        try:
            # This plugin supposes 1 C-Fabric(fabric_id) management.
            # Therefore, not to identify target IP address by using
            # switch_info(mac_address).
            LOG.info(
                _LI("Call %(target)s.  params: %(params)s"),
                {'target': target, 'params': params}
            )
            setup_method(
                params['vlanid'],
                params['local_link_info'],
                self.switches_mac_ip_pair,
            )
        except Exception:
            LOG.exception(_LE("Failed to setup vlan(%s)"), params['vlanid'])
            raise ml2_exc.MechanismDriverError(method=target)

    @log_helpers.log_method_call
    def clear_vlan(self, params):
        """Clear VLAN with specified port(s).

        This method will select driver's method.
        Case1: param['lag'] is True
            This method calls 'clear_vlan_with_lag' and clears VLAN and LAG.
        Case2: param['lag'] is False
            This method calls 'clear_vlan' and clears only VLAN.

        :param params: a dictionary of the return value for
                       get_physical_net_params
        :type params: dictionary
        :returns: None
        :rtype: None
        """

        target = 'clear_vlan_with_lag'
        call_target = target if params['lag'] else 'clear_vlan'
        try:
            clear_method = getattr(self._vlan_driver, call_target)
        except AttributeError:
            LOG.exception(_LE("Unexpected error happend."))
            raise ml2_exc.MechanismDriverError(method="clear_vlan")

        LOG.info(
            _LI("call %(target)s.  params: %(params)s"),
            {'target': call_target, 'params': params})
        try:
            clear_method(
                params['vlanid'],
                params['local_link_info'],
                self.switches_mac_ip_pair,
            )
        except Exception:
            LOG.exception(_LE("Failed to clear vlan(%s)"), params['vlanid'])
            raise ml2_exc.MechanismDriverError(method=target)

    @log_helpers.log_method_call
    def get_physical_net_params(self, mech_context):
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

        :param mech_context: a Context instance
        :type mech_context: PortContext

        :returns: A dictionary parameters for baremetal deploy
        :rtype: dictionary
        """

        port = mech_context.current
        vlanid = utils.get_segmentation_id(mech_context.network)
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
        vnic_type = port['binding:vnic_type']
        LOG.debug("Attempting to bind port %(port)s with vnic_type "
                  "%(vnic_type)s on network %(network)s",
                  {'port': port['id'], 'vnic_type': vnic_type,
                   'network': context.network.current['id']})

        network_type = utils.get_network_type(network)
        if network_type == 'vlan' and utils.is_baremetal(port):
            self.setup_vlan(self.get_physical_net_params(context))
        if network_type == 'vxlan':
            self.bind_port_vxlan(context)
        if utils.is_baremetal(port):
            segments = context.segments_to_bind
            context.set_binding(segments[0][api.ID],
                                portbindings.VIF_TYPE_OTHER, {},
                                status=constants.PORT_STATUS_ACTIVE)

    @log_helpers.log_method_call
    def bind_port_vxlan(self, context):
        """Update VXLAN from specified physical port on switch."""
        # currently supports only one segment per network
        port = context.current
        vni = utils.get_segmentation_id(context.network)
        lli = utils.get_physical_connectivity(port)
        try:
            if utils.is_lag(lli):
                self._vlan_driver.setup_vlan_with_lag(
                    DEFAULT_VLAN, lli, self.switches_mac_ip_pair)
                self._vxlan_driver.update_physical_port_with_lag(
                    vni, lli, port, self.switches_mac_ip_pair)
            else:
                self._vxlan_driver.update_physical_port(
                    vni, lli, port, self.switches_mac_ip_pair)
        except Exception:
            LOG.exception(_LE("Failed to setup VNI(%s)."), vni)
            raise ml2_exc.MechanismDriverError(method='bind_port_vxlan')


def is_supported(network):
    """Validate network parameter(network_type and segmentation_id).

    :param network: a network object
    :type network: NetworkContext

    :returns: True if network_type is 'VLAN' and segmentation_id is included
              otherwise False
    :rtype: boolean
    """

    seg_id = utils.get_segmentation_id(network)
    net_type = utils.get_network_type(network)
    if (net_type in _SUPPORTED_NET_TYPES and seg_id):
        return True
    LOG.warning(_LW("%s is not supported. Skip it."), net_type)
    return False


def validate_baremetal_deploy(port_context):
    """Validate baremetal deploy.

    :param port_context: a PortContext object
    :type port_context: PortContext

    :returns: True if enable to baremetal deploy otherwise False
    :rtype: boolean
    """

    port = port_context.current
    network = port_context.network
    return utils.is_baremetal(port) and is_supported(network)
