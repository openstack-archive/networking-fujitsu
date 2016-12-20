===============================
networking-fujitsu
===============================

FUJITSU plugins/drivers for OpenStack Neutron.
Following mechanism driver is available in this repository:

* (ML2) Mechanism driver for FUJITSU Converged Fabric Switch(C-Fabric)

.. NOTE::
  This package also includes following plugin:

  (ML2) Mechanism driver for FUJITSU Software ServerView Infrastructure Manager

  This plugin is under development.  Therefore, PLEASE DO NOT ADD ``fujitsu_ism``
  to mechanism_drivers option in /etc/neutron/plugins/ml2/ml2_conf.ini.

* Free software: Apache license
* Source: http://git.openstack.org/cgit/openstack/networking-fujitsu
* Bugs: http://bugs.launchpad.net/networking-fujitsu


Mechanism driver for FUJITSU Converged Fabric Switch(C-Fabric)
==============================================================

How to Install
--------------

1. Install the package::

    $ pip install networking-fujitsu

2. Add ``fujitsu_cfab`` to mechanism_drivers option in
   /etc/neutron/plugins/ml2/ml2_conf.ini, for example::

    mechanism_drivers = openvswitch,fujitsu_cfab

3. Modify ml2_conf_fujitsu_cfab.ini and make neutron-server to read it.

   For RedHat, add the following options in ExecStart in
   /usr/lib/systemd/system/neutron-server.service::

    --config-file /etc/neutron/plugins/ml2/ml2_conf_fujitsu_cfab.ini

   For Ubuntu, add the following line to /etc/default/neutron-server::

    NEUTRON_PLUGIN_ML2_CONFIG="/etc/neutron/plugins/ml2/ml2_conf_fujitsu_cfab.ini"

   and add the following line before 'exec start-stop-daemon ...' in
   /etc/init/neutron-server.conf::

    [ -r "$NEUTRON_PLUGIN_ML2_CONFIG" ] && CONF_ARG="${CONF_ARG} --config-file $NEUTRON_PLUGIN_ML2_CONFIG"

Configuration
-------------

Only VLAN network type is supported (ie. both ``type_drivers`` and
``tenant_network_types`` in ``[ml2]`` section of configuration files
should include ``vlan``).

The following parameters can be specified in ``[fujitsu_cfab]``
section of configuration files (such as ml2_conf_fujitsu_cfab.ini).

``address``
  The IP address or the host name of the C-Fabric to connect to using
  telnet protocol. This is a mandatory parameter and it has no
  default value. Only one address can be specified.

  Example::

    address = 192.168.0.1

``username``
  The C-Fabric username to use. Please note that the user must have
  administrator rights to configure C-Fabric. The default value is
  ``admin``.

  Example::

    username = admin

``password``
  The C-Fabric password to use. The default value is ``admin``.

  Example::

    password = admin

``physical_networks``
  List of <physical_network>:<vfab_id> tuples specifying physical
  network names and corresponding VFAB IDs. All possible physical
  network names must be specified in this parameter. If a physical
  network name not specified in this parameter is used, a runtime
  exception will be raised. It is valid to use same VFAB ID for
  different physical networks as long as VLAN IDs are exclusive.
  Please note that VFABs must be created and configured in C-Fabric
  beforehand.

  Example::

    physical_networks = physnet1:1,physnet2:2

``share_pprofile``
  Whether to share a C-Fabric pprofile among Neutron ports using the same VLAN
  ID. If it is true, the pprofile name will be based on the VLAN ID, and the
  pprofile will be used for all Neutron ports using the same VLAN ID. If it is
  false, the pprofile name will be based on the MAC address, and each Neutron
  port will use dedicated pprofile. The default value is ``False``.

  Example::

    share_pprofile = True

``pprofile_prefix``
  The prefix string for pprofile names. The pprofile name will be
  "<pprofile_prefix> + <vlan_id>" or "<pprofile_prefix> + <MAC_address>"
  according to the ``share_pprofile`` parameter. If ``pprofile_prefix`` is
  specified, the mechanism driver will not use the existing pprofiles
  which do not have the prefix. If ``pprofile_prefix`` is not specified, the
  mechanism driver will use the existing pprofile if it corresponds to the VLAN
  ID when ``share_pprofile`` is true, or if the name ends with the MAC address
  when ``share_pprofile`` is false.

  Example::

    pprofile_prefix = neutron-

``save_config``
  Whether to save configuration. If it is true, C-Fabric's
  configuration will be saved every time the configuration is
  committed. The default value is ``True``.

  Example::

    save_config = False

C-Fabric Configuration
----------------------

Common
^^^^^^

As well as the standard configuration of C-Fabric, the following
configurations are needed for the mechanism driver.

1. Enable AMPP using ARP/DHCP.

   By default, only RARP packets are examined for AMPP. It is
   possible to add ARP/DHCP packets to be examined for AMPP.

   Example::

    evb ampp arp on
    evb ampp dhcp on

   Please note that ``evb ampp dhcp`` is not supported in earlier
   versions of C-Fabric firmware.  Therefore, please create the subnet
   with enable_dhcp is FALSE before ampp dhcp function is supported.

2. Create and configure VFABs.

   It is necessary to create and configure the VFAB beforehand. It is
   recommended that the ports connected to the network nodes are
   configured as VLAN through mode.

   Example::

    ifgroup 0 ether 1/1/0/1-1/1/0/18
    ifgroup 1 ether 1/1/0/19-1/1/0/26
    ifgroup 2 ether 1/2/0/1
    vfab 1 cir-ports ifgroup 1
    vfab 1 ampp-area 0
    vfab 1 through ifgroup 2
    interface 1/2/0/1
        vfab through mode on

   Please note that ``vfab through`` commands are only available on
   C-Fabric firmware V02.30 and later.

Baremetal provisioning
^^^^^^^^^^^^^^^^^^^^^^

C-Fabric plugin also supports baremetal tenant network isolation.
This feature is available on firmware V02.40 and later. In order to
use this feature, the following pre-configuration is necessary:

1. Configure ``network mode`` for VFAB which is specified as
   ``physical_networks``.

   Example::

      vfab 1 mode network

.. NOTE::

  While baremetal provisioning is running, PLEASE DO NOT EDIT C-Fabric
  configuration directory.
