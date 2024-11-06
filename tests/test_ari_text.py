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
''' Verify behavior of the ace.ari_text module tree.
'''
import base64
import datetime
import io
import logging
import math
import unittest
import numpy
from ace.ari import (
    ARI, Identity, ReferenceARI, LiteralARI, StructType, UNDEFINED,
    ExecutionSet, ReportSet, Report
)
from ace import ari_text

LOGGER = logging.getLogger(__name__)


class TestAriText(unittest.TestCase):
    maxDiff = 10240

    def assertEqualWithNan(self, aval, bval):  # pylint: disable=invalid-name
        if isinstance(aval, float) or isinstance(bval, float):
            if math.isnan(aval) or math.isnan(bval):
                self.assertEqual(math.isnan(aval), math.isnan(bval))
                return
        self.assertEqual(aval, bval)

    LITERAL_TEXTS = [
        # Specials
        ('undefined', UNDEFINED.value),
        ('null', None),
        ('/NULL/null', None),
        # BOOL
        ('true', True),
        ('false', False),
        ('/BOOL/true', True),
        ('/1/true', True, '/BOOL/true'),
        ('ari:true', True, 'true'),
        # INT
        ('0', 0),
        ('10', 10),
        ('-100', -100),
        ('0x10', 16, '16'),
        ('0b100', 4, '4'),
        ('/INT/10', 10),
        ('/VAST/0', 0),
        ('/VAST/10', 10),
        ('/VAST/0xa', 0xa, '/VAST/10'),
        ('/VAST/0b10', 0b10, '/VAST/2'),
        ('/VAST/-10', -10),
        ('/VAST/-0xa', -0xa, '/VAST/-10'),
        ('ari:/INT/10', 10, '/INT/10'),
        # FLOAT
        ('0.0', 0.0),
        ('1e3', 1000.0, '1000.0'),
        ('0fx63d0', 1000.0, '1000.0'),
        ('+0fx63d0', 1000.0, '1000.0'),
        ('-0fx63d0', -1000.0, '-1000.0'),
        ('0fx447a0000', 1000.0, '1000.0'),
        ('0fx408f400000000000', 1000.0, '1000.0'),
        ('/REAL32/0.0', 0.0),
        ('/REAL64/NaN', float('NaN')),
        ('/REAL64/Infinity', float('Infinity')),
        ('/REAL64/-Infinity', -float('Infinity')),
        ('/REAL64/0.0', 0.0),
        ('/REAL64/0.01', 0.01),
        ('/REAL64/1e2', 1e2, '/REAL64/100.0'),
        ('/REAL64/1e-2', 1e-2, '/REAL64/0.01'),
        ('/REAL64/+1e2', 1e2, '/REAL64/100.0'),
        ('/REAL64/-1e2', -1e2, '/REAL64/-100.0'),
        ('/REAL64/1.25e2', 1.25e2, '/REAL64/125.0'),
        ('/REAL64/1e25', 1e25, '/REAL64/1e+25'),
        ('/REAL64/NaN', float('NaN')),
        ('/REAL64/Infinity', float('Infinity')),
        ('/REAL64/-Infinity', -float('Infinity')),
        # TEXTSTR
        ('hi', 'hi'),
        ('%22hi%20there%22', 'hi there'),
        ('%22hi%5C%22oh%22', 'hi"oh'),
        ('/TEXTSTR/hi', 'hi'),
        ('/TEXTSTR/%22hi%20there%22', 'hi there'),
        # BYTESTR
        ('%27hi%27', b'hi', 'h%276869%27'),
        ('%27hi%5C%22oh%27', b'hi"oh', 'h%276869226f68%27'),
        ('%27hi%5C%27oh%27', b'hi\'oh', 'h%276869276f68%27'),
        ('/BYTESTR/%27hi%27', b'hi', '/BYTESTR/h%276869%27'),
        # RFC 4648 test vectors
        ('h%27666F6F626172%27', b'foobar', 'h%27666f6f626172%27'),
        ('b32%27MZXW6YTBOI%27', b'foobar', 'h%27666f6f626172%27'),
        # not working ('h32%27CPNMUOJ1%27', b'foobar', 'h%27666f6f626172%27'),
        ('b64%27Zm9vYmFy%27', b'foobar', 'h%27666f6f626172%27'),
        # Times
        ('/TP/20230102T030405Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 0)),
        ('/TP/2023-01-02T03:04:05Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 0), '/TP/20230102T030405Z'),  # with formatting
        ('/TP/20230102T030405.250000Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 250000)),
        ('/TP/725943845.0', datetime.datetime(2023, 1, 2, 3, 4, 5, 0), '/TP/20230102T030405Z'),
        ('/TD/PT3H', datetime.timedelta(hours=3)),
        ('/TD/PT10.001S', datetime.timedelta(seconds=10.001)),
        ('/TD/PT10.25S', datetime.timedelta(seconds=10.25), '/TD/PT10.25S'),
        ('/TD/PT10.250000S', datetime.timedelta(seconds=10.25), '/TD/PT10.25S'),
        ('/TD/P1DT10.25S', datetime.timedelta(days=1, seconds=10.25), '/TD/P1DT10.25S'),
        ('/TD/+PT3H', datetime.timedelta(hours=3), '/TD/PT3H'),
        ('/TD/-PT3H', -datetime.timedelta(hours=3)),
        ('/TD/100', datetime.timedelta(seconds=100), '/TD/PT1M40S'),
        ('/TD/1.5', datetime.timedelta(seconds=1.5), '/TD/PT1.5S'),
        # Extras
        ('/LABEL/test', 'test'),
        ('/LABEL/null', 'null'),
        ('/LABEL/undefined', 'undefined'),
        ('/CBOR/h%27a164746573748203f94480%27', base64.b16decode('A164746573748203F94480')),
        # Containers
        ('/AC/()', []),
        ('/AC/(1,2)', [LiteralARI(1), LiteralARI(2)]),
        (
            '/AC/(1,/UVAST/2)',
            [LiteralARI(1), LiteralARI(2, type_id=StructType.UVAST)]
        ),
        ('/AM/()', {}),
        ('/AM/(1=1,2=3)', {LiteralARI(1): LiteralARI(1), LiteralARI(2): LiteralARI(3)}),
        (
            '/AM/(1=/UVAST/1,2=3)',
            {LiteralARI(1): LiteralARI(1, type_id=StructType.UVAST), LiteralARI(2): LiteralARI(3)}
        ),
        ('/AM/(a=1,b=3)', {LiteralARI('a'): LiteralARI(1), LiteralARI('b'): LiteralARI(3)}),
        (
            '/TBL/c=3;',
            numpy.ndarray((0, 3))
        ),
        (
            '/TBL/c=3;(1,2,3)(a,b,c)',
            numpy.array([
                [LiteralARI(1), LiteralARI(2), LiteralARI(3)],
                [LiteralARI('a'), LiteralARI('b'), LiteralARI('c')],
            ])
        ),
        (
            '/EXECSET/n=null;(//adm/CTRL/name)',
            ExecutionSet(nonce=None, targets=[
                ReferenceARI(Identity(ns_id='adm', type_id=StructType.CTRL, obj_id='name'))
            ])
        ),
        (
            '/EXECSET/n=1234;(//adm/CTRL/name)',
            ExecutionSet(nonce=1234, targets=[
                ReferenceARI(Identity(ns_id='adm', type_id=StructType.CTRL, obj_id='name'))
            ])
        ),
        (
            '/EXECSET/n=h%276869%27;(//adm/CTRL/name)',
            ExecutionSet(nonce=b'hi', targets=[
                ReferenceARI(Identity(ns_id='adm', type_id=StructType.CTRL, obj_id='name'))
            ])
        ),
        (
            '/RPTSET/n=null;r=20240102T030405Z;(t=PT;s=//adm/CTRL/name;(null))',
            ReportSet(
                nonce=None,
                ref_time=datetime.datetime(2024, 1, 2, 3, 4, 5),
                reports=[
                    Report(
                        source=ReferenceARI(Identity(ns_id='adm', type_id=StructType.CTRL, obj_id='name')),
                        rel_time=datetime.timedelta(seconds=0),
                        items=[
                            LiteralARI(None)
                        ]
                    )
                ]
            )
        ),
        (
            '/RPTSET/n=1234;r=20240102T030405Z;(t=PT;s=//adm/CTRL/other;(null))',
            ReportSet(
                nonce=1234,
                ref_time=datetime.datetime(2024, 1, 2, 3, 4, 5),
                reports=[
                    Report(
                        source=ReferenceARI(Identity(ns_id='adm', type_id=StructType.CTRL, obj_id='other')),
                        rel_time=datetime.timedelta(seconds=0),
                        items=[
                            LiteralARI(None)
                        ]
                    )
                ]
            )
        ),
    ]

    def test_literal_text_loopback(self):
        dec = ari_text.Decoder()
        enc = ari_text.Encoder()
        for row in self.LITERAL_TEXTS:
            with self.subTest(f'{row}'):
                if len(row) == 2:
                    text, val = row
                    exp_loop = text
                elif len(row) == 3:
                    text, val, exp_loop = row
                else:
                    raise ValueError
                LOGGER.info('Testing text: %s', text)

                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, LiteralARI)
                self.assertEqualWithNan(ari.value, val)

                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text: %s', loop.getvalue())
                self.assertLess(0, loop.tell())
                self.assertEqual(loop.getvalue(), exp_loop)

    LITERAL_OPTIONS = (
        ('1000', dict(int_base=2), '0b1111101000'),
        ('1000', dict(int_base=16), '0x3e8'),
        ('/TP/20230102T030405Z', dict(time_text=False), '/TP/725943845.000000'),
        ('/TD/PT3H', dict(time_text=False), '/TD/10800.000000'),
        ('1e3', dict(float_form='g'), '1000.0'),
        ('1e3', dict(float_form='f'), '1000.000000'),
        ('1e3', dict(float_form='e'), '1.000000e+03'),
        ('1e3', dict(float_form='x'), '0fx63d0'),
        ('hi', dict(text_identity=False), '%22hi%22'),
        ('/CBOR/h%27a164746573748203f94480%27', dict(cbor_diag=True), '/CBOR/' + ari_text.quote('<<{"test":[3,4.5]}>>')),
    )

    def test_literal_text_options(self):
        dec = ari_text.Decoder()
        for row in self.LITERAL_OPTIONS:
            with self.subTest(f'{row}'):
                text_dn, opts, exp_loop = row
                enc = ari_text.Encoder(ari_text.EncodeOptions(**opts))

                ari_dn = dec.decode(io.StringIO(text_dn))
                LOGGER.info('Got ARI %s', ari_dn)
                self.assertIsInstance(ari_dn, LiteralARI)

                loop = io.StringIO()
                enc.encode(ari_dn, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertLess(0, loop.tell())
                text_up = loop.getvalue()
                self.assertEqual(text_up, exp_loop)

                # Verify alternate text form decodes the same
                ari_up = dec.decode(io.StringIO(text_up))
                self.assertEqual(ari_dn, ari_up)

    REFERENCE_TEXTS = [
        'ari://namespace/',
        'ari://!namespace/',
        'ari://namespace/VAR/hello',
        'ari://!namespace/VAR/hello',
        'ari://namespace/VAR/hello()',
        'ari://namespace/VAR/hello(/INT/10)',
        'ari://namespace/VAR/hello(//other/CONST/hi)',
        'ari://namespace@2020-01-01/VAR/hello',
        'ari:./VAR/hello',
        'ari://bp-agent/CTRL/reset_all_counts()',
        'ari://amp-agent/CTRL/gen_rpts(/AC/(//bpsec/CONST/source_report(%22ipn%3A1.1%22)),/AC/())',
        # Per spec:
        'ari://amp-agent/CTRL/ADD_SBR(//APL_SC/SBR/HEAT_ON,/VAST/0,/AC/(//APL_SC/EDD/payload_temperature,//APL_SC/CONST/payload_heat_on_temp,//amp-agent/OPER/LESSTHAN),/VAST/1000,/VAST/1000,/AC/(//APL_SC/CTRL/payload_heater(/INT/1)),%22heater%20on%22)',
    ]

    def test_reference_text_loopback(self):
        dec = ari_text.Decoder()
        enc = ari_text.Encoder()
        for text in self.REFERENCE_TEXTS:
            with self.subTest(text):
                LOGGER.info('Testing text: %s', text)

                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ReferenceARI)

                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text: %s', loop.getvalue())
                self.assertLess(0, loop.tell())
                self.assertEqual(loop.getvalue(), text)

    INVALID_TEXTS = [
        ('ari:hello', 'ari:hello there'),
        ('/BOOL/true', '/BOOL/10'),
        ('/INT/3', '/INT/%22hi%22'),
        ('/TEXTSTR/hi', '/TEXTSTR/3'),
        ('/BYTESTR/\'hi\'', '/BYTESTR/3', '/BYTESTR/hi'),
        ('/AC/()', '/AC/', '/AC/3'),
        ('/AM/()', '/AM/' '/AM/3'),
        ('/TBL/c=1;', '/TBL/' '/TBL/c=1;(1,2)'),
        ('/LABEL/hi', '/LABEL/3', '/LABEL/%22hi%22'),
        ('ari://ns/EDD/hello', 'ari://ns/EDD/hello(('),
        ('ari:./EDD/hello', 'ari://./EDD/hello', 'ari:/./EDD/hello'),
    ]
    ''' Valid ARI followed by invalid variations '''

    def test_invalid_text_failure(self):
        dec = ari_text.Decoder()
        for row in self.INVALID_TEXTS:
            text = row[0]
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)

            for text in row[1:]:
                with self.subTest(text):
                    LOGGER.info('Testing text: %s', text)
                    with self.assertRaises(ari_text.ParseError):
                        ari = dec.decode(io.StringIO(text))
                        LOGGER.info('Instead got ARI %s', ari)

    def test_complex_decode(self):
        text = 'ari://amp-agent/CTRL/gen_rpts(/AC/(//bpsec/CONST/source_report(%22ipn%3A1.1%22)),/AC/())'
        dec = ari_text.Decoder()
        ari = dec.decode(io.StringIO(text))
        LOGGER.info('Got ARI %s', ari)
        self.assertIsInstance(ari, ARI)
        self.assertEqual(ari.ident.ns_id, 'amp-agent')
        self.assertEqual(ari.ident.type_id, StructType.CTRL)
        self.assertEqual(ari.ident.obj_id, 'gen_rpts')
        self.assertIsInstance(ari.params[0], LiteralARI)
        self.assertEqual(ari.params[0].type_id, StructType.AC)

    def test_ari_text_encode_lit_prim_int(self):
        TEST_CASE = [
            (0, 10, "ari:0"),
            (0, 2, "ari:0b0"),
            (0, 16, "ari:0x0"),
            (1234, 10, "ari:1234"),
            (1234, 2, "ari:0b10011010010"),
            (1234, 16, "ari:0x4D2"),
            (-1234, 10, "ari:-1234"),
            (-1234, 2, "ari:-0b10011010010"),
            (-1234, 16, "ari:-0x4D2"),
        ]

        #encoder test
        for row in TEST_CASE:
            value, base, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder(int_base = base)
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())


    def test_ari_text_encode_lit_prim_uint(self):
        TEST_CASE = [
            (0, 10, "ari:0"),
            (0, 2, "ari:0b0"),
            (0, 16, "ari:0x0"),
            (1234, 10, "ari:1234"),
            (1234, 2, "ari:0b10011010010"),
            (1234, 16, "ari:0x4D2"),
            (0xFFFFFFFFFFFFFFFF, 16, "ari:0xFFFFFFFFFFFFFFFF")
        ]

        for row in TEST_CASE:
            value, base, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder(int_base = base)
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_lit_prim_float64(self):
        TEST_CASE = [
            (1.1, 'f', "ari:1.100000"),
            (1.1, 'g', "ari:1.1"),
            (1.1e2, 'g', "ari:110"),
            (1.1e2, 'a', "ari:0x1.b8p+6"),
            (1.1e+10, 'g', "ari:1.1e+10"),
            (10, 'e', "ari:1.000000e+01"),
            (10, 'a', "ari:0x1.4p+3"),
            (NAN, ' ', "ari:NaN"), #TODO: update NAN and INFINITY values
            (INFINITY, ' ', "ari:+Infinity"),
            (-INFINITY, ' ', "ari:-Infinity"),
        ]

        for row in TEST_CASE:
            value, base, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder(int_base = base)
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_lit_prim_tstr(self):
        TEST_CASE = [
            ("test", False, True, "ari:test"),
            ("test", False, False, "ari:%22test%22"),
            ("test", True, True, "ari:test"),
            ("\\'\'", True, True, "ari:%22%5C''%22"),
            ("':!@$%^&*()-+[]{},./?", True, True, "ari:%22':!@%24%25%5E%26%2A%28%29-+%5B%5D%7B%7D%2C.%2F%3F%22"),
            ("_-~The quick brown fox", True, True, "ari:%22_-~The%20quick%20brown%20fox%22"),
            ("hi\u1234", False, False, "ari:%22hi%5Cu1234%22"),
            ("hi\U0001D11E", False, False, "ari:%22hi%5CuD834%5CuDD1E%22"),
        ]

        for row in TEST_CASE:
            value, bool1, bool2, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder() #TODO: update to incorporate bool1, bool2
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_lit_prim_bstr(self):
        TEST_CASE = [
            ("", 0, ARI_TEXT_BSTR_RAW, "ari:''"),
            ("test", 4, ARI_TEXT_BSTR_RAW, "ari:'test'"),
            ("hi\u1234", 5, ARI_TEXT_BSTR_RAW, "ari:'hi%5Cu1234'"),
            ("hi\U0001D11E", 6, ARI_TEXT_BSTR_RAW, "ari:'hi%5CuD834%5CuDD1E'"),
            ("\x68\x00\x69", 3, ARI_TEXT_BSTR_RAW, "ari:h'680069'"),
            ("", 0, ARI_TEXT_BSTR_BASE16, "ari:h''"),
            ("", 0, ARI_TEXT_BSTR_BASE64URL, "ari:b64''"),
            ("f", 1, ARI_TEXT_BSTR_BASE64URL, "ari:b64'Zg=='"),
            ("foobar", 6, ARI_TEXT_BSTR_BASE16, "ari:h'666F6F626172'"),
            ("foobar", 6, ARI_TEXT_BSTR_BASE64URL, "ari:b64'Zm9vYmFy'"),
        ]

            #TODO: add function code

    # NOTE: do I need to add short unit tests with no TEST_CASEs, like 
    # test_ari_text_encode_lit_typed_ac_empty()?

    def test_ari_text_encode_objref_text(self):
        TEST_CASE = [
            ("adm", ARI_TYPE_CONST, "hi", "ari://adm/CONST/hi"),
            ("18", ARI_TYPE_IDENT, "34", "ari://18/IDENT/34"),
        ]

        #TODO: add function code

    def test_ari_text_encode_nsref_text(self):
        TEST_CASE = [
            ("adm", "ari://adm/"),
            ("example-adm-a@2024-06-25", "ari://example-adm-a@2024-06-25/"),
            ("example-adm-a", "ari://example-adm-a/"),
            ("!example-odm-b", "ari://!example-odm-b/"),
            ("65536", "ari://65536/")
            ("-20", "ari://-20/"),
        ]
        for row in TEST_CASE:
            value, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder()
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_nsref_int(self):
        TEST_CASE = [
            (18, "ari://18/"),
            (65536, "ari://65536/"),
            (-20, "ari://-20/"),
        ]

        for row in TEST_CASE:
            value, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder()
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_ariref(self):
        TEST_CASE = [
            (ARI_TYPE_CONST, "hi", "./CONST/hi"),
            (ARI_TYPE_IDENT, "34", "./IDENT/34"),
        ]

        #TODO: add function code

     #TODO: add rest of encode tests

     
'''
# this is a test of a decoder, it's constructing the decoder and calling a decoder
# on the input value so this what the decoder python tests need to do

#this is the decode test and every decode test will have this same form
# they don't have extra parameters needed for extra former
dec = ari_text.Decoder()
        for row in self.INVALID_TEXTS:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

'''