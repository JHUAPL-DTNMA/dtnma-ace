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
''' Verify behavior of the ace.adm_json module tree.
'''
import io
import json
import logging
import os
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from ace import adm_json, models


LOGGER = logging.getLogger(__name__)
SELFDIR = os.path.dirname(__file__)


class TestAdmJson(unittest.TestCase):

    TEST_FILE_PATH = os.path.join(SELFDIR, 'test_adm_minimal.json')
    
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

    def test_load_minimal(self):
        with open(self.TEST_FILE_PATH, 'rb') as buf:
            obj = json.load(buf)
        self.assertIsInstance(obj, dict)
        for sec in ('Mdat', 'Const', 'Ctrl', 'Edd'):
            self.assertIn(sec, obj)

    def test_decode_minimal(self):
        dec = adm_json.Decoder()

        with open(self.TEST_FILE_PATH, 'rb') as buf:
            adm = dec.decode(buf)
        self.assertEqual(adm.abs_file_path,
                         os.path.realpath(self.TEST_FILE_PATH))

        self.assertEqual(4, len(adm.mdat))

        self.assertEqual(1, len(adm.ctrl))
        obj = adm.ctrl[0]
        self.assertIsInstance(obj, models.Ctrl)
        self.assertEqual("test1", obj.name)
        self.assertEqual(2, len(obj.parmspec.items))
        self.assertEqual("ARI", obj.parmspec.items[0].type)
        self.assertEqual("id", obj.parmspec.items[0].name)

        self.assertEqual(1, len(adm.edd))
        obj = adm.edd[0]
        self.assertIsInstance(obj, models.Edd)
        self.assertEqual("edd1", obj.name)
        self.assertEqual("INT", obj.type)

    # As close to real JSON as possible
    LOOPBACK_CASELIST = [
        (models.Var, {
            "name": "myname",
            "description": "Some long text",
            "type": "INT",
        }),
        (models.Var, {
            "name": "myname",
            "description": "Some long text",
            "type": "INT",
            "initializer": {
                "type": "INT",
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
            "type": "STR",
            "description": "Description of an Edd"
        }),
        (models.Edd, {
            "name": "edd_name2",
            "type": "UVAST",
            "description": "Second description of an Edd"
        }),
        (models.Const, {
            "name": "const_name",
            "type": "STR",
            "description": "A description of a Const",
            "value": "some_value"
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
        (models.Mac, {
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
        (models.Oper, {
            "name": "some_op_name",
            "result-type": "INT",
            "in-type": [
                "INT",
                "INT",
            ],
            "description": "a description of an Operator"
        }),
        (models.Rptt, {
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
        # (models.Sbr, {}),
        # (models.Tbr, {}),
        (models.Tblt, {
            "name": "tblt_name",
            "columns": [{"type": "STR", "name": "rule1"},
                        {"type": "STR", "name": "rule2"},
                        {"type": "UINT", "name": "rule3"},
                        {"type": "STR", "name": "rule4"},
                        {"type": "STR", "name": "rule5"}
                        ],
            "description": "Tblt Rules description."
        }),
    ]

    def test_loopback_obj(self):
        # Test per-object loopback with normal and special cases
        dec = adm_json.Decoder()
        enc = adm_json.Encoder()
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
        dec = adm_json.Decoder()
        enc = adm_json.Encoder()

        with open(self.TEST_FILE_PATH, 'r', encoding='utf-8') as buf:
            indata = json.load(buf)
            buf.seek(0)
            adm = dec.decode(buf)
        LOGGER.warning('%s', json.dumps(indata, indent=2))

        outbuf = io.BytesIO()
        enc.encode(adm, outbuf)
        outbuf.seek(0)
        outdata = json.load(outbuf)
        LOGGER.warning('%s', json.dumps(outdata, indent=2))

        # Compare as decoded JSON (the infoset, not the encoded bytes)
        self.assertEqual(indata, outdata)

    def test_loopback_real_adms(self):
        
        def keep(name):
            return name.endswith('.json') and name != 'index.json'
        
        file_names = os.listdir(os.path.join(SELFDIR, 'adms'))
        file_names = tuple(filter(keep, file_names))
        self.assertLess(0, len(file_names))

        for name in file_names:
            LOGGER.warning('Handling file %s', name)
            dec = adm_json.Decoder()
            enc = adm_json.Encoder()
    
            file_path = os.path.join(SELFDIR, 'adms', name)
            with open(file_path, 'r', encoding='utf-8') as buf:
                indata = json.load(buf)
                buf.seek(0)
                adm = dec.decode(buf)
            LOGGER.warning('%s', json.dumps(indata, indent=2))
    
            outbuf = io.BytesIO()
            enc.encode(adm, outbuf)
            outbuf.seek(0)
            outdata = json.load(outbuf)
            LOGGER.warning('%s', json.dumps(outdata, indent=2))
    
            # Compare as decoded JSON (the infoset, not the encoded bytes)
            self.assertEqual(indata, outdata)
