# Copyright 2015-2017 FUJITSU LIMITED
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from neutron_lib.api.definitions import portbindings as pb_def
from neutron_lib.api.definitions import provider_net
from neutron_lib.plugins.ml2 import api
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
RANGE_DEFINITION = re.compile(r'(\d+)-(\d+)')


def eliminate_val(source, reject):
    """Eliminate specified value from range value.

    ex. source='1,2,3-10', reject=[1], result: '2,3-10'
    :param source: a string of range definition separated with ","
    :type source: string
    :param reject: a list of integer to reject. ex. [1, 2]
    :type reject: list of integer

    :returns: a string separated with "," like an example
    :rtype: string
    """
    if source is None:
        return
    values = [str(i) for i in reject]
    rejected = source.split(',')
    found = False
    for val in values:
        for target in rejected:
            m = RANGE_DEFINITION.match(target)
            if m:
                low = m.group(1)
                high = m.group(2)
                if val in target:
                    rejected.remove(target)
                    # matches the lowest one
                    if (val == low):
                        # Case: source is "1-2" and target is "1"
                        if ((int(val) + 1) == int(high)):
                            rejected.append(high)
                        else:
                            rejected.append(str(int(val) + 1) + "-" + high)
                            found = True
                            break
                    # matches the highest one
                    else:
                        # Ex. source is "1-2" and target is "2"
                        if ((int(val) - 1) == int(low)):
                            rejected.append(low)
                        else:
                            rejected.append(low + "-" + str(int(val) - 1))
                        found = True
                        break
                # matches between lower one and higher one
                elif (int(low) < int(val) and int(val) < int(high)):
                    rejected.remove(target)
                    # Ex. source is "1-n" and target is "2"
                    if ((int(val) - 1) == int(low)):
                        rejected.append(low)
                        # Ex. source is "1-3" and target is "2"
                        if ((int(val) + 1) == int(high)):
                            rejected.append(high)
                        # Ex. source is "1-4" and target is "2"
                        else:
                            rejected.append(str(int(val) + 1) + "-" + high)
                    # Ex. source is "n-5" and target is "4"(n is NOT "3")
                    elif ((int(val) + 1) == int(high)):
                        rejected.append(high)
                        rejected.append(low + "-" + str(int(val) - 1))
                    # Ex. source is "1-5" and target is "3"
                    else:
                        rejected.append(low + "-" + str(int(val) - 1))
                        rejected.append(str(int(val) + 1) + "-" + high)
                    found = True
                    break
            # source is not defined with range "-"
            elif val == target:
                rejected.remove(target)
                found = True
                break
    if not found:
        LOG.debug('Reject target doesn\'t exist.')
    return ','.join(rejected)


def _get_provider_attribute(net, net_attr):
    if isinstance(net, dict):
        segment = net['segments'][0] if net.get('segments', None) else net
    else:
        segment = net.network_segments[0]
    try:
        api_attr = getattr(api, net_attr)
        provider_attr = getattr(provider_net, net_attr)
    except AttributeError as e:
        LOG.critical('Attribute(%s) not found. A version of neutron-lib seems '
                     'not to match suitable one. Please check it.', net_attr)
        raise e
    else:
        return segment.get(api_attr, segment.get(provider_attr, None))


def get_network_type(network):
    """Get provider:network_type

    :param network: NetworkContext or network dict
    :type network: NetworkContext or dict

    :returns network_type: 'vlan', 'vxlan', 'local', 'flat' and 'geneve'
    :rtype: string
    """
    return _get_provider_attribute(network, 'NETWORK_TYPE')


def get_segmentation_id(network):
    """Get provider:segmentation_id

    :param network: NetworkContext or network dict
    :type network: NetworkContext or dict

    :returns segmentation_id: VLANID('vlan') or VNI('vxlan')
    :rtype: integer
    """
    return _get_provider_attribute(network, 'SEGMENTATION_ID')


def get_physical_network(network):
    """Get provider:physical_network

    :param network: NetworkContext or network dict
    :type network: NetworkContext or dict

    :returns physical_network: physical network name for the network
    :rtype: string
    """
    return _get_provider_attribute(network, 'PHYSICAL_NETWORK')


def get_physical_connectivity(port):
    """Get local_link_information from specified port.

    :param port: a dictionary of neutron port
    :type port: dictionary

    :returns lli: "local_link_information" as follows
                 [{"switch_id": "MAC_of_switch", "port_id": "1/1/0/1",
                  "switch_info": "switch_name"}]
                 If all of parameter specified, returns above format otherwise
                 empty list
    :rtype: list of dict or empty list
    """

    # TODO(yushiro) replace following characters to constant value
    lli = port['binding:profile'].get("local_link_information", [])
    if not lli:
        return []
    is_all_specified = True
    for i in lli:
        if not (i.get('switch_id') and i.get('port_id') and
                i.get('switch_info')):
            is_all_specified = False
    if is_all_specified:
        return lli
    LOG.warning("Some physical network param is missing:%s", lli)
    return []


def is_baremetal(port):
    """Judge a specified port is for baremetal or not.

    :param port: a dictionary of neutron port
    :type port: dictionary

    :returns: True(vnic_type is baremetal) or False(otherwise)
    :rtype: boolean
    """

    vnic_type = port.get(pb_def.VNIC_TYPE, pb_def.VNIC_NORMAL)
    return (vnic_type == pb_def.VNIC_BAREMETAL)


def is_lag(local_link_information):
    """Judge a specified port param is for LAG(linkaggregation) or not.

    :param local_link_information: physical connectivity information
    :type local_link_information: list of dict

    :returns: True(mode is LAG) or False(otherwise)
    :rtype: boolean
    """

    return (len(local_link_information) > 1)


def is_unbound(context):
    """Judge current port object is unbound or not.

    :param context: port context
    :type context: PortContext object

    :returns: True(port is unbound) or False(otherwise)
    :rtype: boolean
    """
    return (context.current[pb_def.VIF_TYPE] == pb_def.VIF_TYPE_UNBOUND and
            context.original[pb_def.VIF_TYPE] == pb_def.VIF_TYPE_OTHER)
