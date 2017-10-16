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

import copy

from neutron.common import utils
from neutron_lib import context
from oslo_config import cfg
from oslo_log import log as logging

from networking_fujitsu.ml2.common.ovsdb import ovsdb_writer
from networking_fujitsu.ml2.common import tunnel_caller
from networking_fujitsu.ml2.common import type_vxlan
from networking_fujitsu.ml2.fossw import client

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
        self.tunnel_caller = tunnel_caller.TunnelCaller()
        self.initialize()

    def initialize(self):
        """Initialize update

        Both update Neutron DB with switch VTEPs, and update FOS switches
        with host & other switches' VTEPs.
        """

        if "vxlan" in self._conf.ml2.type_drivers:
            self._update_neutron_db()
            self.vxlan_endpoint_ips = [vxlan_endpoint['ip_address']
                                       for vxlan_endpoint in
                                       self.type_vxlan.get_endpoints()]

    def save_all_fossw(self):
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

        for fossw_ip in self.fossw_ips:
            ovsdb_cli = ovsdb_writer.OVSDBWriter(fossw_ip, self.ovsdb_port)
            sw_ep_ip, sw_ep_host = ovsdb_cli.get_sw_ep_info()
            if not sw_ep_host:
                sw_ep_host = "FOSSW"
            if sw_ep_ip:
                neutron_db = self.type_vxlan.get_endpoint_by_ip(
                    sw_ep_ip)
                if not neutron_db:
                    LOG.info("Add FOS switch endpoint information (ip = "
                             "%(ip)s, hostname = %(name)s, udp_dest_port "
                             "= %(port)s) to ml2_vxlan_endpoints table in "
                             "Neutron DB.",
                             {'ip': sw_ep_ip,
                              'name': sw_ep_host,
                              'port': self.udp_dest_port})
                    self.type_vxlan.add_endpoint(sw_ep_ip, sw_ep_host,
                                                 self.udp_dest_port)
                elif (neutron_db['host'] != sw_ep_host or
                      neutron_db['udp_port'] != self.udp_dest_port):
                    LOG.warning("Existed endpoint information with same "
                                "IP address (%(ip)s) has been updated "
                                "with hostname = %(host)s, udp_dest_port "
                                "= %(port)s.",
                                {'ip': sw_ep_ip, 'host': sw_ep_host,
                                 'port': self.udp_dest_port})
                    self.type_vxlan.delete_endpoint(sw_ep_ip)
                    self.type_vxlan.add_endpoint(sw_ep_ip, sw_ep_host,
                                                 self.udp_dest_port)
                else:
                    LOG.info("FOS switch endpoint information (ip = "
                             "%(ip)s, hostname = %(name)s, udp_dest_port "
                             "= %(port)s) has alreadly been added to "
                             "ml2_vxlan_endpoints table in Neutron DB. "
                             "Do nothing.",
                             {'ip': sw_ep_ip, 'name': sw_ep_host,
                              'port': self.udp_dest_port})
            else:
                LOG.warning("Unable to get endpoint information from "
                            "switch (IP = %s). Skip.", fossw_ip)

    @utils.synchronized(_LOCK_NAME, external=True)
    def create_logical_switch(self, net_uuid, vni, save=True):
        """Create a row in Logical_Switch table in FOS switch OVSDB.

        We consider net_uuid is always unique, and both vni and net_uuid
        must be immutable. So there is not a update case.
        :param net_uuid: The uuid of Neutron network.
        :type net_uuid: string
        :param vni: The segment ID of Neutron network.
        :type vni: integer

        :returns: None
        """

        for fossw_ip in self.fossw_ips:
            ovsdb_cli = ovsdb_writer.OVSDBWriter(fossw_ip, self.ovsdb_port)
            ovsdb_cli.insert_logical_switch(vni, net_uuid.replace("-", ""))
        if save:
            self.save_all_fossw()

    @utils.synchronized(_LOCK_NAME, external=True)
    def delete_logical_switch(self, net_uuid, save=True):
        """Delete row in Logical_Switch table in FOS switch OVSDB.

        We only consider deleting the existing Logical_Switch ROW.
        Also note that even it does not exit, the jsonrpc returns no error.
        :param net_uuid: The uuid of Neutron network.
        :type: string

        :returns: None
        """

        ls_name = net_uuid.replace("-", "")
        for fossw_ip in self.fossw_ips:
            ovsdb_cli = ovsdb_writer.OVSDBWriter(fossw_ip, self.ovsdb_port)
            ls_uuid = ovsdb_cli.get_logical_switch_uuid(ls_name)
            if ls_uuid:
                ovsdb_cli.delete_logical_switch(ls_uuid)
        if save:
            self.save_all_fossw()

    def update_physical_port(self, vni, lli, port, ip_mac_pairs, req_id=None,
                             mac_lag_map=None, save=True):
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

        :param vni: The segment ID of Neutron network which the port belongs
                     to.
        :type vni: integer
        :param lli: The local_link_information of the port.
                    If it is a VM port, then [{}] should be given.
        :type lli: list
        :param port: Dictionary of a port
        :type port: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary

        :returns: None
        """

        ls_name = port["network_id"].replace("-", "")
        mac = port["mac_address"]
        port_ips = [fixed_ip['ip_address'] for fixed_ip in port["fixed_ips"]]
        host_id = port['binding:host_id']
        target_ip = ip_mac_pairs[lli[0]['switch_id']] if lli else None
        target = lli[0]['switch_info'] if lli else host_id
        tunnel_ip = self.type_vxlan.db_get_endpoint_ip_by_host(target)

        if lli:
            sw_port_id = lli[0]['port_id']
            if mac_lag_map:
                lag_port = mac_lag_map.get(lli[0]['switch_id'], None)
            else:
                lag_port = None
            # Update Physical_Port table first.
            ovsdb_cli = ovsdb_writer.OVSDBWriter(target_ip, self.ovsdb_port)
            lsw_id = ovsdb_cli.get_logical_switch_uuid(ls_name)
            binding_vid = ovsdb_cli.get_binding_vid(lsw_id)
            bind_vlanid = binding_vid if binding_vid else (
                int(sw_port_id[2:]) + self.ovsdb_vlanid_range_min - 1)

            bind_port_id = lag_port if lag_port else sw_port_id
            ovsdb_cli.update_physical_port(bind_port_id, bind_vlanid, lsw_id)
            # After Physical_Port table has been updated, update
            # Ucast_Macs_Local table.
            # If any garbage exist, remove them first.
            if ovsdb_cli.get_ucast_macs_local(mac):
                ovsdb_cli.delete_ucast_macs_local(mac)
            # Then add what we want to the Ucast_Macs_Local table.
            locator_ip_local, sw_ep_host = ovsdb_cli.get_sw_ep_info()
            locator_uuid_local = ovsdb_cli.get_physical_locator_uuid(
                locator_ip_local)
            # We do not care about port IP address. We only forward using port
            # MAC address.
            if locator_uuid_local:
                ovsdb_cli.insert_ucast_macs_local(
                    lsw_id, locator_uuid_local, mac)
            else:
                ovsdb_cli.insert_ucast_macs_local_and_locator(
                    lsw_id, locator_ip_local, mac)
            # Create vxlan port for FOS Switch when this method was called with
            # req_id.
            if req_id:
                ctxt = context.Context(request_id=req_id, is_admin=True)
                self.tunnel_caller.trigger_tunnel_sync(ctxt, target_ip)
        # At last Ucast_Macs_Remote table of other switches.
        self._update_ucast_macs_remote(
            target_ip, ls_name, mac, tunnel_ip, port_ips)
        if save:
            self.save_all_fossw()

    def _update_ucast_macs_remote(self, target_ip, logical_switch_name, mac,
                                  tunnel_ip, port_ips):
        """Update Ucast_Macs_Remote table in all FOS switches OVSDB."""
        for fossw_ip in self.fossw_ips:
            if target_ip == fossw_ip:
                continue
            ovsdb_cli = ovsdb_writer.OVSDBWriter(fossw_ip, self.ovsdb_port)
            ls_uuid = ovsdb_cli.get_logical_switch_uuid(logical_switch_name)
            if ovsdb_cli.get_ucast_macs_remote(mac):
                ovsdb_cli.delete_ucast_macs_remote(mac)
            locator_uuid = ovsdb_cli.get_physical_locator_uuid(tunnel_ip)
            if locator_uuid:
                ovsdb_cli.insert_ucast_macs_remote(
                    ls_uuid, mac, port_ips, locator_uuid)
            else:
                ovsdb_cli.insert_ucast_macs_remote_and_locator(
                    ls_uuid, mac, port_ips, tunnel_ip)

    def reset_physical_port(self, lli, port, ip_mac_pairs, save=True):
        """Remove setting of raw of Physical_Port table in FOS switch OVSDB.

        ROWs with the same MAC address in Ucast_Macs_Local table and
        Ucast_Macs_Remote table are the target to extinct.

        :param lli: The local_link_information of the port.
        :type lli: list
        :param port: Context of the port.
        :type port: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary

        :returns: None
        """

        if lli:
            target = ip_mac_pairs[lli[0]['switch_id']]
            port_id = lli[0]['port_id']
            ovsdb_cli = ovsdb_writer.OVSDBWriter(target, self.ovsdb_port)
            # TODO(yushiro): Need to send lag port in case of LAG
            ovsdb_cli.reset_physical_port(port_id)

        mac = port["mac_address"]

        for fossw_ip in self.fossw_ips:
            # All Ucast_Macs_Remote and Ucast_Macs_Local tables in all
            # FOS switches will delete the ROW with the MAC address.
            ovsdb_cli = ovsdb_writer.OVSDBWriter(fossw_ip, self.ovsdb_port)
            ovsdb_cli.delete_ucast_macs_local(mac)
            ovsdb_cli.delete_ucast_macs_remote(mac)
        if save:
            self.save_all_fossw()

    @utils.synchronized(_LOCK_NAME, external=True)
    def update_physical_port_with_lag(self, vni, llis, port, ip_mac_pairs,
                                      req_id, mac_lag_map=None):
        """Call update_physical_port for all physical swtich ports.

        :param vni: The segment ID of Neutron network which the port belongs
                     to.
        :type vni: integer
        :param llis: `local_link_information' of 'binding:profile' for the port
                     multiple physical ports(dict) should be given.
        :type llis: list
        :param port: Dictionary of the port.
        :type port: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary
        :param req_id: A request ID of network context which use for generate
                       new context.
        :type req_id: string

        :returns: None
        """

        for lli in llis:
            self.update_physical_port(
                vni, [lli], port, ip_mac_pairs, req_id,
                mac_lag_map=mac_lag_map)

    @utils.synchronized(_LOCK_NAME, external=True)
    def reset_physical_port_with_lag(self, llis, port, ip_mac_pairs,
                                     mac_lag_map=None):
        """Call reset_physical_port for all physical switch ports.

        :param llis: `local_link_information' of 'binding:profile' for the port
                     multiple physical ports(dict) should be given.
        :type llis: list
        :param port: Dictionary of the port.
        :type port: dictionary
        :param ip_mac_pairs: List of MAC(key) - IP(value) pairs of all FOS
                             switches.
        :type ip_mac_pairs: dictionary

        :returns: None
        """

        # TODO(yushiro): Need to refactor
        targets = []
        if mac_lag_map:
            for lli in llis:
                targets.append({
                    'port_id': mac_lag_map[lli['switch_id']],
                    'switch_id': lli['switch_id']})
        else:
            targets = copy.deepcopy(llis)

        for lli in targets:
            self.reset_physical_port([lli], port, ip_mac_pairs)
