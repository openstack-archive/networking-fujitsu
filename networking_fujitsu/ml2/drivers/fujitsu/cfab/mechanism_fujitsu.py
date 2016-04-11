# Copyright 2015-2016 FUJITSU LIMITED
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#


"""Implementation of Fujitsu ML2 Mechanism driver for ML2 Plugin."""

from oslo_config import cfg
from oslo_log import helpers as log_helpers
try:
    from oslo_log import log as logging
except ImportError:
    from neutron.openstack.common import log as logging
try:
    from oslo_utils import importutils
except ImportError:
    from neutron.openstack.common import importutils
from networking_fujitsu.i18n import _LE
from networking_fujitsu.i18n import _LI
from networking_fujitsu.i18n import _LW
from networking_fujitsu.ml2.drivers.fujitsu.common import utils as fj_util
from neutron.common import constants as const
from neutron.extensions import portbindings
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.plugins.ml2 import driver_api


LOG = logging.getLogger(__name__)
FUJITSU_DRIVER = 'networking_fujitsu.ml2.drivers.fujitsu.'
CFAB_DRIVER = FUJITSU_DRIVER + 'cfab.cfabdriver.CFABdriver'

VFAB_ID_DEFAULT = "default"
VFAB_ID_MIN = 1
VFAB_ID_MAX = 3000
_SUPPORTED_NET_TYPES = ['vlan']

ML2_FUJITSU_GROUP = "fujitsu_cfab"
ML2_FUJITSU = [
    cfg.StrOpt(
        'address', default='',
        help=_("The address of the C-Fabric to telnet to.")),
    cfg.StrOpt(
        'username', default='admin',
        help=_("The C-Fabric username to use.")),
    cfg.StrOpt(
        'password', default='admin', secret=True,
        help=_("The C-Fabric password to use.")),
    cfg.ListOpt(
        'physical_networks', default='',
        help=_("List of <physical_network>:<vfab_id> tuples specifying "
               "physical_network names and corresponding vfab ids.")),
    cfg.BoolOpt(
        'share_pprofile', default=False,
        help=_("Whether to share a C-Fabric pprofile among Neutron "
               "ports using the same VLAN ID.")),
    cfg.StrOpt(
        'pprofile_prefix', default='',
        help=_("The prefix string for pprofile name.")),
    cfg.BoolOpt(
        'save_config', default=True,
        help=_("Whether to save configuration."))]

cfg.CONF.register_opts(ML2_FUJITSU, ML2_FUJITSU_GROUP)


class FujitsuMechanism(driver_api.MechanismDriver):
    """ML2 Mechanism driver for Fujitsu C-Fabric switches. This is the upper
    layer driver class that interfaces to lower layer (CLI) below.
    """

    def __init__(self):
        self._driver = None
        self._physical_networks = {}
        self._switch = None
        self.initialize()

    def initialize(self):
        """Initialize of variables needed by this class."""

        self._parse_physical_networks()
        self._switch = {'address': cfg.CONF.fujitsu_cfab.address,
                        'username': cfg.CONF.fujitsu_cfab.username,
                        'password': cfg.CONF.fujitsu_cfab.password
                        }

        if not self._switch['address']:
            raise cfg.RequiredOptError(
                'address', cfg.OptGroup(ML2_FUJITSU_GROUP))

        self._driver = importutils.import_object(CFAB_DRIVER, cfg.CONF)

    def _parse_physical_networks(self):
        """Interpret physical_networks as physical_network:vfab_id entries."""

        for entry in cfg.CONF.fujitsu_cfab.physical_networks:
            try:
                physical_network, vfab_id = entry.split(':')
            except ValueError:
                LOG.exception(
                    _LE("Fujitsu Mechanism: illegal physical_networks entry")
                )
                raise ml2_exc.MechanismDriverError(
                    method="_parse_physical_networks")
            if not (vfab_id == VFAB_ID_DEFAULT or
                    VFAB_ID_MIN <= int(vfab_id) <= VFAB_ID_MAX):
                LOG.error(
                    _LE("Fujitsu Mechanism: illegal vfab id in "
                        "physical_networks entry")
                )
                raise ml2_exc.MechanismDriverError(
                    method="_parse_physical_networks")
            self._physical_networks[physical_network] = vfab_id

    def _get_vfab_id(self, physical_network):
        """Get vfab_id corresponding to the physical_network."""

        try:
            vfab_id = self._physical_networks[physical_network]
        except KeyError:
            LOG.exception(
                _LE("Fujitsu Mechanism: network cannot be found in the "
                    "configured physical network"))
            raise ml2_exc.MechanismDriverError(method="_get_vfab_id")
        return vfab_id

    @log_helpers.log_method_call
    def create_port_postcommit(self, mech_context):
        """Calls setup process for C-Fabric.

        Case1: Baremetal deploy
                   Setup VLAN for specified physical port.
        Case2: Otherwise
                   Associate the assigned MAC address to the portprofile.
        """

        if fj_util.is_baremetal(mech_context.current):
            return

        if not is_supported(mech_context.network):
            return

        method = 'create_port_postcommit'
        port = mech_context.current
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']
        segments = mech_context.network.network_segments
        # currently supports only one segment per network
        segment = segments[0]

        vfab_id = self._get_vfab_id(segment[driver_api.PHYSICAL_NETWORK])
        vlanid = segment[driver_api.SEGMENTATION_ID]

        interface_mac = port['mac_address']

        try:
            self._driver.associate_mac_to_network(self._switch['address'],
                                                  self._switch['username'],
                                                  self._switch['password'],
                                                  vfab_id,
                                                  vlanid,
                                                  interface_mac)
        except Exception:
            LOG.exception(
                _LE("Fujitsu Mechanism: failed to associate mac %s")
                % interface_mac)
            raise ml2_exc.MechanismDriverError(method=method)

        LOG.info(
            _LI("created port (postcommit): port_id=%(port_id)s "
                "network_id=%(network_id)s tenant_id=%(tenant_id)s"),
            {'port_id': port_id,
             'network_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def delete_port_postcommit(self, mech_context):
        """Calls cleanup process for C-Fabric.

        Case1: Baremetal deploy
                   Clear VLAN/LAG for specified physical port.
        Case2: Otherwise
                   Dissociate MAC address from the portprofile.
        """

        method = 'delete_port_postcommit'
        port = mech_context.current
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']
        if fj_util.is_baremetal(port):
            if validate_baremetal_deploy(mech_context):
                params = self.get_physical_net_params(mech_context)
                try:
                    self.clear_vlan(params)
                except Exception:
                    LOG.exception(_LE("Failed to clear vlan%s."),
                        params['vlanid'])
                    raise ml2_exc.MechanismDriverError(method=method)
        elif not is_supported(mech_context.network):
            pass
        else:
            segments = mech_context.network.network_segments
            # currently supports only one segment per network
            segment = segments[0]
            vfab_id = self._get_vfab_id(segment[driver_api.PHYSICAL_NETWORK])
            vlanid = segment[driver_api.SEGMENTATION_ID]
            interface_mac = port['mac_address']

            try:
                self._driver.dissociate_mac_from_network(
                    self._switch['address'],
                    self._switch['username'],
                    self._switch['password'],
                    vfab_id,
                    vlanid,
                    interface_mac)
            except Exception:
                LOG.exception(
                    _LE("Fujitsu Mechanism: failed to dissociate MAC %s") %
                    interface_mac)
                raise ml2_exc.MechanismDriverError(method=method)
        LOG.info(
            _LI("delete port (postcommit): port_id=%(port_id)s "
                "network_id=%(network_id)s tenant_id=%(tenant_id)s"),
            {'port_id': port_id,
             'network_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def setup_vlan(self, params):
        """Provision VLAN with specified port(s).

        This method will select driver's method.
        Case1: param['lag'] is True
            This method calls 'setup_vlan_with_lag' and clears VLAN and LAG.
        Case2: param['lag'] is False
            This method calls 'setup_vlan' and setup only VLAN.

        @param  params  a dictionary of the return value for
                        get_physical_net_params
        @return  None
        """

        target = 'setup_vlan_with_lag' if params['lag'] else 'setup_vlan'
        try:
            setup_method = getattr(self._driver, target)
        except AttributeError:
            LOG.exception(_LE("Unexpected error happend."))
            raise ml2_exc.MechanismDriverError(method='setup_vlan')
        try:
            # This plugin supposes 1 C-Fabric(fabric_id) management.
            # Therefore, not to identify target IP address by using
            # switch_info(mac_address).
            LOG.info(_LI("call %(target)s.  params: %(params)s"),
                {'target': target, 'params': params})
            setup_method(
                params['address'],
                params['username'],
                params['password'],
                params['vfab_id'],
                params['vlanid'],
                params['ports'],
                params['mac'],
            )
        except Exception:
            LOG.exception(_LE("Fujitsu Mechanism: "
                              "failed to setup vlan %s"), params['vlanid'])
            raise ml2_exc.MechanismDriverError(method='setup_vlan')

    @log_helpers.log_method_call
    def clear_vlan(self, params):
        """Clear VLAN with specified port(s).

        This method will select driver's method.
        Case1: param['lag'] is True
            This method calls 'clear_vlan_with_lag' and clears VLAN and LAG.
        Case2: param['lag'] is False
            This method calls 'clear_vlan' and clears only VLAN.

        @param  params A dictionary of the return value for
                       get_physical_net_params
        @return  None
        """

        target = 'clear_vlan_with_lag'
        call_target = target if params['lag'] else 'clear_vlan'
        try:
            clear_method = getattr(self._driver, call_target)
        except AttributeError:
            LOG.exception(_LE("Unexpected error happend."))
            raise ml2_exc.MechanismDriverError(method="clear_vlan")

        try:
            # This plugin supposes 1 C-Fabric(fabric_id) management.
            # Therefore, not to identify target IP address by using
            # switch_info(mac_address).
            LOG.info(_LI("call %(target)s.  params: %(params)s"),
                {'target': call_target, 'params': params})
            clear_method(
                params['address'],
                params['username'],
                params['password'],
                params['vfab_id'],
                params['vlanid'],
                params['ports'],
                params['mac'],
                )
        except Exception:
            LOG.exception(_LE("Fujitsu Mechanism: "
                              "failed to clear vlan %s"), params['vlanid'])
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

        @param  mech_context  a Context instance
        @return  A dictionary parameters for baremetal deploy
        """

        port = mech_context.current
        # currently supports only one segment per network
        segment = mech_context.network.network_segments[0]
        vfab_id = self._get_vfab_id(segment[driver_api.PHYSICAL_NETWORK])
        vlanid = segment[driver_api.SEGMENTATION_ID]
        local_link_info = fj_util.get_physical_connectivity(port)
        physical_ports = ','.join(p['port_id'] for p in local_link_info)
        return {
                   "address": self._switch['address'],
                   "username": self._switch['username'],
                   "password": self._switch['password'],
                   "ports": physical_ports,
                   "vfab_id": vfab_id,
                   "vlanid": vlanid,
                   "mac": port['mac_address'],
                   "lag": fj_util.is_lag(local_link_info)
               }

    @log_helpers.log_method_call
    def bind_port(self, context):

        port = context.current
        vnic_type = port['binding:vnic_type']
        LOG.debug("Attempting to bind port %(port)s with vnic_type "
                  "%(vnic_type)s on network %(network)s",
                  {'port': port['id'], 'vnic_type': vnic_type,
                   'network': context.network.current['id']})

        if validate_baremetal_deploy(context):
            params = self.get_physical_net_params(context)
            segments = context.segments_to_bind
            self.setup_vlan(params)
            context.set_binding(segments[0][driver_api.ID],
                                portbindings.VIF_TYPE_OTHER, {},
                                status=const.PORT_STATUS_ACTIVE)


def is_supported(network):
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
    LOG.warning(_LW("%s is not supported. Skip it."), net_type)
    return False


def validate_baremetal_deploy(mech_context):
    """Validate baremetal deploy.

    @param mech_context a context object
    @return True if enable to baremetal deploy otherwise False
    """

    port = mech_context.current
    network = mech_context.network
    if (fj_util.is_baremetal(port) and
       is_supported(network) and fj_util.get_physical_connectivity(port)):
        return True
    return False
