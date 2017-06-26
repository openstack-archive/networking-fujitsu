==================
networking-fujitsu
==================

FUJITSU plugins/drivers for OpenStack Neutron.

* Free software: Apache license
* Source: http://git.openstack.org/cgit/openstack/networking-fujitsu
* Bugs: http://bugs.launchpad.net/networking-fujitsu

ML2 driver for FUJITSU Converged Fabric Switch(CFX2000)
-------------------------------------------------------

* Please refer [here](https://github.com/openstack/networking-fujitsu/blob/master/doc/source/ml2_cfab.rst).

.. include:: ml2_cfab.rst

ML2 driver for FUJITSU FOS Switch(Draft)
----------------------------------------

* Please refer [here](https://github.com/openstack/networking-fujitsu/blob/master/doc/source/ml2_fossw.rst).

.. include:: ml2_fossw.rst

.. NOTE::

    This package also includes ML2 driver for FUJITSU Software ServerView
    Infrastructure Manager(ISM).  This plugin is under development.  Therefore,
    PLEASE DO NOT ADD **fujitsu_ism** to mechanism_drivers option in
    /etc/neutron/plugins/ml2/ml2_conf.ini.
