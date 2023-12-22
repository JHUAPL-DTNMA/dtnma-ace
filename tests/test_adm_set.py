#
# Copyright (c) 2023 The Johns Hopkins University Applied Physics
# Laboratory LLC.
#
# This file is part of the Asynchronous Network Managment System (ANMS).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This work was performed for the Jet Propulsion Laboratory, California
# Institute of Technology, sponsored by the United States Government under
# the prime contract 80NM0018D0004 between the Caltech and NASA under
# subcontract 1658085.
#
''' Test the adm_set module and AdmSet class.
'''
import io
import logging
import os
import shutil
import unittest
from ace.adm_set import AdmSet
from ace.models import AdmModule
from util import TmpDir

# : Directory containing this file
SELFDIR = os.path.dirname(__file__)


class TestAdmSet(unittest.TestCase):
    ''' Each test case run constructs a separate in-memory DB '''

    def setUp(self):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        self._dir = TmpDir()

    def tearDown(self):
        del self._dir

    def test_construct_default(self):
        adms = AdmSet()
        self.assertTrue(adms.cache_path)
        self.assertEqual(0, len(adms))
        self.assertTrue(os.path.exists(os.environ['XDG_CACHE_HOME']))
        self.assertEqual(['ace'], os.listdir(os.environ['XDG_CACHE_HOME']))
        self.assertEqual(
            ['adms.sqlite'],
            os.listdir(os.path.join(os.environ['XDG_CACHE_HOME'], 'ace'))
        )

    def test_construct_nocache(self):
        adms = AdmSet(cache_dir=False)
        self.assertFalse(adms.cache_path)
        self.assertEqual(0, len(adms))
        self.assertFalse(os.path.exists(os.environ['XDG_CACHE_HOME']))

    def test_load_from_dir(self):
        adms = AdmSet()
        self.assertEqual(0, len(adms))

        # no dir and no files
        adms_path = os.path.join(os.environ['XDG_DATA_HOME'], 'ace', 'adms')
        self.assertEqual(0, adms.load_from_dirs([adms_path]))
        self.assertEqual(0, len(adms))

        # one new ADM
        os.makedirs(adms_path)
        shutil.copy(os.path.join(SELFDIR, 'test-adm-minimal.yang'), adms_path)
        self.assertEqual(1, adms.load_from_dirs([adms_path]))
        self.assertEqual(1, len(adms))

        # cached state
        with self.assertLogs('ace.adm_set', logging.DEBUG) as logcm:
            self.assertEqual(1, adms.load_from_dirs([adms_path]))
            self.assertTrue([ent for ent in logcm.output if 'Skipping file' in ent], msg=logcm.output)
        self.assertEqual(1, len(adms))

        # updated file
        with open(os.path.join(adms_path, 'test-adm-minimal.yang'), 'ab') as outfile:
            outfile.write(b'\r\n')
        self.assertEqual(1, adms.load_from_dirs([adms_path]))
        self.assertEqual(1, len(adms))

    def test_load_default_dirs(self):
        adms = AdmSet()
        self.assertEqual(0, len(adms))

        self.assertEqual(0, adms.load_default_dirs())
        self.assertEqual(0, len(adms))
        self.assertNotIn('test-adm-minimal', adms)
        with self.assertRaises(KeyError):
            adms['test-adm-minimal']  # pylint: disable=pointless-statement
        self.assertEqual(frozenset(), adms.names())

        adms_path = os.path.join(os.environ['XDG_DATA_HOME'], 'ace', 'adms')
        os.makedirs(adms_path)
        shutil.copy(os.path.join(SELFDIR, 'test-adm-minimal.yang'), adms_path)
        self.assertEqual(1, adms.load_default_dirs())
        self.assertEqual(1, len(adms))
        self.assertIn('test-adm-minimal', adms)
        self.assertIsInstance(adms['test-adm-minimal'], AdmModule)
        self.assertEqual(frozenset(['test-adm-minimal']), adms.names())
        for adm in adms:
            self.assertIsInstance(adm, AdmModule)

    def test_load_from_file(self):
        adms = AdmSet()
        self.assertEqual(0, len(adms))
        self.assertNotIn('test-adm-minimal', adms)

        file_path = os.path.join(SELFDIR, 'test-adm-minimal.yang')
        adm_new = adms.load_from_file(file_path)
        self.assertIsNotNone(adm_new.id)
        self.assertEqual('test-adm-minimal', adm_new.norm_name)

        self.assertEqual(1, len(adms))
        self.assertIn('test-adm-minimal', adms)

        # Still only one ADM after loading
        adm_next = adms.load_from_file(file_path)
        self.assertIsNotNone(adm_new.id)
        self.assertEqual('test-adm-minimal', adm_next.norm_name)
        # Identical object due to cache
        self.assertEqual(adm_new.id, adm_next.id)

        self.assertEqual(1, len(adms))
        self.assertIn('test-adm-minimal', adms)

    def test_load_from_data(self):
        adms = AdmSet()
        self.assertEqual(0, len(adms))
        self.assertNotIn('test-adm-minimal', adms)

        file_path = os.path.join(SELFDIR, 'test-adm-minimal.yang')
        buf = io.StringIO()
        with open(file_path, 'r') as infile:
            buf.write(infile.read())

        buf.seek(0)
        adm_new = adms.load_from_data(buf)
        self.assertIsNotNone(adm_new.id)
        self.assertEqual('test-adm-minimal', adm_new.norm_name)
        self.assertEqual(1, len(adms))
        self.assertIn('test-adm-minimal', adms)

        buf.seek(0)
        adm_next = adms.load_from_data(buf, del_dupe=True)
        self.assertIsNotNone(adm_new.id)
        # Non-identical due to replacement
        self.assertNotEqual(adm_new.id, adm_next.id)
        self.assertEqual(1, len(adms))
        self.assertIn('test-adm-minimal', adms)

        buf.seek(0)
        adm_next = adms.load_from_data(buf, del_dupe=False)
        self.assertIsNotNone(adm_new.id)
        self.assertNotEqual(adm_new.id, adm_next.id)
        self.assertEqual(2, len(adms))
        self.assertIn('test-adm-minimal', adms)
