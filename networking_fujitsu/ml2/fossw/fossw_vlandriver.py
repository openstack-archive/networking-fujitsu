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

"""Fujitsu fossw Driver implements CLI over ssh for Neutron network life-cycle
management.
"""

import copy

from neutron.common import utils
from oslo_config import cfg
from oslo_log import log as logging

from networking_fujitsu.ml2.fossw import client

LOG = logging.getLogger(__name__)
_LOCK_NAME = 'fujitsu-fossw'


class FOSSWVlanDriver(object):
    """Fossw CLI interface driver for Neutron network.

    Handles life-cycle management of Neutron network.
    """

    def __init__(self, conf=None):
        if conf:
            self._conf = conf
        else:
            self._conf = cfg.CONF
        self.client = client.FOSSWClient(self._conf)

    @utils.synchronized(_LOCK_NAME)
    def get_switch_mac_ip_pair(self, ips):
        """Get and create pair of switch's MAC address and IP address.

        :param ips: list of IP address of FOS switch
        :type ips: list of IP address strings

        :returns: the dictionary which stores pair of  MAC address and IP
                  address
        :rtype: dictionary of MAC address and IP address

        """
        switches_mac_ip_pair = {}
        for ip in ips:
            self.client.connect(ip)
            mac = self.client.get_switch_mac()
            if not mac:
                self.client.disconnect()
                LOG.exception('Cannot get MAC address from FOS switch(%s)', ip)
                raise client.FOSSWClientException('get_switch_mac_ip_pair')
            switches_mac_ip_pair.update({mac: ip})
            self.client.disconnect()
        return switches_mac_ip_pair

    def create_vlan(self, ip, vlanid):
        """Create VLAN with specified VLAN ID.

        :param ip: IP address of target FOS switch
        :type ip: string
        :param vlanid: ID of VLAN to be created
        :type vlanid: string

        :returns: None
        :rtype: None

        """
        method = 'create_vlan'
        try:
            self.client.connect(ip)
            self.client.create_vlan(vlanid)
            self.client.disconnect()
        except Exception as e:
            self.client.disconnect()
            LOG.exception("an error occurred while creating vlan to FOS "
                          "switch. %s", e)
            raise client.FOSSWClientException(method)

    def delete_vlan(self, ip, vlanid):
        """Delete VLAN with specified VLAN ID.

        :param ip: IP address of target FOS switch
        :type ip: string
        :param vlanid: ID of VLAN to be deleted
        :type vlanid: string

        :returns: None
        :rtype: None

        """
        method = 'delete_vlan'
        try:
            self.client.connect(ip)
            self.client.delete_vlan(vlanid)
            self.client.disconnect()
        except Exception as e:
            self.client.disconnect()
            LOG.exception("An error occurred while deleting vlan from "
                          "FOS switch. %s", e)
            raise client.FOSSWClientException(method)

    def setup_vlan(self, vlanid, lli, ip_mac_pairs):
        """Setup VLAN for physical port on FOS Switch.

        :param vlanid: the ID of VLAN to be associated
        :type vlanid: string
        :param lli: the local link information of ironic node
        :type lli: list of local link information dictionary
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switch
        :type ip_mac_pairs: dictionary

        :returns: None
        :rtype: None

        """
        method = "setup_vlan"
        sw_mac = lli[0]['switch_id']
        port_id = lli[0]['port_id']

        try:
            target_ip = ip_mac_pairs[sw_mac]
        except KeyError as e:
            LOG.exception("FOS switch with MAC(%s) not found.", sw_mac)
            raise client.FOSSWClientException(method)
        try:
            self.client.connect(target_ip)
            self.client.set_vlan(vlanid, port_id)
            self.client.disconnect()
        except Exception as e:
            self.client.disconnect()
            LOG.exception("An error occurred while setup vlan for "
                          "physical port on FOS switch. %s", e)
            raise client.FOSSWClientException(method)

    @utils.synchronized(_LOCK_NAME, external=True)
    def setup_lag(self, llis, ip_mac_pairs, vlanid=None):
        """Setup VLAN and LAG for physical ports FOS switch.

        :param llis: the local link informations of ironic node
        :type llis: list of local link informations dictionary
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switch
        :type ip_mac_pairs: dictionary
        :param vlanid: the VLANID to configure. If it is not set, it will skip
                       VLAN configuration.
        :type vlanid: Integer

        :returns: mac_lag_map MAC address and LAG port ID pair
        :rtype: dictionary

        """
        method = "setup_lag"
        mlag = False
        unique_mac_list = sorted(list(set([lli['switch_id'] for lli in llis])))
        if len(unique_mac_list) > 1:
            mlag = self.is_valid_mlag(unique_mac_list, ip_mac_pairs)
            if not mlag:
                LOG.exception("Specified switches cannot set mLAG pair. "
                              "Please confirm each switch's peerlink setting.")
                raise client.FOSSWClientException(method)

        # NOTE(takanorimiyagishi): Currently this driver is hard-coded for
        # LAG(802.3ad) setting for FOS switch. When logical ports on FOS switch
        # are set as LAG interface, FOS switch skips VLAN setting of physical
        # port.
        #
        # Setup VLAN for each physical port
        # for lli in llis:
        #     self.setup_vlan(vlanid, [lli], ip_mac_pairs)

        # Create lag resource
        mac_lag_map = {}
        for mac in unique_mac_list:
            target_ip = ip_mac_pairs[mac]
            mac_llis = [lli for lli in llis if lli['switch_id'] == mac]
            ports = [m_lli['port_id'] for m_lli in mac_llis]
            self.client.connect(target_ip)
            lag_port = self.client.get_lag_port()
            if not lag_port:
                self.client.disconnect()
                LOG.exception("Could not find available logicalport in "
                              "switch(%s).", target_ip)
                raise client.FOSSWClientException(method)

            mac_lag_map[mac] = lag_port

            # TODO(yushiro): join_to_lag should be separated following methods:
            # 1. Change status for specified logicalport
            # 2. Insert logicalport into physical_port
            for port in ports:
                self.client.join_to_lag(port, lag_port)

            # Setup VLAN for logical port
            lag_lli = copy.deepcopy(mac_llis[0])
            lag_lli['port_id'] = lag_port
            if vlanid:
                self.setup_vlan(vlanid, [lag_lli], ip_mac_pairs)

            if mlag:
                # Get available VPC id from FOS switch
                vpcid = self.client.get_vpcid()
                if vpcid:
                    self.client.join_to_vpc(lag_port, vpcid)
                else:
                    # All vpc is already used by other logical ports.
                    self.client.disconnect()
                    raise client.FOSSWClientException(method)
            self.client.disconnect()
        return mac_lag_map

    def _validate_lli_macs_with_config(self, macs, ip_mac_pairs):
        ips = [ip_mac_pairs.get(mac, None) for mac in macs]
        if None in ips:
            LOG.error("MAC(%s) in local_link_informatio doesn't match "
                      "with FOS switches", macs)
            raise client.FOSSWClientException('_validate_lli_macs_with_config')
        return ips

    def is_valid_mlag(self, macs, ip_mac_pairs):
        """Validates which given pair of MAC address is valid mlag pair or not.

        :param macs: list of MAC address which mlag candidacy pair
        :type macs: list
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switches
        :type ip_mac_pairs: dictionary

        :returns: Result of validation
        :rtype: Boolean

        """
        try:
            ips = self._validate_lli_macs_with_config(macs, ip_mac_pairs)
            self.client.connect(ips[0])
            partner_ip = self.client.get_peerlink_partner()
            self.client.disconnect()
            return (partner_ip in ips)
        except Exception as e:
            self.client.disconnect()
            LOG.warning("An error occurred while validating specified "
                        "FOS switches are VPC pair. %s", e)
            return False

    def clear_vlan(self, lli, ip_mac_pairs):
        """Clear VLAN from FOS switch.

        :param lli: the local link information of ironic node
        :type lli: list
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switches
        :type ip_mac_pairs: dictionary
        """
        method = "clear_vlan"
        sw_mac = lli[0]['switch_id']
        port_id = lli[0]['port_id']

        try:
            target_ip = ip_mac_pairs[sw_mac]
        except KeyError as e:
            LOG.exception("FOS switch with MAC(%s) not found.", sw_mac)
            raise client.FOSSWClientException(method)
        try:
            self.client.connect(target_ip)
            self.client.clear_vlan(port_id)
            self.client.disconnect()
        except Exception as e:
            self.client.disconnect()
            LOG.exception("an error occurred while clearing VLAN from "
                          "physical port on FOS switch. %s", e)
            raise client.FOSSWClientException(method)

    @utils.synchronized(_LOCK_NAME, external=True)
    def clear_lag(self, llis, ip_mac_pairs):
        """Clear VLAN and LAG from FOS switch.

        :param llis: the local link informations of ironic node
        :type llis: list
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switches
        :type ip_mac_pairs: dictionary

        :returns: None
        :rtype: None

        """
        method = "clear_lag"
        mlag = None
        unique_mac_list = sorted(list(set([lli['switch_id'] for lli in llis])))
        if len(unique_mac_list) > 1:
            mlag = self.is_valid_mlag(unique_mac_list, ip_mac_pairs)
            if not mlag:
                LOG.exception("Specified switches are not able to clear "
                              "mLAG pair. Please confirm each switch's "
                              "peerlink setting.")
                raise client.FOSSWClientException(method)

        mac_lag_map = {}
        for mac in unique_mac_list:
            target_ip = ip_mac_pairs[mac]
            mac_llis = [lli for lli in llis if lli['switch_id'] == mac]
            ports = [m_lli['port_id'] for m_lli in mac_llis]
            self.client.connect(target_ip)
            lag_port = self.client.get_lag_port(mac_llis[0]['port_id'])
            if lag_port:
                if mlag:
                    vpcid = self.client.get_vpcid(lag_port)
                    if vpcid:
                        self.client.leave_from_vpc(lag_port, vpcid)
                    else:
                        LOG.warning(
                            "Specified logicalport has been already "
                            "disassociated with any VPC on the switch(%s). "
                            "skip leave_from_vpc.", target_ip)
                for port in ports:
                    self.client.leave_from_lag(port, lag_port)

                mac_lag_map[mac] = lag_port
                # Clear VLAN for logical port
                lag_lli = copy.deepcopy(mac_llis[0])
                lag_lli['port_id'] = lag_port
                self.clear_vlan([lag_lli], ip_mac_pairs)
            else:
                LOG.warning("Specified logicalport has already cleared. Skip "
                            "clearing LAG.")
            self.client.disconnect()
        # NOTE(takanorimiyagishi): Currently this driver is hard-coded for
        # LAG(802.3ad) setting for FOS switch. When logical port on FOS switch
        # are set as LAG interface, FOS switch ignores VLAN setting of physical
        # port which belongs to the LAG interface.
        #
        # Clear VLAN for each physical port
        # for lli in llis:
        #     self.clear_vlan([lli], ip_mac_pairs)
        return mac_lag_map
