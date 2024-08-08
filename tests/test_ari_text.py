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
import io
import logging
import math
import unittest
from ace.ari import ARI, AC, ReferenceARI, LiteralARI, StructType
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
        ('BOOL.true', True, 'true'),
        ('ari:true', True, 'true'),
        # INT
        ('VAST.0', 0),
        ('VAST.10', 10),
        ('VAST.0xa', 0xa, 'VAST.10'),
        ('VAST.0b10', 0b10, 'VAST.2'),
        ('VAST.-10', -10),
        ('VAST.-0xa', -0xa, 'VAST.-10'),
        ('ari:INT.10', 10, 'INT.10'),
        # FLOAT
        ('REAL32.0.0', 0.0),
        ('REAL64.0.0', 0.0),
        ('REAL64.0.01', 0.01),
        ('REAL64.1e2', 1e2, 'REAL64.100.0'),
        ('REAL64.1e-2', 1e-2, 'REAL64.0.01'),
        ('REAL64.-1e2', -1e2, 'REAL64.-100.0'),
        ('REAL64.1.25e2', 1.25e2, 'REAL64.125.0'),
        ('REAL64.1e25', 1e25, 'REAL64.1e+25'),
        ('REAL64.NaN', float('NaN')),
        ('REAL64.Infinity', float('Infinity')),
        ('REAL64.-Infinity', -float('Infinity')),
        # TSTR
        ('"hi"', 'hi'),
        # BSTR
        ('\'hi\'', b'hi', 'h\'6869\''),
        # RFC 4648 test vectors
        ('h\'666F6F626172\'', b'foobar', 'h\'666f6f626172\''),
        ('b32\'MZXW6YTBOI\'', b'foobar', 'h\'666f6f626172\''),
        # not working ('h32\'CPNMUOJ1\'', b'foobar', 'h\'666f6f626172\''),
        ('b64\'Zm9vYmFy\'', b'foobar', 'h\'666f6f626172\''),
    ]

    def test_literal_text_loopback(self):
        dec = ari_text.Decoder()
        enc = ari_text.Encoder()
        for row in self.LITERAL_TEXTS:
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
        'ari:/VAR.hello',
        'ari:/namespace/VAR.hello',
        'ari:/namespace/VAR.hello()',
        'ari:/namespace/VAR.hello(INT.10)',
        'ari:/IANA:DTN.bp_agent/CTRL.reset_all_counts()',
        'ari:/IANA:Amp.Agent/CTRL.gen_rpts([ari:/IANA:DTN.bpsec/RPTT.source_report("ipn:1.1")],[])',
        # Per spec:
        'ari:/IANA:AMP.AGENT/CTRL.ADD_SBR(ari:/IANA:APL_SC/SBR.HEAT_ON,VAST.0,(BOOL)[ari:/IANA:APL_SC/EDD.payload_temperature,ari:/IANA:APL_SC/CONST.payload_heat_on_temp,ari:/IANA:AMP.AGENT/OPER.LESSTHAN],VAST.1000,VAST.1000,[ari:/IANA:APL_SC/CTRL.payload_heater(INT.1)],"heater on")',
        # Neede for old ACE: 'ari:/IANA:AMP.AGENT/CTRL.ADD_SBR(ari:/IANA:APL_SC/SBR.HEAT_ON,0,(BOOL) ari:/IANA:APL_SC/EDD.payload_temperature ari:/IANA:APL_SC/CONST.payload_heat_on_temp ari:/IANA:AMP.AGENT/OPER.LESSTHAN,1000,1000,[ari:/IANA:APL_SC/CTRL.payload_heater(1)],"heater on")',
    ]

    def test_reference_text_loopback(self):
        dec = ari_text.Decoder()
        enc = ari_text.Encoder()
        for text in self.REFERENCE_TEXTS:
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
        'BOOL.10',
        'ari:hello',
        'ari:/namespace/hello((',
    ]

    def test_invalid_text_failure(self):
        dec = ari_text.Decoder()
        for text in self.INVALID_TEXTS:
            LOGGER.info('Testing text: %s', text)
            with self.assertRaises(ari_text.ParseError):
                ari = dec.decode(io.StringIO(text))
                LOGGER.info('Instead got ARI %s', ari)

    def test_complex_decode(self):
        text = 'ari:/IANA:Amp.Agent/Ctrl.gen_rpts([ari:/IANA:DTN.bpsec/Rptt.source_report("ipn:1.1")],[])'
        dec = ari_text.Decoder()
        ari = dec.decode(io.StringIO(text))
        LOGGER.info('Got ARI %s', ari)
        self.assertIsInstance(ari, ARI)
        self.assertEqual(ari.ident.namespace, 'IANA:Amp.Agent')
#        self.assertEqual(ari.ident.type_enum, StructType.CTRL)
        self.assertEqual(ari.ident.name, 'gen_rpts')
        self.assertIsInstance(ari.params[0], AC)
