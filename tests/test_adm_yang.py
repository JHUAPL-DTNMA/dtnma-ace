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
        ('min..10', portion.closed(float('-inf'), 10)),
        # normalizing
        ('5..20 | 10..30', portion.closed(5, 30)),
    )

    def test_range_from_text(self):
        for row in self.RANGES:
            with self.subTest(f'{row}'):
                text, expect = row

                got = adm_yang.range_from_text(text)
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
  namespace "ari:/example-mod/";
  prefix empty;

  import ietf-amm {
    prefix amm;
  }

  revision 2023-10-31 {
    description
      "Initial test";
  }
  amm:enum "255";
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
    amm:type int;
    description
      "EDD test_int";
  }
  amm:ctrl test1 {
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
    amm:type uint;
  }
''',
        '''\
  amm:typedef typeobj {
    amm:ulist {
      amm:type textstr;
    }
  }
''',
        '''\
  amm:typedef typeobj {
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
    amm:umap {
      amm:keys {
        amm:type textstr;
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:umap {
      amm:values {
        amm:type uint;
      }
    }
  }
''',
        '''\
  amm:typedef typeobj {
    amm:tblt {
      amm:column col1 {
        amm:type textstr;
      }
    }
  }
''',
    ]
    '''
        (models.Var, {
            "name": "myname",
            "description": "Some long text",
            "type": "int",
        }),
        (models.Var, {
            "name": "myname",
            "description": "Some long text",
            "type": "int",
            "initializer": {
                "type": "int",
                "postfix-expr": [
                    {
                        "ns": "Amp/Agent",
                        "nm": "edd.num_tbr",
                    },
                ]
            },
        }),
        (models.Edd, {
            "name": "edd_name1",
            "type": "textstr",
            "description": "Description of an Edd"
        }),
        (models.Edd, {
            "name": "edd_name2",
            "type": "uvast",
            "description": "Second description of an Edd"
        }),
        (models.Const, {
            "name": "const_name",
            "type": "textstr",
            "description": "A description of a Const",
            "value": "some_value"
        }),
        (models.Const, {
            "name": "mac_name",
            "description": "A description of a Macro",
            "action": [{
                "ns": "DTN/bpsec",
                "nm": "Edd.num_bad_tx_bib_blks_src"
            }, {
                "ns": "Amp/Agent",
                "nm": "Oper.plusUINT"
            }]
        }),
        (models.Const, {
            "name": "rptt_name",
            "definition": [
                {
                    "ns": "DTN/bpsec",
                    "nm": "Edd.num_good_tx_bcb_blk"
                }, {
                    "ns": "DTN/bpsec",
                    "nm": "Edd.num_bad_tx_bcb_blk"
                }],
            "description": "A description of a Rptt",
        }),
        (models.Ctrl, {
            "name": "ctrl_name",
            "description": "A description of a Ctrl",
        }),
        (models.Ctrl, {
            "name": "another_ctrl_name",
            "parmspec": [{
                "type": "ARI",
                "name": "id"
            },
                {
                "type": "EXPR",
                "name": "def"
            },
                {
                "type": "BYTE",
                "name": "type"
            }],
            "description": "another Ctrl description",
        }),
        (models.Oper, {
            "name": "some_op_name",
            "result-type": "int",
            "in-type": [
                "int",
                "int",
            ],
            "description": "a description of an Operator"
        }),
        # (models.Sbr, {}),
        # (models.Tbr, {}),
    ]
    '''

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
                LOGGER.info('sub %s', adm.typedef[0].typeobj)
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
                    indata = buf.read()
                    LOGGER.debug('%s', indata)
                    buf.seek(0)
                    adm = self._adm_dec.decode(buf)
                self.assertIsInstance(adm, models.AdmModule)
                self.assertEqual(
                    os.path.abspath(file_path),
                    adm.source.abs_file_path
                )
                self._db_sess.add(adm)
                self._db_sess.commit()

                outbuf = io.StringIO()
                enc.encode(adm, outbuf)
                outbuf.seek(0)
                outdata = outbuf.getvalue()
                LOGGER.debug('%s', outdata)

                # FIXME objects in original are not in canonical order
                # self.assertEqual(indata, outdata)
