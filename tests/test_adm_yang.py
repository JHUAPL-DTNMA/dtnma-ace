#
# Copyright (c) 2020-2024 The Johns Hopkins University Applied Physics
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
''' Verify behavior of the :mod:`ace.adm_yang` module tree.
'''
import io
import logging
import os
import unittest
import portion
from typing import TextIO
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pyang.repository import FileRepository
from ace import adm_yang, ari, ari_text, models, lookup

LOGGER = logging.getLogger(__name__)
SELFDIR = os.path.dirname(__file__)


class TestAdmYangHelpers(unittest.TestCase):

    RANGES = (
        ('5', portion.singleton(5)),
        ('5..20', portion.closed(5, 20)),
        ('5..20 | 30..50', portion.closed(5, 20) | portion.closed(30, 50)),
        ('min..10', portion.closed(-float('inf'), 10)),
        ('10..max', portion.closed(10, float('inf'))),
        # normalizing
        ('5..20 | 10..30', portion.closed(5, 30), 'from'),
    )

    def test_range_from_text(self):
        for row in self.RANGES:
            row = list(row)
            if len(row) > 2 and row.pop(2) != 'from':
                continue
            with self.subTest(f'{row}'):
                text, expect = row

                got = adm_yang.range_from_text(text)
                self.assertEqual(expect, got)

    def test_range_to_text(self):
        for row in self.RANGES:
            row = list(row)
            if len(row) > 2 and row.pop(2) != 'to':
                continue
            with self.subTest(f'{row}'):
                expect, ranges = row

                got = adm_yang.range_to_text(ranges)
                self.assertEqual(expect, got)


class BaseYang(unittest.TestCase):
    ''' Common test fixture for all YANG-based test classes. '''

    maxDiff = None

    def setUp(self):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        self._db_eng = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self._db_eng)
        self._db_sess = Session(self._db_eng)

        self._adm_dec = adm_yang.Decoder(FileRepository(path=os.path.join(SELFDIR, 'adms')))
        self._ari_dec = ari_text.Decoder()

    def tearDown(self):
        self._ari_dec = None
        self._adm_dec = None

        self._db_sess.close()
        self._db_sess = None
        models.Base.metadata.drop_all(self._db_eng)
        self._db_eng = None

    def _from_text(self, text:str) -> ari.ARI:
        return self._ari_dec.decode(io.StringIO(text))

    NOOBJECT_MODULE_HEAD = '''\
module example-mod {
  yang-version 1.1;
  namespace "ari://example-mod/";
  prefix empty;

  import ietf-amm {
    prefix amm;
  }

  revision 2023-10-31 {
    description
      "Initial test";
  }
  amm:enum 65536;
'''
    NOOBJECT_MODULE_TAIL = '''\
}
'''

    def _get_mod_buf(self, body:str) -> TextIO:
        buf = io.StringIO()
        buf.write(self.NOOBJECT_MODULE_HEAD)
        buf.write(body)
        buf.write(self.NOOBJECT_MODULE_TAIL)

        buf.seek(0)
        return buf


class TestAdmYang(BaseYang):
    ''' Tests of the YANG-based syntax handler separate from ADM logic. '''

    EMPTY_MODULE = '''\
module empty {}
'''

    def test_decode_empty(self):
        buf = io.StringIO(self.EMPTY_MODULE)
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
        self._db_sess.add(adm)
        self._db_sess.commit()

        self.assertEqual('empty', adm.name)

    def test_decode_noobject(self):
        buf = self._get_mod_buf('')
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
        self._db_sess.add(adm)
        self._db_sess.commit()
        self.assertIsNone(adm.source.abs_file_path)

        self.assertEqual('example-mod', adm.name)
        self.assertEqual('example-mod', adm.norm_name)
        self.assertEqual(1, len(adm.imports))
        self.assertEqual(1, len(adm.revisions))
        self.assertEqual(0, len(adm.typedef))
        self.assertEqual(0, len(adm.const))
        self.assertEqual(0, len(adm.edd))
        self.assertEqual(0, len(adm.var))
        self.assertEqual(0, len(adm.ctrl))
        self.assertEqual(0, len(adm.oper))

    def test_decode_minimal(self):
        buf = self._get_mod_buf('''
  amm:edd edd1 {
    amm:enum 4;
    amm:type "/ARITYPE/INT";
    description
      "EDD test_int";
  }
  amm:ctrl test1 {
    amm:enum 5;
    amm:parameter id {
      amm:type "//ietf-amm/TYPEDEF/any";
    }
    amm:parameter def {
      amm:type "//ietf-amm/TYPEDEF/expr";
    }
  }
''')
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
        self._db_sess.add(adm)
        self._db_sess.commit()
        self.assertIsNone(adm.source.abs_file_path)

        self.assertEqual('example-mod', adm.name)
        self.assertEqual('example-mod', adm.norm_name)
        self.assertEqual(1, len(adm.imports))
        self.assertEqual(1, len(adm.revisions))

        self.assertEqual(1, len(adm.ctrl))
        obj = adm.ctrl[0]
        self.assertIsInstance(obj, models.Ctrl)
        self.assertEqual("test1", obj.name)
        self.assertEqual(2, len(obj.parameters.items))
        self.assertEqual("id", obj.parameters.items[0].name)
        self.assertEqual(
            self._from_text('//ietf-amm/typedef/any'),
            obj.parameters.items[0].typeobj.type_ari
        )

        self.assertEqual(1, len(adm.edd))
        obj = adm.edd[0]
        self.assertIsInstance(obj, models.Edd)
        self.assertEqual("edd1", obj.name)
        self.assertEqual(
            self._from_text('/aritype/int'),
            obj.typeobj.type_ari
        )

    def test_decode_groupings(self):
        buf = self._get_mod_buf('''
  amm:edd edd1 {
    amm:enum 4;
    amm:type "/ARITYPE/int";
    description
      "EDD test_int";
  }
  grouping paramgrp {
    amm:parameter id {
      amm:type "//ietf-amm/TYPEDEF/any";
    }
    amm:parameter def {
      amm:type "//ietf-amm/TYPEDEF/expr";
      amm:default "ari:/AC/()";
    }
  }
  amm:ctrl test1 {
    amm:enum 5;
    uses paramgrp;
  }
''')
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
        self._db_sess.add(adm)
        self._db_sess.commit()
        self.assertIsNone(adm.source.abs_file_path)

        self.assertEqual('example-mod', adm.name)
        self.assertEqual('example-mod', adm.norm_name)
        self.assertEqual(1, len(adm.imports))
        self.assertEqual(1, len(adm.revisions))

        self.assertEqual(1, len(adm.ctrl))
        obj = adm.ctrl[0]
        self.assertIsInstance(obj, models.Ctrl)
        self.assertEqual("test1", obj.name)

        self.assertEqual(2, len(obj.parameters.items))
        param = obj.parameters.items[0]
        self.assertEqual("id", param.name)
        self.assertEqual(
            self._from_text('//ietf-amm/typedef/any'),
            param.typeobj.type_ari
        )
        self.assertIsNone(param.default_value)
        self.assertIsNone(param.default_ari)
        param = obj.parameters.items[1]
        self.assertEqual("def", param.name)
        self.assertEqual(
            self._from_text('//ietf-amm/typedef/expr'),
            param.typeobj.type_ari
        )
        self.assertEqual("ari:/AC/()", param.default_value)
        self.assertEqual(
            self._from_text('ari:/AC/()'),
            param.default_ari
        )

        self.assertEqual(1, len(adm.edd))
        obj = adm.edd[0]
        self.assertIsInstance(obj, models.Edd)
        self.assertEqual("edd1", obj.name)
        self.assertEqual(
            self._from_text('/aritype/int'),
            obj.typeobj.type_ari
        )

    # As close to real YANG syntax as possible
    LOOPBACK_CASELIST = [
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:type "/ARITYPE/UINT" {
      range "10..40";
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:type "/ARITYPE/IDENT" {
      amm:base "./IDENT/name1";
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:type "/ARITYPE/UINT" {
      amm:int-labels {
        enum one {
          value 1;
        }
        enum three {
          value 3;
        }
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:type "/ARITYPE/UINT" {
      amm:int-labels {
        bit one {
          position 1;
        }
        bit three {
          position 3;
        }
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:type "/ARITYPE/CBOR" {
      amm:cddl "uint / tstr";
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:ulist {
      amm:type "/ARITYPE/TEXTSTR" {
        length "min..255";
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:umap {
      amm:keys {
        amm:type "/ARITYPE/TEXTSTR";
      }
      amm:values {
        amm:type "/ARITYPE/UINT";
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:umap {
      amm:keys {
        amm:type "/ARITYPE/TEXTSTR";
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:umap {
      amm:values {
        amm:type "/ARITYPE/UINT";
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:tblt {
      amm:column col1 {
        amm:type "/ARITYPE/TEXTSTR";
      }
    }
  }
''',

        '''\
  amm:ident name1 {
    amm:enum 2;
  }
  amm:ident name2 {
    amm:enum 3;
    amm:base "./IDENT/name1";
  }
''',
        '''\
  amm:ident base1 {
    amm:enum 1;
    description
      "one base";
  }
  amm:ident base2 {
    amm:enum 1;
    description
      "other base";
  }
  amm:ident derived {
    amm:enum 3;
    description
      "some value";
    amm:base "./IDENT/base1";
    amm:base "./IDENT/base2";
  }
''',

        '''\
  amm:const val {
    amm:enum 2;
    description
      "some value";
    amm:init-value "hi";
    amm:type "/ARITYPE/TEXTSTR";
  }
''',

        '''\
  amm:edd val {
    amm:enum 2;
    description
      "some value";
    amm:type "/ARITYPE/TEXTSTR" {
      pattern '.*hello.*';
    }
  }
''',
        '''\
  amm:edd val {
    amm:enum 2;
    description
      "some value";
    amm:parameter opt {
      amm:type "/ARITYPE/UINT";
    }
    amm:type "/ARITYPE/TEXTSTR";
  }
''',
        '''\
  amm:var val {
    amm:enum 2;
    description
      "some value";
    amm:type "/ARITYPE/INT";
  }
''',
        '''\
  amm:var val {
    amm:enum 2;
    description
      "some value";
    amm:init-value "3";
    amm:type "/ARITYPE/INT";
  }
''',

        '''\
  amm:ctrl dothing {
    amm:enum 2;
    description
      "do a thing";
    amm:parameter one {
      amm:type "/ARITYPE/INT";
    }
    amm:parameter two {
      amm:type "//ietf-amm/TYPEDEF/expr";
    }
  }
''',
        '''\
  amm:ctrl dothing {
    amm:enum 2;
    description
      "do a thing";
    amm:parameter one {
      amm:type "/ARITYPE/INT";
    }
    amm:result val {
      amm:type "/ARITYPE/INT";
    }
  }
''',

        '''\
  amm:oper sum {
    amm:enum 2;
    description
      "sum together values";
    amm:parameter count {
      amm:type "/ARITYPE/UINT";
    }
    amm:operand vals {
      amm:seq {
        amm:type "//ietf-amm/TYPEDEF/numeric";
      }
    }
    amm:result total {
      amm:type "//ietf-amm/TYPEDEF/numeric";
    }
  }
''',
    ]

    def test_loopback_caselist(self):
        enc = adm_yang.Encoder()

        for body in self.LOOPBACK_CASELIST:
            with self.subTest(body):
                buf_in = self._get_mod_buf(body)
                LOGGER.info('input:\n%s', buf_in.getvalue())

                adm = self._adm_dec.decode(buf_in)
                self.assertIsInstance(adm, models.AdmModule)
                self._db_sess.add(adm)
                self._db_sess.commit()

                self.assertEqual(1, len(adm.imports))
                self.assertEqual(1, len(adm.revisions))

                buf_out = io.StringIO()
                enc.encode(adm, buf_out)
                LOGGER.info('output:\n%s', buf_out.getvalue())
                self.assertEqual(buf_in.getvalue(), buf_out.getvalue())


class TestAdmContents(BaseYang):

    TYPE_CONSTRAINT = (
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/INT" {
      range "10..40";
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/REAL64" {
      range "10..40";
    }
  }
''', True),
        ('''\
  amm:typedef base {
    amm:type "/ARITYPE/INT";
  }
  // derived from unrestricted
  amm:typedef typeobj {
    amm:type "./TYPEDEF/base" {
      range "10..40";
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/TEXTSTR" {
      range "10..40";
    }
  }
''', False),

        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/TEXTSTR" {
      length "10..40";
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/BYTESTR" {
      length "10..40";
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/INT" {
      length "10..40";
    }
  }
''', False),

        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/TEXTSTR" {
      pattern "hello";
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/BYTESTR" {
      pattern "hello";
    }
  }
''', False),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/INT" {
      pattern "hello";
    }
  }
''', False),

        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/INT" {
      amm:int-labels {
        enum "first" {
          value -3;
        }
        enum "second" {
          value 10;
        }
      }
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/INT" {
      amm:int-labels {
      }
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/TEXTSTR" {
      amm:int-labels {
        enum "first" {
          value -3;
        }
        enum "second" {
          value 10;
        }
      }
    }
  }
''', False),

        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/CBOR" {
      amm:cddl "hi";
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/INT" {
      amm:cddl "hi";
    }
  }
''', False),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/BYTESTR" {
      amm:cddl "hi";
    }
  }
''', False),

        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/IDENT" {
      amm:base "//ietf-amm/IDENT/somename";
    }
  }
''', True),
        ('''\
  amm:typedef typeobj {
    amm:type "/ARITYPE/TEXTSTR" {
      amm:base "//ietf-amm/IDENT/somename";
    }
  }
''', False),
    )

    def test_type_constraint(self):
        for body, valid in self.TYPE_CONSTRAINT:
            with self.subTest(body):
                buf_in = self._get_mod_buf(body)
                LOGGER.info('input:\n%s', buf_in.getvalue())

                adm = self._adm_dec.decode(buf_in)
                self.assertIsInstance(adm, models.AdmModule)
                self._db_sess.add(adm)
                self._db_sess.commit()

                typedef = adm.typedef[0]
                action = lambda: lookup.TypeResolver().resolve(typedef.typeobj, adm)

                if valid:
                    self.assertIsNotNone(action())
                else:
                    with self.assertRaises(lookup.TypeResolverError):
                        action()

    def test_ident_base_constraint(self):
        buf = self._get_mod_buf('''
  amm:ident ident-a {
      description "A base ident";
  }
  amm:ident ident-b {
      amm:base "./IDENT/ident-a";
      description "A derived ident";
  }
  amm:ident ident-c {
      description "Another base ident";
  }
  amm:ident ident-d {
      amm:base "./IDENT/ident-a";
      amm:base "./IDENT/ident-c";
      description "Double derived";
  }
  amm:typedef type-any {
    amm:type "/ARITYPE/ident";
  }
  amm:typedef type-a {
    amm:type "/ARITYPE/ident" {
      amm:base "./IDENT/ident-a";
    }
  }
''')
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
        self._db_sess.add(adm)
        self._db_sess.commit()
        self.assertIsNone(adm.source.abs_file_path)

        self.assertEqual('example-mod', adm.name)
        self.assertEqual('example-mod', adm.norm_name)
        self.assertEqual(1, len(adm.imports))
        self.assertEqual(1, len(adm.revisions))

        self.assertEqual(4, len(adm.ident))
        self.assertEqual(2, len(adm.typedef))

        type_any = adm.typedef[0]
        self.assertEqual('type-any', type_any.norm_name)
        typeobj_any = lookup.TypeResolver().resolve(type_any.typeobj, adm)
        self.assertIsNone(typeobj_any.get(self._from_text('hi')))
        self.assertIsNotNone(typeobj_any.get(self._from_text('//example-mod/IDENT/ident-z')))
        self.assertIsNotNone(typeobj_any.get(self._from_text('//example-mod/IDENT/ident-a')))
        self.assertIsNotNone(typeobj_any.get(self._from_text('//example-mod/IDENT/ident-b')))
        self.assertIsNotNone(typeobj_any.get(self._from_text('//example-mod/IDENT/ident-c')))

        type_a = adm.typedef[1]
        self.assertEqual('type-a', type_a.norm_name)
        typeobj_a = lookup.TypeResolver().resolve(type_a.typeobj, adm)
        self.assertIsNone(typeobj_a.get(self._from_text('hi')))
        self.assertIsNone(typeobj_a.get(self._from_text('//example-mod/IDENT/ident-z')))
        self.assertIsNotNone(typeobj_a.get(self._from_text('//example-mod/IDENT/ident-a')))
        self.assertIsNotNone(typeobj_a.get(self._from_text('//example-mod/IDENT/ident-b')))
        self.assertIsNone(typeobj_a.get(self._from_text('//example-mod/IDENT/ident-c')))

    def test_ident_params(self):
        buf = self._get_mod_buf('''
  amm:ident ident-a {
    description "A base ident";
  }
  amm:ident ident-b {
    amm:parameter one {
      amm:type "/ARITYPE/INT";
    }
    amm:base "./IDENT/ident-a";
    description "A derived ident";
  }
''')
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
        self._db_sess.add(adm)
        self._db_sess.commit()
        self.assertIsNone(adm.source.abs_file_path)

        self.assertEqual('example-mod', adm.name)
        self.assertEqual('example-mod', adm.norm_name)
        self.assertEqual(1, len(adm.imports))
        self.assertEqual(1, len(adm.revisions))

        self.assertEqual(2, len(adm.ident))
        self.assertEqual(0, len(adm.typedef))

        obj = adm.ident[0]
        self.assertEqual('ident-a', obj.norm_name)
        self.assertEqual(0, len(obj.parameters.items))

        obj = adm.ident[1]
        self.assertEqual('ident-b', obj.norm_name)
        self.assertEqual(1, len(obj.parameters.items))
