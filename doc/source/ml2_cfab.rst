How to Install
^^^^^^^^^^^^^^

.. code-block:: python

    pip install networking-fujitsu

Configuration
^^^^^^^^^^^^^

Please edit **/etc/neutron/plugins/ml2/ml2_conf.ini** as follows:

1. Add **fujitsu_cfab** to **mechanism_drivers** option.

   .. code-block:: ini

       mechanism_drivers = openvswitch,fujitsu_cfab

2. Both **type_drivers** and **tenant_network_types** in **[ml2]** section
   should include **vlan**.  Only VLAN network type is supported.

   .. code-block:: ini

       [ml2]
       type_drivers = vlan
       tenant_network_types = vlan

3. The following parameters should specify after **[fujitsu_cfab]** section.

**address**
  The IP address or the host name of the CFX2000 to connect to using
  telnet protocol. This is a mandatory parameter and it has no
  default value. Only one address can be specified.

  .. code-block:: ini

      address = 192.168.0.1

**username**
  The CFX2000 username to use. Please note that the user must have
  administrator rights to configure CFX2000. The default value is **admin**.

  .. code-block:: ini

      username = admin

**password**
  The CFX2000 password to use. The default value is **admin**.

  .. code-block:: ini

      password = admin

**physical_networks**
  List of <physical_network>:<vfab_id> tuples specifying physical
  network names and corresponding VFAB IDs. All possible physical
  network names must be specified in this parameter. If a physical
  network name not specified in this parameter is used, a runtime
  exception will be raised. It is valid to use same VFAB ID for
  different physical networks as long as VLAN IDs are exclusive.
  Please note that VFAB must be created and configured in CFX2000
  beforehand.

  .. code-block:: ini

      physical_networks = physnet1:1,physnet2:2

**share_pprofile**
  Whether to share a CFX2000 pprofile among Neutron ports using the same VLAN
  ID. If it is true, the pprofile name will be based on the VLAN ID, and the
  pprofile will be used for all Neutron ports using the same VLAN ID. If it is
  false, the pprofile name will be based on the MAC address, and each Neutron
  port will use dedicated pprofile. The default value is **False**.

  .. code-block:: ini

      share_pprofile = True

**pprofile_prefix**
  The prefix string for pprofile names. The pprofile name will be
  "<pprofile_prefix> + <vlan_id>" or "<pprofile_prefix> + <MAC_address>"
  according to the **share_pprofile** parameter. If **pprofile_prefix** is
  specified, the mechanism driver will not use the existing pprofiles
  which do not have the prefix. If **pprofile_prefix** is not specified, the
  mechanism driver will use the existing pprofile if it corresponds to the VLAN
  ID when **share_pprofile** is true, or if the name ends with the MAC address
  when **share_pprofile** is false.

  .. code-block:: ini

      pprofile_prefix = neutron-

**save_config**
  Whether to save configuration. If it is true, CFX2000's
  configuration will be saved every time the configuration is
  committed. The default value is **True**.

  .. code-block:: ini

      save_config = False


CFX2000 Configuration
^^^^^^^^^^^^^^^^^^^^^

As well as the standard configuration of CFX2000, the following
configurations are needed for the mechanism driver.

1. Enable AMPP using ARP/DHCP.

   By default, only RARP packets are examined for AMPP. It is
   possible to add ARP/DHCP packets to be examined for AMPP.

   .. code-block:: ini

       evb ampp arp on
       evb ampp dhcp on


   .. NOTE::

       **evb ampp dhcp** is not supported in earlier versions of CFX2000
       firmware.  Therefore, please create the subnet with enable_dhcp is FALSE
       before ampp dhcp function is supported.

2. Create and configure VFABs.

   It is necessary to create and configure the VFAB beforehand. It is
   recommended that the ports connected to the network nodes are
   configured as VLAN through mode.

   .. code-block:: ini

       ifgroup 0 ether 1/1/0/1-1/1/0/18
       ifgroup 1 ether 1/1/0/19-1/1/0/26
       ifgroup 2 ether 1/2/0/1
       vfab 1 cir-ports ifgroup 1
       vfab 1 ampp-area 0
       vfab 1 through ifgroup 2
       interface 1/2/0/1
       vfab through mode on


   .. NOTE::

       **vfab through** commands are only available on CFX2000 firmware V02.30
       and later.

Baremetal provisioning
~~~~~~~~~~~~~~~~~~~~~~

CFX2000 driver also supports baremetal tenant network isolation.
This feature is available on firmware **V02.40** and later. In order to
use this feature, the following pre-configuration is necessary:

Configure **network mode** for VFAB which is specified as
**physical_networks**.

.. code-block:: ini

    vfab 1 mode network


.. NOTE::

    While baremetal provisioning is running, PLEASE DO NOT EDIT CFX2000
    configuration directory.
