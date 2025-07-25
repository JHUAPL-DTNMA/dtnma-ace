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
''' Verify behavior of the ace.ari_cbor module tree.
'''
import datetime
import base64
import io
import logging
import unittest
import cbor2
import math
from ace.ari import ReferenceARI, LiteralARI, StructType, Identity, ReportSet
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
        (cbor2.dumps(0.01, canonical=True), 0.01),
        (cbor2.dumps(1e2, canonical=True), 1e2),
        (cbor2.dumps(1e-2, canonical=True), 1e-2),
        (cbor2.dumps(-1e2, canonical=True), -1e2),
        (cbor2.dumps(1.25e2, canonical=True), 1.25e2),
        (cbor2.dumps(1e25, canonical=True), 1e25),
        # TEXTSTR
        (cbor2.dumps("hi"), 'hi'),
        # BYTESTR
        (cbor2.dumps(b'hi'), b'hi'),
        # Times
        (cbor2.dumps([StructType.TP, 101]), (ari_cbor.DTN_EPOCH + datetime.timedelta(seconds=101))),
        (cbor2.dumps([StructType.TP, [3, 1]]), (ari_cbor.DTN_EPOCH + datetime.timedelta(seconds=1000))),
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
            with self.subTest(f'Testing data: {to_diag(data)}'):
                ari = dec.decode(io.BytesIO(data))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, LiteralARI)
                self.assertEqual(ari.value, val)

                loop = io.BytesIO()
                enc.encode(ari, loop)
                LOGGER.info('Got data: %s', to_diag(loop.getvalue()))
                self.assertEqual(
                    base64.b16encode(loop.getvalue()),
                    base64.b16encode(exp_loop)
                )

    REFERENCE_DATAS = [
        # from `ari://65535/1/`
        cbor2.dumps([65535, 1, None, None]),
        # from `ari://65535/hi/`
        cbor2.dumps([65535, "hi", None, None]),
        # from 'ari:/ietf/dtnma-agent@2024-06-25/',
        cbor2.dumps([1, 1, cbor2.CBORTag(1004, "2024-06-25"), None, None]),
        # from `ari://65535/1/CTRL/0`
        cbor2.dumps([65535, 1, StructType.CTRL.value, 0]),
        # from 'ari:/ietf/bp-agent/CTRL/reset_all_counts()',
        cbor2.dumps([1, "bp-agent", StructType.CTRL.value, 10]),
    ]

    def test_reference_cbor_loopback(self):
        dec = ari_cbor.Decoder()
        enc = ari_cbor.Encoder()
        for data in self.REFERENCE_DATAS:
            LOGGER.info('Testing data: %s', to_diag(data))

            ari = dec.decode(io.BytesIO(data))
            LOGGER.info('Got ARI %s', ari)
            self.assertIsInstance(ari, ReferenceARI)

            loop = io.BytesIO()
            enc.encode(ari, loop)
            LOGGER.info('Got data: %s', to_diag(loop.getvalue()))
            loop.seek(0)
            LOGGER.info('Re-decode ARI %s', dec.decode(loop))
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
            LOGGER.info('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

#    def test_complex_decode(self):
#        text = 'ari:/IANA:Amp.Agent/Ctrl.gen_rpts([ari:/IANA:DTN.bpsec/Rptt.source_report("ipn:1.1")],[])'
#        dec = ari_text.Decoder()
#        ari = dec.decode(text)
#        LOGGER.info('Got ARI %s', ari)
#        self.assertIsInstance(ari, (ReferenceARI, LiteralARI))
#        self.assertEqual(ari.ident.ns_id, 'IANA:Amp.Agent')
#        self.assertEqual(ari.ident.obj_id, 'Ctrl.gen_rpts')
#        self.assertIsInstance(ari.params[0], AC)

    def test_ari_cbor_encode_objref_path_text(self):
        TEST_CASE = [
            ("example", "adm-a@2024-06-25", None, None, b"84676578616D706C657061646D2D6140323032342D30362D3235F6F6"),
            ("example", "adm-a", None, None, b"84676578616D706C656561646D2D61F6F6"),
            ("example", "!odm-b", None, None, b"84676578616D706C6566216F646D2D62F6F6"),
            (65535, "adm", None, None, b"8419FFFF6361646DF6F6"),
            (None, None, StructType.CONST, "hi", b"84F6F621626869"),
            (65535, "adm", StructType.CONST, "hi", b"8419FFFF6361646D21626869"),
            (65535, "test", StructType.CONST, "that", b"8419FFFF6474657374216474686174"),
            (65535, "test@1234", StructType.CONST, "that", b"8419FFFF69746573744031323334216474686174"),
            (65535, "!test", StructType.CONST, "that", b"8419FFFF652174657374216474686174"),
        ]

        enc = ari_cbor.Encoder()
        for row in TEST_CASE:
            org_id, model_id, type_id, obj_id, expect = row
            with self.subTest(expect):
                ari = ReferenceARI(
                    ident=Identity(org_id=org_id, model_id=model_id, type_id=type_id, obj_id=obj_id),
                    params=None
                )
                loop = io.BytesIO()
                enc.encode(ari, loop)
                # LOGGER.info('Got text_dn: %s', loop.getvalue())
                # self.assertEqual(expect, loop.getvalue())
                LOGGER.info('Got data: %s', to_diag(loop.getvalue()))
                self.assertEqual(
                    base64.b16encode(loop.getvalue()),
                    expect  # base64.b16encode(expect)
                )

    def test_ari_cbor_encode_objref_path_int(self):
        TEST_CASE = [
            (65535, 18, None, None, b"8419FFFF12F6F6"),
            (65535, -20, None, None, b"8419FFFF33F6F6"),
            (None, None, StructType.IDENT, 34, b"84F6F6201822"),
            (65535, 18, StructType.IDENT, 34, b"8419FFFF12201822"),
        ]

        enc = ari_cbor.Encoder()
        for row  in TEST_CASE:
            org_id, model_id, type_id, obj_id, expect = row
            ari = ReferenceARI(
                ident=Identity(org_id=org_id, model_id=model_id, type_id=type_id, obj_id=obj_id),
                params=None
            )
            buf = io.BytesIO()
            enc.encode(ari, buf)
            LOGGER.info('Got data: %s', to_diag(buf.getvalue()))
            self.assertEqual(
                base64.b16encode(buf.getvalue()),
                expect)

    def test_ari_cbor_encode_objref_AM(self):
        TEST_CASE = [
            ("example", "adm", StructType.EDD, "myEDD", {
                LiteralARI(value=True, type_id=None):
                LiteralARI(value=True, type_id=StructType.BOOL)},
                b'85676578616D706C656361646D23656D79454444A1F58201F5'),
            (65535, 18, StructType.IDENT, "34", {
                LiteralARI(value=101, type_id=None):
                LiteralARI(value=11, type_id=StructType.IDENT)},
                b'8519FFFF1220623334A1186582200B')
        ]

        enc = ari_cbor.Encoder()
        for row in TEST_CASE:
            org_id, model_id, type_id, obj_id, params, expect = row
            with self.subTest(expect):
                ari = ReferenceARI(
                    ident=Identity(org_id=org_id, model_id=model_id, type_id=type_id, obj_id=obj_id),
                    params=params
                )
                loop = io.BytesIO()
                enc.encode(ari, loop)
                LOGGER.info('Got data: %s', to_diag(loop.getvalue()))
                self.assertEqual(
                    base64.b16encode(loop.getvalue()),
                    expect  # base64.b16encode(expect)
                )

    def test_ari_cbor_decode_objref_path_text(self):
        TEST_CASE = [
            ("84676578616D706C656361646D21626869", "example", "adm", StructType.CONST, "hi"),
            ("84676578616D706C656474657374216474686174", "example", "test", StructType.CONST, "that"),
            ("84676578616D706C6569746573744031323334216474686174", "example", "test@1234", StructType.CONST, "that"),
            ("84676578616D706C65652174657374216474686174", "example", "!test", StructType.CONST, "that"),
            ("85676578616D706C656474657374226474686174811822", "example", "test", StructType.CTRL, "that"),
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect_org_id, expect_model_id, expect_type_id, expect_obj_id = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.ident.org_id, expect_org_id)
            self.assertEqual(ari.ident.model_id, expect_model_id)
            self.assertEqual(ari.ident.type_id, expect_type_id)
            self.assertEqual(ari.ident.obj_id, expect_obj_id)

    def test_ari_cbor_decode_objref_path_int(self):
        TEST_CASE = [
            ("8419FFFF12201822", 65535, 18, StructType.IDENT, 34),
            ("8519FFFF02220481626869", 65535, 2, StructType.CTRL, 4),
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect_org_id, expect_model_id, expect_type_id, expect_obj_id = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.ident.org_id, expect_org_id)
            self.assertEqual(ari.ident.model_id, expect_model_id)
            self.assertEqual(ari.ident.type_id, expect_type_id)
            self.assertEqual(ari.ident.obj_id, expect_obj_id)

    def test_ari_cbor_decode_rptset(self):
        TEST_CASE = [
          ("8215831904D21903E885008419FFFF647465737422626869F603426869", 1234, 1000, 0, 1),
          ("8215831904D282211904D285008419FFFF647465737422626869F603426869", 1234, 12, 340000000, 1),
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect_nonce, expect_sec, expect_nsec, expect_reports = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.type_id, StructType.RPTSET)
            self.assertEqual(ari.value.nonce.value, expect_nonce)
            delta = (ari.value.ref_time - ari_cbor.DTN_EPOCH).total_seconds()
            sec = int(delta)
            nsec = round((delta % 1) * 1000000000)
            self.assertEqual(sec, expect_sec)
            self.assertEqual(nsec, expect_nsec)
            self.assertEqual(len(ari.value.reports), expect_reports)


    def test_ari_cbor_encode_rptset(self):
       TEST_CASE = [
           (b"8215821904D2820301", 1234, 1000, 0)
       ]

       enc = ari_cbor.Encoder()
       for row  in TEST_CASE:
           expect, nonce, sec, nsec = row
           t = ari_cbor.DTN_EPOCH + datetime.timedelta(0, sec)
           rptset = ReportSet(
             nonce = LiteralARI(nonce),
             ref_time = t,
             reports = [])
           ari = LiteralARI(value = rptset, type_id = StructType.RPTSET)
           loop = io.BytesIO()
           enc.encode(ari, loop)
           LOGGER.info('Got data: %s', to_diag(loop.getvalue()))
           self.assertEqual(
               base64.b16encode(loop.getvalue()),
               expect)

    def test_ari_cbor_decode_lit_prim_bool(self):
        TEST_CASE = [
            ("F4", False),
            ("F5", True),
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, None)

    def test_ari_cbor_decode_lit_prim_int64(self):
        TEST_CASE = [
            ("3B7FFFFFFFFFFFFFFF", -0x8000000000000000),
            ("29", -10),
            ("20", -1),
            ("00", 0),
            ("01", 1),
            ("0A", 10),
            ("1904D2", 1234),
            ("1B0000000100000000", 4294967296),
            ("1B7FFFFFFFFFFFFFFF", 0x7FFFFFFFFFFFFFFF),
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, None)

    def test_ari_cbor_decode_lit_prim_uint64(self):
        TEST_CASE = [
            ("1B8000000000000000", 0x8000000000000000),
            ("1BFFFFFFFFFFFFFFFF", 0xFFFFFFFFFFFFFFFF),
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, None)

    def test_ari_cbor_decode_lit_prim_float64(self):
        TEST_CASE = [
            ("F90000", 0.0),
            ("F93E00", 1.5),
            ("F97E00", (float('nan'))),
            ("F97C00", (float('infinity'))),
            ("F9FC00", (float('-infinity'))),
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            if math.isnan(expect):
                self.assertEqual(math.isnan(ari.value), True)
            else:
                self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, None)

    def test_ari_cbor_decode_lit_prim_tstr(self):
        TEST_CASE = [
            ("60", ""),
            ("626869", "hi")
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, None)

    def test_ari_cbor_decode_lit_prim_bstr(self):
        TEST_CASE = [
            ("40", b''),
            ("426869", b"hi")
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, None)

    def test_ari_cbor_decode_lit_typed_bool(self):
        TEST_CASE = [
            (b"8201F4", False),
            (b"8201F5", True)
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, StructType.BOOL)

    def test_ari_cbor_decode_lit_typed_int64(self):
        TEST_CASE = [
            ("820200", StructType.BYTE, 0),
            ("82021864", StructType.BYTE, 100),
            ("82041864", StructType.INT, 100),
            ("82051864", StructType.UINT, 100),
            ("82061864", StructType.VAST, 100),
            ("82071864", StructType.UVAST, 100)
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect_type, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, expect_type)

    def test_ari_cbor_decode_lit_typed_real64(self):
        TEST_CASE = [
            ("8209F93E00", 1.5)
        ]

        dec = ari_cbor.Decoder()
        for row in TEST_CASE:
            data, expect = row
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            ari = dec.decode(io.BytesIO(data))
            self.assertEqual(ari.value, expect)
            self.assertEqual(ari.type_id, StructType.REAL64)


    def test_ari_cbor_decode_failure(self):
        TEST_CASE = [
            (b"8519FFFF02200520"),                   # invalid parameter format (must be list or dict)
            (b"8619FFFF02200580182D"),               # extra segment after parameters
            (b"A0"),                                 # bad major type:{}
            (b"821182A0820417"),                    # AC with item having bad major type
            (b"8364746573740A6474686174"),          # ari://test/TEXTSTR/that
            (b"820C82290C"),                         # TP with decimal fraction exponent of -10
            (b"820C820A0C"),                         # TP with decimal fraction exponent of 10
            (b"820EFB3FF3333333333333"),             # ari:/LABEL/1.2
            (b"821386030102030405"),                # ari:/TBL/c=3;(1,2,3)(4,5)
            (b"821380"),                            # ari:/TBL/
            (b"8213816474657374"),                 # ari:/TBL/test
            (b"8214816474657374"),                 # ari:/EXECSET/n=test;()
            (b"82148120"),                         # ari:/EXECSET/n=-1;()
            (b"82158264746573741A2B450625"),       # ari:/RPTSET/n=test;r=725943845;
            (b"821582FB3FF33333333333331A2B450625"),   # ari:/RPTSET/n=1.2;r=725943845;
            # ari:/RPTSET/n=1234;r=test;(t=/TD/PT0S;s=//test/CTRL/hi;(null,3,h'6869'))
            (b"8215831904D26474657374850083647465737422626869F603426869"),
            #  ari:/RPTSET/n=1234;r=/REAL64/1.0;(t=/TD/PT0S;s=//test/CTRL/hi;(null,3,h'6869'))
            (b"8215831904D28209F93C00850083647465737422626869F603426869"),
        ]

        dec = ari_cbor.Decoder()
        for data in TEST_CASE:
            data = base64.b16decode(data)
            LOGGER.info('Testing data: %s', to_diag(data))
            try:
                dec.decode(io.BytesIO(data))
            except Exception as e:
                self.assertIn(type(e), (ari_cbor.ParseError, ValueError, TypeError))
                
    # def test_ari_cbor_decode_partial(self):
    #    TEST_CASE = [(b"0001")]

    #    dec = ari_cbor.Decoder()
    #    for data in TEST_CASE:
    #        LOGGER.info('Testing data: %s', to_diag(data))
    #        with self.assertRaises(ari_cbor.ParseError):
    #            dec.decode(io.BytesIO(data))

    # def test_ari_cbor_decode_invalid(self):
    #    TEST_CASE = [
    #        (b"820001"),
    #        (b"820101"),
    #        (b"820220"),
    #        (b"8212A182040AF5"),
    #        (b"8202190100"),
    #        (b"82043A80000000"),
    #        (b"82041A80000000"),
    #        (b"820520"),
    #        (b"82051B0000000100000000"),
    #        (b"82061B8000000000000000"),
    #        (b"820720"),
    #        (b"8208FBC7EFFFFFE091FF3D"),
    #        (b"8208FB47EFFFFFE091FF3D"),
    #    ]

    #    dec = ari_cbor.Decoder()
    #    for data in TEST_CASE:
    #        data = base64.b16decode(data)
    #        LOGGER.info('Testing data: %s', to_diag(data))
    #        with self.assertRaises(ari_cbor.ParseError):
    #            dec.decode(io.BytesIO(data))

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
            ("85676578616D706C6564746573742A6474686174811822"),
            ("85676578616D706C656361646D23656D79454444A1F58201F5"),  # Ref with AM params
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
            ("8214821904D28419FFFF647465737422626869"),
            ("82148342686984676578616D706C6564746573742262686984676578616D706C65647465737422626568"), # ari:/EXECSET/n=h'6869';(//example/test/CTRL/hi,//example/test/CTRL/eh)
            ("84676578616D706C656474657374216474686174"), # ari://example/test/CONST/that
            ("8214834268698419FFFF6474657374226268698419FFFF647465737422626568"),
            ("8214821904D284676578616D706C65647465737422626869"),
            ("8419FFFF6474657374216474686174"),
            ("8419FFFF69746573744031323334216474686174"),
            ("8419FFFF652174657374216474686174"),
            ("8519FFFF6474657374226474686174811822"),
            ("8519FFFF02220481626869"),
            ("820F410A"),
            ("820F4BA164746573748203F94480"),
        ]

        dec = ari_cbor.Decoder()
        enc = ari_cbor.Encoder()
        for data in TEST_CASE:
            with self.subTest(f'data {data}'):
                data = base64.b16decode(data)
                LOGGER.info('Testing data: %s', to_diag(data))

                ari = dec.decode(io.BytesIO(data))
                LOGGER.info('Got ARI %s', ari)

                loop = io.BytesIO()
                enc.encode(ari, loop)
                LOGGER.info('Got data: %s', to_diag(loop.getvalue()))
                loop.seek(0)
                LOGGER.info('Re-decode ARI %s', dec.decode(loop))
                self.assertEqual(
                    base64.b16encode(loop.getvalue()),
                    base64.b16encode(data)
                )
