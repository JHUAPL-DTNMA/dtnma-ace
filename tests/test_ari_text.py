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
    ExecutionSet, ReportSet, Report, NULL
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
        ('ari:undefined', UNDEFINED.value),
        ('ari:null', None),
        ('ari:/NULL/null', None),
        # BOOL
        ('ari:true', True),
        ('ari:false', False),
        ('ari:/BOOL/true', True),
        ('ari:/1/true', True, 'ari:/BOOL/true'),
        ('true', True, 'ari:true'),
        # INT
        ('ari:0', 0),
        ('ari:10', 10),
        ('ari:-100', -100),
        ('ari:0x10', 16, 'ari:16'),
        ('ari:0b100', 4, 'ari:4'),
        ('ari:/INT/10', 10),
        ('ari:/VAST/0', 0),
        ('ari:/VAST/10', 10),
        ('ari:/VAST/0xa', 0xa, 'ari:/VAST/10'),
        ('ari:/VAST/0b10', 0b10, 'ari:/VAST/2'),
        ('ari:/VAST/-10', -10),
        ('ari:/VAST/-0xa', -0xa, 'ari:/VAST/-10'),
        ('/INT/10', 10, 'ari:/INT/10'),
        # FLOAT
        ('ari:0.0', 0.0),
        ('ari:1e3', 1000.0, 'ari:1000.0'),
        # ('ari:0fx63d0', 1000.0, 'ari:1000.0'),
        # ('ari:+0fx63d0', 1000.0, 'ari:1000.0'),
        # ('ari:-0fx63d0', -1000.0, 'ari:-1000.0'),
        # ('ari:0fx447a0000', 1000.0, 'ari:1000.0'),
        # ('ari:0fx408f400000000000', 1000.0, 'ari:1000.0'),
        ('ari:/REAL32/0.0', 0.0),
        ('ari:/REAL64/NaN', float('NaN')),
        ('ari:/REAL64/Infinity', float('Infinity')),
        ('ari:/REAL64/-Infinity', -float('Infinity')),
        ('ari:/REAL64/0.0', 0.0),
        ('ari:/REAL64/0.01', 0.01),
        ('ari:/REAL64/1e2', 1e2, 'ari:/REAL64/100.0'),
        ('ari:/REAL64/1e-2', 1e-2, 'ari:/REAL64/0.01'),
        ('ari:/REAL64/+1e2', 1e2, 'ari:/REAL64/100.0'),
        ('ari:/REAL64/-1e2', -1e2, 'ari:/REAL64/-100.0'),
        ('ari:/REAL64/1.25e2', 1.25e2, 'ari:/REAL64/125.0'),
        ('ari:/REAL64/1e25', 1e25, 'ari:/REAL64/1e+25'),
        ('ari:/REAL64/NaN', float('NaN')),
        ('ari:/REAL64/Infinity', float('Infinity')),
        ('ari:/REAL64/-Infinity', -float('Infinity')),
        # TEXTSTR
        ('ari:hi', 'hi'),
        ('ari:%22hi%20there%22', 'hi there'),
        ('ari:%22hi%5C%22oh%22', 'hi"oh'),
        ('ari:/TEXTSTR/hi', 'hi'),
        ('ari:/TEXTSTR/%22hi%20there%22', 'hi there'),
        # BYTESTR
        ('ari:\'hi\'', b'hi', 'ari:h\'6869\''),
        ('ari:%27hi%27', b'hi', 'ari:h\'6869\''),
        ('ari:\'hi%5C%22oh\'', b'hi"oh', 'ari:h\'6869226F68\''),
        ('ari:\'hi%5C\'oh\'', b'hi\'oh', 'ari:h\'6869276F68\''),
        ('ari:/BYTESTR/\'hi\'', b'hi', 'ari:/BYTESTR/h\'6869\''),
        # RFC 4648 test vectors
        ('ari:h\'666f6f626172\'', b'foobar', 'ari:h\'666F6F626172\''),
        ('ari:b64\'Zm9vYmFy\'', b'foobar', 'ari:h\'666F6F626172\''),
        # Times
        ('ari:/TP/20230102T030405Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 0)),
        ('ari:/TP/2023-01-02T03:04:05Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 0), 'ari:/TP/20230102T030405Z'),  # with formatting
        ('ari:/TP/20230102T030405.250000Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 250000)),
        ('ari:/TP/725943845.0', datetime.datetime(2023, 1, 2, 3, 4, 5, 0), 'ari:/TP/20230102T030405Z'),
        ('ari:/TD/PT3H', datetime.timedelta(hours=3)),
        ('ari:/TD/PT10.001S', datetime.timedelta(seconds=10.001)),
        ('ari:/TD/PT10.25S', datetime.timedelta(seconds=10.25), 'ari:/TD/PT10.25S'),
        ('ari:/TD/PT10.250000S', datetime.timedelta(seconds=10.25), 'ari:/TD/PT10.25S'),
        ('ari:/TD/P1DT10.25S', datetime.timedelta(days=1, seconds=10.25), 'ari:/TD/P1DT10.25S'),
        ('ari:/TD/+PT3H', datetime.timedelta(hours=3), 'ari:/TD/PT3H'),
        ('ari:/TD/-PT3H', -datetime.timedelta(hours=3)),
        ('ari:/TD/100', datetime.timedelta(seconds=100), 'ari:/TD/PT1M40S'),
        ('ari:/TD/1.5', datetime.timedelta(seconds=1.5), 'ari:/TD/PT1.5S'),
        # Extras
        ('ari:/LABEL/test', 'test'),
        ('ari:/LABEL/null', 'null'),
        ('ari:/LABEL/undefined', 'undefined'),
        ('ari:/CBOR/h\'A164746573748203F94480\'', base64.b16decode('A164746573748203F94480')),
        # Containers
        ('ari:/AC/()', []),
        ('ari:/AC/(1,2)', [LiteralARI(1), LiteralARI(2)]),
        (
            'ari:/AC/(1,/UVAST/2)',
            [LiteralARI(1), LiteralARI(2, type_id=StructType.UVAST)]
        ),
        ('ari:/AM/()', {}),
        ('ari:/AM/(1=1,2=3)', {LiteralARI(1): LiteralARI(1), LiteralARI(2): LiteralARI(3)}),
        (
            'ari:/AM/(1=/UVAST/1,2=3)',
            {LiteralARI(1): LiteralARI(1, type_id=StructType.UVAST), LiteralARI(2): LiteralARI(3)}
        ),
        ('ari:/AM/(a=1,b=3)', {LiteralARI('a'): LiteralARI(1), LiteralARI('b'): LiteralARI(3)}),
        (
            'ari:/TBL/c=3;',
            numpy.ndarray((0, 3))
        ),
        (
            'ari:/TBL/c=3;(1,2,3)(a,b,c)',
            numpy.array([
                [LiteralARI(1), LiteralARI(2), LiteralARI(3)],
                [LiteralARI('a'), LiteralARI('b'), LiteralARI('c')],
            ])
        ),
        (
            'ari:/EXECSET/n=null;(//example/adm/CTRL/name)',
            ExecutionSet(nonce=LiteralARI(None), targets=[
                ReferenceARI(Identity(org_id='example', model_id='adm', type_id=StructType.CTRL, obj_id='name'))
            ])
        ),
        (
            'ari:/EXECSET/n=1234;(//example/adm/CTRL/name)',
            ExecutionSet(nonce=LiteralARI(1234), targets=[
                ReferenceARI(Identity(org_id='example', model_id='adm', type_id=StructType.CTRL, obj_id='name'))
            ])
        ),
        (
            'ari:/EXECSET/n=h\'6869\';(//example/adm/CTRL/name)',
            ExecutionSet(nonce=LiteralARI(b'hi'), targets=[
                ReferenceARI(Identity(org_id='example', model_id='adm', type_id=StructType.CTRL, obj_id='name'))
            ])
        ),
        (
            'ari:/RPTSET/n=null;r=/TP/20240102T030405Z;(t=/TD/PT;s=//example/adm/CTRL/name;(null))',
            ReportSet(
                nonce=LiteralARI(None),
                ref_time=datetime.datetime(2024, 1, 2, 3, 4, 5),
                reports=[
                    Report(
                        source=ReferenceARI(Identity(org_id='example', model_id='adm', type_id=StructType.CTRL, obj_id='name')),
                        rel_time=datetime.timedelta(seconds=0),
                        items=[
                            LiteralARI(None)
                        ]
                    )
                ]
            )
        ),
        (
            'ari:/RPTSET/n=1234;r=/TP/20240102T030405Z;(t=/TD/PT;s=//example/adm/CTRL/other;(null))',
            ReportSet(
                nonce=LiteralARI(1234),
                ref_time=datetime.datetime(2024, 1, 2, 3, 4, 5),
                reports=[
                    Report(
                        source=ReferenceARI(Identity(org_id='example', model_id='adm', type_id=StructType.CTRL, obj_id='other')),
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
        ('1000', dict(int_base=2), 'ari:0b1111101000'),
        ('1000', dict(int_base=16), 'ari:0x3E8'),
        ('/TP/20230102T030405Z', dict(time_text=False), 'ari:/TP/725943845.000000'),
        ('/TD/PT3H', dict(time_text=False), 'ari:/TD/10800.000000'),
        ('1e3', dict(float_form='g'), 'ari:1000.0'),
        ('1e3', dict(float_form='f'), 'ari:1000.000000'),
        ('1e3', dict(float_form='e'), 'ari:1.000000e+03'),
        ('1e3', dict(float_form='a'), 'ari:0x1.f400000000000p+9'),
        ('hi', dict(text_identity=False), 'ari:%22hi%22'),
        ('/CBOR/h\'a164746573748203f94480\'', dict(cbor_diag=True), 'ari:/CBOR/' + ari_text.percent_encode('<<{"test":[3,4.5]}>>')),
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
        'ari://65535/0/',
        'ari://example/namespace/',
        'ari://example/!namespace/',
        'ari://example/namespace/VAR/hello',
        'ari://example/!namespace/VAR/hello',
        'ari://example/namespace/VAR/hello()',
        'ari://example/namespace/VAR/hello(/INT/10)',
        'ari://example/namespace/VAR/hello(//example/other/CONST/hi)',
        'ari://example/namespace@2020-01-01/VAR/hello',
        'ari://65535/0/CTRL/0',
        'ari://!private/adm/',
        'ari://!private/adm@2024-02-06/',
        'ari://!private/!odm/',
        'ari:./VAR/hello',
        'ari://ietf/bp-agent/CTRL/reset_all_counts()',
        'ari://ietf/amp-agent/CTRL/gen_rpts(/AC/(//ietf/bpsec/CONST/source_report(%22ipn%3A1.1%22)),/AC/())',
        # Per spec:
        'ari://ietf/amp-agent/CTRL/ADD_SBR(//APL/SC/SBR/HEAT_ON,/VAST/0,/AC/(//APL/SC/EDD/payload_temperature,//APL/SC/CONST/payload_heat_on_temp,//ietf/amp-agent/OPER/LESSTHAN),/VAST/1000,/VAST/1000,/AC/(//APL/SC/CTRL/payload_heater(/INT/1)),%22heater%20on%22)',
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
        ('ari:/REAL32/0.0', 'ari:/REAL32/0'),
        ('ari:/REAL64/0.0', 'ari:/REAL64/0'),
        ('/TEXTSTR/hi', '/TEXTSTR/3'),
        ('/BYTESTR/\'hi\'', '/BYTESTR/3', '/BYTESTR/hi'),
        ('/AC/()', '/AC/', '/AC/3'),
        ('/AM/()', '/AM/' '/AM/3'),
        ('/TBL/c=1;', '/TBL/' '/TBL/c=1;(1,2)'),
        ('/LABEL/hi', '/LABEL/\'hi\'', '/LABEL/%22hi%22'),
        ('ari://example/ns/EDD/hello', 'ari://example/ns/EDD/hello(('),
        ('ari:./EDD/hello', 'ari://./EDD/hello', 'ari:/./EDD/hello'),
        ('ari:/RPTSET/n=null;r=/TP/20240102T030405Z;(t=/TD/PT;s=//example/adm/CTRL/name;(null))',
         'ari:/RPTSET/n=null;r=20240102T030405Z;(t=/TD/PT;s=//example/adm/CTRL/name;(null))',
         'ari:/RPTSET/n=null;r=/TP/20240102T030405Z;(t=PT;s=//example/adm/CTRL/name;(null))'),
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
        text = 'ari://ietf/amp-agent/CTRL/gen_rpts(/AC/(//ietf/bpsec/CONST/source_report(%22ipn%3A1.1%22)),/AC/())'
        dec = ari_text.Decoder()
        ari = dec.decode(io.StringIO(text))
        LOGGER.info('Got ARI %s', ari)
        self.assertIsInstance(ari, ARI)
        self.assertEqual(ari.ident.org_id, 'ietf')
        self.assertEqual(ari.ident.model_id, 'amp-agent')
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

        # encoder test
        for row in TEST_CASE:
            value, base, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder(int_base=base)
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
                enc = ari_text.Encoder(int_base=base)
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_lit_prim_float64(self):
        TEST_CASE = [
            (1.1, 'f', "ari:1.100000"),
            (1.1, 'g', "ari:1.1"),
            (1.1e2, 'g', "ari:110.0"),
            (1.1e2, 'a', "ari:0x1.b800000000000p+6"),
            (1.1e+10, 'e', "ari:1.100000e+10"),
            (10.0, 'e', "ari:1.000000e+01"),
            (10.0, 'a', "ari:0x1.4000000000000p+3"),
            (float('nan'), ' ', "ari:NaN"),
            (float('infinity'), ' ', "ari:Infinity"),
            (float('-infinity'), ' ', "ari:-Infinity"),
        ]

        for row in TEST_CASE:
            value, base, expect = row
            with self.subTest(expect):
                enc = ari_text.Encoder(float_form=base)
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
            ("\\'\'", True, True, "ari:%22%5C\'\'%22"),
            ("':!@$%^&*()-+[]{},./?", True, True, "ari:%22\'%3A%21%40%24%25%5E%26%2A%28%29-%2B%5B%5D%7B%7D%2C.%2F%3F%22"),
            ("_-~The quick brown fox", True, True, "ari:%22_-~The%20quick%20brown%20fox%22"),
            ("hi\u1234", False, False, "ari:%22hi%E1%88%B4%22"),
            ("hi\u0001D11E", False, False, "ari:%22hi%01D11E%22")
        ]

        for row in TEST_CASE:
            value, copy, identity, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder(text_identity=identity)
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_lit_prim_bstr(self):
        TEST_CASE = [
            (b"", 0, "ari:h\'\'"),
            (b"test", 4, "ari:h\'74657374\'"),
            (b"hi\\u1234", 5, "ari:h\'68695C7531323334\'"),
            (b"hi\\U0001D11E", 6, "ari:h\'68695C553030303144313145\'"),
            (b"\x68\x00\x69", 3, "ari:h\'680069\'"),
            (b"foobar", 6, "ari:h\'666F6F626172\'"),
        ]

        for row in TEST_CASE:
            value, size, expect = row
            with self.subTest(value):
                enc = ari_text.Encoder()
                ari = LiteralARI(value)
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_objref_text(self):
        TEST_CASE = [
            ("example", "adm", StructType.CONST, "hi", "ari://example/adm/CONST/hi"),
            (65535, 18, StructType.IDENT, "34", "ari://65535/18/IDENT/34"),
        ]

        for row in TEST_CASE:
            org_id, model_id, type_id, obj, expect = row
            with self.subTest(expect):
                enc = ari_text.Encoder()
                ari = ReferenceARI(
                    ident=Identity(org_id=org_id, model_id=model_id, type_id=type_id, obj_id=obj),
                    params=None
                )
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    # Test case for an Object Reference with AM (dictionary) Parameters
    def test_ari_text_encode_objref_AM(self):
        TEST_CASE = [
            ("example", "adm", StructType.EDD, "myEDD", {
                LiteralARI(value=True):
                LiteralARI(value=True, type_id=StructType.BOOL)},
                "ari://example/adm/EDD/myEDD(true=/BOOL/true)"),
            (65535, 18, StructType.INT, "34", {
                LiteralARI(value=101):
                ReferenceARI(
                    ident=Identity(type_id=StructType.INT, obj_id="11")
                )},
                "ari://65535/18/INT/34(101=./INT/11)")
        ]

        for row in TEST_CASE:
            org_id, model_id, type_id, obj, params, expect = row
            with self.subTest(expect):
                enc = ari_text.Encoder()
                ari = ReferenceARI(
                    ident=Identity(org_id=org_id, model_id=model_id, type_id=type_id, obj_id=obj),
                    params=params
                )
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_nsref_text(self):
        TEST_CASE = [
            ("example", "adm", "ari://example/adm/"),
            ("example", "adm-a@2024-06-25", "ari://example/adm-a@2024-06-25/"),
            ("example", "adm-a", "ari://example/adm-a/"),
            ("example", "!odm-b", "ari://example/!odm-b/"),
            (65535, 0, "ari://65535/0/"),
            (65535, -20, "ari://65535/-20/"),
        ]
        for row in TEST_CASE:
            org, model, expect = row
            with self.subTest(f'{org}-{model}'):
                enc = ari_text.Encoder()
                ari = ReferenceARI(
                    ident=Identity(org_id=org, model_id=model),
                    params=None
                )
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
                ari = ReferenceARI(
                    ident=Identity(value, None, None),
                    params=None
                )
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    def test_ari_text_encode_ariref(self):
        TEST_CASE = [
            # FIXME: (StructType.CONST, "hi", "./CONST/hi"),
            # FIXME: (StructType.IDENT, "34", "./IDENT/34"),
        ]

        for row in TEST_CASE:
            type_id, obj, expect = row
            with self.subTest(expect):
                enc = ari_text.Encoder()
                ari = ReferenceARI(
                    ident=Identity(None, None, type_id, obj),
                    params=None
                )
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text_dn: %s', loop.getvalue())
                self.assertEqual(expect, loop.getvalue())

    # this is a test of a decoder, it's constructing the decoder and calling a decoder
    # on the input value so this what the decoder python tests need to do
    def test_ari_text_decode_lit_prim_null(self):
        TEST_CASE = [
            ("null"),
            ("NULL"),
            ("nUlL"),
        ]
        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, None)

    def test_ari_text_decode_lit_prim_bool(self):
        TEST_CASE = [
            ("false", False),
            ("true", True),
            ("TRUE", True),
        ]
        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_prim_int64(self):
        TEST_CASE = [
            ("-0x8000000000000000", -0x8000000000000000),
            ("-0x7FFFFFFFFFFFFFFF", -0x7FFFFFFFFFFFFFFF),
            ("-4294967297", -4294967297),
            ("-10", -10),
            ("-0x10", -0x10),
            ("-1", -1),
            ("+0", 0),
            ("+10", 10),
            ("+0b1010", 10),
            ("+0X10", 0x10),
            ("+4294967296", 4294967296),
            ("+0x7FFFFFFFFFFFFFFF", 0x7FFFFFFFFFFFFFFF),
            ("0", 0),
            ("-0", 0),
            ("+0", 0),
            ("10", 10),
            ("0b1010", 10),
            ("0B1010", 10),
            ("0B0111111111111111111111111111111111111111111111111111111111111111", 0x7FFFFFFFFFFFFFFF),
            ("0x10", 0x10),
            ("4294967296", 4294967296),
            ("0x7FFFFFFFffFFFFFF", 0x7FFFFFFFFFFFFFFF),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_prim_uint64(self):
        TEST_CASE = [
            ("0x8000000000000000", 0x8000000000000000),
            ("0xFFFFFFFFFFFFFFFF", 0xFFFFFFFFFFFFFFFF),
        ]
        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_byte(self):
        TEST_CASE = [
            ("ari:/BYTE/0", 0),
            ("ari:/BYTE/0xff", 255),
            ("ari:/BYTE/0b10000000", 128),
        ]
        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_int(self):
        TEST_CASE = [
            ("ari:/INT/0", 0),
            ("ari:/INT/1234", 1234),
            ("ari:/INT/-0xff", -255),
            ("ari:/INT/0b10000000", 128),
        ]
        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_uint(self):
        TEST_CASE = [
            ("ari:/VAST/-0", 0),
            ("ari:/VAST/0xff", 255),
            ("ari:/VAST/0b10000000", 128),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_vast(self):
        TEST_CASE = [
            ("ari:/VAST/-0", 0),
            ("ari:/VAST/0xff", 255),
            ("ari:/VAST/0b10000000", 128),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_uvast(self):
        TEST_CASE = [
            ("ari:/UVAST/0x8000000000000000", 0x8000000000000000),
            ("ari:/UVAST/0xFFFFFFFFFFFFFFFF", 0xFFFFFFFFFFFFFFFF),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_prim_float64(self):
        TEST_CASE = [
            ("1.1", 1.1),
            ("1.1e2", 1.1e2),
            ("1.1e+10", 1.1e+10),
            ("0x1.4p+3", 10),
            ("NaN", float('NaN')),
            ("nan", float('NaN')),
            ("infinity", float('Infinity')),
            ("+Infinity", float('Infinity')),
            ("-Infinity", -float('Infinity')),
        ]
        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                if math.isnan(expect):
                  self.assertEqual(math.isnan(ari.value), True)
                else:
                  self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_float32(self):
        TEST_CASE = [
            # FIXME: ("ari:/REAL32/0", 0.0),
            ("ari:/REAL32/-0.", 0.0),
            ("ari:/REAL32/0.255", 0.255),
            # FIXME: ("ari:/REAL32/0xF", 15.0),
            # FIXME: ("ari:/REAL32/0xF.", 15.0),
            # FIXME: ("ari:/REAL32/0xfF", 255.0),
            # FIXME: ("ari:/REAL32/0xfF.ff", 255.255),
            # FIXME: ("ari:/REAL32/0xfF.ffp0", 255.255),
            # FIXME: ("ari:/REAL32/0xfF.ffp+0", 255.255),
            # FIXME: ("ari:/REAL32/0x1.b8p+6", 1.1e2),
            # FIXME: ("ari:/REAL32/0x1p+6", 64),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_float64(self):
        TEST_CASE = [
            # FIXME: ("ari:/REAL64/0", 0.0),
            ("ari:/REAL64/-0.", 0.0),
            ("ari:/REAL64/0.255", 0.255),
            # FIXME: ("ari:/REAL64/0xF", 15.0),
            # FIXME: ("ari:/REAL64/0xF.", 15.0),
            # FIXME: ("ari:/REAL64/0xfF", 255.0),
            # FIXME: ("ari:/REAL64/0xfF.ff", 255.255),
            # FIXME: ("ari:/REAL64/0xfF.ffp0", 255.255),
            # FIXME: ("ari:/REAL64/0xfF.ffp+0", 255.255),
            # FIXME: ("ari:/REAL64/0x1.b8p+6", 1.1e2),
            # FIXME: ("ari:/REAL64/0x1p+6", 64),
            ("ari:/REAL64/-3.40282347E+38", -3.40282347E+38),
            ("ari:/REAL64/3.40282347E+38", 3.40282347e38),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_prim_tstr(self):
        TEST_CASE = [
            ("label", "label"),
            ("\"hi\"", "hi"),
            ("\"%22h%20i%22\"", "h i"),
            ("\"%22h%5c%22i%22\"", "h\"i"),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_tstr(self):
        TEST_CASE = [
            ("ari:/TEXTSTR/label", "label", 6),
            ("ari:/TEXTSTR/\"hi\"", "hi", 3),
            ("ari:/TEXTSTR/\"%22h%20i%22\"", "h i", 4),
            ("ari:/TEXTSTR/%22h%5c%22i%22", "h\"i", 4),
            ("ari:/TEXTSTR/%22!@-+.:'%22", "!@-+.:'", 8),
            ("ari:/TEXTSTR/%22%5C%22'%22", "\"'", 3),
            ("ari:/TEXTSTR/%22''%22", "''", 3),
            ("ari:/TEXTSTR/%22%5C''%22", "''", 3),
            ("ari:/TEXTSTR/%22a%5Cu0000test%22", "a\x00test", 6),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect, value = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_prim_bstr(self):
        TEST_CASE = [
            ("''", b'', 0),
            ("'hi'", b"hi", 2),
            ("'hi%20there'", b"hi there", 8),
            ("'h%5C'i'", b"h'i", 3),
            ("h'6869'", b"hi", 2),
            ("ari:h'5C0069'", b"\\\0i", 3),
            ("ari:h'666F6F626172'", b"foobar", 6),
            ("ari:b64'Zm9vYmFy'", b"foobar", 6),
            ("ari:b64'Zg%3d%3d'", b"f", 1),
            # FIXME: ("ari:h'%20666%20F6F626172'", b"foobar", 6),
            ("ari:b64'Zm9v%20YmFy'", b"foobar", 6),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect, value = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_cbor(self):
        TEST_CASE = [
            ("ari:/CBOR/h''", b""),
            ("ari:/CBOR/h'A164746573748203F94480'", b'\xa1dtest\x82\x03\xf9D\x80'),
            ("ari:/CBOR/h'0064746573748203F94480'", b'\x00dtest\x82\x03\xf9D\x80'),
            # FIXME: ("ari:/CBOR/h'A1%2064%2074%2065%2073%2074%2082%2003%20F9%2044%20%2080'", b"A164746573748203F94480")
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_null(self):
        TEST_CASE = [
            ("ari:/NULL/null"),
            ("ari:/0/null"),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, None)

    def test_ari_text_decode_lit_typed_bool(self):
        TEST_CASE = [
            ("ari:/BOOL/false", False),
            ("ari:/BOOL/true", True),
            ("ari:/1/true", True),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_tp(self):
        TEST_CASE = [
            ("ari:/TP/2000-01-01T00:00:20Z", datetime.datetime(2000, 1, 1, 0, 0, 20)),
            ("ari:/TP/20000101T000020Z", datetime.datetime(2000, 1, 1, 0, 0, 20)),
# FIXME: datetime does not support nanoseconds
            # ("ari:/TP/20000101T000020.5Z", 20, 500e6),
            # ("ari:/TP/20.5", 20, 500e6),
            # ("ari:/TP/20.500", 20, 500e6),
            # ("ari:/TP/20.000001", 20, 1e3),
            # ("ari:/TP/20.000000001", 20, 1),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_td(self):
        TEST_CASE = [
            ("ari:/TD/PT1M", datetime.timedelta(seconds=60)),
            ("ari:/TD/PT20S", datetime.timedelta(seconds=20)),
            ("ari:/TD/PT20.5S", datetime.timedelta(seconds=20, microseconds=500000)),
            ("ari:/TD/20.5", datetime.timedelta(seconds=20, microseconds=500000)),
            ("ari:/TD/20.500", datetime.timedelta(seconds=20, microseconds=500000)),
            ("ari:/TD/20.000001", datetime.timedelta(seconds=20, microseconds=1)),
            ("ari:/TD/20.000000001", datetime.timedelta(seconds=20, microseconds=0)),  # FIXME: nanonseconds not supported, truncates to 0
            ("ari:/TD/+PT1M", datetime.timedelta(seconds=60, microseconds=0)),
            ("ari:/TD/-PT1M", datetime.timedelta(seconds=-60, microseconds=0)),
            ("ari:/TD/-P1DT", datetime.timedelta(seconds=-(24 * 60 * 60))),
            ("ari:/TD/PT", datetime.timedelta(seconds=0)),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value, expect)

    def test_ari_text_decode_lit_typed_ac(self):
        TEST_CASE = [
            ("ari:/AC/()", 0, StructType.NULL),
            ("ari:/AC/(23)", 1, None),
            ("ari:/AC/(/INT/23)", 1, StructType.INT),
            # FIXME: ("ari:/AC/(\"hi%2C%20there%21\")", 1, StructType.TEXTSTR),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, length, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(len(ari.value), length)
                for i in range(length):
                    self.assertEqual(ari.value[i].type_id, expect)

    def test_ari_text_decode_lit_typed_am(self):
        TEST_CASE = [
            ("ari:/AM/()", 0),
            ("ari:/AM/(undefined=1,undefined=/INT/2,1=a)", 2),
            ("ari:/AM/(a=/AM/(),b=/AM/(),c=/AM/())", 3),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(len(ari.value), expect)

    def test_ari_text_decode_lit_typed_tbl(self):
        TEST_CASE = [
            ("ari:/TBL/c=3;(1,2,3)(4,5,6)", 3, 6),
            ("ari:/TBL/c=0;()()()", 0, 0),
            ("ari:/TBL/c=2;(1,2)", 2, 2),
            ("ari:/TBL/C=1;(1)(2)(3)", 1, 3),
            ("ari:/TBL/C=1;(/INT/4)(/TBL/c=0;)(20)", 1, 3),
            ("ari:/TBL/c=/INT/1;(/INT/4)(/TBL/c=0;)(20)", 1, 3)
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect_cols, expect_items = row
            with self.subTest(text):  # TODO: update loop
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.value.shape[1], expect_cols)
                count = 0
                for row in ari.value:
                    count += len(row)
                self.assertEqual(count, expect_items)

    def test_ari_text_decode_lit_typed_execset(self):
        TEST_CASE = [
            ("ari:/EXECSET/n=null;()", 0),
            ("ari:/EXECSET/N=null;()", 0),
            ("ari:/EXECSET/N=0xabcd;()", 0),
            ("ari:/EXECSET/n=1234;(//example/test/CTRL/hi)", 1),
            ("ari:/EXECSET/n=h'6869';(//example/test/CTRL/hi,//example/test/CTRL/eh)", 2),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(len(ari.value.targets), expect)

    def test_ari_text_decode_lit_typed_rptset(self):
        TEST_CASE = [
            ("ari:/RPTSET/n=1234;r=725943845;(t=0;s=//example/test/CTRL/hi;())", 1),  # ARI_PRIM_INT64, 1),
            ("ari:/RPTSET/n=1234;r=725943845;(t=0.0;s=//example/test/CTRL/hi;())", 1),  # ARI_PRIM_INT64, 1),
            ("ari:/RPTSET/n=1234;r=/TP/725943845.000;(t=/TD/0;s=//example/test/CTRL/hi;())", 1),
            # FIXME: ("ari:/RPTSET/n=1234;r=/TP/725943845;(t=/TD/0;s=//example/test/CTRL/hi;())", 1), #, ARI_PRIM_INT64, 1),
            # FIXME: ("ari:/RPTSET/n=1234;r=/TP/725943845.000;(t=/TD/0;s=//example/test/CTRL/hi;())", 1), #, ARI_PRIM_INT64, 1),
            # FIXME: ("ari:/RPTSET/n=1234;r=/TP/20230102T030405Z;(t=/TD/0;s=//example/test/CTRL/hi;())", 1), #, ARI_PRIM_INT64, 1),
            # FIXME: ("ari:/RPTSET/n=h'6869';r=/TP/725943845;(t=/TD/0;s=//example/test/CTRL/hi;())(t=/TD/1;s=//example/test/CTRL/eh;())", 2), #ARI_PRIM_BSTR, 2),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(len(ari.value.reports), expect)

    def test_ari_text_decode_objref(self):
        TEST_CASE = [
            ("ari://example/test/const/hi", StructType.CONST),
            ("ari://example/test/ctrl/hi", StructType.CTRL),
            ("ari://example/test/IDENT/hi", StructType.IDENT),
            ("ari://example/test/TYPEDEF/hi", StructType.TYPEDEF),
            ("ari://example/test/CONST/hi", StructType.CONST),
            ("ari://example/test/VAR/hi", StructType.VAR),
            ("ari://example/test/EDD/hi", StructType.EDD),
            ("ari://example/test/CTRL/hi", StructType.CTRL),
            ("ari://example/test/OPER/hi", StructType.OPER),
            ("ari://example/test/SBR/hi", StructType.SBR),
            ("ari://example/test/TBR/hi", StructType.TBR),
            ("ari://example/test/ident/hi", StructType.IDENT),
            ("ari://example/test/typedef/hi", StructType.TYPEDEF),
            ("ari://example/test/const/hi", StructType.CONST),
            ("ari://example/test/var/hi", StructType.VAR),
            ("ari://example/test/edd/hi", StructType.EDD),
            ("ari://example/test/ctrl/hi", StructType.CTRL),
            ("ari://example/test/CtRl/hi", StructType.CTRL),
            ("ari://example/test/oper/hi", StructType.OPER),
            ("ari://example/test/sbr/hi", StructType.SBR),
            ("ari://example/test/tbr/hi", StructType.TBR),
            ("ari://example/adm/const/hi", StructType.CONST),
            ("ari://example/adm/CONST/hi", StructType.CONST),
            ("ari://example/adm/-2/hi", StructType.CONST),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertEqual(ari.ident.type_id, expect)

    def test_ari_text_decode_objref_invalid(self):
        TEST_CASE = [
            ("ari://example/test/LITERAL/hi"),
            ("ari://example/test/NULL/hi"),
            ("ari://example/test/BOOL/hi"),
            ("ari://example/test/BYTE/hi"),
            ("ari://example/test/INT/hi"),
            ("ari://example/test/UINT/hi"),
            ("ari://example/test/VAST/hi"),
            ("ari://example/test/UVAST/hi"),
            ("ari://example/test/REAL32/hi"),
            ("ari://example/test/REAL64/hi"),
            ("ari://example/test/TEXTSTR/hi"),
            ("ari://example/test/BYTESTR/hi"),
            ("ari://example/test/TP/hi"),
            ("ari://example/test/TD/hi"),
            ("ari://example/test/LABEL/hi"),
            ("ari://example/test/CBOR/hi"),
            ("ari://example/test/ARITYPE/hi"),
            ("ari://example/test/AC/hi"),
            ("ari://example/test/AM/hi"),
            ("ari://example/test/TBL/hi"),
            ("ari://example/test/EXECSET/hi"),
            ("ari://example/test/RPTSET/hi"),
            ("ari://example/test/OBJECT/hi"),
            ("ari://example/test/literal/hi"),
            ("ari://example/test/null/hi"),
            ("ari://example/test/bool/hi"),
            ("ari://example/test/byte/hi"),
            ("ari://example/test/int/hi"),
            ("ari://example/test/uint/hi"),
            ("ari://example/test/vast/hi"),
            ("ari://example/test/uvast/hi"),
            ("ari://example/test/real32/hi"),
            ("ari://example/test/real64/hi"),
            ("ari://example/test/textstr/hi"),
            ("ari://example/test/bytestr/hi"),
            ("ari://example/test/tp/hi"),
            ("ari://example/test/td/hi"),
            ("ari://example/test/label/hi"),
            ("ari://example/test/cbor/hi"),
            ("ari://example/test/aritype/hi"),
            ("ari://example/test/ac/hi"),
            ("ari://example/test/am/hi"),
            ("ari://example/test/tbl/hi"),
            ("ari://example/test/execset/hi"),
            ("ari://example/test/rptset/hi"),
            ("ari://example/test/object/hi"),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                with self.assertRaises(ari_text.ParseError):
                    ari = dec.decode(io.StringIO(text))
                    LOGGER.info('Got ARI %s', ari)

    def test_ari_text_decode_nsref(self):
        TEST_CASE = [
            ("ari://example/adm"),
            ("ari://example/adm/"),
            ("ari://65535/22"),
            ("ari://65535/22/"),
            ("ari://65535/-22/"),
            ("ari://-10/22/"),
            ("ari://example/adm-a@2024-06-25/"),
            ("ari://example/adm-a/"),
            ("ari://example/!odm-b/"),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertIsInstance(ari, ReferenceARI)
                self.assertNotEqual(ari.ident.ns_id, None)
                self.assertEqual(ari.ident.type_id, None)
                self.assertEqual(ari.ident.obj_id, None)

    def test_ari_text_decode_ariref(self):
        TEST_CASE = [
            ("ari:./CTRL/do_thing", None, StructType.CTRL),  # TODO: update values
            ("ari:../adm/CTRL/do_thing", 'adm', StructType.CTRL),  # TODO: update values
            ("ari:./CTRL/otherobj(%22a%20param%22,/UINT/10)", None, StructType.CTRL),
            ("ari:./-2/30", None, StructType.CONST),
            ("./CTRL/do_thing", None, StructType.CTRL),
            ("./CTRL/otherobj(%22a%20param%22,/UINT/10)", None, StructType.CTRL),
            ("./-2/30", None, StructType.CONST),
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text, expect_mod, expect_typ = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)
                self.assertIsInstance(ari, ReferenceARI)
                self.assertEqual(ari.ident.org_id, None)
                self.assertEqual(ari.ident.model_id, expect_mod)
                self.assertEqual(ari.ident.type_id, expect_typ)

    def test_ari_text_loopback(self):
        TEST_CASE = [
            ("ari:undefined"),
            ("ari:null"),
            ("ari:true"),
            ("ari:false"),
            ("ari:1234"),
            ("ari:hi"),
            ("ari:%22hi%20there%22"),
            ("ari:h'6869'"),
            ("ari:/NULL/null"),
            ("ari:/BOOL/false"),
            ("ari:/BOOL/true"),
            ("ari:/INT/10"),
            ("ari:/INT/-10"),
            ("ari:/REAL32/10.1"),
            ("ari:/REAL32/0.1"),
            ("ari:/REAL32/NaN"),
            ("ari:/REAL64/Infinity"),
            ("ari:/REAL64/-Infinity"),
            ("ari:/TEXTSTR/hi"),
            ("ari:/TEXTSTR/%22hi%20there%22"),
            ("ari:/BYTESTR/h'6869'"),
            ("ari:/LABEL/hi"),
            ("ari:/TP/20230102T030405Z"),
            ("ari:/AC/()"),
            ("ari:/AC/(a)"),
            ("ari:/AC/(a,b,c)"),
            ("ari:/AC/(null,/INT/23)"),
            ("ari:/AC/(null,/AC/(undefined,/INT/23,/AC/()))"),
            ("ari:/AM/()"),
            ("ari:/AM/(1=true)"),
            ("ari:/AM/(3=true,10=hi,oh=4)"),
            ("ari:/TBL/c=3;(1,2,3)"),
            ("ari:/TBL/c=3;(1,2,3)(4,5,6)"),
            ("ari:/TBL/c=0;"),
            ("ari:/TBL/c=1;"),
            ("ari:/EXECSET/n=null;()"),
            ("ari:/EXECSET/n=1234;(//example/test/CTRL/hi)"),
            # FIXME: ("ari:/EXECSET/n=h'6869';(//example/test/CTRL/hi,//example/test/CTRL/eh)"),
            # FIXME: ("ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # FIXME: ("ari:/RPTSET/n=1234;r=/TP/20230102T030405Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            ("ari://example/test/CONST/that"),
            ("ari://example/test@2025-01-01/CONST/that"),
            ("ari://example/!test/CONST/that"),
            ("ari://example/test/CTRL/that(34)"),
            ("ari://65535/2/CTRL/4(hi)"),
            # FIXME: ("./CTRL/do_thing"),
            ("ari:/CBOR/h'0A'"),
            ("ari:/CBOR/h'A164746573748203F94480'"),
        ]

        dec = ari_text.Decoder()
        enc = ari_text.Encoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text: %s', loop.getvalue())
                self.assertLess(0, loop.tell())
                self.assertEqual(loop.getvalue(), text)

    def test_ari_AM_loopback(self):
        TEST_CASE = [
            ("ari://example/adm-a/CTRL/otherobj(true,3)"),
            ("ari://example/adm/EDD/myEDD(true=/BOOL/true)"),
        ]

        dec = ari_text.Decoder()
        enc = ari_text.Encoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text: %s', loop.getvalue())
                self.assertLess(0, loop.tell())
                self.assertEqual(loop.getvalue(), text)

    def test_ari_text_reencode(self):
        TEST_CASE = [
            ("ari:/null/null", "ari:/NULL/null"),
            ("ari:/bool/false", "ari:/BOOL/false"),
            ("ari:/int/10", "ari:/INT/10"),
            ("ari:/uint/10", "ari:/UINT/10"),
            ("ari:/vast/10", "ari:/VAST/10"),
            ("ari:/uvast/10", "ari:/UVAST/10"),
            # FIXME: ("ari:/real32/10", "ari:/REAL32/10"),
            ("ari:/real64/+Infinity", "ari:/REAL64/Infinity"),
            # FIXME: ("ari:/bytestr/h'6869'", "ari:/BYTESTR/h'6869'"),
            ("ari:/textstr/hi", "ari:/TEXTSTR/hi"),
            ("ari:/label/hi", "ari:/LABEL/hi"),
            ("ari:/tp/20230102T030405Z", "ari:/TP/20230102T030405Z"),
            ("ari:/ac/()", "ari:/AC/()"),
            ("ari:/am/()", "ari:/AM/()"),
            ("ari:/tbl/c=3;(1,2,3)", "ari:/TBL/c=3;(1,2,3)"),
            ("ari:/execset/n=null;()", "ari:/EXECSET/n=null;()"),
            # FIXME:
            # ("ari:/rptset/n=1234;r=1000;(t=0;s=//example/test/ctrl/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=/TP/1000;(t=/TD/0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=/TP/1000;(t=0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=/TP/1000;(t=100.5;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT1M40.5S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=1000;(t=/TD/0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=1000.0;(t=/TD/0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=/UVAST/1000;(t=/TD/0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=/UVAST/0b1000;(t=/TD/0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T000008Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=/TP/1000.987654321;(t=/TD/0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640.987654321Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            # ("ari:/rptset/n=1234;r=1000.9876543210987654321;(t=/TD/0;s=//example/test/CTRL/hi;(null,3,h'6869'))",
            #        "ari:/RPTSET/n=1234;r=/TP/20000101T001640.987654321Z;(t=/TD/PT0S;s=//example/test/CTRL/hi;(null,3,h'6869'))"),
            ("ari://example/test", "ari://example/test/"),
            # FIXME: ("ari:./ctrl/hi", "./CTRL/hi"),
        ]

        dec = ari_text.Decoder()
        enc = ari_text.Encoder()
        for row in TEST_CASE:
            text, expect_outtext = row
            with self.subTest(text):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Got ARI %s', ari)
                self.assertIsInstance(ari, ARI)

                loop = io.StringIO()
                enc.encode(ari, loop)
                LOGGER.info('Got text: %s', loop.getvalue())
                self.assertLess(0, loop.tell())
                self.assertEqual(loop.getvalue(), expect_outtext)

    def test_ari_text_decode_failure(self):
        TEST_CASE = [
            # FIXME: ("-0x8FFFFFFFFFFFFFFF"),
            # FIXME: ("-0x1FFFFFFFFFFFFFFFF"),
            ("ari:/OTHERNAME/0"),
            ("ari:/UNDEFINED/undefined"),
            ("ari:/NULL/fae"),
            ("ari:/NULL/undefined"),
            ("ari:/NULL/10"),
            ("ari:/BOOL/fae"),
            ("ari:/BOOL/3"),
            ("ari:/TEXTSTR/1"),
            ("ari:/BYTESTR/1"),
            ("ari:/AC/"),
            ("ari:/AC/(a,"),
            ("ari:/AC/(,,,)"),
            ("ari:/AM/"),
            ("ari:/TBL/"),
            ("ari:/TBL/c=hi;"),
            ("ari:/TBL/c=5;(1,2)"),
            ("ari:/TBL/(1,2,3)"),
            ("ari:/TBL/c=aaa;c=2;(1,2)"),
            ("ari:/TBL/c=2;c=2;(1,2)"), 
            ("ari:/EXECSET/()"),
            ("ari:/EXECSET/g=null;()"), 
            ("ari:/EXECSET/n=undefined;()"),
            ("ari:/EXECSET/n=1;"),
            ("ari:/EXECSET/n=1;n=2;()"),
            ("ari://./object/hi"),
            ("./object/hi"), 
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                with self.assertRaises(ari_text.ParseError):
                    ari = dec.decode(io.StringIO(text))

    def test_ari_text_decode_invalid(self):
        TEST_CASE = [
            ("ari:/BYTE/-1"),
            ("ari:/BYTE/256"),
            ("ari:/INT/-2147483649"),
            ("ari:/INT/2147483648"),
            ("ari:/UINT/-1"),
            ("ari:/UINT/4294967296"),
            ("ari:/VAST/0x8000000000000000"),
            ("ari:/VAST/-0x8FFFFFFFFFFFFFFF"),
            ("ari:/VAST/-0x1FFFFFFFFFFFFFFFF"),
            ("ari:/UVAST/-1"),
            ("ari:/REAL32/-3.40282347E+38"),
            ("ari:/REAL32/3.40282347E+38"),
            ("ari:/EXECSET/N=1234;"),  # no targets
            ("ari:/RPTSET/n=null;r=725943845;"),  # no reports
        ]

        dec = ari_text.Decoder()
        for row in TEST_CASE:
            text = row
            with self.subTest(text):
                with self.assertRaises(ari_text.ParseError):
                    dec.decode(io.StringIO(text))
