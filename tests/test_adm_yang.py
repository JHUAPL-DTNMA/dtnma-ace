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
from ace import adm_yang, models

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


class TestAdmYang(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
        self._db_eng = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self._db_eng)
        self._db_sess = Session(self._db_eng)

        self._adm_dec = adm_yang.Decoder(FileRepository(path=os.path.join(SELFDIR, 'adms')))

    def tearDown(self):
        self._adm_dec = None

        self._db_sess.close()
        self._db_sess = None
        models.Base.metadata.drop_all(self._db_eng)
        self._db_eng = None

    EMPTY_MODULE = '''\
module empty {}
'''

    def test_decode_empty(self):
        buf = io.StringIO(self.EMPTY_MODULE)
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)

        self.assertEqual('empty', adm.name)

    NOOBJECT_MODULE_HEAD = '''\
module example-mod {
  yang-version 1.1;
  namespace "ari:/example-mod/";
  prefix empty;

  import ietf-amm {
    prefix amm;
  }

  revision 2023-10-31 {
    description
      "Initial test";
  }
  amm:enum 255;
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

    def test_decode_noobject(self):
        buf = self._get_mod_buf('')
        adm = self._adm_dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
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
    amm:type int;
    description
      "EDD test_int";
  }
  amm:ctrl test1 {
    amm:enum 5;
    amm:parameter id {
      amm:type amm:any;
    }
    amm:parameter def {
      amm:type amm:expr;
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
        self.assertEqual("any", obj.parameters.items[0].typeobj.type_name)

        self.assertEqual(1, len(adm.edd))
        obj = adm.edd[0]
        self.assertIsInstance(obj, models.Edd)
        self.assertEqual("edd1", obj.name)
        self.assertEqual("int", obj.typeobj.type_name)

    def test_decode_groupings(self):
        buf = self._get_mod_buf('''
  amm:edd edd1 {
    amm:enum 4;
    amm:type int;
    description
      "EDD test_int";
  }
  grouping paramgrp {
    amm:parameter id {
      amm:type amm:any;
    }
    amm:parameter def {
      amm:type amm:expr;
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
        self.assertEqual("id", obj.parameters.items[0].name)
        self.assertEqual("any", obj.parameters.items[0].typeobj.type_name)

        self.assertEqual(1, len(adm.edd))
        obj = adm.edd[0]
        self.assertIsInstance(obj, models.Edd)
        self.assertEqual("edd1", obj.name)
        self.assertEqual("int", obj.typeobj.type_name)

    # As close to real YANG syntax as possible
    LOOPBACK_CASELIST = [
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:type uint {
      range "10..40";
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:ulist {
      amm:type textstr {
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
        amm:type textstr;
      }
      amm:values {
        amm:type uint;
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:umap {
      amm:keys {
        amm:type textstr;
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:umap {
      amm:values {
        amm:type uint;
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:enum 2;
    amm:tblt {
      amm:column col1 {
        amm:type textstr;
      }
    }
  }
''',

        '''\
  amm:const val {
    amm:enum 2;
    amm:type textstr;
    amm:init-value "hi";
  }
''',

        '''\
  amm:edd val {
    amm:enum 2;
    amm:type textstr {
      pattern '.*hello.*';
    }
  }
''',
        '''\
  amm:edd val {
    amm:enum 2;
    amm:parameter opt {
      amm:type uint;
    }
    amm:type textstr;
  }
''',
        '''\
  amm:var val {
    amm:enum 2;
    amm:type int;
  }
''',
        '''\
  amm:var val {
    amm:enum 2;
    amm:type int;
    amm:init-value "3";
  }
''',

        '''\
  amm:ctrl dothing {
    amm:enum 2;
    amm:parameter one {
      amm:type int;
    }
    amm:parameter two {
      amm:type amm:expr;
    }
    description
      "do a thing";
  }
''',
        '''\
  amm:ctrl dothing {
    amm:enum 2;
    amm:parameter one {
      amm:type int;
    }
    amm:result val {
      amm:type int;
    }
    description
      "do a thing";
  }
''',

        '''\
  amm:oper sum {
    amm:enum 2;
    amm:parameter count {
      amm:type uint;
    }
    amm:operand vals {
      amm:seq {
        amm:type amm:numeric;
      }
    }
    amm:result total {
      amm:type amm:numeric;
    }
    description
      "sum together values";
  }
''',
    ]

    def test_loopback_examples(self):
        enc = adm_yang.Encoder()

        for body in self.LOOPBACK_CASELIST:
            with self.subTest(body):
                buf_in = self._get_mod_buf(body)
                LOGGER.info('input:\n%s', buf_in.getvalue())

                adm = self._adm_dec.decode(buf_in)
                self.assertIsInstance(adm, models.AdmModule)
                self.assertEqual(1, len(adm.imports))
                self.assertEqual(1, len(adm.revisions))
                self._db_sess.add(adm)
                self._db_sess.commit()

                buf_out = io.StringIO()
                enc.encode(adm, buf_out)
                LOGGER.info('output:\n%s', buf_out.getvalue())
                self.assertEqual(buf_in.getvalue(), buf_out.getvalue())

    def test_loopback_real_adms(self):

        def keep(name):
            return name.endswith('.yang')

        file_names = os.listdir(os.path.join(SELFDIR, 'adms'))
        file_names = tuple(filter(keep, file_names))
        self.assertLess(0, len(file_names))

        enc = adm_yang.Encoder()

        for name in file_names:
            with self.subTest(name):
                LOGGER.info('Handling file %s', name)

                file_path = os.path.join(SELFDIR, 'adms', name)
                with open(file_path, 'r', encoding='utf-8') as buf:
                    text_in = buf.read()
                    LOGGER.debug('ADM source:\n%s', text_in)
                    buf.seek(0)
                    adm = self._adm_dec.decode(buf)
                self.assertIsInstance(adm, models.AdmModule)
                self.assertEqual(
                    os.path.abspath(file_path),
                    adm.source.abs_file_path
                )
                self._db_sess.add(adm)
                self._db_sess.commit()

                out_first = io.StringIO()
                enc.encode(adm, out_first)
                text_first = out_first.getvalue()
                LOGGER.debug('out first:\n%s', text_first)

                out_first.seek(0)
                adm = self._adm_dec.decode(out_first)
                self.assertIsInstance(adm, models.AdmModule)
                self._db_sess.add(adm)
                self._db_sess.commit()

                out_second = io.StringIO()
                enc.encode(adm, out_second)
                text_second = out_second.getvalue()
                LOGGER.debug('out second:\n%s', text_second)

                # source ADM objects in original are not in canonical order
                # but loopback text outputs will be
                self.assertEqual(text_first, text_second)
