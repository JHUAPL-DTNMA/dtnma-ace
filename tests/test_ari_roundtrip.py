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
''' Verify behavior of round-trips from text to CBOR and back.
'''
import base64
import io
import logging
import unittest
from ace.ari import ARI, ReferenceARI
from ace.cborutil import to_diag
from ace import ari_text, ari_cbor

LOGGER = logging.getLogger(__name__)


class TestAriRoundtrip(unittest.TestCase):

    CANONICAL_TEXTS = [
        # BOOL
        'true',
        'false',
        '/BOOL/true',
        # INT
        '/BYTE/0',
        '/INT/10',
        '/UINT/10',
        '/VAST/10',
        '/UVAST/10',
        # Times
        '/TD/PT3H2M10S',
        '/TD/PT3H2M10.1S',
        '/TD/PT3H2M10.001S',
        # Reference
        'ari:/namespace/VAR/hello',
        'ari:/namespace/VAR/hello()',
        'ari:/namespace/VAR/hello(/INT/10)',
        'ari:/bp-agent/CTRL/reset_all_counts()',
        'ari:/amp-agent/CTRL/gen_rpts(/AC/(ari:/DTN.bpsec/CONST/source_report("ipn:1.1")),/AC/())',
        # Per spec:
        # 'ari:/AMP-AGENT/CTRL/ADD_SBR(ari:/APL_SC/SBR/HEAT_ON,VAST/0,(BOOL)[ari:/APL_SC/EDD/payload_temperature,ari:/APL_SC/CONST/payload_heat_on_temp,ari:/AMP.AGENT/OPER/LESSTHAN],/VAST/1000,/VAST/1000,[ari:/APL_SC/CTRL/payload_heater(/INT/1)],"heater on")',
    ]
    
    def test_text_cbor_roundtrip(self):
        text_dec = ari_text.Decoder()
        text_enc = ari_text.Encoder()
        cbor_dec = ari_cbor.Decoder()
        cbor_enc = ari_cbor.Encoder()

        for text in self.CANONICAL_TEXTS:
            LOGGER.warning('Testing text: %s', text)

            ari_dn = text_dec.decode(io.StringIO(text))
            LOGGER.warning('Got ARI %s', ari_dn)
            self.assertIsInstance(ari_dn, ARI)
            if isinstance(ari_dn, ReferenceARI):
                self.assertIsNotNone(ari_dn.ident.type_enum)
                self.assertIsNotNone(ari_dn.ident.name)

            cbor_loop = io.BytesIO()
            cbor_enc.encode(ari_dn, cbor_loop)
            self.assertLess(0, cbor_loop.tell())
            LOGGER.warning('Intermediate binary: %s', to_diag(cbor_loop.getvalue()))

            cbor_loop.seek(0)
            ari_up = cbor_dec.decode(cbor_loop)
            LOGGER.warning('Intermediate ARI %s', ari_up)
            self.assertEqual(ari_up, ari_dn)

            text_loop = io.StringIO()
            text_enc.encode(ari_up, text_loop)
            LOGGER.warning('Got text: %s', text_loop.getvalue())
            self.assertLess(0, text_loop.tell())
            self.assertEqual(text_loop.getvalue(), text)

    CANONICAL_DATAS = (
        # 'c115410a05062420201625120b493030313030313030310001183c8187182d41006b54425220437573746f6479',
        # 'C115410A05062420201625120B456E616D65310001183C81C7182F4100006B54425220437573746F6479',
    )

    def test_cbor_text_roundtrip(self):
        text_dec = ari_text.Decoder()
        text_enc = ari_text.Encoder()
        cbor_dec = ari_cbor.Decoder()
        cbor_enc = ari_cbor.Encoder()

        for data16 in self.CANONICAL_DATAS:
            data = base64.b16decode(data16, casefold=True)
            LOGGER.warning('Testing data: %s', to_diag(data))

            ari_dn = cbor_dec.decode(io.BytesIO(data))
            LOGGER.warning('Got ARI %s', ari_dn)
            self.assertIsInstance(ari_dn, ARI)
            if isinstance(ari_dn, ReferenceARI):
                self.assertIsNotNone(ari_dn.ident.type_enum)
                self.assertIsNotNone(ari_dn.ident.name)

            text_loop = io.StringIO()
            text_enc.encode(ari_dn, text_loop)
            self.assertLess(0, text_loop.tell())
            LOGGER.warning('Intermediate: %s', text_loop.getvalue())

            text_loop.seek(0)
            ari_up = text_dec.decode(text_loop)
            self.assertEqual(ari_up, ari_dn)

            cbor_loop = io.BytesIO()
            cbor_enc.encode(ari_up, cbor_loop)
            LOGGER.warning('Got data: %s', to_diag(cbor_loop.getvalue()))
            self.assertLess(0, cbor_loop.tell())
            self.assertEqual(
                base64.b16encode(cbor_loop.getvalue()),
                base64.b16encode(data)
            )
