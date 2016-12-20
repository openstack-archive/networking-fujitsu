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

import mock
import os
import re
import select
import socket
import testtools
import time

from itertools import chain
from networking_fujitsu.ml2.cfab import cfabdriver
from networking_fujitsu.ml2.cfab.mech_cfab import cfg
from neutron.common import utils
from neutron.plugins.ml2.common import exceptions as ml2_exc
from neutron.plugins.ml2 import config as ml2_config
from neutron.tests import base

FUJITSU_CFAB = "networking_fujitsu.ml2.cfab."
_CFABDRIVER__CFABMANAGER = FUJITSU_CFAB + "cfabdriver._CFABManager"
_TELNETLIB_TELNET = FUJITSU_CFAB + "cfabdriver.telnetlib.Telnet"
_EXCLUDE_BRACKET_LINE_RE = re.compile(r"^[^[].*$", re.MULTILINE)


class BaseTestMockedCFABManager(base.BaseTestCase):
    """Base class to test Fujitsu C-Fabric manager."""

    def setUp(self):
        super(BaseTestMockedCFABManager, self).setUp()
        self.manager = cfabdriver._CFABManager()
        self.manager.close_session = mock.MagicMock()

    def assert_wrote(self, lines):
        telnet = self.manager._telnet
        """:type : mock.MagicMock"""
        self.assertEqual(
            lines, [x[0][0] for x in telnet.write.call_args_list])


class TestMockedCFABManager(BaseTestMockedCFABManager):
    """Test Fujitsu C-Fabric manager."""

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

    def test_reconnect_raise_exceptions(self):

        with mock.patch(_TELNETLIB_TELNET, autospec=True) as telnet:
            for er in [EOFError, EnvironmentError, ValueError, OSError]:
                tel = telnet.return_value
                tel.read_until.side_effect = er
                self.manager.close_session()
                self.assertRaises(er, self.manager._reconnect)
                self.assertEqual(0, self.manager._retry_count)

    def test_reconnect_busy_and_retry(self):

        busy = 'The system is busy. Please login after waiting for a while.\n'
        max_session = 'Login failed to switch.(too many sessions. bye!\n)'
        with mock.patch(_TELNETLIB_TELNET, autospec=True) as telnet:
            tel = telnet.return_value
            tel.read_until.side_effect = [busy,
                                          max_session,
                                          cfabdriver._PROMPT_LOGIN,
                                          cfabdriver._PROMPT_PASS,
                                          cfabdriver._PROMPT_ADMIN]
            time.sleep = mock.MagicMock()
            time.sleep.side_effect = None

            self.manager.connect("address", "username", "password")
            self.assertEqual(3, self.manager.close_session.call_count)
            self.assertEqual(0, self.manager._retry_count)
            time.sleep.assert_called_with(cfabdriver._WAIT_FOR_BUSY)

    def test_reconnect_busy_and_reached_maxium_retry(self):

        busy = 'The system is busy. Please login after waiting for a while.\n'
        with mock.patch(_TELNETLIB_TELNET, autospec=True) as telnet:
            tel = telnet.return_value
            tel.read_until.return_value = busy
            time.sleep = mock.MagicMock()
            time.sleep.side_effect = None

            self.assertRaises(
                ValueError,
                self.manager.connect, "address", "username", "password")
            retry_count = cfabdriver._TIMEOUT / cfabdriver._WAIT_FOR_BUSY
            self.assertEqual(12, self.manager.close_session.call_count)
            self.assertEqual(retry_count, time.sleep.call_count)
            self.assertEqual(0, self.manager._retry_count)


class BaseTestMockedCFABManagerConnected(BaseTestMockedCFABManager):
    """Base class to test Fujitsu C-Fabric manager after connected."""

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
        self.ports = "1/1/0/1"
        self.mac = "00:01:02:03:04:05"
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

    def test_associate_mac_to_network_raises(self):
        self.driver.mgr = mock.Mock()
        mgr = self.driver.mgr
        cfab = self.driver
        for er in [EOFError, EnvironmentError, OSError, select.error]:
            mgr.connect.side_effect = er
            self.assertRaises(er, cfab.associate_mac_to_network,
                              'a', 'u', 'p', '1', 8, self.mac)
        mgr.connect.side_effect = ml2_exc.MechanismDriverError(
            method='connect')
        self.assertRaises(ml2_exc.MechanismDriverError,
                          cfab.associate_mac_to_network,
                          'a', 'u', 'p', '1', 8, self.mac)
        self.assertEqual(5, mgr.close_session.call_count)

    def test_disassociate_mac_from_network_raises(self):
        self.driver.mgr = mock.Mock()
        mgr = self.driver.mgr
        cfab = self.driver
        for er in [EOFError, EnvironmentError, OSError, select.error]:
            mgr.connect.side_effect = er
            self.assertRaises(er, cfab.dissociate_mac_from_network,
                              'a', 'u', 'p', '1', 8, self.mac)
        mgr.connect.side_effect = ml2_exc.MechanismDriverError(
            method='connect')
        self.assertRaises(ml2_exc.MechanismDriverError,
                          cfab.dissociate_mac_from_network,
                          'a', 'u', 'p', '1', 8, self.mac)
        self.assertEqual(5, mgr.close_session.call_count)

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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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
        mgr.close_session.assert_called_once_with()
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


class TestCFABdriverSetupVlan(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver for VLAN configuration.

    """

    def setUp(self):
        cfg.CONF.set_override('pprofile_prefix', "test-", "fujitsu_cfab")
        super(TestCFABdriverSetupVlan, self).setUp()

    def test_raises(self):
        mgr = self.driver.mgr
        cfab = self.driver
        for er in [EOFError, EnvironmentError, OSError, select.error]:
            mgr.get_candidate_config.side_effect = er
            self.assertRaises(er,
                              cfab.setup_vlan, 'a', 'u', 'p', '1', 8,
                              self.ports, self.mac)
        self.assertEqual(4, mgr.close_session.call_count)

    def test_no_preconfig_exist(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = "no_preconfig"
        expect = []
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_already_configured_vlan_but_missing_interface(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    exit
vfab 1 vlan 8 endpoint untag 0
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'delete') \
            + cfab_cmd('interface', 'add', ports=self.ports) \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_already_configured_vlan(self):
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
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'delete') \
            + cfab_cmd('interface', 'add', ports=self.ports) \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_already_configured_vlan_and_includes_boundary(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
ifgroup 1 ether 1/1/0/2
ifgroup 2 ether 1/1/0/3
interface 1/1/0/1
    exit
vfab 1 vlan 8 endpoint untag 0-2
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('vlan', 'replace', ifg='1-2') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1-2,0')
        self.assert_configured(expect)

    def test_already_configured_vlan_and_includes_between_boundary(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/2
ifgroup 1 ether 1/1/0/1
ifgroup 2 ether 1/1/0/3
interface 1/1/0/1
    exit
vfab 1 vlan 8 endpoint untag 0-2
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('vlan', 'replace', ifg='0,2') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='0,2,1')
        self.assert_configured(expect)

    def test_already_configured_vlan_and_not_included_in_boundary(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/2
ifgroup 1 ether 1/1/0/3
ifgroup 2 ether 1/1/0/4
interface 1/1/0/1
    exit
vfab 1 vlan 8 endpoint untag 0-2
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='3') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='0-2,3')
        self.assert_configured(expect)

    def test_exists_other_vlan_definition_missing_interface_def(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    exit
vfab 1 vlan 100 endpoint untag 0
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('vlan', 'delete', vlanid=100) \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exists_other_vlan_definition(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
vfab 1 vlan 100 endpoint untag 0
        """

        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('vlan', 'delete', vlanid=100) \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exists_other_vlan_definition_with_different_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
ifgroup 100 ether 1/1/0/1
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
vfab 1 vlan 100 endpoint untag 100
        """

        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('vlan', 'delete', vlanid=100) \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exists_interface_def_for_target_port(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.close_session.assert_called_once_with()
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exists_interface_def_for_other_port(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
interface 1/1/0/2
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exists_interface_def_of_lag(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
interface 1/1/0/1
    type linkaggregation 1
    exit
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('lag', 'delete') \
            + cfab_cmd('ifgroup', 'add') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exist_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = "ifgroup 0 ether 1/1/0/10"
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exist_ifgroup_and_reuse(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = "ifgroup 0 ether 1/1/0/1"
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exist_ifgroup_with_port_range(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1-1/1/0/5
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exist_ifgroup_with_port_range_and_out_of_range(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/2-1/1/0/5
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exist_ifgroup_with_lag(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = "ifgroup 0 linkaggregation 1 1"
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exist_ifgroup_with_lag_range(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1-4
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exists_lag_without_interface(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    exit
interface 1/1/0/2
    exit
linkaggregation 1 1 type endpoint
linkaggregation 1 1 mode active
linkaggregation 1 1 cfab port-mode external
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exist_definition_type_is_lag(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    exit
interface 1/1/0/2
    type linkaggregation 1
    exit
linkaggregation 1 1 type endpoint
linkaggregation 1 1 mode active
linkaggregation 1 1 cfab port-mode external
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('lag', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exist_lag_and_vlan_definition(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    exit
interface 1/1/0/2
    type linkaggregation 1
    exit
linkaggregation 1 1 type endpoint
linkaggregation 1 1 mode active
linkaggregation 1 1 cfab port-mode external
vfab 1 vlan 8 endpoint untag 0
        """
        self.driver.setup_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete') \
            + cfab_cmd('vlan', 'delete') \
            + cfab_cmd('lag', 'delete') \
            + cfab_cmd('ifgroup', 'add', ifg='1') \
            + cfab_cmd('interface', 'add') \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_ifgroup_ether_is_exhauted(self):
        mgr = self.driver.mgr
        candidate = ""
        for i in range(0, 4096):
            candidate += 'ifgroup {if_id} ether 1/1/0/{port}\n'.format(
                if_id=i, port=100)
        mgr.get_candidate_config.return_value = candidate
        self.assertRaises(ml2_exc.MechanismDriverError,
                          self.driver.setup_vlan, "a", "u", "p",
                          "1", 8, self.ports, self.mac)


class TestCFABdriverSetupVlanWithLAG(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver for VLAN configuration.

    """

    def setUp(self):
        cfg.CONF.set_override('pprofile_prefix', "test-", "fujitsu_cfab")
        super(TestCFABdriverSetupVlanWithLAG, self).setUp()
        self.ports = "1/1/0/1,1/1/0/2"

    def test_raises(self):
        mgr = self.driver.mgr
        cfab = self.driver
        for er in [EOFError, EnvironmentError, OSError, select.error]:
            mgr.get_candidate_config.side_effect = er
            self.assertRaises(er,
                              cfab.setup_vlan_with_lag, 'a', 'u', 'p', '1', 8,
                              self.ports, self.mac)
        self.assertEqual(4, mgr.close_session.call_count)

    def test_ifgroup_ether_is_exhauted(self):
        mgr = self.driver.mgr
        candidate = ""
        for i in range(0, 4096):
            candidate += 'ifgroup {if_id} ether 1/1/0/{port}\n'.format(
                if_id=i, port=(i + 1))
        mgr.get_candidate_config.return_value = candidate
        self.assertRaises(ml2_exc.MechanismDriverError,
                          self.driver.setup_vlan_with_lag, "a", "u", "p",
                          "1", 8, self.ports, self.mac)

    def test_lag_id_is_exhauted(self):
        mgr = self.driver.mgr
        candidate = ""
        for i in range(1, 200):
            candidate += 'linkaggregation 1 {lag}\n'.format(lag=i)
        mgr.get_candidate_config.return_value = candidate
        self.assertRaises(ml2_exc.MechanismDriverError,
                          self.driver.setup_vlan_with_lag, "a", "u", "p",
                          "1", 8, self.ports, self.mac)

    def test_no_preconfig_exist(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = "no_preconfig"
        self.driver.setup_vlan_with_lag("a", "u", "p", "1", 8,
                                        self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('lag', 'add') \
            + cfab_cmd('ifgroup', 'add', lag=True) \
            + cfab_cmd('interface', 'add', ports=self.ports, lag=True) \
            + cfab_cmd('vlan', 'add')
        self.assert_configured(expect)

    def test_exist_lag_id_and_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
ifgroup 1 linkaggregation 1 2
interface 1/1/0/1
    exit
interface 1/1/0/2
    exit
interface 1/1/0/3
    type linkaggregation 1
    exit
interface 1/1/0/4
    type linkaggregation 1
    exit
interface 1/1/0/5
    type linkaggregation 2
    exit
interface 1/1/0/6
    type linkaggregation 2
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
        self.driver.setup_vlan_with_lag("a", "u", "p", "1", 8,
                                        self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('lag', 'add', lag_id='3') \
            + cfab_cmd('ifgroup', 'add', ifg='2', lag_id='3', lag=True) \
            + cfab_cmd('interface', 'add', lag_id='3',
                       ports=self.ports, lag=True) \
            + cfab_cmd('vlan', 'add', ifg='0,2')
        self.assert_configured(expect)

    def test_illegal_exist_different_lag_id(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
ifgroup 1 linkaggregation 1 2
interface 1/1/0/1
    type linkaggregation 1
    exit
interface 1/1/0/2
    type linkaggregation 2
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
linkaggregation 1 2 cfab port-mode external
linkaggregation 1 2 mode active
linkaggregation 1 2 type endpoint
vfab 1 vlan 8 endpoint untag 0-1
        """
        self.driver.setup_vlan_with_lag("a", "u", "p", "1", 8,
                                        self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'replace', ifg='1') \
            + cfab_cmd('lag', 'delete') \
            + cfab_cmd('lag', 'add', lag_id='3') \
            + cfab_cmd('ifgroup', 'add', ifg='2', lag_id='3', lag=True) \
            + cfab_cmd('interface', 'add', lag_id='3',
                       ports=self.ports, lag=True) \
            + cfab_cmd('vlan', 'add', ifg='1,2')
        self.assert_configured(expect)

    def test_exists_ether_vlan_definition(self):
        cfab = self.driver
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1,1/1/0/2
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
vfab 1 vlan 8 endpoint untag 0
        """
        cfab.setup_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'delete') \
            + cfab_cmd('lag', 'add', lag_id='1') \
            + cfab_cmd('ifgroup', 'add', ifg='1', lag=True) \
            + cfab_cmd('interface', 'add', ports=self.ports, lag=True) \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_reuse_ifgroup(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
ifgroup 1 linkaggregation 1 2
ifgroup 2 linkaggregation 1 3
interface 1/1/0/1
    exit
interface 1/1/0/2
    exit
interface 1/1/0/3
    type linkaggregation 2
    exit
interface 1/1/0/4
    type linkaggregation 2
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
linkaggregation 1 2 cfab port-mode external
linkaggregation 1 2 mode active
linkaggregation 1 2 type endpoint
vfab 1 vlan 16 endpoint untag 1
        """
        self.driver.setup_vlan_with_lag("a", "u", "p", "1", 8,
                                        self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('lag', 'add', lag_id='3') \
            + cfab_cmd('interface', 'add', lag_id='3', ports=self.ports,
                       lag=True) \
            + cfab_cmd('vlan', 'add', ifg='2')
        self.assert_configured(expect)

    def test_exist_lag_id_and_override(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    exit
interface 1/1/0/2
    type linkaggregation 1
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
vfab 1 vlan 100 endpoint untag 0
        """
        self.driver.setup_vlan_with_lag("a", "u", "p", "1", 8,
                                        self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'delete', vlanid=100) \
            + cfab_cmd('lag', 'delete') \
            + cfab_cmd('lag', 'add', lag_id='2') \
            + cfab_cmd('ifgroup', 'add', ifg='1', lag_id='2', lag=True) \
            + cfab_cmd('interface', 'add', lag_id='2',
                       ports=self.ports, lag=True) \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_exist_ifgroup_with_lag_range_and_out_of_range(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1-2
interface 1/1/0/1
    exit
interface 1/1/0/2
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
linkaggregation 1 2 cfab port-mode external
linkaggregation 1 2 mode active
linkaggregation 1 2 type endpoint
        """
        self.driver.setup_vlan_with_lag("a", "u", "p", "1", 8,
                                        self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('lag', 'add', lag_id='3') \
            + cfab_cmd('ifgroup', 'add', ifg='1', lag_id='3', lag=True) \
            + cfab_cmd('interface', 'add', lag_id='3',
                       ports=self.ports, lag=True) \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)

    def test_already_configured_lag_and_vlan(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    exit
interface 1/1/0/2
    type linkaggregation 1
    exit
linkaggregation 1 1 type endpoint
linkaggregation 1 1 mode active
linkaggregation 1 1 cfab port-mode external
vfab 1 vlan 8 endpoint untag 0
        """
        self.driver.setup_vlan_with_lag("a", "u", "p", "1", 8,
                                        self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'delete') \
            + cfab_cmd('lag', 'delete') \
            + cfab_cmd('lag', 'add', lag_id='2') \
            + cfab_cmd('ifgroup', 'add', ifg='1', lag_id='2', lag=True) \
            + cfab_cmd('interface', 'add', ports=self.ports,
                       lag_id='2', lag=True) \
            + cfab_cmd('vlan', 'add', ifg='1')
        self.assert_configured(expect)


class TestCFABdriverClearVlan(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver for VLAN configuration."""

    def setUp(self):
        cfg.CONF.set_override('share_pprofile', True, "fujitsu_cfab")
        cfg.CONF.set_override('pprofile_prefix', "test-", "fujitsu_cfab")
        super(TestCFABdriverClearVlan, self).setUp()

    def test_raises(self):
        mgr = self.driver.mgr
        cfab = self.driver
        for er in [EOFError, EnvironmentError, OSError, select.error]:
            mgr.get_candidate_config.side_effect = er
            self.assertRaises(er,
                              cfab.clear_vlan, 'a', 'u', 'p', '1', 8,
                              self.ports, self.mac)
        self.assertEqual(4, mgr.close_session.call_count)

    def test_ifgroup_ether_is_exhauted(self):
        mgr = self.driver.mgr
        candidate = ""
        for i in range(0, 4096):
            candidate += 'ifgroup {if_id} ether 1/1/0/{port}\n'.format(
                if_id=i, port=(i + 1))
        mgr.get_candidate_config.return_value = candidate
        ret = self.driver.clear_vlan("a", "u", "p", "1", 8,
                                     self.ports, self.mac)
        self.assertIsNone(ret)

    def test_clear_with_no_command(self):
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
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('vlan', 'delete') + cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_clear_vlan_and_assoc(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
pprofile test-1 vlan tag 8
vfab 1 vlan 8 endpoint untag 0
vfab 1 pprofile 0 vsiid mac 00:01:02:03:04:05 test-1
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('pp_assoc', 'delete') \
            + cfab_cmd('vlan', 'delete') \
            + cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_eliminate_own_definition(self):
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
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('vlan', 'replace', ifg='1') \
            + cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_eliminate_own_definition_from_boundary(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/2
ifgroup 1 ether 1/1/0/3
ifgroup 2 ether 1/1/0/4
ifgroup 3 ether 1/1/0/1
ifgroup 4 ether 1/1/0/5
ifgroup 5 ether 1/1/0/6
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
vfab 1 vlan 8 endpoint untag 0-5
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('vlan', 'replace', ifg='0-2,4-5') \
            + cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_already_cleared_vlan(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    exit
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_already_cleared_vlan_without_interface(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    type endponit
    cfab port-mode external
    lldp mode enable
    exit
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_already_cleared_all_definitions(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
interface 1/1/0/1
    exit
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_exists_different_vlan(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    cfab port-mode external
    type endpoint
    exit
vfab 1 vlan 100 endpoint untag 0
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('vlan', 'delete', vlanid=100) \
            + cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_exists_different_vlans(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
interface 1/1/0/1
    cfab port-mode external
    type endpoint
    exit
vfab 1 vlan 100 endpoint untag 0
vfab 1 vlan 200 endpoint untag 0
vfab 1 vlan 300 endpoint untag 0
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('vlan', 'delete', vlanid=100) \
            + cfab_cmd('vlan', 'delete', vlanid=200) \
            + cfab_cmd('vlan', 'delete', vlanid=300) \
            + cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_exists_different_vlan_with_range(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
ifgroup 1 ether 1/1/0/2
interface 1/1/0/1
    cfab port-mode external
    type endpoint
    exit
vfab 1 vlan 100 endpoint untag 0-1
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('vlan', 'replace', vlanid=100, ifg=1) \
            + cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_exists_lag(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    exit
linkaggregation 1 1 mode active
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 type endpoint
vfab 1 vlan 8 endpoint untag 0
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_exists_lag_without_vlan(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    type linkaggregation 1
    exit
linkaggregation 1 1 mode active
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 type endpoint
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_exists_lag_without_interface(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    exit
linkaggregation 1 1 mode active
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 type endpoint
vfab 1 vlan 8 endpoint untag 0
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete')
        self.assert_configured(expect)

    def test_illegal_exists_port_range(self):
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1,1/1/0/2
interface 1/1/0/1
    cfab port-mode external
    type endpoint
    exit
interface 1/1/0/2
    cfab port-mode external
    type endpoint
    exit
vfab 1 vlan 8 endpoint untag 0
        """
        self.driver.clear_vlan("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete')
        self.assert_configured(expect)


class TestCFABdriverClearVlanWithLAG(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver for VLAN configuration."""

    def setUp(self):
        cfg.CONF.set_override('share_pprofile', True, "fujitsu_cfab")
        cfg.CONF.set_override('pprofile_prefix', "test-", "fujitsu_cfab")
        super(TestCFABdriverClearVlanWithLAG, self).setUp()
        self.ports = "1/1/0/1,1/1/0/2"

    def test_raises(self):
        mgr = self.driver.mgr
        cfab = self.driver
        for er in [EOFError, EnvironmentError, OSError, select.error]:
            mgr.get_candidate_config.side_effect = er
            self.assertRaises(er,
                              cfab.clear_vlan_with_lag, 'a', 'u', 'p', '1', 8,
                              self.ports, self.mac)
        self.assertEqual(4, mgr.close_session.call_count)

    def test_ifgroup_ether_is_exhauted(self):
        cfab = self.driver
        mgr = self.driver.mgr
        candidate = ""
        for i in range(0, 4096):
            candidate += 'ifgroup {if_id} ether 1/1/0/{port}\n'.format(
                if_id=i, port=(i + 1))
        mgr.get_candidate_config.return_value = candidate
        ret = cfab.clear_vlan_with_lag("a", "u", "p", "1", 8,
                                       self.ports, self.mac)
        self.assertIsNone(ret)

    def test_clear_with_no_command(self):
        cfab = self.driver
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
        cfab.clear_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'delete') + cfab_cmd('lag', 'delete')
        self.assert_configured(expect)

    def test_eliminate_own_definition(self):
        cfab = self.driver
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
        cfab.clear_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'replace', ifg='1') \
            + cfab_cmd('lag', 'delete')
        self.assert_configured(expect)

    def test_already_cleared_only_interface(self):
        cfab = self.driver
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 linkaggregation 1 1
interface 1/1/0/1
    lldp mode enable
    exit
interface 1/1/0/2
    lldp mode enable
    exit
linkaggregation 1 1 cfab port-mode external
linkaggregation 1 1 mode active
linkaggregation 1 1 type endpoint
vfab 1 vlan 8 endpoint untag 0
        """
        cfab.clear_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports)
        self.assert_configured(expect)

    def test_already_cleared_only_vlan(self):
        cfab = self.driver
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
        """
        cfab.clear_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('lag', 'delete')
        self.assert_configured(expect)

    def test_already_cleared_lag_definition(self):
        cfab = self.driver
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
vfab 1 vlan 8 endpoint untag 0
        """
        cfab.clear_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports) \
            + cfab_cmd('vlan', 'delete') \
            + cfab_cmd('lag', 'delete')
        self.assert_configured(expect)

    def test_already_cleared_all_definitions(self):
        cfab = self.driver
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
interface 1/1/0/1
    exit
        """
        cfab.clear_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports)
        self.assert_configured(expect)

    def test_exists_ether_vlan(self):
        cfab = self.driver
        mgr = self.driver.mgr
        mgr.get_candidate_config.return_value = """
ifgroup 0 ether 1/1/0/1
ifgroup 1 ether 1/1/0/2
interface 1/1/0/1
    type endpoint
    cfab port-mode external
    exit
interface 1/1/0/2
    type endpoint
    cfab port-mode external
    exit
vfab 1 vlan 8 endpoint untag 0-1
        """
        cfab.clear_vlan_with_lag("a", "u", "p", "1", 8, self.ports, self.mac)
        mgr.connect.assert_called_once_with("a", "u", "p")
        mgr.get_candidate_config.assert_called_once_with()
        expect = cfab_cmd('interface', 'delete', ports=self.ports)
        self.assert_configured(expect)


class TestCFABdriverPrivateMethods(BaseTestCFABdriver):
    """Test Fujitsu C-Fabric mechanism driver with private methods.

    This class is for illegal case tests.

    """

    def setUp(self):
        cfg.CONF.set_override('share_pprofile', True, "fujitsu_cfab")
        cfg.CONF.set_override('pprofile_prefix', "test-", "fujitsu_cfab")
        super(TestCFABdriverPrivateMethods, self).setUp()

    def test_is_ifgroup_included_between_range(self):
        ifgroup_id = 2
        ifgroups = '1-3'
        self.assertTrue(cfabdriver._is_ifgroup_included(ifgroup_id, ifgroups))


def cfab_cmd(target, op, vfab_id='1', vlanid=8, pp_name='test-1', ppid='0',
             lag=False, ports='1/1/0/1', domain_id='1', lag_id='1', ifg='0'):
    """Expected result for C-Fabric commands via operations.

    @param target  A string of target definition name. Following targets are
                   available:
                       'interface', 'lag', 'vlan', 'ifgroup', 'ifgroup_lag'
                       'assoc', 'pp_assoc'
    @param op      A string of operation. Following operations are available:
                       'add', 'replace', 'delete'
    @return  ret   A list of string object

    """
    ret = []
    if target is 'interface':
        ret.append("interface range {ports}".format(ports=ports))
        if op is 'add' or op is 'replace':
            if lag:
                ret.append('type linkaggregation {lag}'.format(lag=lag_id))
            else:
                ret.append("cfab port-mode external")
                ret.append("type endpoint")
        if op is 'delete':
            ret.append('no type')
            ret.append("no cfab port-mode")
        ret.append('exit')

    elif target is 'lag':
        lag = 'linkaggregation {dom} {lag}'.format(lag=lag_id, dom=domain_id)
        if op is 'add' or op is 'replace':
            ret.append(lag + ' cfab port-mode external')
            ret.append(lag + ' mode active')
            ret.append(lag + ' type endpoint')
        if op is 'delete':
            ret.append('no ' + lag + ' cfab port-mode')
            ret.append('no ' + lag + ' mode')
            ret.append('no ' + lag + ' type')

    elif target is 'vlan':
        if op is 'add' or op is 'replace':
            ret.append("vfab {vfab} vlan {vid} endpoint untag {ifg}".format(
                vfab=vfab_id, vid=vlanid, ifg=ifg))
        if op is 'delete':
            ret.append("no vfab {vfab} vlan {vid} endpoint untag".format(
                vfab=vfab_id, vid=vlanid))

    elif target is 'ifgroup':
        if op is 'add':
            if lag:
                ret.append("ifgroup {ifg} linkaggregation {dom} {lag}".format(
                    ifg=ifg, dom=domain_id, lag=lag_id))
            else:
                ret.append('ifgroup {ifg} ether {p}'.format(ifg=ifg, p=ports))

    elif target is 'assoc':
        if op is 'delete':
            ret.append("no pprofile {pp_name}".format(pp_name=pp_name))

    elif target is 'pp_assoc':
        if op is 'delete':
            ret.append("no vfab {vfab} pprofile {ppid}".format(
                vfab=vfab_id, ppid=ppid))
            ret.append("no pprofile {pp_name}".format(pp_name=pp_name))
    else:
        raise 'Illegal target(%s) is specified' % target
    return ret
