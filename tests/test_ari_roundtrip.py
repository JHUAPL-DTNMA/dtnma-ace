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
        # others
        '/LABEL/test',
        '/CBOR/h%27a164746573748203f94480%27',
        # Containers
        '/AC/()',
        '/AC/(1,2)',
        '/AM/()',
        '/AM/(1=1,2=3)',
        '/TBL/c=3;',
        '/TBL/c=3;(1,2,3)(a,b,c)',
        '/EXECSET/n=1234;(//adm/CTRL/name)',
        '/RPTSET/n=null;r=20240102T030405Z;(t=PT;s=//adm/CTRL/name;(null))',
        # Reference
        'ari://65536/VAR/0',
        'ari://4294967296/VAR/2',
        'ari://namespace/VAR/hello',
        'ari://namespace/VAR/hello()',
        'ari://namespace/VAR/hello(/INT/10)',
        'ari://bp-agent/CTRL/reset_all_counts()',
        'ari://amp-agent/CTRL/gen_rpts(/AC/(//DTN.bpsec/CONST/source_report(%22ipn%3A1.1%22)),/AC/())',
        # Per spec:
        'ari://AMP-AGENT/CTRL/ADD_SBR(//APL_SC/SBR/HEAT_ON,/VAST/0,/AC/(//APL_SC/EDD/payload_temperature,//APL_SC/CONST/payload_heat_on_temp,//AMP.AGENT/OPER/LESSTHAN),/VAST/1000,/VAST/1000,/AC/(//APL_SC/CTRL/payload_heater(/INT/1)),%22heater%20on%22)',
    ]

    def test_text_cbor_roundtrip(self):
        text_dec = ari_text.Decoder()
        text_enc = ari_text.Encoder()
        cbor_dec = ari_cbor.Decoder()
        cbor_enc = ari_cbor.Encoder()

        for text in self.CANONICAL_TEXTS:
            LOGGER.info('Testing text: %s', text)

            ari_dn = text_dec.decode(io.StringIO(text))
            LOGGER.info('Got ARI %s', ari_dn)
            self.assertIsInstance(ari_dn, ARI)
            if isinstance(ari_dn, ReferenceARI):
                self.assertIsNotNone(ari_dn.ident.type_id)
                self.assertIsNotNone(ari_dn.ident.obj_id)

            cbor_loop = io.BytesIO()
            cbor_enc.encode(ari_dn, cbor_loop)
            self.assertLess(0, cbor_loop.tell())
            LOGGER.info('Intermediate binary: %s', to_diag(cbor_loop.getvalue()))

            cbor_loop.seek(0)
            ari_up = cbor_dec.decode(cbor_loop)
            LOGGER.info('Intermediate ARI %s', ari_up)
            self.assertEqual(ari_up, ari_dn)

            text_loop = io.StringIO()
            text_enc.encode(ari_up, text_loop)
            LOGGER.info('Got text: %s', text_loop.getvalue())
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
            LOGGER.info('Testing data: %s', to_diag(data))

            ari_dn = cbor_dec.decode(io.BytesIO(data))
            LOGGER.info('Got ARI %s', ari_dn)
            self.assertIsInstance(ari_dn, ARI)
            if isinstance(ari_dn, ReferenceARI):
                self.assertIsNotNone(ari_dn.ident.type_id)
                self.assertIsNotNone(ari_dn.ident.obj_id)

            text_loop = io.StringIO()
            text_enc.encode(ari_dn, text_loop)
            self.assertLess(0, text_loop.tell())
            LOGGER.info('Intermediate: %s', text_loop.getvalue())

            text_loop.seek(0)
            ari_up = text_dec.decode(text_loop)
            self.assertEqual(ari_up, ari_dn)

            cbor_loop = io.BytesIO()
            cbor_enc.encode(ari_up, cbor_loop)
            LOGGER.info('Got data: %s', to_diag(cbor_loop.getvalue()))
            self.assertLess(0, cbor_loop.tell())
            self.assertEqual(
                base64.b16encode(cbor_loop.getvalue()),
                base64.b16encode(data)
            )
