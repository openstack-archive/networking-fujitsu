How to Install
--------------

1. Install the package::

    $ pip install networking-fujitsu

2. Add ``fujitsu_fossw`` to mechanism_drivers option in
   /etc/neutron/plugins/ml2/ml2_conf.ini, for example::

    mechanism_drivers = openvswitch,fujitsu_fossw

3. Modify ml2_conf_fujitsu_fossw.ini and make neutron-server to read it.

   For RedHat, add the following options in ExecStart in
   /usr/lib/systemd/system/neutron-server.service::

    --config-file /etc/neutron/plugins/ml2/ml2_conf_fujitsu_fossw.ini

   For Ubuntu, add the following line to /etc/default/neutron-server::

    NEUTRON_PLUGIN_ML2_CONFIG="/etc/neutron/plugins/ml2/ml2_conf_fujitsu_fossw.ini"

   and add the following line before 'exec start-stop-daemon ...' in
   /etc/init/neutron-server.conf::

    [ -r "$NEUTRON_PLUGIN_ML2_CONFIG" ] && CONF_ARG="${CONF_ARG} --config-file $NEUTRON_PLUGIN_ML2_CONFIG"

Configuration
-------------

Both VLAN and VXLAN network type are supported (ie. both ``type_drivers`` and
``tenant_network_types`` in ``[ml2]`` section of configuration files
should include ``vlan`` or ``vxlan``).

The following parameters can be specified in ``[fujitsu_fossw]``
section of configuration files (such as ml2_conf_fujitsu_fossw.ini).

``fossw_ips`` (Mandatory)
  The List of IP addresses of all FOS switches. This is a mandatory parameter.

  Example::

    fossw_ips = 192.168.0.1,192.168.0.2,...

.. NOTE::

  Following configurations are common to all FOS switches in fossw_ips.

``username`` (Mandatory)
  The FOS switches username to use. Please note that the user must have
  administrator rights to configure FOS switches. This is a mandatory parameter.

  Example::

    username = admin

``password`` (Mandatory)
  The FOS switches password to use. It has no default value. This is a mandatory parameter.

  Example::

    password = admin

``port`` (Optional)
  The port number which is used for SSH connection. The default value is 22.

  Example::

    port = 22

``timeout`` (Optional)
  The timeout of SSH connection. The default value is 30.

  Example::

    timeout = 30

``udp_dest_port`` (Optional)
  The port number of VXLAN UDP destination on the FOS switches. All VXLANs on
  the switches use this UDP port as the UDP destination port in the UDP header
  when encapsulating. The default value is 4789.

  Example::

    udp_dest_port = 4789

``ovsdb_vlanid_range_min`` (Optional)
  The minimum VLAN ID in the range that is used for binding VNI and physical
  port. The range of 78 VLAN IDs (starts from this value) will be reserved.
  The default value is 2 (VLAN ID from 2 to 79 will be reserved).

  Example::

    ovsdb_vlanid_range_min = 2

.. NOTE::

  DO NOT include VLAN IDs specified by ``ovsdb_vlanid_range_min`` into
  "network_vlan_ranges" in ml2_conf.ini.

``ovsdb_port`` (Optional)
  The port number which OVSDB server on the FOS switches listen.  The default
  value is 6640.

  Example::

    ovsdb_port = 6640

FOS Switch Configuration
------------------------

The following configurations are needed for all FOS switches. These are needed
only for VXLAN. In the case of VLAN, any configurations is not needed.

1. Log in to FOS switch.

2. Enter configuration mode.

   Example::

    (ET-7648BRA-FOS) #configure

3. Set VTEP IP address for switch side.

   Example::

    (ET-7648BRA-FOS) (Config)#vxlan vtep source-ip 192.167.3.111

4. Set port number of VXLAN UDP destination, which is specified as
   ``udp_dest_port`` in the configuration file.

   Example::

    (ET-7648BRA-FOS) (Config)#vxlan udp-dst-port 4789

5. Exit configuration mode and start ovsdb setup.

   Example::

    (ET-7648BRA-FOS) (Config)#exit
    (ET-7648BRA-FOS) #ovsdb

6. Set port number of OVSDB server in the FOS switch, which is specified as
   ``ovsdb_port`` in the configuration file.

   Example::

    (ET-7648BRA-FOS) #ovsdb tcp port 6640

7. Check ``ovsdb_vlanid_range_min`` value in configuration file, and confirm
   that the VLAN ID within the range from ``ovsdb_vlanid_range_min`` to
   ``ovsdb_vlanid_range_min + 77`` are not used.

   Example::

    (ET-7648BRA-FOS) #show vlan 3
    VLAN does not exist.

8. Log out of FOS switch.
