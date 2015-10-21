# Copyright 2015 FUJITSU LIMITED
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
try:
    from oslo_log import log as logging
except ImportError:
    from neutron.openstack.common import log as logging
try:
    from oslo_utils import importutils
except ImportError:
    from neutron.openstack.common import importutils
try:
    from neutron.i18n import _LE
    from neutron.i18n import _LI
except ImportError:
    try:
        from neutron.openstack.common._i18n import _LE
        from neutron.openstack.common._i18n import _LI
    except ImportError:
        from neutron.openstack.common.gettextutils import _LE
        from neutron.openstack.common.gettextutils import _LI
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.plugins.ml2 import driver_api

LOG = logging.getLogger(__name__)
FUJITSU_DRIVER = 'networking_fujitsu.ml2.drivers.fujitsu.'
CFAB_DRIVER = FUJITSU_DRIVER + 'cfab.cfabdriver.CFABdriver'

VFAB_ID_DEFAULT = "default"
VFAB_ID_MIN = 1
VFAB_ID_MAX = 3000

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

    def create_network_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("create_network_precommit: called")

    def create_network_postcommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("create_network_postcommit: called")

    def delete_network_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("delete_network_precommit: called")

    def delete_network_postcommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("delete_network_postcommit: called")

    def update_network_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("update_network_precommit(self: called")

    def update_network_postcommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("update_network_postcommit(self: called")

    def create_port_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("create_port_precommit: called")

    def create_port_postcommit(self, mech_context):
        """Associate the assigned MAC address to the portprofile."""

        LOG.debug("create_port_postcommit: called")

        port = mech_context.current
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']

        segments = mech_context.network.network_segments
        # currently supports only one segment per network
        segment = segments[0]
        _validate_network_type(
            segment[driver_api.NETWORK_TYPE],
            method="create_port_postcommit")
        vfab_id = self._get_vfab_id(segment[driver_api.PHYSICAL_NETWORK])
        vlan_id = segment[driver_api.SEGMENTATION_ID]

        interface_mac = port['mac_address']

        try:
            self._driver.associate_mac_to_network(self._switch['address'],
                                                  self._switch['username'],
                                                  self._switch['password'],
                                                  vfab_id,
                                                  vlan_id,
                                                  interface_mac)
        except Exception:
            LOG.exception(
                _LE("Fujitsu Mechanism: failed to associate mac %s")
                % interface_mac)
            raise ml2_exc.MechanismDriverError(
                method="create_port_postcommit")

        LOG.info(
            _LI("created port (postcommit): port_id=%(port_id)s "
                "network_id=%(network_id)s tenant_id=%(tenant_id)s"),
            {'port_id': port_id,
             'network_id': network_id, 'tenant_id': tenant_id})

    def delete_port_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("delete_port_precommit: called")

    def delete_port_postcommit(self, mech_context):
        """Dissociate MAC address from the portprofile."""

        LOG.debug("delete_port_postcommit: called")
        port = mech_context.current
        port_id = port['id']
        network_id = port['network_id']
        tenant_id = port['tenant_id']

        segments = mech_context.network.network_segments
        # currently supports only one segment per network
        segment = segments[0]
        _validate_network_type(
            segment[driver_api.NETWORK_TYPE],
            method="delete_port_postcommit")
        vfab_id = self._get_vfab_id(segment[driver_api.PHYSICAL_NETWORK])
        vlan_id = segment[driver_api.SEGMENTATION_ID]

        interface_mac = port['mac_address']

        try:
            self._driver.dissociate_mac_from_network(
                self._switch['address'],
                self._switch['username'],
                self._switch['password'],
                vfab_id,
                vlan_id,
                interface_mac)
        except Exception:
            LOG.exception(
                _LE("Fujitsu Mechanism: failed to dissociate MAC %s") %
                interface_mac)
            raise ml2_exc.MechanismDriverError(
                method="delete_port_postcommit")

        LOG.info(
            _LI("delete port (postcommit): port_id=%(port_id)s "
                "network_id=%(network_id)s tenant_id=%(tenant_id)s"),
            {'port_id': port_id,
             'network_id': network_id, 'tenant_id': tenant_id})

    def update_port_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("update_port_precommit(self: called")

    def update_port_postcommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("update_port_postcommit: called")

    def create_subnet_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("create_subnetwork_precommit: called")

    def create_subnet_postcommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("create_subnetwork_postcommit: called")

    def delete_subnet_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("delete_subnetwork_precommit: called")

    def delete_subnet_postcommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("delete_subnetwork_postcommit: called")

    def update_subnet_precommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("update_subnet_precommit(self: called")

    def update_subnet_postcommit(self, mech_context):
        """Noop now, it is left here for future."""
        LOG.debug("update_subnet_postcommit: called")


def _validate_network_type(network_type, method="_validate_network_type"):
    if network_type != 'vlan':
        LOG.error(
            _LE("Fujitsu Mechanism: only network type vlan is supported"))
        raise ml2_exc.MechanismDriverError(method=method)
