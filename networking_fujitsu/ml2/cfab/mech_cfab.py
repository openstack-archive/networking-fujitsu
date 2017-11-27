# Copyright 2015-2017 FUJITSU LIMITED
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

from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron_lib.api.definitions import portbindings as pb_def
from neutron_lib import constants
from neutron_lib.plugins.ml2 import api
from oslo_config import cfg
from oslo_log import helpers as log_helpers
from oslo_log import log as logging
from oslo_utils import importutils

from networking_fujitsu._i18n import _
from networking_fujitsu.ml2.common import utils

LOG = logging.getLogger(__name__)
FUJITSU_DRIVER = 'networking_fujitsu.ml2.'
CFAB_DRIVER = FUJITSU_DRIVER + 'cfab.cfabdriver.CFABdriver'

VFAB_ID_DEFAULT = "default"
VFAB_ID_MIN = 1
VFAB_ID_MAX = 3000
_SUPPORTED_NET_TYPES = [constants.TYPE_VLAN]

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


class CFABMechanismDriver(api.MechanismDriver):
    """ML2 Mechanism driver for Fujitsu C-Fabric switches.

    This is the upper layer driver class that interfaces to lower layer (CLI)
    below.
    """

    def __init__(self):
        self._driver = None
        self._physical_networks = {}
        self._switch = None
        self.initialize()

    def initialize(self):
        """Initialize of variables needed by this class."""

        self._parse_physical_networks()
        self._switch = {
            'address': cfg.CONF.fujitsu_cfab.address,
            'username': cfg.CONF.fujitsu_cfab.username,
            'password': cfg.CONF.fujitsu_cfab.password
        }

        if not self._switch['address']:
            raise cfg.RequiredOptError(
                'address', cfg.OptGroup(ML2_FUJITSU_GROUP))
        self._driver = importutils.import_object(CFAB_DRIVER, cfg.CONF)

    def _parse_physical_networks(self):
        """Interpret physical_networks as physical_network:vfab_id entries."""

        method = "_parse_physical_networks"
        for entry in cfg.CONF.fujitsu_cfab.physical_networks:
            try:
                physical_network, vfab_id = entry.split(':')
            except ValueError:
                LOG.exception("Illegal physical_networks entry")
                raise ml2_exc.MechanismDriverError(method=method)
            if not (vfab_id == VFAB_ID_DEFAULT or
                    VFAB_ID_MIN <= int(vfab_id) <= VFAB_ID_MAX):
                LOG.exception("Illegal VFAB in physical_networks entry")
                raise ml2_exc.MechanismDriverError(method=method)
            self._physical_networks[physical_network] = vfab_id

    def _get_vfab_id(self, physical_network):
        """Get vfab_id corresponding to the physical_network."""

        try:
            vfab_id = self._physical_networks[physical_network]
        except KeyError:
            LOG.exception(
                "Network not found in the configured physical network")
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
        port = mech_context.current
        network = mech_context.network
        if utils.is_baremetal(port):
            return

        if not is_supported(network):
            return

        method = 'create_port_postcommit'
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']
        mac = port['mac_address']
        vfab_id = self._get_vfab_id(utils.get_physical_network(network))
        vlanid = utils.get_segmentation_id(network)

        try:
            self._driver.associate_mac_to_network(
                self._switch['address'],
                self._switch['username'],
                self._switch['password'],
                vfab_id,
                vlanid,
                mac
            )
        except Exception:
            LOG.exception("Failed to associate mac %s", mac)
            raise ml2_exc.MechanismDriverError(method=method)

        LOG.info(
            "created port (postcommit): port_id=%(port_id)s "
            "network_id=%(network_id)s tenant_id=%(tenant_id)s",
            {'port_id': port_id,
             'network_id': network_id, 'tenant_id': tenant_id})

    @log_helpers.log_method_call
    def update_port_postcommit(self, context):
        """Update specified physical port on switch."""

        method = 'update_port_postcommit'
        port = context.current

        if (is_supported(context.network) and utils.is_baremetal(port)
                and utils.is_unbound(context)):
            params = self.get_physical_net_params(context, use_original=True)
            try:
                self.clear_vlan(params)
            except Exception:
                LOG.exception("Failed to clear VLAN(%s)", params['vlanid'])
                raise ml2_exc.MechanismDriverError(method=method)

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
        network = mech_context.network
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']

        if utils.is_baremetal(port):
            if validate_baremetal_deploy(mech_context):
                params = self.get_physical_net_params(mech_context)
                try:
                    self.clear_vlan(params)
                except Exception:
                    LOG.exception("Failed to clear VLAN(%s).",
                                  params['vlanid'])
                    raise ml2_exc.MechanismDriverError(method=method)
        elif is_supported(network):
            physical_network = utils.get_physical_network(network)
            vlanid = utils.get_segmentation_id(network)
            vfab_id = self._get_vfab_id(physical_network)
            mac = port['mac_address']

            try:
                self._driver.dissociate_mac_from_network(
                    self._switch['address'],
                    self._switch['username'],
                    self._switch['password'],
                    vfab_id,
                    vlanid,
                    mac)
            except Exception:
                LOG.exception("Failed to dissociate MAC %s", mac)
                raise ml2_exc.MechanismDriverError(method=method)
        LOG.info(
            "delete port (postcommit): port_id=%(p_id)s "
            "network_id=%(net_id)s tenant_id=%(tenant_id)s",
            {'p_id': port_id, 'net_id': network_id, 'tenant_id': tenant_id})

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
            # This plugin supposes 1 C-Fabric(fabric_id) management.
            # Therefore, not to identify target IP address by using
            # switch_info(mac_address).
            LOG.info("call %(target)s.  params: %(params)s",
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
            LOG.exception("Failed to setup VLAN(%s)", params['vlanid'])
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

        target = 'clear_vlan_with_lag' if params['lag'] else 'clear_vlan'
        try:
            clear_method = getattr(self._driver, target)
            # This plugin supposes 1 C-Fabric(fabric_id) management.
            # Therefore, not to identify target IP address by using
            # switch_info(mac_address).
            LOG.info("Call %(target)s.  params: %(params)s",
                     {'target': target, 'params': params})
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
            LOG.exception("Failed to clear VLAN(%s)", params['vlanid'])
            raise ml2_exc.MechanismDriverError(target)

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

        :param context: PortContext object
        :type port: PortContext
        :param network: a network object
        :type network: NetworkContext
        :param use_original: A flag to use context.original or not
        :type use_original: boolean

        :returns: A dictionary parameters for baremetal deploy
        :rtype: dictionary
        """

        port = context.original if use_original else context.current
        network = context.network
        local_link_info = utils.get_physical_connectivity(port)
        return {
            "address": self._switch['address'],
            "username": self._switch['username'],
            "password": self._switch['password'],
            "ports": ','.join(p['port_id'] for p in local_link_info),
            "vfab_id": self._get_vfab_id(utils.get_physical_network(network)),
            "vlanid": utils.get_segmentation_id(network),
            "mac": port['mac_address'],
            "lag": utils.is_lag(local_link_info)
        }

    @log_helpers.log_method_call
    def bind_port(self, context):

        port = context.current
        LOG.debug("Attempting to bind port %(port)s with vnic_type "
                  "%(vnic_type)s on network %(network)s",
                  {'port': port['id'],
                   'vnic_type': port[pb_def.VIF_TYPE],
                   'network': port['network_id']})

        if validate_baremetal_deploy(context):
            params = self.get_physical_net_params(context)
            segments = context.segments_to_bind
            self.setup_vlan(params)
            context.set_binding(segments[0][api.ID],
                                pb_def.VIF_TYPE_OTHER, {},
                                status=constants.PORT_STATUS_ACTIVE)


def is_supported(network):
    """Validate network parameter(network_type and segmentation_id).

    @param a network object
    @return True if network_type is 'VLAN' and segmentation_id is included
            otherwise False
    """

    net_type = utils.get_network_type(network)
    if net_type not in _SUPPORTED_NET_TYPES:
        LOG.warning("Network type(%s) is not supported. Skip it.",
                    net_type)
        return False
    return True if utils.get_segmentation_id(network) else False


def validate_baremetal_deploy(mech_context):
    """Validate baremetal deploy.

    @param mech_context a context object
    @return True if enable to baremetal deploy otherwise False
    """

    port = mech_context.current
    network = mech_context.network
    if (utils.is_baremetal(port) and
       is_supported(network) and utils.get_physical_connectivity(port)):
        return True
    return False
