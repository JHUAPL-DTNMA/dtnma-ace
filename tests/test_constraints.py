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
import logging
import os
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from ace import models, constraints

SELFDIR = os.path.dirname(__file__)
LOGGER = logging.getLogger(__name__)


class BaseTest(unittest.TestCase):
    ''' Each test case run constructs a separate in-memory DB '''

    def setUp(self):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        self._db_eng = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self._db_eng)
        self._db_sess = Session(self._db_eng)

    def tearDown(self):
        self._db_sess.close()
        self._db_sess = None
        models.Base.metadata.drop_all(self._db_eng)
        self._db_eng = None

    def assertIssuePattern(self, issue: constraints.Issue, adm_name, check_name, obj_ref, detail_re):
        self.assertEqual(adm_name, issue.adm_name)
        self.assertEqual(check_name, issue.check_name)
        self.assertEqual(obj_ref, issue.obj)
        self.assertRegex(issue.detail, detail_re)


@unittest.skip  # FIXME: reinstate later
class TestConstraintsBasic(BaseTest):

    def _add_mdat(self, adm):
        adm.mdat.append(models.Mdat(name='name', value=adm.norm_name))
        adm.mdat.append(models.Mdat(name='namespace', value=adm.norm_namespace))
        adm.mdat.append(models.Mdat(name='enum', value=str(adm.enum)))
        adm.mdat.append(models.Mdat(name='version', value='v0'))

    def test_file_name(self):
        adm = models.AdmFile(
            abs_file_path='othername.json',
            norm_name='myadm',
            norm_namespace='myns',
            enum=200,
        )
        self._add_mdat(adm)
        self._db_sess.add(adm)

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm)
        LOGGER.warning(issues)
        self.assertEqual(1, len(issues))
        self.assertIssuePattern(
            issues[0],
            adm_name='myadm',
            check_name='ace.constraints.basic.same_file_name',
            obj_ref=adm,
            detail_re=r'different',
        )

    def test_duplicate_adm_names(self):
        adm_a = models.AdmFile(
            norm_name='myadm',
            norm_namespace='myns',
            enum=200,
        )
        self._add_mdat(adm_a)
        self._db_sess.add(adm_a)

        adm_b = models.AdmFile(
            norm_name='myadm',
            norm_namespace='otherns',
            enum=201,
        )
        self._add_mdat(adm_b)
        self._db_sess.add(adm_b)

        eng = constraints.Checker(self._db_sess)
        issues = eng.check()
        LOGGER.warning(issues)
        self.assertEqual(2, len(issues))
        self.assertIssuePattern(
            issues[0],
            adm_name='myadm',
            check_name='ace.constraints.basic.unique_adm_names',
            obj_ref=adm_a,
            detail_re=r'Multiple ADMs with metadata "norm_name" of "myadm"',
        )

    def test_duplicate_object_names(self):
        adm = models.AdmFile(
            abs_file_path='myadm.json',
            norm_name='myadm',
            norm_namespace='myns',
            enum=200,
        )
        self._add_mdat(adm)
        adm.mdat.append(models.Mdat(name='name', value='bar'))
        self._db_sess.add(adm)

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm)
        LOGGER.warning(issues)
        self.assertEqual(1, len(issues))
        self.assertIssuePattern(
            issues[0],
            adm_name='myadm',
            check_name='ace.constraints.basic.unique_object_names',
            obj_ref=adm.mdat[-1],
            detail_re=r'duplicate',
        )

    def test_valid_type_name(self):
        adm = models.AdmFile(
            abs_file_path='myadm.json',
            norm_name='myadm',
            norm_namespace='myns',
            enum=200,
        )
        self._add_mdat(adm)
        adm.var.append(models.Var(name='organization', type='foo'))
        self._db_sess.add(adm)

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm)
        LOGGER.warning(issues)
        self.assertEqual(1, len(issues))
        self.assertIssuePattern(
            issues[0],
            adm_name='myadm',
            check_name='ace.constraints.basic.valid_type_name',
            obj_ref=adm.var[0],
            detail_re=r'the type name "foo" is not known',
        )

    def test_valid_reference_ari(self):
        adm_a = models.AdmFile(
            abs_file_path='adm_a.json',
            norm_name='adm_a',
            norm_namespace='adm_a',
            enum=200,
        )
        self._add_mdat(adm_a)
        adm_a.ctrl.append(models.Ctrl(name='control_a', norm_name='control_a'))
        self._db_sess.add(adm_a)

        adm_b = models.AdmFile(
            abs_file_path='adm_b.json',
            norm_name='adm_b',
            norm_namespace='adm_b',
            enum=201,
        )
        self._add_mdat(adm_b)
        adm_b.mac.append(models.Mac(name='macro', action=models.AC(items=[
            models.ARI(ns='adm_a', nm='ctrl.control_a'),
            models.ARI(ns='adm_a', nm='ctrl.control_c'),
            models.ARI(ns='adm_c', nm='ctrl.control_a'),
        ])))
        self._db_sess.add(adm_b)
        self._db_sess.commit()

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm_a)
        LOGGER.warning(issues)
        self.assertEqual(0, len(issues))

        issues = eng.check(adm_b)
        LOGGER.warning(issues)
        self.assertEqual(2, len(issues))
        self.assertIssuePattern(
            issues[0],
            adm_name='adm_b',
            check_name='ace.constraints.basic.valid_reference_ari',
            obj_ref=adm_b.mac[0],
            detail_re=r'Within the object named "macro" the reference ARI for .*\bcontrol_c\b.* is not resolvable',
        )
        self.assertIssuePattern(
            issues[1],
            adm_name='adm_b',
            check_name='ace.constraints.basic.valid_reference_ari',
            obj_ref=adm_b.mac[0],
            detail_re=r'Within the object named "macro" the reference ARI for .*\bcontrol_a\b.* is not resolvable',
        )
