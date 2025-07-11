#
# Copyright (c) 2020-2025 The Johns Hopkins University Applied Physics
# Laboratory LLC.
#
# This file is part of the AMM CODEC Engine (ACE) under the
# DTN Management Architecture (DTNMA) reference implementaton set from APL.
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
# Portions of this work were performed for the Jet Propulsion Laboratory,
# California Institute of Technology, sponsored by the United States Government
# under the prime contract 80NM0018D0004 between the Caltech and NASA under
# subcontract 1658085.
#
''' Test the pure ORM models within models.py
'''
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from ace import models


class TestModels(unittest.TestCase):
    ''' Each test case run constructs a separate in-memory DB '''

    def setUp(self):
        self._db_eng = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self._db_eng)
        self._db_sess = Session(self._db_eng)

    def tearDown(self):
        self._db_sess.close()
        self._db_sess = None
        models.Base.metadata.drop_all(self._db_eng)
        self._db_eng = None

    def test_simple(self):
        src = models.AdmSource(
            abs_file_path='example-hi',
        )
        mod = models.AdmModule(
            source=src,
            norm_name='example-hi',
            ns_org_name="example",
            ns_org_enum=65535,
            ns_model_name="hi",
            ns_model_enum=10,
            metadata_list=models.MetadataList(),
        )
        self._db_sess.add_all([src, mod])
        self._db_sess.commit()

        objs = self._db_sess.query(models.AdmModule)
        self.assertEqual(1, objs.count())
        adm = objs.first()
        self.assertEqual('example-hi', adm.source.abs_file_path)
