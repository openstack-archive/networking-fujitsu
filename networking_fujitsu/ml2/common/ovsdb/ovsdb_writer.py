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

import ast
import copy
import random
import socket

from oslo_log import log as logging
from oslo_utils import excutils

from networking_fujitsu.ml2.common.ovsdb import base_connection
from networking_fujitsu.ml2.common.ovsdb import constants as n_const

LOG = logging.getLogger(__name__)


class OVSDBWriter(base_connection.BaseConnection):
    """Performs transactions to OVSDB server tables."""
    def __init__(self, ovsdb_ip, ovsdb_port):
        super(OVSDBWriter, self).__init__(ovsdb_ip, ovsdb_port)

    def _send_and_receive(self, query, operation_id, rcv_required):
        # The self.send(query) never fails.
        # Either it returns true, or there will be a Exception there.
        # However, none of the business here.
        LOG.info("OVSDBWriter query: %s", query)
        self.send(query)
        if rcv_required:
            self._get_reply(operation_id)

    def _get_reply(self, operation_id):
        count = 0
        while count < n_const.MAX_RETRIES:
            response = self._recv_data()
            LOG.debug("Response from OVSDB server = %s", str(response))
            if response:
                try:
                    self.response = ast.literal_eval(
                        response.replace(':null', ':None'))
                    if (self.response.get('method', None) != "echo" and
                            self._process_response(operation_id)):
                        return True
                except Exception as ex:
                    with excutils.save_and_reraise_exception():
                        LOG.exception("Exception while receiving the "
                                      "response for the write request: "
                                      "[%s]", ex)

            count += 1
        with excutils.save_and_reraise_exception():
            LOG.exception("Could not obtain response from the OVSDB "
                          "server for the request")

    def _recv_data(self):
        chunks = []
        chunks.append(self.cache[0:])
        lc = rc = 0
        prev_char = None
        while True:
            try:
                response = self.socket.recv(n_const.BUFFER_SIZE)
                if response:
                    for i, c in enumerate(response):
                        if c == '{' and not (prev_char and
                                             prev_char == '\\'):
                            lc += 1
                        elif c == '}' and not (prev_char and
                                               prev_char == '\\'):
                            rc += 1
                        if lc == rc and lc is not 0:
                            chunks.append(response[0:i + 1])
                            self.cache = response[i + 1:]
                            message = "".join(chunks)
                            return message
                        prev_char = c
                    chunks.append(response)
                else:
                    LOG.warning("Did not receive any reply from the OVSDB "
                                "server")
                    return
            except (socket.error, socket.timeout):
                LOG.warning("Did not receive any reply from the OVSDB "
                            "server")
                return

    def _process_response(self, op_id):
        result = self._response(op_id)
        if not result:
            raise base_connection.OVSDBError(
                message="No operation_id(%s) matched to response." % op_id)
        error = result.get("error", None)
        if error:
            raise base_connection.OVSDBError(
                message="Error from the OVSDB server: %s" % error)
        # Check errors in responses of all the subqueries
        outcomes = result.get("result", None)
        if outcomes:
            for outcome in outcomes:
                error = outcome.get("error", None)
                if error:
                    raise base_connection.OVSDBError(
                        message="Error from the OVSDB server: %s" % error)
        return result

    def _response(self, op_id):
        if self.response['id'] == op_id:
            return copy.deepcopy(self.response)

    def get_sw_ep_info(self, rcv_required=True):
        """Get switch endpoint information.

        :returns: (endpoint_ip, endpoint_hostname)
                  endpoint_ip: tunnel_ips in Physical_Switch table
                  endpoint_hostname: name in Physical_Switch table
        :rtype: string, string
        """

        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Physical_Switch',
                             'where': [],
                             'columns': ['tunnel_ips', 'name']}],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)
        try:
            result_rows = self.response['result'][0]['rows']
            return_data = result_rows[0] if result_rows else None
        except Exception as ex:
            with excutils.save_and_reraise_exception():
                LOG.exception("Exception while receiving the "
                              "response for the write request: "
                              "[%s]", ex)
        endpoint_ip = return_data['tunnel_ips'] if return_data else ""
        endpoint_hostname = return_data['name'] if return_data else ""
        return (endpoint_ip, endpoint_hostname)

    def insert_logical_switch(self, tunnel_key, logical_switch_name,
                              rcv_required=True):
        """Insert an entry to Logical_Switch OVSDB table.

        Note that if logical_switch_name has already been inserted,
        constraint violation error will get returned.

        :param tunnel_key: The segment ID of Neutron network.
        :type tunnel_key: integer
        :param logical_switch_name: Neutron network uuid, but delete all '-'
                                    to make sure the length is within 32.
        :type logical_switch_name: string

        :returns: None
        """

        commit_dict = {'op': 'commit', 'durable': True}
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Logical_Switch',
                             'row': {'name': logical_switch_name,
                                     'tunnel_key': tunnel_key}},
                            commit_dict],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def get_logical_switch_uuid(self, logical_switch_name, rcv_required=True):
        """Return _uuid of row in Logical_Switch table with the given name.

        :param logical_switch_name: Neutron network uuid, but delete all '-'
                                    to make sure the length is within 32.
        :type logical_switch_name: string

        :returns: UUID of ROW in Logical_Switch table.
        :rtype: uuid
        """

        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Logical_Switch',
                             'where': [['name', '==', logical_switch_name]]}],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)
        try:
            result_rows = self.response['result'][0]['rows']
            return_data = result_rows[0] if result_rows else None
        except Exception as ex:
            with excutils.save_and_reraise_exception():
                LOG.exception("Exception while receiving the "
                              "response for the write request: "
                              "[%s]", ex)
        return return_data['_uuid'][1] if return_data else ""

    def delete_logical_switch(self, logical_switch_uuid, rcv_required=True):
        """Delete an entry from Logical_Switch OVSDB table.

        Even if the logical_switch_name does not exist, no ERROR will occur.

        :param logical_switch_uuid: UUID of ROW in Logical_Switch table.
        :type logical_switch_uuid: uuid

        :returns: None
        """

        commit_dict = {'op': 'commit', 'durable': True}
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'delete',
                             'table': 'Mcast_Macs_Local',
                             'where': [['logical_switch', '==',
                                        ['uuid', logical_switch_uuid]]]},
                            {'op': 'delete',
                             'table': 'Logical_Switch',
                             'where': [['_uuid', '==',
                                        ['uuid', logical_switch_uuid]]]},
                            commit_dict],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def get_binding_vid(self, logical_switch_uuid, rcv_required=True):
        """Get mapping vlanid of binding-pair in Physical_Port table.

        If the uuid is not binding to any port, returns 0.

        :param logical_switch_uuid: UUID of logical_switch in the binding-pair
                                    mapping.
        :type logical_switch_uuid: uuid

        :returns: vlanid in the binding-pair mapping.
        :rtype: integer
        """

        binding_vid = 0
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Physical_Port',
                             'where': [['vlan_bindings', '!=', ['map', []]]],
                             'columns': ['vlan_bindings']}],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)
        binding_list = []
        try:
            binding_list = self.response["result"][0]["rows"]
        except Exception as ex:
            with excutils.save_and_reraise_exception():
                LOG.exception("Exception while receiving the "
                              "response for the write request: "
                              "[%s]", ex)

        if binding_list:
            for b_c in range(len(binding_list)):
                if (binding_list[b_c]["vlan_bindings"][1][0][1][1] ==
                        logical_switch_uuid):
                    binding_vid = binding_list[b_c]["vlan_bindings"][1][0][0]
                    break
        return binding_vid

    def update_physical_port(self, port_name, vlanid, logical_switch_uuid,
                             rcv_required=True):
        """Update a ROW in Physical_Port OVSDB table.

        Updates Physical Port's VNI to VLAN binding.
        Which also means to connect a physical port (port_name) to a
        Neutron network (logical_switch_uuid).

        :param port_name: Symbolic name for the port of FOS switch.
                          format: <slot/port>
                          example: 0/2
        :type port_name: string
        :param vlanid: Identifier of physical port and logical switch binding.
                        Must be in range 0 to 4095.
        :type vlanid: integer
        :param logical_switch_uuid: UUID of logical_switch in the binding-pair
                                    mapping.
        :type logical_switch_uuid: uuid

        :returns: None
        """

        commit_dict = {'op': 'commit', 'durable': True}
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'update',
                             'table': 'Physical_Port',
                             'where': [['name', '==', port_name]],
                             'row': {
                                 'vlan_bindings': [
                                     'map',
                                     [[vlanid, ['uuid',
                                                logical_switch_uuid]]]]}},
                            commit_dict],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def get_ucast_macs_local(self, port_mac, rcv_required=True):
        """Get ROWs of port_mac in Ucast_Macs_Local table.

        :param port_mac: MAC address of physical port.
        :type port_mac: string

        :returns: list of ROWs information of the given port_mac in
                  Ucast_Macs_Local table.
        :rtype: list
        """

        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Ucast_Macs_Local',
                             'where': [['MAC', '==', port_mac]]}],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)
        try:
            return_list = self.response['result'][0]['rows']
        except Exception as ex:
            with excutils.save_and_reraise_exception():
                LOG.exception("Exception while receiving the "
                              "response for the write request: "
                              "[%s]", ex)
        return return_list if return_list else []

    def delete_ucast_macs_local(self, port_mac, rcv_required=True):
        """Delete ROW(s) from Ucast_Macs_Local table.

        Even if the port_mac does not exist, no ERROR will occur.

        :param port_mac: MAC address of physical port.
        :type port_mac: string

        :returns: None
        """

        commit_dict = {'op': 'commit', 'durable': True}
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'delete',
                             'table': 'Ucast_Macs_Local',
                             'where': [['MAC', '==', port_mac]]},
                            commit_dict],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def get_physical_locator_uuid(self, dst_ip, rcv_required=True):
        """Get _uuid of ROW in Physical_Locator table.

        :param dst_ip: IP address of physical locator.
        :type dst_ip: string

        :returns: uuid of ROW of the given dst_ip in Physical_Locator table.
        :rtype: uuid
        """

        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Physical_Locator',
                             'where': [['dst_ip', '==', dst_ip]]}],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)
        try:
            result_rows = self.response['result'][0]['rows']
            return_data = result_rows[0] if result_rows else None
        except Exception as ex:
            with excutils.save_and_reraise_exception():
                LOG.exception("Exception while receiving the "
                              "response for the write request: "
                              "[%s]", ex)
        return return_data['_uuid'][1] if return_data else ""

    def insert_ucast_macs_local(self, logical_switch_uuid, locator_uuid,
                                MAC_value, rcv_required=True):
        """Insert ROW to Ucast_Macs_Local table.

        :param logical_switch_uuid: uuid of logical switch.
        :type dst_ip: uuid
        :param locator_uuid: uuid of physical locator which its dst_ip is the
                             tunnel_ips of physical switch.
        :type locator_uuid: uuid
        :param MAC_value: MAC address of NIC of baremetal server.
        :type MAC_value: string

        :returns: None
        """

        commit_dict = {'op': 'commit', 'durable': True}
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Local',
                             'row': {'MAC': MAC_value,
                                     'logical_switch': ['uuid',
                                                        logical_switch_uuid],
                                     'locator': ['uuid', locator_uuid]}},
                            commit_dict],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def insert_ucast_macs_local_and_locator(self, logical_switch_uuid,
                                            locator_ip, MAC_value,
                                            rcv_required=True):
        """Insert ROW to Ucast_Macs_Local table.

        :param logical_switch_uuid: uuid of logical switch.
        :type dst_ip: uuid
        :param locator_ip: IP address of physical locator which also is the
                           tunnel_ips of physical switch.
        :type locator_ip: string
        :param MAC_value: MAC address of NIC of baremetal server.
        :type MAC_value: string

        :returns: None
        """

        commit_dict = {'op': 'commit', 'durable': True}
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'insert',
                             'table': 'Physical_Locator',
                             'row': {'dst_ip': locator_ip,
                                     'encapsulation_type': 'vxlan_over_ipv4'
                                     }, 'uuid-name': 'RVTEP'},
                            {'op': 'insert',
                             'table': 'Ucast_Macs_Local',
                             'row': {'MAC': MAC_value,
                                     'logical_switch': ['uuid',
                                                        logical_switch_uuid],
                                     'locator': ['named-uuid', 'RVTEP']}},
                            commit_dict],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def get_ucast_macs_remote(self, port_mac, rcv_required=True):
        """Get ROWs of port_mac in Ucast_Macs_Remote table.

        :param port_mac: MAC address of VM port.
        :type port_mac: string

        :returns: list of ROWs information of the given port_mac in
                  Ucast_Macs_Remote table.
        :rtype: list
        """

        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'select',
                             'table': 'Ucast_Macs_Remote',
                             'where': [['MAC', '==', port_mac]]}],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)
        try:
            return_list = self.response['result'][0]['rows']
        except Exception as ex:
            with excutils.save_and_reraise_exception():
                LOG.exception("Exception while receiving the "
                              "response for the write request: "
                              "[%s]", ex)
        return return_list if return_list else []

    def delete_ucast_macs_remote(self, port_mac, rcv_required=True):
        """Delete ROW(s) from Ucast_Macs_Remote table.

        Even if the port_mac does not exist, no ERROR will occur.

        :param port_mac: MAC address of VM port.
        :type port_mac: string

        :returns: None
        """

        commit_dict = {'op': 'commit', 'durable': True}
        op_id = str(random.getrandbits(128))
        query = {'method': 'transact',
                 'params': [n_const.OVSDB_SCHEMA_NAME,
                            {'op': 'delete',
                             'table': 'Ucast_Macs_Remote',
                             'where': [['MAC', '==', port_mac]]},
                            commit_dict],
                 'id': op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def insert_ucast_macs_remote(self, logical_switch_uuid, MAC_value,
                                 ipaddrs, locator_uuid, rcv_required=True):
        """Insert ROW(s) to Ucast_Macs_Remote table.

        There are two cases:
        Case 1:
            A VM port has been created or updated in a Compute node somewhere.
        Case 2:
            A BM port has been created or updated in another FOS switch.

        :param logical_switch_uuid: uuid of logical switch.
        :type logical_switch_uuid: uuid
        :param MAC_value: MAC address of port.
        :type MAC_value: string
        :param ipaddrs: list of fixed ips pairs to MAC_value.
        :type ipaddrs: list
        :param locator_uuid: uuid of physical locator (remote VTEP) where
                             the port is binding to.
        :type locator_uuid: uuid

        :returns: None
        """

        commit_dict = {"op": "commit", "durable": True}
        op_id = str(random.getrandbits(128))
        params = [n_const.OVSDB_SCHEMA_NAME]
        for ipaddr in ipaddrs:
            params.append({"op": "insert",
                           "table": "Ucast_Macs_Remote",
                           "row": {"MAC": MAC_value,
                                   "logical_switch": ["uuid",
                                                      logical_switch_uuid],
                                   "locator": ["uuid", locator_uuid],
                                   "ipaddr": ipaddr}})
        params.append(commit_dict)
        query = {"method": "transact",
                 "params": params,
                 "id": op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def insert_ucast_macs_remote_and_locator(self, logical_switch_uuid,
                                             MAC_value, ipaddrs, locator_ip,
                                             rcv_required=True):
        """Insert ROW(s) to Ucast_Macs_Remote table.

        Also insert related locator ROW to Pysical_Locator.
        There are two cases:
        Case 1:
        A VM port has been created or updated in a Compute node somewhere.
        Case 2:
        A BM port has been created or updated in another FOS switch.

        :param logical_switch_uuid: uuid of logical switch.
        :type logical_switch_uuid: uuid
        :param MAC_value: MAC address of port.
        :type MAC_value: string
        :param ipaddrs: list of fixed ips pairs to MAC_value.
        :type ipaddrs: list
        :param locator_IP: IP address of physical locator (remote VTEP) where
                           the port is binding to.
        :type locator_uuid: string

        :returns: None
        """

        commit_dict = {"op": "commit", "durable": True}
        op_id = str(random.getrandbits(128))
        params = [n_const.OVSDB_SCHEMA_NAME,
                  {'op': 'insert',
                   'table': 'Physical_Locator',
                   'row': {'dst_ip': locator_ip,
                           'encapsulation_type': 'vxlan_over_ipv4'
                           }, 'uuid-name': 'RVTEP'}]
        for ipaddr in ipaddrs:
            params.append({'op': 'insert',
                           'table': 'Ucast_Macs_Remote',
                           'row': {'MAC': MAC_value,
                                   'logical_switch': ['uuid',
                                                      logical_switch_uuid],
                                   'locator': ['named-uuid', 'RVTEP'],
                                   'ipaddr': ipaddr}})
        params.append(commit_dict)
        query = {"method": "transact",
                 "params": params,
                 "id": op_id}
        self._send_and_receive(query, op_id, rcv_required)

    def reset_physical_port(self, port_name, rcv_required=True):
        """Reset a ROW in Physical_Port table.

        :param port_name: Symbolic name for the port of FOS switch.
                          format: <slot/port>
                          example: 0/2
        :type port_name: string

        :returns: None
        """

        commit_dict = {"op": "commit", "durable": True}
        op_id = str(random.getrandbits(128))
        query = {"method": "transact",
                 "params": [n_const.OVSDB_SCHEMA_NAME,
                            {"op": "update",
                             "table": "Physical_Port",
                             "where": [["name", "==", port_name]],
                             "row": {"vlan_bindings": ["map", []]}},
                            commit_dict],
                 "id": op_id}
        self._send_and_receive(query, op_id, rcv_required)
