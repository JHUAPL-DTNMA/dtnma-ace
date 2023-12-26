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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
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

    TEST_FILE_PATH = os.path.join(SELFDIR, 'test-adm-minimal.yang')

    maxDiff = None

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

    EMPTY_MODULE = '''\
module empty {}
'''

    def test_decode_empty(self):
        dec = adm_yang.Decoder(adm_yang.EmptyRepos())

        buf = io.StringIO(self.EMPTY_MODULE)
        adm = dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)

        self.assertEqual('empty', adm.name)

    NOOBJECT_MODULE = '''\
module empty {
  namespace "ari:/empty";
  prefix empty;
  amm:enum "0";

  import ietf-amm {
    prefix amm;
  }

}
'''

    def test_decode_noobject(self):
        dec = adm_yang.Decoder(adm_yang.EmptyRepos())

        buf = io.StringIO(self.NOOBJECT_MODULE)
        adm = dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)

        self.assertEqual('empty', adm.name)
        self.assertEqual(0, len(adm.typedef))
        self.assertEqual(0, len(adm.const))
        self.assertEqual(0, len(adm.edd))
        self.assertEqual(0, len(adm.var))
        self.assertEqual(0, len(adm.ctrl))
        self.assertEqual(0, len(adm.oper))

    def test_decode_minimal(self):
        dec = adm_yang.Decoder(adm_yang.EmptyRepos())

        with open(self.TEST_FILE_PATH, 'r') as buf:
            adm = dec.decode(buf)
        self.assertIsInstance(adm, models.AdmModule)
        self.assertEqual(
            adm.source.abs_file_path,
            os.path.realpath(self.TEST_FILE_PATH)
        )

        self.assertEqual('test-adm-minimal', adm.name)
        self.assertEqual('test-adm-minimal', adm.norm_name)

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
        (models.Typedef, {
            "name": "tblt_name",
            "columns": [{"type": "textstr", "name": "rule1"},
                        {"type": "textstr", "name": "rule2"},
                        {"type": "uint", "name": "rule3"},
                        {"type": "textstr", "name": "rule4"},
                        {"type": "textstr", "name": "rule5"}
                        ],
            "description": "Tblt Rules description."
        }),
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

    @unittest.skip  # FIXME: reinstate later
    def test_loopback_obj(self):
        # Test per-object loopback with normal and special cases
        dec = adm_yang.Decoder(adm_yang.EmptyRepos())
        enc = adm_yang.Encoder()
        for case in self.LOOPBACK_CASELIST:
            cls, json_in = case
            LOGGER.warning('%s', json.dumps(json_in, indent=2))

            orm_obj = dec.from_json_obj(cls, json_in)
            self._db_sess.add(orm_obj)
            self._db_sess.commit()

            json_out = enc.to_json_obj(orm_obj)
            LOGGER.warning('%s', json.dumps(json_out, indent=2))
            self.assertEqual(json_in, json_out)

    def test_loopback_adm(self):
        dec = adm_yang.Decoder(adm_yang.EmptyRepos())
        enc = adm_yang.Encoder()

        with open(self.TEST_FILE_PATH, 'r', encoding='utf-8') as buf:
            indata = buf.read()
            buf.seek(0)
            adm = dec.decode(buf)
        LOGGER.warning('%s', indata)

        outbuf = io.StringIO()
        enc.encode(adm, outbuf)
        outbuf.seek(0)
        outdata = outbuf.getvalue()
        LOGGER.warning('%s', outdata)

        # Compare as decoded JSON (the infoset, not the encoded bytes)
        self.assertEqual(indata, outdata)

    @unittest.skip  # FIXME: reinstate later
    def test_loopback_real_adms(self):

        def keep(name):
            return name.endswith('.yang')

        file_names = os.listdir(os.path.join(SELFDIR, 'adms'))
        file_names = tuple(filter(keep, file_names))
        self.assertLess(0, len(file_names))

        for name in file_names:
            LOGGER.warning('Handling file %s', name)
            dec = adm_yang.Decoder(adm_yang.EmptyRepos())
            enc = adm_yang.Encoder()

            file_path = os.path.join(SELFDIR, 'adms', name)
            with open(file_path, 'r', encoding='utf-8') as buf:
                indata = buf.read()
                buf.seek(0)
                adm = dec.decode(buf)
            LOGGER.warning('%s', indata)

            outbuf = io.StringIO()
            enc.encode(adm, outbuf)
            outbuf.seek(0)
            outdata = outbuf.getvalue()
            LOGGER.warning('%s', outdata)

            # Compare as decoded JSON (the infoset, not the encoded bytes)
            self.assertEqual(indata, outdata)
