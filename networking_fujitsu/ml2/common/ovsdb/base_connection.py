# Copyright 2017 FUJITSU LIMITED
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

import socket
import time

from neutron_lib import exceptions
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import excutils

from networking_fujitsu._i18n import _
from networking_fujitsu.ml2.common.ovsdb import constants as n_const

LOG = logging.getLogger(__name__)


class OVSDBError(exceptions.NeutronException):
    message = _("%(message)s")


class BaseConnection(object):
    """Connects to OVSDB server.

       Connects to an ovsdb server on a given host and TCP port.
    """
    def __init__(self, ovsdb_ip, ovsdb_port):
        self.response = {}
        self.cache = ""
        self.ovsdb_ip = ovsdb_ip
        self.ovsdb_port = ovsdb_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        retryCount = 0
        while True:
            try:
                self.socket.connect((str(self.ovsdb_ip), int(self.ovsdb_port)))
                break
            except (socket.error, socket.timeout):
                LOG.warning('Unable to reach OVSDB server %s',
                            self.ovsdb_ip)
                if retryCount == n_const.MAX_CONNECTION_RETRIES:
                    # Retried for max_connection_retries times.
                    # Give up and return so that it can be tried in
                    # the next periodic interval.
                    with excutils.save_and_reraise_exception(reraise=True):
                        LOG.exception("Socket error in connecting to "
                                      "the OVSDB server")
                else:
                    time.sleep(1)
                    retryCount += 1

        # Successfully connected to the socket
        LOG.debug("Connected to OVSDB server %(ip)s, with tcp port %(port)s",
                  {'ip': self.ovsdb_ip, 'port': self.ovsdb_port})

    def disconnect(self):
        """disconnects the connection from the OVSDB server."""
        self.socket.close()

    def send(self, message):
        """Sends a message to the OVSDB server."""
        retry_count = 0
        while retry_count < n_const.MAX_RETRIES:
            try:
                # The self.socket.send always sends more than 1 byte.
                # Because, at least, query id will be add to the query.
                self.socket.send(jsonutils.dumps(message))
                return True
            except Exception as ex:
                LOG.exception("Exception [%s] occurred while sending "
                              "message to the OVSDB server", ex)
            retry_count += 1

        LOG.exception("Could not send message to the OVSDB server.")
        self.disconnect()
        return False
