===============================
networking-fujitsu
===============================

FUJITSU plugins/drivers for OpenStack Neutron.
Following mechanism driver is available in this repository:

* (ML2) Mechanism driver for FUJITSU Converged Fabric Switch(C-Fabric)
* (ML2) Mechanism driver for FUJITSU FOS Switch

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
.. include:: ml2_cfab.rst

Mechanism driver for FUJITSU FOS Switch
=======================================
.. include:: ml2_fossw.rst
