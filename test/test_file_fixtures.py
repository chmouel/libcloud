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

from file_fixtures import FileFixtures

import sys
import unittest

class FileFixturesTests(unittest.TestCase):

    def test_success(self):
        f = FileFixtures('meta')
        self.assertEqual("Hello, World!", f.load('helloworld.txt'))

    def test_failure(self):
        f = FileFixtures('meta')
        self.assertRaises(IOError, f.load, 'nil')

if __name__ == '__main__':
    sys.exit(unittest.main())
