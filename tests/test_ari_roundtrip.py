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
    maxDiff = None

    CANONICAL_TEXTS = [
        # BOOL
        'ari:true',
        'ari:false',
        'ari:/BOOL/true',
        # INT
        'ari:/BYTE/0',
        'ari:/INT/10',
        'ari:/UINT/10',
        'ari:/VAST/10',
        'ari:/UVAST/10',
        "ari:/REAL32/NaN",
        "ari:/REAL64/Infinity",
        "ari:/REAL64/-Infinity",
        # Times
        'ari:/TD/PT3H2M10S',
        'ari:/TD/PT3H2M10.1S',
        'ari:/TD/PT3H2M10.001S',
        # others
        'ari:/LABEL/test',
        'ari:/CBOR/h\'A164746573748203F94480\'',
        # Containers
        'ari:/AC/()',
        'ari:/AC/(1,2)',
        'ari:/AM/()',
        'ari:/AM/(1=1,2=3)',
        'ari:/TBL/c=3;',
        'ari:/TBL/c=3;(1,2,3)(a,b,c)',
        'ari:/EXECSET/n=1234;(//example/adm/CTRL/name)',
        'ari:/RPTSET/n=null;r=/TP/20240102T030405Z;(t=/TD/PT;s=//example/adm/CTRL/name;(null))',
        # Reference
        'ari://65536/65536/VAR/0',
        'ari://4294967296/4294967296/VAR/2',
        'ari://org/model/VAR/hello',
        'ari://org/model/VAR/hello()',
        'ari://org/model/VAR/hello(/INT/10)',
        'ari://ietf/bp-agent/CTRL/reset_all_counts()',
        'ari://ietf/amp-agent/CTRL/gen_rpts(/AC/(//ietf/bpsec/CONST/source_report(%22ipn%3A1.1%22)),/AC/())',
        # Per spec:
        'ari://ietf/AMP-AGENT/CTRL/ADD_SBR(//APL/SC/SBR/HEAT_ON,/VAST/0,/AC/(//APL/SC/EDD/payload_temperature,//APL/SC/CONST/payload_heat_on_temp,//ietf/AMP-AGENT/OPER/LESSTHAN),/VAST/1000,/VAST/1000,/AC/(//APL/SC/CTRL/payload_heater(/INT/1)),%22heater%20on%22)',
    ]

    def test_text_cbor_roundtrip(self):
        text_dec = ari_text.Decoder()
        text_enc = ari_text.Encoder()
        cbor_dec = ari_cbor.Decoder()
        cbor_enc = ari_cbor.Encoder()

        for text in self.CANONICAL_TEXTS:
            with self.subTest(text):
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
        "f7",
        "f6",
        "8214841904d28519ffff01220c8af7f6f5f40a29fa497424006268696a24"
        "2e3f21272009402b3a4268698519ffff0122187b981a8200f68201f58201"
        "f482020a82043903e782051903e882063a000f423f82071a000f42408208"
        "fa501502f98209fb4415af1d78b58c40820a626869820a6a242e3f212720"
        "09402b3a820b426869820b426869820b426869820c82201b00000001df45"
        "1d83820c82201b00000001df451d83820d82211a00057e45820d82211a00"
        "057e45820e646e616d65820e1904d2820f42187b82100582118202048212"
        "a20102030482138502010203048519ffff01221904d2a2008419ffff0220"
        "0c018419ffff022b15",  # EXECSET
        "8214841904d28519ffff01220c8af7f6f5f40a29fa497424006268696a24"
        "2e3f21272009402b3a4268698519ffff0122187b981d8200f68201f58201"
        "f482020a82043903e782051903e882063a000f423f82071a000f42408208"
        "fa501502f98209fb4415af1d78b58c408209f97e008209f97c008209f9fc"
        "00820a626869820a6a242e3f21272009402b3a820b426869820b42686982"
        "0b426869820c82201b00000001df451d83820c82201b00000001df451d83"
        "820d82211a00057e45820d82211a00057e45820e646e616d65820e1904d2"
        "820f42187b82100582118202048212a20102030482138502010203048519"
        "ffff01221904d2a2008419ffff02200c018419ffff022b15",  # RPTSET
    )

    def test_cbor_text_roundtrip(self):
        text_dec = ari_text.Decoder()
        text_enc = ari_text.Encoder()
        cbor_dec = ari_cbor.Decoder()
        cbor_enc = ari_cbor.Encoder()

        for data16 in self.CANONICAL_DATAS:
            with self.subTest(f'data {data16}'):
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
