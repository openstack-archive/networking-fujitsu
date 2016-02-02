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

import httplib2
import json
import os.path
import re
import subprocess
import urllib

from six.moves import http_client as httplib

from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

ML2_ISM_GROUP = "fujitsu_ism"
ML2_FUJITSU_ISM = [
    cfg.StrOpt('address', default='furukawa-ism',
               help=("The IP address or hostname of the ISM.")),
    cfg.StrOpt('username', default='admin',
               help=("The ISM username to use.")),
    cfg.StrOpt('password', default='admin', secret=True,
               help=("The ISM password to use.")),
    cfg.StrOpt('port', default='25566',
               help=("The port number of the ISM.")),
    cfg.StrOpt('certificate_authority',
               default='/etc/neutron/plugins/ml2/fujitsu/server.crt',
               help=("The certification authority for ISM.")),
    cfg.StrOpt('timeout', default=30,
               help=("The API timeout value for ISM."))]

cfg.CONF.register_opts(ML2_FUJITSU_ISM, ML2_ISM_GROUP)

STATUS_SUCCESS = [httplib.OK,  # 200
                  httplib.CREATED,  # 201
                  httplib.ACCEPTED,  # 202
                  httplib.NON_AUTHORITATIVE_INFORMATION,  # 203
                  httplib.NO_CONTENT,  # 204
                  httplib.RESET_CONTENT,  # 205
                  httplib.PARTIAL_CONTENT,  # 206
                  httplib.MULTI_STATUS,  # 207
                  httplib.IM_USED]  # 226

TIMEOUT = int(cfg.CONF.fujitsu_ism.timeout)
VLAN_PATTERN = '^%s$|%s[,-]|[,-]%s[,-]|[,-]%s'
ISM_VERSION = 'v1/'
ISM_URI_PREFIX = '/ism/api/' + ISM_VERSION
ISM_URI_NODES = ISM_URI_PREFIX + 'topology/nodes/%(node)s/'
ISM_URI_PORTS = ISM_URI_PREFIX + 'topology/nodes/%(node)s/ports/%(port)s/'
ISM_BODY = 'IsmBody'
ISM_AUTH_COMMAND = 'echo "%(user)s:%(pass)s" | openssl enc -aes-256-cbc ' \
                   '-e -base64 -pass pass:%(addr)s'
HTTPS = 'https://%s:%s' % (cfg.CONF.fujitsu_ism.address,
                           cfg.CONF.fujitsu_ism.port)


class IsmBase(object):

    def __init__(self, network_type=None, segmentation_id=None):
        self.address = cfg.CONF.fujitsu_ism.address
        self.username = cfg.CONF.fujitsu_ism.username
        self.password = cfg.CONF.fujitsu_ism.password
        self.port = cfg.CONF.fujitsu_ism.port
        self.auth_header = self.generate_auth_header()
        self.ca_cert = cfg.CONF.fujitsu_ism.certificate_authority
        self.network_type = network_type
        # TODO(yushiro): research segmentation_id's type
        self.segmentation_id = segmentation_id

    def do_request(self, uri, method='GET', body={}, headers=None,
                   keyfile=None, certfile=None, ca_certs=None,
                   timeout=TIMEOUT):
        # TODO(yushiro) Confirm ISM specification about certs file

        if ca_certs:
            if not os.path.isfile(ca_certs):
                raise FujitsuIsmException("ca_cert(%s) not found." % ca_certs)

        https = httplib2.Http(ca_certs=ca_certs, timeout=timeout)
        https.force_exception_to_status_code = True
        if body is not None:
            body = urllib.urlencode(body)
        LOG.info("request URI=%s, method=%s" % (uri, method))
        LOG.info("headers=%s, ca_certs=%s" % (headers, ca_certs))
        LOG.info("request body: %s" % body)

        # through request
        try:
            res_headers, res_body = https.request(uri,
                                                  method,
                                                  headers=headers,
                                                  body=body)
            status = int(res_headers.get('status'))
            if (status in STATUS_SUCCESS):
                LOG.info("ISM response: %s" % res_headers)
                LOG.debug("ISM res_body: %s" % res_body)
                return res_headers, json.loads(res_body)
            else:
                LOG.warning("ISM res_headers: %s" % res_headers)
                LOG.warning("ISM res_body: %s" % res_body)
                raise FujitsuIsmException(res_body)
        except Exception as er:
            LOG.exception("Unknown ISM error. detail=%s" % er)
            raise FujitsuIsmException(er)

    def generate_auth_header(self):
        '''Generate authentication header for ISM'''
        auth_command = ISM_AUTH_COMMAND % {'user': self.username,
                                           'pass': self.password,
                                           'addr': self.address}
        try:
            encrypted = subprocess.check_output(auth_command, shell=True)
        except subprocess.CalledProcessError as er:
            LOG.exception("ISMPlugin configuration error.(%s)" % type(er))
            LOG.exception("detail: %s" % er)
            raise FujitsuIsmException(er)
        return 'ISM: ' + encrypted

    def generate_req_param_for_port(self, phy_info):
        '''Generate request parameter for port'''
        pass

    def generate_req_param_for_switch(self, phy_info):
        '''Generate request parameter for switch'''
        pass

    def setup_for_switch(self, phy_info):
        '''Setup switch configuration using ISM API'''
        pass

    def setup_for_port(self, req_body, phy_info):
        '''Setup port configuration using ISM API'''
        pass

    def get_current_config(self, params):
        '''Get current configuration using ISM API'''
        pass

    def trim_ism_body(self, body):
        '''Trim ISM body for request.  ISM's response body includes
           unnecessary attribute named "SchemaType".
        '''
        trimmed = dict(body).get(ISM_BODY)
        del trimmed['SchemaType']
        return trimmed


class IsmVlanBase(IsmBase):

    def __init__(self, network_type=None, segmentation_id=None):
        super(IsmVlanBase, self).__init__(network_type, segmentation_id)

    def get_current_config(self, params):
        '''Get current VLAN configuration of specified switch/port
            :params:  Physical connections information from Ironic
            :returns: Response body of VLAN configurations with
                      specified switch and port
        '''
        # TODO(yushiro) get ISM nodeid from switch_id(MAC)
        nodeid = urllib.quote(str(params['switch_id']))
        portname = urllib.quote(str(params['port_id']))
        _uri = HTTPS + ISM_URI_PORTS % {'node': nodeid, 'port': portname}
        uri = _uri + self.network_type
        headers = {'Content-Type': 'application/json',
                   'Authorization': self.auth_header}
        headers, res_body = self.do_request(uri,
                                            method='GET',
                                            body=None,
                                            headers=headers,
                                            ca_certs=self.ca_cert)
        return res_body

    def setup_for_port(self, req_body, params):
        '''Set specified VLANID with specified switch-port
        '''
        # TODO(yushiro) get ISM nodeid from switch_id(MAC)
        nodeid = urllib.quote(str(params['switch_id']))
        portname = urllib.quote(str(params['port_id']))
        _uri = HTTPS + ISM_URI_PORTS % {'node': nodeid, 'port': portname}
        uri = _uri + self.network_type
        req_headers = {'Content-Type': 'application/json',
                       'Authorization': self.auth_header}
        headers, res_body = self.do_request(uri,
                                            method='PATCH',
                                            body=req_body,
                                            headers=req_headers,
                                            ca_certs=self.ca_cert)
        return headers, res_body

    def generate_req_param_for_port(self, body,
                                    vlan_type="UntaggedVLanId"):
        '''Generate request parameter for PATCH VLAN '''
        customized = self.trim_ism_body(body)
        vlan_param = customized.get(vlan_type)
        vlanid = self.segmentation_id

        if not self.__judge_vlanid_is_included(vlan_param, vlanid, vlan_type):
            if (vlan_type == 'UntaggedVLanId'):
                modify_param = self.segmentation_id
            if (vlan_type == 'TaggedVLanId'):
                modify_param = vlan_param + ',' + self.segmentation_id

        customized[vlan_type] = modify_param
        return customized

    def __judge_vlanid_is_included(self, vlan_param, vlanid, vlan_type):
        _pattern = VLAN_PATTERN % (vlanid, vlanid, vlanid, vlanid)
        pattern = r'%s' % _pattern
        if (re.match(pattern, vlan_param)):
            return True
        elif (vlan_type == 'UntaggedVLanId'):
            return False

        # Taggedvlanid case
        boundary = r'(\d+)-(\d+)'
        matched_list = re.findall(boundary, vlan_param)
        for vlan in matched_list:
            if (int(vlan[0]) <= vlanid and vlanid <= int(vlan[1])):
                return True
        return False


class IsmVxlanBase(IsmBase):

    def __init__(self, context, network_type=None, segmentation_id=None):
        super(IsmVxlanBase, self).__init__(network_type, segmentation_id)

        def get_current_config(self, params):
            '''Get current VXLAN configuration of specified switch
            '''
            pass

        def generate_req_param_for_switch(self, phy_info):
            '''Generate request parameter for PATCH VXLAN node'''
            pass

        def generate_req_param_for_port(self, phy_info):
            '''Generate request parameter for PATCH VLAN '''
            pass

        def setup_for_switch(self, phy_info):
            pass

        def setup_for_port(self, req_body, phy_info):
            pass


class FujitsuIsmException(Exception):
    '''FujitsuIsmException'''
