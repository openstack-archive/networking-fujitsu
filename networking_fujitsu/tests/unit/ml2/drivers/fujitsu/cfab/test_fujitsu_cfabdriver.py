# Copyright 2015 FUJITSU LIMITED
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

import mock
import os
import re
import socket
import testtools

from itertools import chain
from networking_fujitsu.ml2.drivers.fujitsu.cfab import cfabdriver
from networking_fujitsu.ml2.drivers.fujitsu.cfab.mechanism_fujitsu import cfg
from neutron.common import utils
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.plugins.ml2 import config as ml2_config
from neutron.tests import base

FUJITSU_CFAB = "networking_fujitsu.ml2.drivers.fujitsu.cfab."
_CFABDRIVER__CFABMANAGER = FUJITSU_CFAB + "cfabdriver._CFABManager"
_TELNETLIB_TELNET = FUJITSU_CFAB + "cfabdriver.telnetlib.Telnet"

_EXCLUDE_BRACKET_LINE_RE = re.compile(r"^[^[].*$", re.MULTILINE)


class BaseTestMockedCFABManager(base.BaseTestCase):
    """Base class to test Fujitsu C-Fabric manager.
    """

    def setUp(self):
        super(BaseTestMockedCFABManager, self).setUp()
        self.manager = cfabdriver._CFABManager()

    def assert_wrote(self, lines):
        telnet = self.manager._telnet
        """:type : mock.MagicMock"""
        self.assertEqual(
            lines, [x[0][0] for x in telnet.write.call_args_list])


class TestMockedCFABManager(BaseTestMockedCFABManager):
    """Test Fujitsu C-Fabric manager.
    """

    def test_connect(self):
        with mock.patch(_TELNETLIB_TELNET, autospec=True) as telnet:

            self.manager.connect("address", "username", "password")

        telnet.assert_called_once_with(
            host="address",
            port=cfabdriver.TELNET_PORT,
            timeout=cfabdriver._TIMEOUT)
        self.assert_wrote(["username\n", "password\n"])

    def test_connect_fail(self):
        with mock.patch(_TELNETLIB_TELNET, autospec=True) as telnet:
            telnet.side_effect = socket.error

            self.assertRaises(
                socket.error,
                self.manager.connect, "address", "username", "password")


class BaseTestMockedCFABManagerConnected(BaseTestMockedCFABManager):
    """Base class to test Fujitsu C-Fabric manager after connected.
    """

    def setUp(self):
        super(BaseTestMockedCFABManagerConnected, self).setUp()
        with mock.patch(_TELNETLIB_TELNET, autospec=True):
            self.manager.connect("address", "username", "password")
        self.prompt = "# "

        def read_until(*args, **kwargs):
            return "(config)# "

        def expect(*args, **kwargs):
            s = self.prompt
            m = args[0][0].search(s)
            return 0 if m is not None else -1, m, s

        self.manager._telnet.read_until.side_effect = read_until
        self.manager._telnet.expect.side_effect = expect


class TestMockedCFABManagerConnected(BaseTestMockedCFABManagerConnected):
    """Test Fujitsu C-Fabric manager after connected.
    """

    def test_get_candidate_config(self):
        candidate_config = self.manager.get_candidate_config()

        self.assertEqual(
            mock.call("show candidate-config\n"),
            self.manager._telnet.write.call_args)
        self.assertEqual("", candidate_config)

    def test_get_running_config(self):
        running_config = self.manager.get_running_config()

        self.assertEqual(
            mock.call("show running-config\n"),
            self.manager._telnet.write.call_args)
        self.assertEqual("", running_config)

    def test_configure(self):
        cmd = "pprofile 1 vlan tag 1"

        self.manager.configure([cmd])

        call_args_list = self.manager._telnet.write.call_args_list
        self.assertIn(mock.call("configure\n"), call_args_list)
        self.assertIn(mock.call(cmd + "\n"), call_args_list)
        self.assertIn(mock.call("commit\n"), call_args_list)
        self.assertEqual(
            mock.call("save\n"), self.manager._telnet.write.call_args)

    def test_configure_without_commit(self):
        cmd = "pprofile 1 vlan tag 1"

        self.manager.configure([cmd], commit=False)

        call_args_list = self.manager._telnet.write.call_args_list
        self.assertIn(mock.call("configure\n"), call_args_list)
        self.assertIn(mock.call(cmd + "\n"), call_args_list)
        self.assertNotIn(mock.call("commit\n"), call_args_list)


class TestMockedCFABManagerConnectedWithoutSave(
        BaseTestMockedCFABManagerConnected):
    """Test Fujitsu C-Fabric manager after connected without save.
    """

    def setUp(self):
        super(TestMockedCFABManagerConnectedWithoutSave, self).setUp()
        self.manager.save_config = False

    def test_configure_without_save(self):
        cmd = "pprofile 1 vlan tag 1"

        self.manager.configure([cmd])

        call_args_list = self.manager._telnet.write.call_args_list
        self.assertIn(mock.call("configure\n"), call_args_list)
        self.assertIn(mock.call(cmd + "\n"), call_args_list)
        self.assertEqual(
            mock.call("commit\n"), self.manager._telnet.write.call_args)
        self.assertNotIn(mock.call("save\n"), call_args_list)


@testtools.skipUnless(
    'OS_FUJITSU_CFAB_ADDRESS' in os.environ,
    "OS_FUJITSU_CFAB_ADDRESS environment variable is not defined.")
class TestCFABManager(base.BaseTestCase):
    """Test Fujitsu C-Fabric manager using the real telnet connection.

    Tests will be performed using the C-Fabric CLI through a telnet connection
    to the address OS_FUJITSU_CFAB_ADDRESS and the port OS_FUJITSU_CFAB_PORT
    (defaults to 23). The username will be taken from OS_FUJITSU_CFAB_USERNAME
    (defaults to "admin") and the password will be taken from
    OS_FUJITSU_CFAB_PASSWORD (defaults to "password").
    If the environment variable OS_FUJITSU_CFAB_ADDRESS is NOT defined, tests
    will be skipped.
    """

    def _setup_lock(self):
        """Set up lock_path so that all tests are serialized.

        This is necessary to keep the C-Fabric config consistent within each
        test.
        """

        try:
            ml2_config.cfg.CONF.set_override('lock_path', "lock")
        except ml2_config.cfg.NoSuchOptError:
            ml2_config.cfg.CONF.set_override(
                'lock_path', "lock", "oslo_concurrency")

    def setUp(self):
        super(TestCFABManager, self).setUp()
        self._setup_lock()
        try:
            cfabdriver.TELNET_PORT = int(os.environ['OS_FUJITSU_CFAB_PORT'])
        except KeyError:
            pass
        self.manager = cfabdriver.CFAB_MANAGER
        self.manager.connect(
            os.environ.get('OS_FUJITSU_CFAB_ADDRESS'),
            os.environ.get('OS_FUJITSU_CFAB_USERNAME') or "admin",
            os.environ.get('OS_FUJITSU_CFAB_PASSWORD') or "password",
        )

    def assert_running_config(self, prefix, expected_config):
        running_config = self.manager.get_running_config(prefix=prefix)
        self.assertEqual(
            expected_config, _EXCLUDE_BRACKET_LINE_RE.findall(running_config))

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_modes(self):
        self.manager._close_session()
        self.assertEqual(cfabdriver._MODE_ADMIN, self.manager._get_mode())
        self.manager._execute("configure")
        self.assertEqual(cfabdriver._MODE_CONFIG, self.manager._get_mode())
        self.manager._execute("interface 1/1/1/1")
        self.assertEqual(cfabdriver._MODE_CONFIG_IF, self.manager._get_mode())
        self.manager._execute("exit")
        self.assertEqual(cfabdriver._MODE_CONFIG, self.manager._get_mode())
        self.manager._execute("exit")
        self.assertEqual(cfabdriver._MODE_ADMIN, self.manager._get_mode())
        self.manager._execute("exit")
        self.assertEqual(cfabdriver._MODE_USER, self.manager._get_mode())

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_get_running_config(self):
        self.manager.configure(
            ["no pprofile",
             "pprofile 1 vlan tag 1",
             "pprofile 2 vlan tag 2"])

        running_config = self.manager.get_running_config()

        self.assertEqual(
            ["pprofile 1 vlan tag 1", "pprofile 2 vlan tag 2"],
            re.findall(r"^pprofile\s+.+$", running_config, re.MULTILINE))

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_get_running_config_prefix(self):
        self.manager.configure(
            ["no pprofile",
             "pprofile 1 vlan tag 1",
             "pprofile 2 vlan tag 2"])

        self.assert_running_config(
            "pprofile", ["1 vlan tag 1", "2 vlan tag 2"])

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_configure(self):
        self.manager.configure(["no pprofile"])

        self.assert_running_config("pprofile", [])

        self.manager.configure(["pprofile 1 vlan tag 1"])

        self.assert_running_config("pprofile", ["1 vlan tag 1"])

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_configure_from_interface_config(self):
        self.manager.configure(["no pprofile"])
        self.manager._execute("interface 1/1/1/1")

        self.manager.configure(["pprofile 1 vlan tag 1"])

        self.assert_running_config("pprofile", ["1 vlan tag 1"])

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_configure_from_user(self):
        self.manager.configure(["no pprofile"])
        self.manager._execute("exit")
        self.manager._execute("exit")

        self.manager.configure(["pprofile 1 vlan tag 1"])

        self.assert_running_config("pprofile", ["1 vlan tag 1"])

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_configure_from_closed(self):
        self.manager.configure(["no pprofile"])
        self.manager._close_session()

        self.manager.configure(["pprofile 1 vlan tag 1"])

        self.assert_running_config("pprofile", ["1 vlan tag 1"])

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_configure_no_commit(self):
        self.manager.configure(["no pprofile"])

        self.manager.configure(["pprofile 1 vlan tag 1"], commit=False)

        self.assert_running_config("pprofile", [])

        self.manager.configure([])

        self.assert_running_config("pprofile", ["1 vlan tag 1"])

    @utils.synchronized(cfabdriver._LOCK_NAME, external=True)
    def test_configure_error(self):
        self.assertRaises(
            ml2_exc.MechanismDriverError, self.manager.configure, ["error"])


class BaseTestCFABdriver(base.BaseTestCase):
    """Base class to test Fujitsu C-Fabric mechanism driver.
    """

    def setUp(self):
        super(BaseTestCFABdriver, self).setUp()
        with mock.patch(_CFABDRIVER__CFABMANAGER, autospec=True) as mocked:
            self.driver = cfabdriver.CFABdriver(cfg.CONF)
            self.driver.mgr = mocked.return_value

    def assert_configured(self, cmds):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        tmp = [x[0][0] for x in mgr.configure.call_args_list]
        actual = list(chain.from_iterable(tmp))
        self.assertEqual(cmds, actual)

        # Make sure that only the last configure has commit=True.
        commits = [x[1].get('commit', True)
                   for x in mgr.configure.call_args_list]
        self.assertTrue(commits.pop())
        commits.append(False)
        self.assertEqual({False}, set(commits))


class TestCFABdriver(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver.
    """

    def test_associate_mac_to_network(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = (
            """pprofile 00:01:02:03:04:05 vlan tag 2
vfab 4 pprofile 0 vsiid mac 00:01:02:03:04:05 00:01:02:03:04:05
""")

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 "
             "00:01:02:03:04:05"])

    def test_associate_mac_to_network_no_pprofile(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = ""

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["pprofile 00:01:02:03:04:05 vlan tag 2",
             "vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 "
             "00:01:02:03:04:05"])

    def test_associate_mac_to_network_existing(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = (
            """pprofile 00:01:02:03:04:05 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 00:01:02:03:04:05
""")

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assertFalse(mgr.configure.called)

    def test_associate_mac_to_network_existing_override(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = (
            """pprofile test-2 vlan tag 2
vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:05 test-2
""")

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["pprofile 00:01:02:03:04:05 vlan tag 2",
             "vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:05 "
             "00:01:02:03:04:05"])

    def test_associate_mac_to_network_override_pprofile(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = (
            """pprofile 00:01:02:03:04:05 vlan tag 1,2
vfab 4 pprofile 0 vsiid mac 00:01:02:03:04:05 00:01:02:03:04:05
""")

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["pprofile 00:01:02:03:04:05 vlan tag 2",
             "vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 "
             "00:01:02:03:04:05"])

    def test_dissociate_mac_from_network(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = (
            """pprofile 00:01:02:03:04:05 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 00:01:02:03:04:05
""")

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["no vfab 3 pprofile 0",
             "no pprofile 00:01:02:03:04:05"])

    def test_dissociate_mac_from_network_still_used_in_other_vfab(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = (
            """pprofile 00:01:02:03:04:05 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 00:01:02:03:04:05
vfab 4 pprofile 0 vsiid mac 00:01:02:03:04:05 00:01:02:03:04:05
""")

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(["no vfab 3 pprofile 0"])


class TestCFABdriverSharePprofile(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver with shared pprofile.
    """

    def setUp(self):
        cfg.CONF.set_override('share_pprofile', True, "fujitsu_cfab")
        super(TestCFABdriverSharePprofile, self).setUp()

    def test_associate_mac_to_network(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 2 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:00:00:00:00:01 2
"""

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:05 2"])

    def test_associate_mac_to_network_no_pprofile(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = ""

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["pprofile 2 vlan tag 2",
             "vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 2"])

    def test_associate_mac_to_network_existing(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 1
"""

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assertFalse(mgr.configure.called)

    def test_associate_mac_to_network_existing_override(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 4
vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:05 1
"""

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["pprofile 2 vlan tag 2",
             "vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:05 2"])

    def test_dissociate_mac_from_network(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["no vfab 3 pprofile 0",
             "no pprofile 1"])

    def test_dissociate_mac_from_network_still_used(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 1
vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:06 1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(["no vfab 3 pprofile 0"])

    def test_dissociate_mac_from_network_still_used_in_other_vfab(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 1
vfab 4 pprofile 0 vsiid mac 00:01:02:03:04:06 1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(["no vfab 3 pprofile 0"])

    def test_dissociate_mac_from_network_no_match(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 4
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assertFalse(mgr.configure.called)


class TestCFABdriverSharedPprofilePrefixed(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver with pprofile prefix.
    """

    def setUp(self):
        cfg.CONF.set_override('share_pprofile', True, "fujitsu_cfab")
        cfg.CONF.set_override('pprofile_prefix', "test-", "fujitsu_cfab")
        super(TestCFABdriverSharedPprofilePrefixed, self).setUp()

    def test_associate_mac_to_network(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile test-2 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:00:00:00:00:01 test-2
"""

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:05 test-2"])

    def test_associate_mac_to_network_no_pprofile(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = ""

        self.driver.associate_mac_to_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["pprofile test-2 vlan tag 2",
             "vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 test-2"])

    def test_dissociate_mac_from_network(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 2
pprofile test-1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 test-1
vfab 4 pprofile 0 vsiid mac 00:01:02:03:04:06 1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(
            ["no vfab 3 pprofile 0",
             "no pprofile test-1"])

    def test_dissociate_mac_from_network_still_used(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile test-1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 test-1
vfab 3 pprofile 1 vsiid mac 00:01:02:03:04:06 test-1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(["no vfab 3 pprofile 0"])

    def test_dissociate_mac_from_network_still_used_in_other_vfab(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile test-1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 test-1
vfab 4 pprofile 0 vsiid mac 00:01:02:03:04:06 test-1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assert_configured(["no vfab 3 pprofile 0"])

    def test_dissociate_mac_from_network_no_match(self):
        mgr = self.driver.mgr
        """:type : mock.MagicMock"""
        mgr.get_running_config.return_value = """pprofile 1 vlan tag 2
vfab 3 pprofile 0 vsiid mac 00:01:02:03:04:05 1
"""

        self.driver.dissociate_mac_from_network(
            "address", "username", "password", "3", 2, "00:01:02:03:04:05")

        mgr.connect.assert_called_once_with("address", "username", "password")
        mgr.get_running_config.assert_called_once_with()
        self.assertFalse(mgr.configure.called)


class TestCFABdriverPprofilePrefix(base.BaseTestCase):
    """Test Fujitsu C-Fabric mechanism driver for pprofile_prefix errors.
    """

    def test_too_long(self):
        cfg.CONF.set_override('pprofile_prefix', "a" * 29, "fujitsu_cfab")
        with mock.patch(_CFABDRIVER__CFABMANAGER, autospec=True):
            self.assertRaises(ValueError, cfabdriver.CFABdriver, cfg.CONF)

    def test_illegal_character(self):
        cfg.CONF.set_override('pprofile_prefix', '"', "fujitsu_cfab")
        with mock.patch(_CFABDRIVER__CFABMANAGER, autospec=True):
            self.assertRaises(ValueError, cfabdriver.CFABdriver, cfg.CONF)


class TestCFABdriverVlan(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver for VLAN configuration.
    """

    def test_setup_vlan_no_preconfig_exist(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = ""
        ports = "1/1/0/1"
        self.driver.setup_vlan("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_single())

    def test_setup_vlan_exist_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = "ifgroup 0 ether 1/1/0/10"
        ports = "1/1/0/1"
        self.driver.setup_vlan("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_single(ifgroup_id="1"))

    def test_setup_vlan_exists_vlan_definition(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
vfab 1 vlan 8 endpoint untag 0
        """
        ports = "1/1/0/2"
        self.driver.setup_vlan("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_single(ports=ports, ifgroup_id="1",
                                          ifg="0,1"))

    def test_ifgroup_for_vfab_vlan_exists_and_includes_boundary(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
ifgroup 1 ether 1/1/0/2
ifgroup 2 ether 1/1/0/3
ifgroup 3 ether 1/1/0/4
ifgroup 4 ether 1/1/0/5
ifgroup 5 ether 1/1/0/6
ifgroup 6 ether 1/1/0/7
interface 1/1/0/1
    exit
vfab 1 vlan 8 endpoint untag 0-6
        """
        ports = "1/1/0/1"
        ignore = ['ifgroup']
        self.driver.setup_vlan("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_single(ports=ports,
                                          ifg="0-6",
                                          ignore=ignore))

    def test_ifgroup_ether_is_exhauted(self):
        mgr = self.driver.mgr
        candidate = ""
        for i in range(0, 4096):
            candidate += 'ifgroup {if_id} ether 1/1/0/{port}'.format(
                             if_id=i, port=(i + 1))
            candidate += '\n'
        mgr.get_candidate_config.return_value = candidate
        ports = "1/1/1/1"
        self.assertRaises(ml2_exc.MechanismDriverError,
                          self.driver.setup_vlan,
                          "addr", "user", "pass", "1", 8, ports)

    def test_lag_id_is_exhauted(self):
        mgr = self.driver.mgr
        candidate = ""
        for i in range(1, 200):
            candidate += 'linkaggregation 1 {lag}'.format(lag=i)
            candidate += '\n'
        mgr.get_candidate_config.return_value = candidate
        ports = "1/1/0/1,1/1/0/2"
        self.assertRaises(ml2_exc.MechanismDriverError,
                          self.driver.setup_vlan_with_lag,
                          "addr", "user", "pass", "1", 8, ports)

    def test_setup_vlan_with_lag_no_preconfig_exist(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = ""
        ports = "1/1/0/1,1/1/0/2"
        self.driver.setup_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_lag())

    def test_setup_vlan_with_lag_exist_lag_id_and_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
ifgroup 1 linkaggregation 1 2
interface 1/1/0/3
    type linkaggregation 1
    lldp mode enable
    exit
interface 1/1/0/4
    type linkaggregation 1
    lldp mode enable
    exit
interface 1/1/0/5
    type linkaggregation 2
    lldp mode enable
    exit
interface 1/1/0/6
    type linkaggregation 2
    lldp mode enable
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
linkaggregation 1 2 cfab port-mode external
linkaggregation 1 2 mode active
linkaggregation 1 2 type endpoint
vfab 1 vlan 8 endpoint untag 0
vfab 1 vlan 16 endpoint untag 1
        """
        ports = "1/1/0/1,1/1/0/2"
        self.driver.setup_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_lag(lag_id="3", ifgroup_id="2",
                                       ifg="0,2"))

    def test_setup_vlan_with_lag_reuse_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
ifgroup 1 linkaggregation 1 2
ifgroup 2 linkaggregation 1 3
interface 1/1/0/1
    lldp mode enable
    exit
interface 1/1/0/2
    lldp mode enable
    exit
interface 1/1/0/3
    type linkaggregation 2
    lldp mode enable
    exit
interface 1/1/0/4
    type linkaggregation 2
    lldp mode enable
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
linkaggregation 1 2 cfab port-mode external
linkaggregation 1 2 mode active
linkaggregation 1 2 type endpoint
vfab 1 vlan 16 endpoint untag 1
        """
        ports = "1/1/0/1,1/1/0/2"
        self.driver.setup_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        ignore = ['ifgroup']
        self.assert_configured(exp_lag(lag_id="3", ifgroup_id="2",
                                       ifg="2", ignore=ignore))

    def test_setup_vlan_with_lag_exist_lag_id_and_override(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    lldp mode enable
    exit
interface 1/1/0/2
    type linkaggregation 1
    lldp mode enable
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
vfab 1 vlan 100 endpoint untag 0
        """
        ports = "1/1/0/1,1/1/0/2"
        self.driver.setup_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_lag(lag_id="2",
                                       ifgroup_id="1",
                                       exist_lag_id="1"))

    def test_setup_vlan_with_lag_exist_lag_id_and_reuse_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    lldp mode enable
    exit
interface 1/1/0/2
    type linkaggregation 1
    lldp mode enable
    exit
vfab 1 vlan 100 endpoint untag 0
        """
        ports = "1/1/0/1,1/1/0/2"
        self.driver.setup_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_lag(exist_lag_id="1",
                                       ignore=['ifgroup']))

    def test_clear_vlan_completely(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
vfab 1 vlan 8 endpoint untag 0
        """
        ports = "1/1/0/1"
        self.driver.clear_vlan("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_cl_single())

    def test_clear_vlan_eliminate_own_definition(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
ifgroup 1 ether 1/1/0/2
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
interface 1/1/0/2
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
vfab 1 vlan 8 endpoint untag 0,1
        """
        ports = "1/1/0/1"
        self.driver.clear_vlan("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_mod_single(ifg="1"))

    def test_clear_vlan_with_lag_completely(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    lldp mode enable
    exit
interface 1/1/0/2
    type linkaggregation 1
    lldp mode enable
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
vfab 1 vlan 8 endpoint untag 0
        """
        ports = "1/1/0/1,1/1/0/2"
        self.driver.clear_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_cl_lag())

    def test_clear_vlan_with_lag_eliminate_own_definition(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
ifgroup 1 linkaggregation 1 2
interface 1/1/0/1
    type linkaggregation 1
    lldp mode enable
    exit
interface 1/1/0/2
    type linkaggregation 1
    lldp mode enable
    exit
interface 1/1/0/3
    type linkaggregation 2
    lldp mode enable
    exit
interface 1/1/0/4
    type linkaggregation 2
    lldp mode enable
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
linkaggregation 1 2 cfab port-mode external
linkaggregation 1 2 mode active
linkaggregation 1 2 type endpoint
vfab 1 vlan 8 endpoint untag 0,1
        """
        ports = "1/1/0/1,1/1/0/2"
        self.driver.clear_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        self.assert_configured(exp_mod_lag(ifg="1"))

    def test_clear_vlan_with_lag_illegal_lag_id_not_found(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
ifgroup 1 linkaggregation 1 2
interface 1/1/0/1
    lldp mode enable
    exit
interface 1/1/0/2
    lldp mode enable
    exit
interface 1/1/0/3
    type linkaggregation 2
    lldp mode enable
    exit
interface 1/1/0/4
    type linkaggregation 2
    lldp mode enable
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
linkaggregation 1 2 cfab port-mode external
linkaggregation 1 2 mode active
linkaggregation 1 2 type endpoint
vfab 1 vlan 8 endpoint untag 0
        """
        ports = "1/1/0/1,1/1/0/2"
        self.driver.clear_vlan_with_lag("addr", "user", "pass", "1", 8, ports)
        mgr.connect.assert_called_once_with("addr", "user", "pass")
        mgr.get_candidate_config.assert_called_once_with()
        ignore = ['vfab', 'linkaggregation']
        self.assert_configured(exp_mod_lag(ignore=ignore))


def exp_single(vfab_id="1", vlanid=8, ifgroup_id="0",
               ports="1/1/0/1", ifg=None, ignore=[]):
    ifg = ifgroup_id if ifg is None else ifg
    ret = []
    if 'ifgroup' not in ignore:
        ret.append("ifgroup {ifid} ether {p}".format(ifid=ifgroup_id, p=ports))
    ret.append("interface range {p}".format(p=ports))
    ret.append("cfab port-mode external")
    ret.append("type endpoint")
    ret.append("vfab {vfab} vlan {vid} endpoint untag {ifg}".format(
                   vfab=vfab_id, vid=vlanid, ifg=ifg))
    return ret


def exp_lag(vfab_id="1", vlanid=8, ifgroup_id="0", ports="1/1/0/1,1/1/0/2",
            lag_id="1", domain_id="1", ifg=None, ignore=[], exist_lag_id=None):
    ifg = ifgroup_id if ifg is None else ifg
    ret = []
    lagdef = 'linkaggregation {dom} {lag}'.format(lag=lag_id, dom=domain_id)
    if exist_lag_id:
        ex_lagdef = 'no linkaggregation 1 {lag}'.format(lag=exist_lag_id)
        ret.append(ex_lagdef + ' cfab port-mode')
        ret.append(ex_lagdef + ' mode')
        ret.append(ex_lagdef + ' type')
    if 'linkaggregation' not in ignore:
        ret.append(lagdef + ' cfab port-mode external')
        ret.append(lagdef + ' mode active')
        ret.append(lagdef + ' type endpoint')
    if 'ifgroup' not in ignore:
        ret.append('ifgroup {if_id} '.format(if_id=ifgroup_id) + lagdef)
    if 'interface' not in ignore:
        ret.append('interface range {ports}'.format(ports=ports))
        ret.append('type linkaggregation {lag}'.format(lag=lag_id))
    if 'vfab' not in ignore:
        ret.append("vfab {vfab} vlan {vid} endpoint untag {ifg}".format(
            vfab=vfab_id, vid=vlanid, ifg=ifg))
    return ret


# Remove VFAB VLAN definition completely
def exp_cl_single(vfab_id="1", vlanid=8, ifgroup_id="0", ports="1/1/0/1",
                  ifg="0"):
    ifg = ifgroup_id if ifg is None else ifg
    return ["interface range {ports}".format(ports=ports),
            "no type",
            "no cfab port-mode",
            "no vfab {vfab} vlan {vid} endpoint untag".format(vfab=vfab_id,
                                                              vid=vlanid)]


# Modify(eliminate) own VFAB VLAN definition
def exp_mod_single(vfab_id="1", vlanid=8, ifgroup_id="0", ifg="0",
                   ports="1/1/0/1"):
    ifg = ifgroup_id if ifg is None else ifg
    return ["interface range {ports}".format(ports=ports),
            "no type",
            "no cfab port-mode",
            "vfab {vfab} vlan {vid} endpoint untag {ifg}".format(
                vfab=vfab_id, vid=vlanid, ifg=ifg)]


# Remove VFAB VLAN definition completely in case of LAG
def exp_cl_lag(vfab_id="1", vlanid=8, lag_id="1", domain_id="1",
               ports="1/1/0/1,1/1/0/2", ignore=[]):
    ret = []
    if 'interface' not in ignore:
        ret.append("interface range {ports}".format(ports=ports))
        ret.append("no type")
    if 'vfab' not in ignore:
        ret.append("no vfab {vfab} vlan {vid} endpoint untag".format(
            vfab=vfab_id, vid=vlanid))
    if 'linkaggregation' not in ignore:
        no_lagdef = 'no linkaggregation {dom} {lag}'.format(lag=lag_id,
                                                            dom=domain_id)
        ret.append(no_lagdef + ' cfab port-mode')
        ret.append(no_lagdef + ' mode')
        ret.append(no_lagdef + ' type')
    return ret


# Modify(eliminate) own VFAB VLAN definition in case of LAG
def exp_mod_lag(vfab_id="1", vlanid=8, lag_id="1", domain_id="1",
                ifg="0", ports="1/1/0/1,1/1/0/2", ignore=[]):
    ret = []
    if 'interface' not in ignore:
        ret.append("interface range {ports}".format(ports=ports))
        ret.append('no type')
    if 'vfab' not in ignore:
        ret.append("vfab {vfab} vlan {vid} endpoint untag {ifg}".format(
            vfab=vfab_id, vid=vlanid, ifg=ifg))
    if 'linkaggregation' not in ignore:
        no_lagdef = 'no linkaggregation {dom} {lag}'.format(lag=lag_id,
                                                            dom=domain_id)
        ret.append(no_lagdef + ' cfab port-mode')
        ret.append(no_lagdef + ' mode')
        ret.append(no_lagdef + ' type')
    print('ret=%s' % ret)
    return ret
