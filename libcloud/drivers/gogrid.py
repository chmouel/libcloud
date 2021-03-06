# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
GoGrid driver
"""
from libcloud.providers import Provider
from libcloud.types import NodeState, MalformedResponseError,\
        InvalidCredsError, LibcloudError
from libcloud.base import Node, ConnectionUserAndKey, Response, NodeDriver
from libcloud.base import NodeSize, NodeImage, NodeLocation
import time
import hashlib

# JSON is included in the standard library starting with Python 2.6.  For 2.5
# and 2.4, there's a simplejson egg at: http://pypi.python.org/pypi/simplejson
try:
    import json
except ImportError:
    import simplejson as json

HOST = 'api.gogrid.com'
PORTS_BY_SECURITY = { True: 443, False: 80 }
API_VERSION = '1.5'

STATE = {
    "Starting": NodeState.PENDING,
    "On": NodeState.RUNNING,
    "Off": NodeState.PENDING,
    "Restarting": NodeState.REBOOTING,
    "Saving": NodeState.PENDING,
    "Restoring": NodeState.PENDING,
}

GOGRID_INSTANCE_TYPES = {'512MB': {'id': '512MB',
                       'name': '512MB',
                       'ram': 512,
                       'disk': 30,
                       'bandwidth': None,
                       'price':0.095},
        '1GB': {'id': '1GB',
                       'name': '1GB',
                       'ram': 1024,
                       'disk': 60,
                       'bandwidth': None,
                       'price':0.19},
        '2GB': {'id': '2GB',
                       'name': '2GB',
                       'ram': 2048,
                       'disk': 120,
                       'bandwidth': None,
                       'price':0.38},
        '4GB': {'id': '4GB',
                       'name': '4GB',
                       'ram': 4096,
                       'disk': 240,
                       'bandwidth': None,
                       'price':0.76},
        '8GB': {'id': '8GB',
                       'name': '8GB',
                       'ram': 8192,
                       'disk': 480,
                       'bandwidth': None,
                       'price':1.52}}


class GoGridResponse(Response):

    def success(self):
        if self.status == 403:
            raise InvalidCredsError('Invalid credentials', GoGridNodeDriver)
        if self.status == 401:
            raise InvalidCredsError('API Key has insufficient rights', GoGridNodeDriver)
        if not self.body:
            return None
        try:
            return json.loads(self.body)['status'] == 'success'
        except ValueError:
            raise MalformedResponseError('Malformed reply', body=self.body, driver=GoGridNodeDriver)

    def parse_body(self):        
        if not self.body:
            return None
        return json.loads(self.body)

    def parse_error(self):
        try:
            return json.loads(self.body)["list"][0]['message']
        except ValueError:
            return None

class GoGridConnection(ConnectionUserAndKey):
    """
    Connection class for the GoGrid driver
    """

    host = HOST
    responseCls = GoGridResponse

    def add_default_params(self, params):
        params["api_key"] = self.user_id
        params["v"] = API_VERSION
        params["format"] = 'json'
        params["sig"] = self.get_signature(self.user_id, self.key)

        return params

    def get_signature(self, key, secret):
        """ create sig from md5 of key + secret + time """
        m = hashlib.md5(key+secret+str(int(time.time())))
        return m.hexdigest()

class GoGridNode(Node):
    # Generating uuid based on public ip to get around missing id on
    # create_node in gogrid api
    #
    # Used public ip since it is not mutable and specified at create time,
    # so uuid of node should not change after add is completed
    def get_uuid(self):
        return hashlib.sha1(
            "%s:%d" % (self.public_ip,self.driver.type)
        ).hexdigest()

class GoGridNodeDriver(NodeDriver):
    """
    GoGrid node driver
    """

    connectionCls = GoGridConnection
    type = Provider.GOGRID
    name = 'GoGrid'
    features = {"create_node": ["generates_password"]}

    _instance_types = GOGRID_INSTANCE_TYPES

    def _get_state(self, element):
        try:
            return STATE[element['state']['name']]
        except:
            pass
        return NodeState.UNKNOWN

    def _get_ip(self, element):
        return element.get('ip').get('ip')

    def _get_id(self, element):
        return element.get('id')

    def _to_node(self, element, password=None):
        state = self._get_state(element)
        ip = self._get_ip(element)
        id = self._get_id(element)
        n = GoGridNode(id=id,
                 name=element['name'],
                 state=state,
                 public_ip=[ip],
                 private_ip=[],
                 extra={'ram': element.get('ram').get('name'),
                     'isSandbox': element['isSandbox'] == 'true'},
                 driver=self.connection.driver)
        if password:
            n.extra['password'] = password

        return n

    def _to_image(self, element):
        n = NodeImage(id=element['id'],
                      name=element['friendlyName'],
                      driver=self.connection.driver)
        return n

    def _to_images(self, object):
        return [ self._to_image(el)
                 for el in object['list'] ]

    def _to_location(self, element):
        location = NodeLocation(id=element['id'],
                name=element['name'],
                country="US",
                driver=self.connection.driver)
        return location

    def _to_locations(self, object):
        return [self._to_location(el)
                for el in object['list']]

    def list_images(self, location=None):
        params = {}
        if location is not None:
            params["datacenter"] = location.id
        images = self._to_images(
                self.connection.request('/api/grid/image/list', params).object)
        return images

    def list_nodes(self):
        passwords_map = {}

        res = self._server_list()
        try:
          for password in self._password_list()['list']:
              try:
                  passwords_map[password['server']['id']] = password['password']
              except KeyError:
                  pass
        except InvalidCredsError, e:
          # some gogrid API keys don't have permission to access the password list.
          pass

        return [ self._to_node(el, passwords_map.get(el.get('id')))
                 for el
                 in res['list'] ]

    def reboot_node(self, node):
        id = node.id
        power = 'restart'
        res = self._server_power(id, power)
        if not res.success():
            raise Exception(res.parse_error())
        return True

    def destroy_node(self, node):
        id = node.id
        res = self._server_delete(id)
        if not res.success():
            raise Exception(res.parse_error())
        return True

    def _server_list(self):
        return self.connection.request('/api/grid/server/list').object

    def _password_list(self):
        return self.connection.request('/api/support/password/list').object

    def _server_power(self, id, power):
        # power in ['start', 'stop', 'restart']
        params = {'id': id, 'power': power}
        return self.connection.request("/api/grid/server/power", params,
                                         method='POST')

    def _server_delete(self, id):
        params = {'id': id}
        return self.connection.request("/api/grid/server/delete", params,
                                        method='POST')

    def _get_first_ip(self, location=None):
        params = {'ip.state': 'Unassigned', 'ip.type': 'public'}
        if location is not None:
            params['datacenter'] = location.id
        object = self.connection.request("/api/grid/ip/list", params).object
        if object['list']:
            return object['list'][0]['ip']
        else:
            raise LibcloudError('No public unassigned IPs left',
                    GoGridNodeDriver)

    def list_sizes(self, location=None):
        return [ NodeSize(driver=self.connection.driver, **i)
                    for i in self._instance_types.values() ]

    def list_locations(self):
        locations = self._to_locations(
            self.connection.request('/api/common/lookup/list',
                params={'lookup': 'ip.datacenter'}).object)
        return locations

    def ex_create_node_nowait(self, **kwargs):
        """Don't block until GoGrid allocates id for a node
        but return right away with id == None.

        The existance of this method is explained by the fact
        that GoGrid assigns id to a node only few minutes after
        creation."""
        name = kwargs['name']
        image = kwargs['image']
        size = kwargs['size']
        first_ip = self._get_first_ip(kwargs.get('location'))
        params = {'name': name,
                  'image': image.id,
                  'description': kwargs.get('ex_description', ''),
                  'isSandbox': str(kwargs.get('ex_issandbox', False)).lower(),
                  'server.ram': size.id,
                  'ip': first_ip}

        object = self.connection.request('/api/grid/server/add',
                                         params=params, method='POST').object
        node = self._to_node(object['list'][0])

        return node

    def create_node(self, **kwargs):
        """Create a new GoGird node

        See L{NodeDriver.create_node} for more keyword args.

        @keyword    ex_description: Description of a Node
        @type       ex_description: C{string}
        @keyword    ex_issandbox: Should server be sendbox?
        @type       ex_issandbox: C{bool}
        """
        node = self.ex_create_node_nowait(**kwargs)

        timeout = 60 * 20
        waittime = 0
        interval = 2 * 60

        while node.id is None and waittime < timeout:
            nodes = self.list_nodes()

            for i in nodes:
                if i.public_ip[0] == node.public_ip[0] and i.id is not None:
                    return i

            waittime += interval
            time.sleep(interval)

        if id is None:
            raise Exception("Wasn't able to wait for id allocation for the node %s" % str(node))

        return node

    def ex_save_image(self, node, name):
        """Create an image for node.

        Please refer to GoGrid documentation to get info
        how prepare a node for image creation:

        http://wiki.gogrid.com/wiki/index.php/MyGSI

        @keyword    node: node to use as a base for image
        @param      node: L{Node}
        @keyword    name: name for new image
        @param      name: C{string}
        """
        params = {'server': node.id,
                  'friendlyName': name}
        object = self.connection.request('/api/grid/image/save', params=params,
                                         method='POST').object

        return self._to_images(object)[0]
