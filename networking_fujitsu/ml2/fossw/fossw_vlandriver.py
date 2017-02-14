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

from oslo_config import cfg
from oslo_log import log as logging

from networking_fujitsu._i18n import _LE
from networking_fujitsu.ml2.fossw import client
from neutron.common import utils

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
            res_mac = self.client.get_switch_mac()
            index = res_mac.rfind('. ') + 2
            switch_mac = res_mac[index:(index + 17)]
            switches_mac_ip_pair.update({switch_mac.lower(): ip})
            self.client.disconnect()
        return switches_mac_ip_pair

    @utils.synchronized(_LOCK_NAME)
    def create_vlan(self, ip, vlan_id):
        """Create VLAN with specified VLAN ID.

        :param ip: IP address of target FOS switch
        :type ip: string
        :param vlan_id: ID of VLAN to be created
        :type vlan_id: string

        :returns: None
        :rtype: None

        """
        method = 'create_vlan'
        try:
            self.client.connect(ip)
            self.client.create_vlan(vlan_id)
            self.client.disconnect()
        except Exception as e:
            self.client.disconnect()
            LOG.exception(_LE("an error occurred while creating vlan to FOS "
                              "switch. %s"), e)
            raise client.FOSSWClientException(method)

    @utils.synchronized(_LOCK_NAME)
    def delete_vlan(self, ip, vlan_id):
        """Delete VLAN with specified VLAN ID.

        :param ip: IP address of target FOS switch
        :type ip: string
        :param vlan_id: ID of VLAN to be deleted
        :type vlan_id: string

        :returns: None
        :rtype: None

        """
        method = 'delete_vlan'
        try:
            self.client.connect(ip)
            self.client.delete_vlan(vlan_id)
            self.client.disconnect()
        except Exception as e:
            self.client.disconnect()
            LOG.exception(_LE("an error occurred while deleting vlan from "
                              "FOS switch. %s"), e)
            raise client.FOSSWClientException(method)

    @utils.synchronized(_LOCK_NAME)
    def setup_vlan(self, vlan_id, lli, ip_mac_pairs):
        """Setup VLAN for physical port on FOS Switch.

        :param vlan_id: the ID of VLAN to be associated
        :type vlan_id: string
        :param lli: the local link information of ironic node
        :type lli: list of local link information dictionary
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switch
        :type ip_mac_pairs: dictionary

        :returns: None
        :rtype: None

        """
        method = "setup_vlan"
        try:
            target_ip = ip_mac_pairs[lli[0]['switch_id']]
        except KeyError as e:
            LOG.exception(_LE("Valid IP and MAC pair is: %s"), ip_mac_pairs)
            LOG.exception(
                _LE("Target FOS Switch which have MAC address(%(mac)s) "
                    "not found. %(err)s"),
                {'mac': lli[0]['switch_id'], 'err': e}
            )
            raise client.FOSSWClientException(method)
        except Exception as e:
            LOG.exception(
                _LE("fossw driver caught unexpected error. %s"), e
            )
            raise client.FOSSWClientException(method)
        self.client.connect(target_ip)
        self.client.set_vlan(vlan_id, lli[0]['port_id'])
        self.client.disconnect()

    @utils.synchronized(_LOCK_NAME, external=True)
    def setup_vlan_with_lag(self, vlan_id, llis, ip_mac_pairs):
        """Setup VLAN and LAG for physical ports FOS switch.

        :param vlan_id: the ID of VLAN to be associated
        :type vlan_id: string
        :param llis: the local link informations of ironic node
        :type llis: list of local link informations dictionary
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switch
        :type ip_mac_pairs: dictionary

        :returns: None
        :rtype: None

        """
        method = "setup_vlan_with_lag"
        mlag = None
        switch_mac_list = []
        for lli in llis:
            switch_mac_list.add(lli['switch_id'])
        unique_mac_list = set(switch_mac_list)
        if len(unique_mac_list) > 1:
            if not self.is_valid_mlag(unique_mac_list, ip_mac_pairs):
                LOG.exception(
                    _LE("Specified switches cannot set mLAG pair. "
                        "Please confirm each switch's peerlink setting.")
                )
                raise self.client.FOSSWClientException(method)
            mlag = True

        # setup vlan for each physical port
        for lli in llis:
            arr_lli = []
            arr_lli.append(lli)
            self.setup_vlan(vlan_id, arr_lli, ip_mac_pairs)

        # Create lag resource
        lag = {}
        for mac in unique_mac_list:
            target_ip = ip_mac_pairs[mac]

            lag_ports = []
            for lli in llis:
                if lli['switch_id'] is mac:
                    lag_ports.append(lli['port_id'])

            lag.update({mac: lag_ports})
            self.client.connect(target_ip)
            lag_portname = self.client.get_free_logicalport()
            for port in lag[mac]:
                self.client.join_to_lag(port, lag_portname)
            if mlag:
                vpcid = self.client.get_free_vpcid()
                self.client.join_to_vpc(target_ip, lag_portname, vpcid)
            self.client.disconnect()

    @utils.synchronized(_LOCK_NAME, external=True)
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
        first_switch = ip_mac_pairs[macs[0]]
        mlag_partner_ip = self.client.get_peerlink_pertner(first_switch)
        if mlag_partner_ip == macs[1]:
            return True
        else:
            return False

    @utils.synchronized(_LOCK_NAME)
    def clear_vlan(self, vlan_id, lli, ip_mac_pairs):
        """Clear VLAN from FOS switch.

        :param vlan_id: the ID of VLAN to be disassociated
        :type vlan_id: string
        :param lli: the local link information of ironic node
        :type lli: list
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switches
        :type ip_mac_pairs: dictionary
        """
        method = "clear_vlan"
        try:
            target_ip = ip_mac_pairs[lli[0]['switch_id']]
        except KeyError as e:
            LOG.exception(_LE("Valid IP and MAC pair is: %s"), ip_mac_pairs)
            LOG.error(_LE("Target FOS Switch whitch have MAC address(%(mac)s "
                          "not found. %(err)s"),
                      {'mac': lli[0]['switch_id'], 'err': e})
            raise client.FOSSWClientException(method)
        try:
            self.client.connect(target_ip)
            self.client.clear_vlan(vlan_id, lli[0]['port_id'])
            self.client.disconnect()
        except Exception as e:
            self.client.disconnect()
            LOG.exception(_LE("an error occurred while clearing VLAN from "
                              "physical port on FOS switch. %s"), e)
            raise client.FOSSWClientException(method)

    @utils.synchronized(_LOCK_NAME, external=True)
    def clear_vlan_with_lag(self, vlan_id, llis, ip_mac_pairs):
        """Clear VLAN and LAG from FOS switch.

        :param vlan_id: the ID of VLAN to be disassociated
        :type vlan_id: string
        :param llis: the local link informations of ironic node
        :type vlan_id: list
        :param ip_mac_pairs: the pair of MAC address and IP address of FOS
                             switches
        :type ip_mac_pairs: dictionary

        :returns: None
        :rtype: None

        """
        method = "clear_vlan_with_lag"
        mlag = None
        switch_mac_list = []
        for lli in llis:
            switch_mac_list.append(lli['switch_id'])
        unique_mac_list = set(switch_mac_list)
        if len(unique_mac_list) > 1:
            if not self.is_valid_mlag(unique_mac_list, ip_mac_pairs):
                LOG.exception(_LE("Specified switches are not able to clear "
                                  "mLAG pair. Please confirm each switch's "
                                  "peerlink setting."))
                raise client.FOSSWClientException(method)
            mlag = True

        for mac in unique_mac_list:
            target_ip = ip_mac_pairs[mac]
            portname = None
            for lli in llis:
                if mac is lli['switch_id']:
                    portname = lli['port_id']
            self.client.connect(target_ip)
            lag_portname = self.client.get_lagname(portname)

            if mlag:
                for i in iter(range(64)):
                    res = self.client.get_vpc_interface(i + 1)
                    if lag_portname in res:
                        self.client.clear_vpc(lag_portname, i)
            self.client.clear_lag(lag_portname)

        # Clear lag setting
        for lli in llis:
            arr_lli = []
            arr_lli.append(lli)
            self.clear_vlan(vlan_id, arr_lli, ip_mac_pairs)
