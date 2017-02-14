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

from networking_fujitsu._i18n import _LE
from networking_fujitsu._i18n import _LI
from networking_fujitsu._i18n import _LW
from networking_fujitsu.ml2.common import utils as fj_util

from neutron_lib import constants as const

from neutron.extensions import portbindings
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.plugins.ml2 import driver_api


LOG = logging.getLogger(__name__)
FUJITSU_DRIVER = 'networking_fujitsu.ml2.'
FOSSW_VLAN_DRIVER = FUJITSU_DRIVER + 'fossw.fossw_vlandriver.FOSSWVlanDriver'
FOSSW_VXLAN_DRIVER = FUJITSU_DRIVER + \
    'fossw.fossw_vxlandriver.FOSSWVxlanDriver'

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


class FOSSWMechanismDriver(driver_api.MechanismDriver):
    """ML2 Mechanism driver for Fujitsu FOS switches.

    This is the upper layer driver class that interfaces to lower layer (CLI)
    below.
    """

    def __init__(self):
        self._vlan_driver = None
        self._vxlan_driver = None
        self._list_switch_info = None
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
    def create_network_postcommit(self, mech_context):
        """Calls setup process for FOS switch.

        Case1: Baremetal deploy with VLAN network
                   Create VLAN with specified VLAN ID.
        Case2: Baremetal deploy with VXLAN network
                   Create DCVPN with specified VNI.
        Case3: Otherwise
                   Do nothing.

        :param mech_context: context of network
        :type mech_context: NetworkContext

        :returns: None
        :rtype: None

        """

        network = mech_context.current
        network_id = network['id']
        tenant_id = network['tenant_id']
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']

        if (provider_type == 'vlan' and segmentation_id and
           not fj_util.is_baremetal(mech_context.current)):
            self.create_network_postcommit_vlan(segmentation_id)
        elif provider_type == 'vxlan' and segmentation_id:
            self.create_network_postcommit_vxlan(network_id, segmentation_id)
        else:
            return

        LOG.info(
            _LI("created network (postcommit): network_id=%(network_id)s "
                "tenant_id=%(tenant_id)s"),
            {'network_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def create_network_postcommit_vlan(self, vlan_id):
        """Create VLAN to FOS switch.

        :param vlan_id: the ID of VLAN to be created
        :type vlan_id: string

        :returns: None
        :rtype: None

        """
        method = 'create_network_postcommit'
        for ip in self.ips:
            try:
                self._vlan_driver.create_vlan(
                    ip,
                    vlan_id
                )
            except Exception as e:
                LOG.exception(_LE("Fujitsu Mechanism: failed to create vlan "
                                  "switch(%(ip)s. %(err)s"),
                              ip=ip, err=e)
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def create_network_postcommit_vxlan(self, net_uuid, vnid):
        method = 'create_network_postcommit'
        try:
            self._vxlan_driver.create_logical_switch(net_uuid, vnid)
        except Exception as e:
            LOG.exception(_LE("Fujitsu Mechanism: failed to create vlxan "
                              "switch(%(ip)). %(err)s"),
                          ip=self.ips, err=e)
            raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_network_postcommit(self, mech_context):
        """Calls clean process for FOS switch.

        Case1: Baremetal deploy with VLAN network
                   Delete VLAN definition.
        Case2: Baremetal deploy with VXLAN network
                   Delete DCVPN definition.
        Case3: Otherwise:
                   Do nothing.

        :param mech_context: context of network
        :type mech_context: NetworkContext

        :returns: None
        :rtype: None
        """

        network = mech_context.current
        network_id = network['id']
        tenant_id = network['tenant_id']
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']

        if (provider_type == 'vlan' and segmentation_id and
           not fj_util.is_baremetal(mech_context.current)):
            self.delete_network_postcommit_vlan(segmentation_id)
        elif provider_type == 'vxlan' and segmentation_id:
            self.delete_network_postcommit_vxlan(network_id)
        else:
            return

        LOG.info(
            _LI("deleted network (postcommit): network_id=%(network_id)s "
                "tenant_id=%(tenant_id)s"),
            {'network_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def delete_network_postcommit_vlan(self, vlan_id):
        """Calls clean vlan process for FOS switch.

        :param vlan_id: the ID of VLAN to be deleted
        :type vlan_id: string

        :returns: None
        :rtypes: None

        """
        method = 'delete_network_postcommit'
        for ip in self.ips:
            try:
                self._vlan_driver.delete_vlan(
                    ip,
                    vlan_id
                )
            except Exception as e:
                LOG.exception(
                    _LE("Fujitsu Mechanism: failed to validate "
                        "on switch(%(ip)s). %(err)"),
                    ip=ip, err=e
                )
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_network_postcommit_vxlan(self, net_uuid):
        method = 'delete_network_postcommit'
        try:
            self._vxlan_driver.delete_logical_switch(net_uuid)
        except Exception as e:
            LOG.exception(
                _LE("Fujitsu Mechanism: failed to validate "
                    "on switch(%(ip)). %(err)"),
                ip=self.ips, err=e
            )
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
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']
        segment = mech_context.network.network_segments[0]
        provider_type = segment[driver_api.NETWORK_TYPE]

        if (provider_type == 'vlan' and
           fj_util.is_baremetal(mech_context.current)):
            self.delete_port_postcommit_vlan(mech_context, method)
        elif provider_type == 'vxlan':
            self.delete_port_postcommit_vxlan(mech_context, method)
        else:
            return
        LOG.info(
            _LI("delete port (postcommit): port_id=%(port_id)s "
                "network_id=%(network_id)s tenant_id=%(tenant_id)s"),
            {'port_id': port_id,
             'network_id': network_id, 'tenant_id': tenant_id})

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
                    _LE("Failed to clear vlan(%s)."),
                    params['vlan_id']
                )
                raise ml2_exc.MechanismDriverError(method=method)

    @log_helpers.log_method_call
    def delete_port_postcommit_vxlan(self, context, method):
        """Clear VXLAN from specified physical port on switch."""
        if validate_baremetal_deploy(context):
            # currently supports only one segment per network
            segment = context.network.network_segments[0]
            vnid = segment[driver_api.SEGMENTATION_ID]
            lli = fj_util.get_physical_connectivity(context.current)
            lag = fj_util.is_lag(lli)
            target = 'reset_physical_port_with_lag' \
                if lag else 'reset_physical_port'
            try:
                reset_method = getattr(self._vxlan_driver, target)
            except AttributeError:
                LOG.exception(_LE("Unexpected error happend."))
                raise ml2_exc.MechanismDriverError(
                    method='delete_port_postcommit_vxlan')

            try:
                reset_method(lli, context, self.switches_mac_ip_pair)
            except Exception:
                LOG.exception(
                    _LE("Failed to clear vxlan(%s)."),
                    vnid
                )
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
                _LI("call %(target)s.  params: %(params)s"),
                {'target': target, 'params': params}
            )
            setup_method(
                params['vlan_id'],
                params['local_link_info'],
                self.switches_mac_ip_pair,
            )
        except Exception:
            LOG.exception(_LE("Fujitsu Mechanism: "
                              "failed to setup vlan %s"), params['vlan_id'])
            raise ml2_exc.MechanismDriverError(method='setup_vlan')

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

        try:
            # This plugin supposes 1 C-Fabric(fabric_id) management.
            # Therefore, not to identify target IP address by using
            # switch_info(mac_address).
            LOG.info(
                _LI("call %(target)s.  params: %(params)s"),
                {'target': call_target, 'params': params}
            )
            clear_method(
                params['vlan_id'],
                params['local_link_info'],
                self.switches_mac_ip_pair,
            )
        except Exception:
            LOG.exception(_LE("Fujitsu Mechanism: "
                              "failed to clear vlan %s"), params['vlan_id'])
            raise ml2_exc.MechanismDriverError(method="clear_vlan")

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
        # currently supports only one segment per network
        segment = mech_context.network.network_segments[0]
        vlan_id = segment[driver_api.SEGMENTATION_ID]
        local_link_info = fj_util.get_physical_connectivity(port)
        return {
            "local_link_info": local_link_info,
            "vlan_id": vlan_id,
            "mac": port['mac_address'],
            "lag": fj_util.is_lag(local_link_info)
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
        provider_type = network.network_segments[0][driver_api.NETWORK_TYPE]
        params = self.get_physical_net_params(context)
        segments = context.segments_to_bind
        if provider_type == 'vlan' and validate_baremetal_deploy(context):
            self.setup_vlan(params)
        elif provider_type == 'vxlan':
            self.bind_port_vxlan(context)
        else:
            return
        context.set_binding(segments[0][driver_api.ID],
                            portbindings.VIF_TYPE_OTHER, {},
                            status=const.PORT_STATUS_ACTIVE)

    @log_helpers.log_method_call
    def bind_port_vxlan(self, context, method):
        """Update VXLAN from specified physical port on switch."""
        # currently supports only one segment per network
        segment = context.network.network_segments[0]
        vnid = segment[driver_api.SEGMENTATION_ID]
        lli = fj_util.get_physical_connectivity(context.current)
        lag = fj_util.is_lag(lli)
        target = 'update_physical_port_with_lag' \
            if lag else 'update_physical_port'
        try:
            update_method = getattr(self._vxlan_driver, target)
        except AttributeError:
            LOG.exception(_LE("Unexpected error happend."))
            raise ml2_exc.MechanismDriverError(method='bind_port_vxlan')

        try:
            update_method(vnid, lli, context, self.switches_mac_ip_pair)
        except Exception:
            LOG.exception(_LE("Failed to create vxlan(%s)."), vnid)
            raise ml2_exc.MechanismDriverError(method='bind_port_vxlan')


def is_supported(network):
    """Validate network parameter(network_type and segmentation_id).

    :param network: a network object
    :type network: NetworkContext

    :returns: True if network_type is 'VLAN' and segmentation_id is included
              otherwise False
    :rtype: boolean
    """

    segment = network.network_segments[0]
    seg_id = segment[driver_api.SEGMENTATION_ID]
    net_type = segment[driver_api.NETWORK_TYPE]
    if (net_type in _SUPPORTED_NET_TYPES and seg_id):
        return True
    LOG.warning(_LW("%s is not supported. Skip it."), net_type)
    return False


def validate_baremetal_deploy(mech_context):
    """Validate baremetal deploy.

    :param mech_context: a context object
    :type mech_context: PortContext

    :returns: True if enable to baremetal deploy otherwise False
    :rtype: boolean
    """

    port = mech_context.current
    network = mech_context.network
    if (fj_util.is_baremetal(port) and
       is_supported(network) and fj_util.get_physical_connectivity(port)):
        return True
    return False
