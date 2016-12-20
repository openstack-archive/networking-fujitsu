# Copyright 2015-2016 FUJITSU LIMITED
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

from networking_fujitsu._i18n import _
from networking_fujitsu._i18n import _LW
from neutron.extensions import portbindings
from neutron.plugins.ml2 import driver_api
from oslo_log import log as logging
import re

LOG = logging.getLogger(__name__)
RANGE_DEFINITION = re.compile(r'(\d+)-(\d+)')
_SUPPORTED_NET_TYPES = ['vlan']


def eliminate_val(source, reject):
    """Eliminate specified value from range value.

    ex. source='1,2,3-10', reject=[1], result: '2,3-10'
    @param source a string of range definition separated with ","
           ex. "1,2,3" or "1-5"(same as "1,2,3,4,5")
    @param reject a list of integer to reject. ex. [1, 2]
    @return eliminated a string of eliminated value separated with ","
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
        LOG.debug(_('Reject target doesn\'t exist.'))
    return ','.join(rejected)


def get_network_segments(network):
    """Get network_type and segmentation_id from specified network.

    @param network a network object
    @return network_type a string of network type(ex. "vlan" or "vxlan")
            segmentation_id a integer of segmentation_id
    """

    segment = network.network_segments[0]
    network_type = segment[driver_api.NETWORK_TYPE]
    segmentation_id = segment[driver_api.SEGMENTATION_ID]
    return network_type, segmentation_id


def get_physical_connectivity(port):
    """Get local_link_information from specified port.

    @param port a port object
    @return lli a list of following dict
                {"switch_id": "MAC_of_switch", "port_id": "1/1/0/1",
                 "switch_info": "switch_name"}
    """

    # TODO(yushiro) replace following characters to constant value
    binding_profile = port['binding:profile']
    lli = binding_profile.get("local_link_information", {})
    is_all_specified = True if lli else False
    for i in lli:
        if not (i.get('switch_id') and i.get('port_id') and
                i.get('switch_info')):
            is_all_specified = False
    if is_all_specified:
        return lli
    LOG.warning(_LW("Some physical network param is missing:%s"), lli)
    return {}


def is_baremetal(port):
    """Judge a specified port is for baremetal or not.

    @param port a port object
    @return True/False a boolean baremetal:True, otherwise:False
    """

    vnic_type = port.get(portbindings.VNIC_TYPE, portbindings.VNIC_NORMAL)
    if (vnic_type == portbindings.VNIC_BAREMETAL):
        return True
    else:
        return False


def is_lag(local_link_information):
    """Judge a specified port param is for LAG(linkaggregation) or not.

    @param local_link_information a list of dict
    @return True/False a boolean LAG:True, otherwise:False
    """

    return True if len(local_link_information) > 1 else False
