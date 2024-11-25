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
''' Verify behavior of the ace.ari_cbor module tree.
'''
import datetime
import base64
import io
import logging
import unittest
import cbor2
from ace.ari import ReferenceARI, LiteralARI, StructType
from ace.cborutil import to_diag
from ace import ari_cbor

LOGGER = logging.getLogger(__name__)


class TestAriCbor(unittest.TestCase):

    LITERAL_DATAS = [
        # BOOL
        (base64.b16decode('F5'), True),
        (base64.b16decode('F4'), False),
        # INT
        (base64.b16decode('00'), 0),
        (base64.b16decode('0A'), 10),
        (base64.b16decode('29'), -10),
        # FLOAT
        (cbor2.dumps(0.01), 0.01),
        (cbor2.dumps(1e2), 1e2),
        (cbor2.dumps(1e-2), 1e-2),
        (cbor2.dumps(-1e2), -1e2),
        (cbor2.dumps(1.25e2), 1.25e2),
        (cbor2.dumps(1e25), 1e25),
        # TEXTSTR
        (cbor2.dumps("hi"), 'hi'),
        # BYTESTR
        (cbor2.dumps(b'hi'), b'hi'),
        # Times
        (cbor2.dumps([StructType.TP, 101]), (ari_cbor.DTN_EPOCH + datetime.timedelta(seconds=101))),
        (cbor2.dumps([StructType.TP, [1, 3]]), (ari_cbor.DTN_EPOCH + datetime.timedelta(seconds=1000))),
        (cbor2.dumps([StructType.TD, 18]), datetime.timedelta(seconds=18)),
        (cbor2.dumps([StructType.TD, -18]), -datetime.timedelta(seconds=18)),
    ]

    def test_literal_cbor_loopback(self):
        dec = ari_cbor.Decoder()
        enc = ari_cbor.Encoder()
        for row in self.LITERAL_DATAS:
            if len(row) == 2:
                data, val = row
                exp_loop = data
            elif len(row) == 3:
                data, val, exp_loop = row
            LOGGER.warning('Testing data: %s', to_diag(data))

            ari = dec.decode(io.BytesIO(data))
            LOGGER.warning('Got ARI %s', ari)
            self.assertIsInstance(ari, LiteralARI)
            self.assertEqual(ari.value, val)

            loop = io.BytesIO()
            enc.encode(ari, loop)
            LOGGER.warning('Got data: %s', to_diag(loop.getvalue()))
            self.assertEqual(
                base64.b16encode(loop.getvalue()),
                base64.b16encode(exp_loop)
            )

    REFERENCE_DATAS = [
        # from 'ari:/bp-agent/CTRL/reset_all_counts()',
        cbor2.dumps([0, StructType.CTRL.value, 10]),

    ]

    def test_reference_cbor_loopback(self):
        dec = ari_cbor.Decoder()
        enc = ari_cbor.Encoder()
        for data in self.REFERENCE_DATAS:
            LOGGER.warning('Testing data: %s', to_diag(data))

            ari = dec.decode(io.BytesIO(data))
            LOGGER.warning('Got ARI %s', ari)
            self.assertIsInstance(ari, ReferenceARI)

            loop = io.BytesIO()
            enc.encode(ari, loop)
            LOGGER.warning('Got data: %s', to_diag(loop.getvalue()))
            loop.seek(0)
            LOGGER.warning('Re-decode ARI %s', dec.decode(loop))
            self.assertEqual(
                base64.b16encode(loop.getvalue()),
                base64.b16encode(data)
            )

    INVALID_DATAS = [
        b'',
        cbor2.dumps([]),
    ]

    def test_invalid_enc_failure(self):
        dec = ari_cbor.Decoder()
        for data in self.INVALID_DATAS:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

#    def test_complex_decode(self):
#        text = 'ari:/IANA:Amp.Agent/Ctrl.gen_rpts([ari:/IANA:DTN.bpsec/Rptt.source_report("ipn:1.1")],[])'
#        dec = ari_text.Decoder()
#        ari = dec.decode(text)
#        LOGGER.warning('Got ARI %s', ari)
#        self.assertIsInstance(ari, (ReferenceARI, LiteralARI))
#        self.assertEqual(ari.ident.ns_id, 'IANA:Amp.Agent')
#        self.assertEqual(ari.ident.obj_id, 'Ctrl.gen_rpts')
#        self.assertIsInstance(ari.params[0], AC)


    def test_ari_cbor_encode_objref_path_text(self):
        TEST_CASE = [
            ("example-adm-a@2024-06-25", False, 0, None,
          "8378186578616D706C652D61646D2D6140323032342D30362D3235F6F6"),
            ("example-adm-a", False, 0, None, "836D6578616D706C652D61646D2D61F6F6"),
            ("!example-odm-b",False, 0, None, "836E216578616D706C652D6F646D2D62F6F6"),
            ("adm", False, 0, None, "836361646DF6F6"),
            (None, True, ARI_TYPE_CONST, "hi", "83F621626869"),
            ("adm", True, ARI_TYPE_CONST, "hi", "836361646D21626869"),
            ("test", True, ARI_TYPE_CONST, "that", "836474657374216474686174"),
            ("test@1234", True, ARI_TYPE_CONST, "that", "8369746573744031323334216474686174"),
            ("!test", True, ARI_TYPE_CONST, "that", "83652174657374216474686174"),
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_encode_objref_path_int(self):
        TEST_CASE = [
            (True, 18, False, 0, False, 0, "8312F6F6"),
            (True, 65536, False, 0, False, 0, "831A00010000F6F6"),
            (True, -20, False, 0, False, 0, "8333F6F6"),
            (False, 0, True, ARI_TYPE_IDENT, True, 34, "83F6201822"),
            (True, 18, True, ARI_TYPE_IDENT, True, 34, "8312201822"),
        ]

        #TODO: add function code

    def test_ari_cbor_decode_objref_path_text(self):
        TEST_CASE = [
            ("836361646D21626869", "adm", ARI_TYPE_CONST, "hi"),
            ("836474657374216474686174", "test", ARI_TYPE_CONST, "that"),
            ("8369746573744031323334216474686174", "test@1234", ARI_TYPE_CONST, "that"),
            ("83652174657374216474686174", "!test", ARI_TYPE_CONST, "that"),
            ("846474657374226474686174811822", "test", ARI_TYPE_CTRL, "that"),
        ]

        #TODO: add function code

    def test_ari_cbor_decode_objref_path_int(self):
        TEST_CASE = [
            ("8312201822", 18, ARI_TYPE_IDENT, 34),
            ("8402220481626869", 2, ARI_TYPE_CTRL, 4),
        ]
        #TODO: add function code 

    def test_ari_cbor_decode_rptset(self):
        TEST_CASE = [
            ("8215831904D21903E8850083647465737422626869F603426869", 1234, 1000, 0,
          1),
          ("8215831904D282211904D2850083647465737422626869F603426869", 1234, 12, 340000000, 1)
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_encode_rptset(self):
        TEST_CASE = [
            ("82158282041904D21903E8", 1234, 1000, 0)
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    #TODO: add unit tests with no TEST_CASEs like test_ari_cbor_decode_lit_prim_undef()?

    def test_ari_cbor_decode_lit_prim_bool(self):
        TEST_CASE = [
            ("F4", False),
            ("F5", True),
        ]
        
        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_lit_prim_int64(self):
        TEST_CASE = [
            ("3B7FFFFFFFFFFFFFFF", -0x8000000000000000),
            ("29", -10),
            ("20", -1),
            ("00", 0),
            ("01", 1),
            ("0a", 10),
            ("1904D2", 1234),
            ("1B0000000100000000", 4294967296),
            ("1B7FFFFFFFFFFFFFFF", 0x7FFFFFFFFFFFFFFF),
        ]
        
        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_lit_prim_uint64(self):
        TEST_CASE = [
            ("1B8000000000000000", 0x8000000000000000),
            ("1BFFFFFFFFFFFFFFFF", 0xFFFFFFFFFFFFFFFF),
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_lit_prim_float64(self):
        TEST_CASE = [
            ("F90000", 0.0),
            ("F93E00", 1.5),
            ("F97E00", (float('nan'))),
            ("F97C00", (float('infinity'))),
            ("F9FC00", (float('-infinity'))),
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_lit_prim_tstr(self):
        TEST_CASE = [
            ("60", ""),
            ("626869", "hi")
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_lit_prim_bstr(self):
        TEST_CASE = [
            ("40", None, 0),
            ("426869", "hi", 2)
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_lit_typed_bool(self):
        TEST_CASE = [
            ("8201F4", False),
            ("8201F5", True)
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))


    def test_ari_cbor_decode_lit_typed_int64(self):
        TEST_CASE = [
            ("820200", ARI_TYPE_BYTE, 0),
            ("82021864", ARI_TYPE_BYTE, 100),
            ("82041864", ARI_TYPE_INT, 100),
            ("82051864", ARI_TYPE_UINT, 100),
            ("82061864", ARI_TYPE_VAST, 100),
            ("82071864", ARI_TYPE_UVAST, 100)
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_lit_typed_real64(self):
        TEST_CASE = [
            ("8209F93E00", True)
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_failure(self):
        TEST_CASE = [
            (b"8402202020"),
            (b"A0"),
            (b"821182A0820417"),
            (b"8364746573740A6474686174"),
            (b"821386030102030405"),
            (b"821380"),
            (b"8213816474657374"),
            (b"8213816474657374"), #note the duplicate test cases are on purpose
            (b"82148120"),
            (b"82158264746573741A2B450625"),
            (b"821582FB3FF33333333333331A2B450625"),
            (b"8215831904D26474657374850083647465737422626869F603426869"),
            (b"8215831904D28209F93C00850083647465737422626869F603426869"),

        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_partial(self):
        TEST_CASE = [("0001")]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

    def test_ari_cbor_decode_invalid(self):
        TEST_CASE = [
            ("820001"),                 
            ("820101"),                 
            ("820220"),                 
            ("8212A182040AF5"),         
            ("8202190100"),             
            ("82043A80000000"),        
            ("82041A80000000"),         
            ("820520"),                 
            ("82051B0000000100000000"), 
            ("82061B8000000000000000"), 
            ("820720"),                
            ("8208FBC7EFFFFFE091FF3D"), 
            ("8208FB47EFFFFFE091FF3D"), 
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))


    def test_ari_cbor_loopback(self):
        TEST_CASE = [
            ("F7"),
            ("F6"),
            ("8201F4"),
            ("8201F5"),
            ("82041864"),
            ("82051864"),
            ("82061864"),
            ("82071864"),
            ("8212A303F50A626869626F6804"),
            ("8464746573742A6474686174811822"),
            ("F5"),
            ("F4"),
            ("1904D2"),
            ("626869"),
            ("686869207468657265"),
            ("426869"),
            ("8200F6"),
            ("8201F4"),
            ("8201F5"),
            ("82040A"),
            ("820429"),
            ("8208F94900"),
            ("8208FB4024333333333333"),
            ("8208FB3FB999999999999A"),
            ("8208F97E00"),
            ("8209F97C00"),
            ("8209F9FC00"),
            ("820B426869"),
            ("820A626869"),
            ("820A686869207468657265"),
            ("820E626869"),
            ("820E01"),
            ("820EFB3FF3333333333333"),
            ("820C1A2B450625"),
            ("821180"),
            ("8211816161"),
            ("821183616161626163"),
            ("821182F6820417"),
            ("821182F6821183F7820417821180"),
            ("8212A0"),
            ("8212A303F50A626869626F6804"),
            ("82138403010203"),
            ("82138703010203040506"),
            ("82138100"),
            ("82138101"),
            ("821481F6"),
            ("8214821904D283647465737422626869"),
            ( "8214834268698364746573742262686983647465737422626568"),
            ("8215831904D21903E8850083647465737422626869F603426869"),
            ("8215831904D21A2B450625850083647465737422626869F603426869"),
            ("836474657374216474686174"),
            ("8369746573744031323334216474686174"),
            ("83652174657374216474686174"),
            ("846474657374226474686174811822"),
            ("8402220481626869"),
            ("820F410A"),
            ("820F4BA164746573748203F94480"),
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))
