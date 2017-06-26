How to Install
^^^^^^^^^^^^^^

.. code-block:: bash

    pip install networking-fujitsu


Neutron Configuration
^^^^^^^^^^^^^^^^^^^^^

.. NOTE::

    Please edit **/etc/neutron/plugins/ml2/ml2_conf.ini** as follows:
    Following configurations are common to all FOS switches in **fossw_ips**.

Add **fujitsu_fossw** to **mechanism_drivers** option.

.. code-block:: ini

    mechanism_drivers = openvswitch,fujitsu_fossw

Both **type_drivers** and **tenant_network_types** in **[ml2]** section
should include **vlan** or **vxlan**.  (This driver supports VLAN and VXLAN
of neutron network)

.. code-block:: ini

    [ml2]
    type_drivers = vlan,vxlan
    tenant_network_types = vlan,vxlan

The following parameters should specify after **[fujitsu_fossw]**.

**fossw_ips** (Mandatory)
  The List of IP addresses of all FOS switches.

.. code-block:: ini

    fossw_ips = 192.168.0.1,192.168.0.2,...

**username** (Mandatory)
  The FOS switches username to use. Please note that the user must have
  administrator rights to configure FOS switches.

.. code-block:: ini

    username = admin

**password** (Optional)
  The FOS switches password to use.

.. code-block:: ini

    password = admin

**port** (Optional)
  The port number which is used for SSH connection. The default value is 22.

.. code-block:: ini

    port = 22

**timeout** (Optional)
  The timeout of SSH connection. The default value is 30.

.. code-block:: ini

    timeout = 30

**udp_dest_port** (Optional)
  The port number of VXLAN UDP destination on the FOS switches. All
  VXLANs on the switches use this UDP port as the UDP destination port
  in the UDP header when encapsulating. The default value is 4789.

.. code-block:: ini

    udp_dest_port = 4789

**ovsdb_vlanid_range_min** (Optional)
  The minimum VLAN ID in the range that is used for binding VNI and
  physical port. The range of 78 VLAN IDs (starts from this value) will
  be reserved.  The default value is 2 (VLAN ID from 2 to 79 will be reserved).

.. code-block:: ini

    ovsdb_vlanid_range_min = 2

.. NOTE::

    DO NOT include VLAN IDs specified by **ovsdb_vlanid_range_min** into
    **network_vlan_ranges** in **/etc/neutron/plugins/ml2/ml2_conf.ini**.

**ovsdb_port** (Optional)
  The port number which OVSDB server on the FOS switches listen.
  The default value is 6640.

.. code-block:: ini

    ovsdb_port = 6640

FOS Switch Configuration
^^^^^^^^^^^^^^^^^^^^^^^^

The following configurations are necessary for all FOS switches in case of
**VXLAN** network.

1. Enable IP routing.

   .. code-block:: ini

       configure
       ip routing

2. Enable vxlan service.

   .. code-block:: ini

       vxlan enable

3. Set VTEP IP address for switch side.

   .. code-block:: ini

       vxlan vtep source-ip 192.167.3.111

4. Set port number of VXLAN UDP destination, which is specified as
   **udp_dest_port**

   .. code-block:: ini

       vxlan udp-dst-port 4789

5. Set IP address for physical port which is connected to OpenStack controller
   node. The value of IP address equals to VTEP IP address of switch.

   .. code-block:: ini

       interface 0/10
       ip address 192.167.3.111 255.255.255.0

6. Enable routing of the physical port.

   .. code-block:: ini

       routing

7. Return to Privileged EXEC mode.

   .. code-block:: ini

       end

8. Set port number of OVSDB server in the FOS switch, which is specified as
   **ovsdb_port**.

   .. code-block:: ini

       ovsdb
       ovsdb tcp port 6640

9. Check **ovsdb_vlanid_range_min** and confirm that the VLAN ID within the
   range from **ovsdb_vlanid_range_min** to **ovsdb_vlanid_range_min + 77**
   are not defined.

   .. code-block:: ini

       show vlan

10. Save configurations.

    .. code-block:: ini

        copy system:running-config nvram:startup-config
