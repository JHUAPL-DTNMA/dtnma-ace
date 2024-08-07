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
import base64
import io
import logging
import unittest
import cbor2
from ace.ari import ReferenceARI, LiteralARI
from ace.cborutil import to_diag
from ace import ari_cbor


LOGGER = logging.getLogger(__name__)


class TestAriCbor(unittest.TestCase):

    LITERAL_DATAS = [
        # BOOL
        (base64.b16decode('03F5'), True),
        (base64.b16decode('03F4'), False),
        # INT
        (base64.b16decode('5300'), 0),
        (base64.b16decode('530A'), 10),
        (base64.b16decode('5329'), -10),
        # FLOAT
        (base64.b16decode('83') + cbor2.dumps(0.01), 0.01),
        (base64.b16decode('83') + cbor2.dumps(1e2), 1e2),
        (base64.b16decode('83') + cbor2.dumps(1e-2), 1e-2),
        (base64.b16decode('83') + cbor2.dumps(-1e2), -1e2),
        (base64.b16decode('83') + cbor2.dumps(1.25e2), 1.25e2),
        (base64.b16decode('83') + cbor2.dumps(1e25), 1e25),
        # TSTR
        (base64.b16decode('23') + cbor2.dumps("hi"), 'hi'),
        # BSTR
        (base64.b16decode('03') + cbor2.dumps(b'hi'), b'hi'),
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
        'c1188d410c05031614141a633df8cb0301',
        # from ari:/IANA:AMP.AGENT/CTRL.ADD_TBR(ari:/IANA:APL_SC/TBR.TLM_CYCLE, 0, 10, 0, [ari:/IANA:APL_SC/MAC.TLM_CYCLE], "telemetry cycle")
        'c115410a05062420201625122b49544c4d5f4359434c454449414e41000a008184194e0f41006f74656c656d65747279206379636c65',
    ]

    def test_reference_cbor_loopback(self):
        dec = ari_cbor.Decoder()
        enc = ari_cbor.Encoder()
        for data16 in self.REFERENCE_DATAS:
            data = base64.b16decode(data16, casefold=True)
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
        '00',
        '01',
    ]

    def test_invalid_enc_failure(self):
        dec = ari_cbor.Decoder()
        for data16 in self.INVALID_DATAS:
            data = base64.b16decode(data16, casefold=True)
            LOGGER.warning('Testing data: %s', to_diag(data))
            with self.assertRaises(ari_cbor.ParseError):
                dec.decode(io.BytesIO(data))

#    def test_complex_decode(self):
#        text = 'ari:/IANA:Amp.Agent/Ctrl.gen_rpts([ari:/IANA:DTN.bpsec/Rptt.source_report("ipn:1.1")],[])'
#        dec = ari_text.Decoder()
#        ari = dec.decode(text)
#        LOGGER.warning('Got ARI %s', ari)
#        self.assertIsInstance(ari, (ReferenceARI, LiteralARI))
#        self.assertEqual(ari.ident.namespace, 'IANA:Amp.Agent')
#        self.assertEqual(ari.ident.name, 'Ctrl.gen_rpts')
#        self.assertIsInstance(ari.params[0], AC)
