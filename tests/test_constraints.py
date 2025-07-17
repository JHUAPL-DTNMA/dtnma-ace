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
''' Test the adm_set module and AdmSet class.
'''
import io
import logging
import os
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from ace import ari, ari_text, models, typing, constraints

SELFDIR = os.path.dirname(__file__)
LOGGER = logging.getLogger(__name__)


class BaseTest(unittest.TestCase):
    ''' Each test case run constructs a separate in-memory DB '''

    def setUp(self):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        self._db_eng = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self._db_eng)
        self._db_sess = Session(self._db_eng, autoflush=False)

        self._ari_dec = ari_text.Decoder()

    def tearDown(self):
        self._ari_dec = None

        self._db_sess.close()
        self._db_sess = None
        models.Base.metadata.drop_all(self._db_eng)
        self._db_eng = None

    def assertIssuePattern(self, issue: constraints.Issue, module_name, check_name, obj_ref, detail_re):
        self.assertEqual(module_name, issue.module_name)
        self.assertEqual(check_name, issue.check_name)
        self.assertEqual(obj_ref, issue.obj)
        self.assertRegex(issue.detail, detail_re)

    def _from_text(self, text:str) -> ari.ARI:
        return self._ari_dec.decode(io.StringIO(text))

    def _add_mod(self, abs_file_path, org_name, org_enum, model_name, model_enum):
        src = models.AdmSource(
            abs_file_path=abs_file_path,
            file_text='',
        )
        adm = models.AdmModule(
            source=src,
            module_name=f'{org_name}-{model_name}',
            norm_name=f'{org_name}-{model_name}',
            ns_org_name=org_name,
            ns_org_enum=org_enum,
            ns_model_name=model_name,
            ns_model_enum=model_enum,
            metadata_list=models.MetadataList(),
        )
        adm.revisions = [
            models.AdmRevision(
                name='2023-01-02',
            )
        ]
        self._db_sess.add_all([src, adm])
        return adm


class TestConstraintsBasic(BaseTest):

    def test_file_name(self):
        adm = self._add_mod(
            abs_file_path='othername.yang',
            org_name='example',
            org_enum=65535,
            model_name='myadm',
            model_enum=200,
        )
        self._db_sess.commit()

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm)
        LOGGER.warning(issues)
        self.assertEqual(1, len(issues), msg=issues)
        self.assertIssuePattern(
            issues[0],
            module_name='example-myadm',
            check_name='ace.constraints.basic.same_file_name',
            obj_ref=adm,
            detail_re=r'different',
        )

    def test_duplicate_adm_names(self):
        adm_a = self._add_mod(
            abs_file_path='dir-a/example-myadm.yang',
            org_name='example',
            org_enum=65535,
            model_name='myadm',
            model_enum=200,
        )

        adm_b = self._add_mod(
            abs_file_path='dir-b/example-myadm.yang',
            org_name='example',
            org_enum=65535,
            model_name='myadm',
            model_enum=201,
        )
        self._db_sess.commit()

        eng = constraints.Checker(self._db_sess)
        issues = eng.check()
        LOGGER.warning(issues)
        self.assertEqual(2, len(issues), msg=issues)
        self.assertIssuePattern(
            issues[0],
            module_name='example-myadm',
            check_name='ace.constraints.basic.unique_adm_names',
            obj_ref=adm_a,
            detail_re=r'Multiple ADMs with metadata "norm_name" of "example-myadm"',
        )

    def test_duplicate_object_names(self):
        adm = self._add_mod(
            abs_file_path='example-myadm.yang',
            org_name='example',
            org_enum=65535,
            model_name='myadm',
            model_enum=200,
        )
        adm.ctrl.append(models.Ctrl(name='control_a', norm_name='control_a'))
        adm.ctrl.append(models.Ctrl(name='control_a', norm_name='control_a'))
        self._db_sess.commit()

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm)
        LOGGER.warning(issues)
        self.assertEqual(1, len(issues), msg=issues)
        self.assertIssuePattern(
            issues[0],
            module_name='example-myadm',
            check_name='ace.constraints.basic.unique_object_names',
            obj_ref=adm.ctrl[-1],
            detail_re=r'duplicate',
        )

    def test_valid_type_name(self):
        adm = self._add_mod(
            abs_file_path='example-myadm.yang',
            org_name='example',
            org_enum=65535,
            model_name='myadm',
            model_enum=200,
        )
        val = 'ari:/INT/10'
        adm.var.append(models.Var(
            name='someval',
            typeobj=typing.TypeUse(type_ari='asdf'),
            init_value=val,
            init_ari=self._from_text(val)
        ))
        self._db_sess.commit()

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm)
        LOGGER.warning(issues)
        self.assertEqual(1, len(issues), msg=issues)
        self.assertIssuePattern(
            issues[0],
            module_name='example-myadm',
            check_name='ace.constraints.basic.valid_type_name',
            obj_ref=adm.var[0],
            detail_re=r'Within the object named "someval" the type names are not known',
        )

    def test_valid_reference_ari(self):
        adm_a = self._add_mod(
            abs_file_path='example-adm-a.yang',
            org_name='example',
            org_enum=65535,
            model_name='adm-a',
            model_enum=200,
        )

        adm_a.ctrl.append(models.Ctrl(name='control_a', norm_name='control_a'))

        adm_b = self._add_mod(
            abs_file_path='example-adm-b.yang',
            org_name='example',
            org_enum=65535,
            model_name='adm-b',
            model_enum=201,
        )

        val = 'ari:/AC/(//example/adm-a/CTRL/control_a,//example/adm-a/CTRL/control_c,//example/adm-c/CTRL/control_a)'
        adm_b.const.append(models.Const(
            name='macro',
            typeobj=typing.TypeUse(type_ari=ari.LiteralARI(ari.StructType.AC, ari.StructType.ARITYPE)),
            init_value=val,
            init_ari=self._from_text(val),
        ))

        self._db_sess.commit()

        eng = constraints.Checker(self._db_sess)
        issues = eng.check(adm_a)
        LOGGER.warning(issues)
        self.assertEqual(0, len(issues), msg=issues)

        issues = eng.check(adm_b)
        LOGGER.warning(issues)
        self.assertEqual(2, len(issues), msg=issues)
        self.assertIssuePattern(
            issues[0],
            module_name='example-adm-b',
            check_name='ace.constraints.basic.valid_reference_ari',
            obj_ref=adm_b.const[0],
            detail_re=r'Within the object named "macro" the reference ARI for .*\bcontrol_c\b.* is not resolvable',
        )
        self.assertIssuePattern(
            issues[1],
            module_name='example-adm-b',
            check_name='ace.constraints.basic.valid_reference_ari',
            obj_ref=adm_b.const[0],
            detail_re=r'Within the object named "macro" the reference ARI for .*\bcontrol_a\b.* is not resolvable',
        )
