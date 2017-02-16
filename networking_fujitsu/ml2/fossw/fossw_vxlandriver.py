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

from oslo_config import cfg
from oslo_log import log as logging

from networking_fujitsu._i18n import _LI
from networking_fujitsu._i18n import _LW
from networking_fujitsu.ml2.common.ovsdb import ovsdb_writer
from networking_fujitsu.ml2.common import type_vxlan
from networking_fujitsu.ml2.fossw import client
from networking_fujitsu.ml2.fossw import fossw_vlandriver

from neutron.common import utils

LOG = logging.getLogger(__name__)
_LOCK_NAME = 'fujitsu_fossw'


class FOSSWVxlanDriver(object):
    """Fossw CLI interface driver for Neutron network.

    Handles life-cycle management of Neutron network (OVSDB on FOSSW)
    """

    def __init__(self, conf=None):
        if conf:
            self._conf = conf
        else:
            self._conf = cfg.CONF
        self.ovsdb_port = self._conf.fujitsu_fossw.ovsdb_port
        self.udp_dest_port = self._conf.fujitsu_fossw.udp_dest_port
        self.ovsdb_vlanid_range_min = (
            self._conf.fujitsu_fossw.ovsdb_vlanid_range_min)
        self.fossw_ips = self._conf.fujitsu_fossw.fossw_ips

        self.client = client.FOSSWClient(self._conf)
        self.type_vxlan = type_vxlan.TypeVxlan()
        self.vxlan_endpoint_ips = []
        self.initialize()

    def initialize(self):
        """Initialize update

        Both update Neutron DB with switch VTEPs, and update FOS switches
        with host & other switches' VTEPs.
        """

        self.ml2_tenant_network_types = cfg.CONF.ml2.tenant_network_types
        if "vxlan" in self.ml2_tenant_network_types:
            self._update_neutron_db()
            self.vxlan_endpoint_ips = [vxlan_endpoint['ip_address']
                                       for vxlan_endpoint in
                                       self.type_vxlan.get_endpoints()]

    def _save_all_fossw(self):
        """Save running-config to startup-config in all FOS switches."""
        for fossw_ip in self.fossw_ips:
            self.client.connect(fossw_ip)
            self.client.save_running_config()
            self.client.disconnect()

    def _update_neutron_db(self):
        """Update Neutron DB ml2_vxlan_endpoints table

        Update with VTEPs of all FOS switches.
        :returns: None
        """

        for target_ip in self.fossw_ips:
            ovsdb_client = ovsdb_writer.OVSDBWriter(target_ip, self.ovsdb_port)
            sw_ep_ip, sw_ep_host = ovsdb_client.get_sw_ep_info()
            if not sw_ep_host:
                sw_ep_host = "FOSSW"
            if sw_ep_ip:
                neutron_db = self.type_vxlan.get_endpoint_by_ip(
                    sw_ep_ip)
                if not neutron_db:
                    LOG.info(_LI("Add FOS switch endpoint information (ip = "
                                 "%(ip)s, hostname = %(name)s, udp_dest_port "
                                 "= %(port)s) to ml2_vxlan_endpoints table in "
                                 "Neutron DB."), {'ip': sw_ep_ip,
                                                  'name': sw_ep_host,
                                                  'port': self.udp_dest_port})
                    self.type_vxlan.add_endpoint(sw_ep_ip, sw_ep_host,
                                                 self.udp_dest_port)
                elif (neutron_db['host'] != sw_ep_host or
                      neutron_db['udp_port'] != self.udp_dest_port):
                    LOG.warning(_LW("Existed endpoint information with same "
                                    "IP address (%(ip)s) has been updated "
                                    "with hostname = %(host)s, udp_dest_port "
                                    "= %(port)s."),
                                {'ip': sw_ep_ip, 'host': sw_ep_host,
                                 'port': self.udp_dest_port})
                    self.type_vxlan.delete_endpoint(sw_ep_ip)
                    self.type_vxlan.add_endpoint(sw_ep_ip, sw_ep_host,
                                                 self.udp_dest_port)
                else:
                    LOG.info(_LI("FOS switch endpoint information (ip = "
                                 "%(ip)s, hostname = %(name)s, udp_dest_port "
                                 "= %(port)s) has alreadly been added to "
                                 "ml2_vxlan_endpoints table in Neutron DB. "
                                 "Do nothing."),
                             {'ip': sw_ep_ip, 'name': sw_ep_host,
                              'port': self.udp_dest_port})
            else:
                LOG.warning(_LW("Unable to get endpoint information from "
                                "switch (IP = %s). Skip."), target_ip)

    @utils.synchronized(_LOCK_NAME, external=True)
    def create_logical_switch(self, net_uuid, vnid):
        """Create a row in Logical_Switch table in FOS switch OVSDB.

        We consider net_uuid is always unique, and both vnid and net_uuid
        must be immutable. So there is not a update case.
        :param net_uuid: The uuid of Neutron network.
        :type net_uuid: string
        :param vnid: The segment ID of Neutron network.
        :type vnid: integer

        :returns: None
        """

        logical_switch_name = net_uuid.replace("-", "")
        for switch_ip in self.fossw_ips:
            ovsdb_client = ovsdb_writer.OVSDBWriter(switch_ip,
                                                    self.ovsdb_port)
            ovsdb_client.insert_logical_switch(vnid, logical_switch_name)
        self._save_all_fossw()

    @utils.synchronized(_LOCK_NAME, external=True)
    def delete_logical_switch(self, net_uuid):
        """Delete row in Logical_Switch table in FOS switch OVSDB.

        We only consider deleting the existing Logical_Switch ROW.
        Also note that even it does not exit, the jsonrpc returns no error.
        :param net_uuid: The uuid of Neutron network.
        :type: string

        :returns: None
        """

        logical_switch_name = net_uuid.replace("-", "")
        for switch_ip in self.fossw_ips:
            ovsdb_client = ovsdb_writer.OVSDBWriter(switch_ip,
                                                    self.ovsdb_port)
            logical_switch_uuid = ovsdb_client.get_logical_switch_uuid(
                logical_switch_name)
            if logical_switch_uuid:
                ovsdb_client.delete_logical_switch(logical_switch_uuid)
        self._save_all_fossw()

    @utils.synchronized(_LOCK_NAME, external=True)
    def update_physical_port(self, vnid, lli, port_context, ip_mac_pairs):
        """Update Physical_Port table in FOS switch OVSDB.

        There are 3 cases about port operation
        Case 1:
        Port in FOS switch need to get bind. In this case, Ucast_Macs_Local
        table and Physical_locator table also need to insert a new row or
        update at the same time.
        Case 2:
        Another FOS switch has updated its port. In this case, other FOS
        switches need to sync the information to Ucast_Macs_Remote table and
        Physical_locator table.
        Case 3:
        Nova Compute Node has created a new VM or something others occurred
        around Neutron network. In this case, all FOS switches should do the
        same thing as in Case 2.

        :param vnid: The segment ID of Neutron network which the port belongs
                     to.
        :type vnid: integer
        :param lli: The local_link_information of the port.
                    If it is a VM port, then [{}] should be given.
        :type lli: list
        :param port_context: Context of the port.
        :type port_context: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary

        :returns: None
        """

        if lli[0]:
            target_name = lli[0]['switch_info']
            target_ip = ip_mac_pairs[lli[0]['switch_id']]
            port_id = lli[0]['port_id']
        else:
            target_name = port_context['binding:host_id']
            target_ip = ""
            # In this case, it will be a VM port, and we do not need to
            # care about port_id.

        target_tunnel_ip = self.type_vxlan.db_get_endpoint_ip_by_host(
            target_name)
        net_uuid = port_context["network_id"]
        port_mac = port_context["mac_address"]
        fixed_ips = port_context["fixed_ips"]
        port_ips = []
        for fixed_ip in fixed_ips:
            port_ips.append(fixed_ip["ip_address"])

        if target_ip in self.fossw_ips:
            # Update Physical_Port table first.
            ovsdb_client = ovsdb_writer.OVSDBWriter(target_ip,
                                                    self.ovsdb_port)
            logical_switch_name = net_uuid.replace("-", "")
            bind_ls_uuid = ovsdb_client.get_logical_switch_uuid(
                logical_switch_name)
            binding_vid = ovsdb_client.get_binding_vid(bind_ls_uuid)
            if binding_vid:
                bind_vid = binding_vid
            else:
                bind_vid = (int(port_id[2:]) + 1 + self.ovsdb_vlanid_range_min
                            - 2)

            ovsdb_client.update_physical_port(port_id, bind_vid, bind_ls_uuid)

            # After Physical_Port table has been updated, update
            # Ucast_Macs_Local table.
            # If any garbage exist, remove them first.
            if ovsdb_client.get_ucast_macs_local(port_mac):
                ovsdb_client.delete_ucast_macs_local(port_mac)
            # Then add what we want to the Ucast_Macs_Local table.
            locator_ip_local, sw_ep_host = ovsdb_client.get_sw_ep_info()
            locator_uuid_local = ovsdb_client.get_physical_locator_uuid(
                locator_ip_local)
            # We do not care about port IP address. We only forward using port
            # MAC address.
            if locator_uuid_local:
                ovsdb_client.insert_ucast_macs_local(
                    bind_ls_uuid, locator_uuid_local, port_mac)
            else:
                ovsdb_client.insert_ucast_macs_local_and_locator(
                    bind_ls_uuid, locator_ip_local, port_mac)

        # At last Ucast_Macs_Remote table of other switches.
        self._update_ucast_macs_remote(target_ip, logical_switch_name,
                                       port_mac, target_tunnel_ip, port_ips)
        self._save_all_fossw()

    def _update_ucast_macs_remote(self, target_ip, logical_switch_name,
                                  port_mac, target_tunnel_ip, port_ips):
        """Update Ucast_Macs_Remote table in all FOS switches OVSDB."""
        for fossw_ip in self.fossw_ips:
            if fossw_ip != target_ip:
                ovsdb_client = ovsdb_writer.OVSDBWriter(fossw_ip,
                                                        self.ovsdb_port)
                ls_uuid = ovsdb_client.get_logical_switch_uuid(
                    logical_switch_name)
                if ovsdb_client.get_ucast_macs_remote(port_mac):
                    ovsdb_client.delete_ucast_macs_remote(port_mac)
                locator_uuid = ovsdb_client.get_physical_locator_uuid(
                    target_tunnel_ip)
                if locator_uuid:
                    ovsdb_client.insert_ucast_macs_remote(
                        ls_uuid, port_mac, port_ips, locator_uuid)
                else:
                    ovsdb_client.insert_ucast_macs_remote_and_locator(
                        ls_uuid, port_mac, port_ips, target_tunnel_ip)

    @utils.synchronized(_LOCK_NAME, external=True)
    def reset_physical_port(self, lli, port_context, ip_mac_pairs):
        """Remove setting of raw of Physical_Port table in FOS switch OVSDB.

        ROWs with the same MAC address in Ucast_Macs_Local table and
        Ucast_Macs_Remote table are the target to extinct.

        :param lli: The local_link_information of the port.
        :type lli: list
        :param port_context: Context of the port.
        :type port_context: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary

        :returns: None
        """

        if lli[0]:
            target_ip = ip_mac_pairs[lli[0]['switch_id']]
            port_id = lli[0]['port_id']
        else:
            target_ip = ""
            # In this case, it will be a VM port, and we do not need to
            # care about port_id.

        port_mac = port_context["mac_address"]

        if target_ip in self.fossw_ips:
            ovsdb_client = ovsdb_writer.OVSDBWriter(target_ip,
                                                    self.ovsdb_port)
            ovsdb_client.reset_physical_port(port_id)
        for fossw_ip in self.fossw_ips:
            # All Ucast_Macs_Remote and Ucast_Macs_Local tables in all
            # FOS switches will delete the ROW with the MAC address.
            ovsdb_client = ovsdb_writer.OVSDBWriter(fossw_ip,
                                                    self.ovsdb_port)
            ovsdb_client.delete_ucast_macs_local(port_mac)
            ovsdb_client.delete_ucast_macs_remote(port_mac)
        self._save_all_fossw()

    @utils.synchronized(_LOCK_NAME, external=True)
    def update_physical_port_with_lag(self, vnid, llis, port_context,
                                      ip_mac_pairs):
        """Update Physical_Port table in FOS switch OVSDB.

        (lag case)
        :param vnid: The segment ID of Neutron network which the port belongs
                     to.
        :type vnid: integer
        :param llis: `local_link_information' of 'binding:profile' for the port
                     multiple physical ports(dict) should be given.
        :type llis: list
        :param port_context: Context of the port.
        :type port_context: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary

        :returns: None
        """

        vlan_id = 1
        fossw_vlandriver.FOSSWVlanDriver().setup_vlan_with_lag(
            vlan_id, llis, ip_mac_pairs)

        # setup ovsdb for each physical port
        for lli in llis:
            self.update_physical_port(vnid, lli, self.fossw_ips,
                                      port_context, ip_mac_pairs)

    @utils.synchronized(_LOCK_NAME, external=True)
    def reset_physical_port_with_lag(self, llis, port_context, ip_mac_pairs):
        """Remove setting of raw of Physical_Port table in FOS switch OVSDB.

        (lag case)
        :param llis: `local_link_information' of 'binding:profile' for the port
                     multiple physical ports(dict) should be given.
        :type llis: list
        :param port_context: Context of the port.
        :type port_context: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary

        :returns: None
        """

        vlan_id = 1
        fossw_vlandriver.FOSSWVlanDriver().clear_vlan_with_lag(
            vlan_id, llis, ip_mac_pairs)

        # Clear lag setting
        for lli in llis:
            self.reset_physical_port(lli, self.fossw_ips,
                                     port_context, ip_mac_pairs)
