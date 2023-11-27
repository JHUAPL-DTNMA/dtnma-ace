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
''' Verify behavior of the ace.ari_text module tree.
'''
import datetime
import io
import logging
import math
import unittest
from ace.ari import ARI, ReferenceARI, LiteralARI, StructType
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
        ('/VAST/0', 0),
        ('/VAST/10', 10),
        ('/VAST/0xa', 0xa, '/VAST/10'),
        ('/VAST/0b10', 0b10, '/VAST/2'),
        ('/VAST/-10', -10),
        ('/VAST/-0xa', -0xa, '/VAST/-10'),
        ('ari:/INT/10', 10, '/INT/10'),
        # FLOAT
        ('0.0', 0.0),
        ('/REAL32/0.0', 0.0),
        ('/REAL64/0.0', 0.0),
        ('/REAL64/0.01', 0.01),
        ('/REAL64/1e2', 1e2, '/REAL64/100.0'),
        ('/REAL64/1e-2', 1e-2, '/REAL64/0.01'),
        ('/REAL64/-1e2', -1e2, '/REAL64/-100.0'),
        ('/REAL64/1.25e2', 1.25e2, '/REAL64/125.0'),
        ('/REAL64/1e25', 1e25, '/REAL64/1e+25'),
        ('/REAL64/NaN', float('NaN')),
        ('/REAL64/Infinity', float('Infinity')),
        ('/REAL64/-Infinity', -float('Infinity')),
        # TEXTSTR
        ('"hi"', 'hi'),
        ('/TEXTSTR/"hi"', 'hi'),
        # BYTESTR
        ('\'hi\'', b'hi', 'h\'6869\''),
        ('/BYTESTR/\'hi\'', b'hi', '/BYTESTR/h\'6869\''),
        # RFC 4648 test vectors
        ('h\'666F6F626172\'', b'foobar', 'h\'666f6f626172\''),
        ('b32\'MZXW6YTBOI\'', b'foobar', 'h\'666f6f626172\''),
        # not working ('h32\'CPNMUOJ1\'', b'foobar', 'h\'666f6f626172\''),
        ('b64\'Zm9vYmFy\'', b'foobar', 'h\'666f6f626172\''),
        # Times
        ('/TP/20230102T030405Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 0)),
        ('/TP/2023-01-02T03:04:05Z', datetime.datetime(2023, 1, 2, 3, 4, 5, 0), '/TP/20230102T030405Z'),  # with formatting
        ('/TD/PT3H', datetime.timedelta(hours=3)),
        ('/TD/PT10.001S', datetime.timedelta(seconds=10.001)),
        ('/TD/PT10.25S', datetime.timedelta(seconds=10.25), '/TD/PT10.25S'),
        ('/TD/PT10.250000S', datetime.timedelta(seconds=10.25), '/TD/PT10.25S'),
        ('/TD/P1DT10.25S', datetime.timedelta(days=1, seconds=10.25), '/TD/P1DT10.25S'),
        # Containers
        # ('(1,2)', [LiteralARI(1), LiteralARI(2)]),
        ('/AC/()', []),
        ('/AC/(1,2)', [LiteralARI(1), LiteralARI(2)]),
        (
            '/AC/(1,/UVAST/2)',
            [LiteralARI(1), LiteralARI(2, type_enum=StructType.UVAST)]
        ),
        ('/AM/()', {}),
        ('/AM/(1=1,2=3)', {LiteralARI(1): LiteralARI(1), LiteralARI(2): LiteralARI(3)}),
        (
            '/AM/(1=/UVAST/1,2=3)',
            {LiteralARI(1): LiteralARI(1, type_enum=StructType.UVAST), LiteralARI(2): LiteralARI(3)}
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

    REFERENCE_TEXTS = [
        'ari:/namespace/VAR/hello',
        'ari:/namespace/VAR/hello()',
        'ari:/namespace/VAR/hello(/INT/10)',
        'ari:/bp-agent/CTRL/reset_all_counts()',
        'ari:/amp-agent/CTRL/gen_rpts(/AC/(ari:/bpsec/CONST/source_report("ipn:1.1")),/AC/())',
        # Per spec:
        'ari:/amp-agent/CTRL/ADD_SBR(ari:/APL_SC/SBR/HEAT_ON,/VAST/0,/AC/(ari:/APL_SC/EDD/payload_temperature,ari:/APL_SC/CONST/payload_heat_on_temp,ari:/amp-agent/OPER/LESSTHAN),/VAST/1000,/VAST/1000,/AC/(ari:/APL_SC/CTRL/payload_heater(/INT/1)),"heater on")',
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
        '/BOOL/10',
        '/INT/"hi"',
        '/TEXTSTR/3',
        '/AC/3',
        '/AM/3',
        'ari:hello',
        'ari:/namespace/hello((',
    ]

    def test_invalid_text_failure(self):
        dec = ari_text.Decoder()
        for text in self.INVALID_TEXTS:
            with self.subTest(text):
                LOGGER.info('Testing text: %s', text)
                with self.assertRaises(ari_text.ParseError):
                    ari = dec.decode(io.StringIO(text))
                    LOGGER.info('Instead got ARI %s', ari)

    def test_complex_decode(self):
        text = 'ari:/amp-agent/CTRL/gen_rpts(/AC/(ari:/bpsec/CONST/source_report("ipn:1.1")),/AC/())'
        dec = ari_text.Decoder()
        ari = dec.decode(io.StringIO(text))
        LOGGER.info('Got ARI %s', ari)
        self.assertIsInstance(ari, ARI)
        self.assertEqual(ari.ident.namespace, 'amp-agent')
#        self.assertEqual(ari.ident.type_enum, StructType.CTRL)
        self.assertEqual(ari.ident.name, 'gen_rpts')
        self.assertIsInstance(ari.params[0], LiteralARI)
        self.assertEqual(ari.params[0].type_enum, StructType.AC)
