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
import argparse
import io
import logging
import os
import sys
import unittest
from ace.tools import ace_ari
from ace import ari_text, ari_cbor, cborutil
from ace.ari import ARI, ReferenceARI
from .util import TmpDir

LOGGER = logging.getLogger(__name__)
# : Directory containing this file
SELFDIR = os.path.dirname(__file__)


@unittest.skip  # FIXME: reinstate later
class TestAriRoundtrip(unittest.TestCase):

    CANONICAL_PAIRS = [
        # BOOL
        ('true\n', '0x03F5\n'),
        ('false\n', '0x03F4\n'),
        # INT
        ('BYTE.10\n', '0x130A\n'),
        ('INT.10\n', '0x330A\n'),
        ('UINT.10\n', '0x430A\n'),
        ('VAST.10\n', '0x530A\n'),
        ('UVAST.10\n', '0x630A\n'),
        # Reference ARIs
        ('ari:/IANA:amp_agent/RPTT.full_report\n', '0x8718194100\n'),
        (
            'ari:/IANA:amp_agent/CTRL.gen_rpts([ari:/IANA:amp_agent/RPTT.full_report],[])\n',
            '0xc11541050502252381871819410000\n'
        ),
        (
            'ari:/IANA:amp_agent/CTRL.gen_rpts([ari:/IANA:amp_agent/RPTT.full_report],["ipn:1.7"])\n',
            '0xc1154105050225238187181941000501126769706e3a312e37\n'
        ),
        (
            'ari:/IANA:amp_agent/CTRL.gen_rpts([ari:/IANA:amp_agent/RPTT.full_report()],["ipn:1.7"])\n',
            '0xc11541050502252381c718194100000501126769706e3a312e37\n'
        ),
        (
            'ari:/IANA:amp_agent/CTRL.add_tbr(ari:/TBR.h\'303031303031303031\',TV.0,TV.1,UVAST.60,[ari:/IANA:bp_agent/RPTT.full_report],"TBR Custody")\n',
            '0xc115410a05062420201625120b493030313030313030310001183c8187182d41006b54425220437573746f6479\n'
        ),
    ]

    @classmethod
    def setUpClass(cls):
        cls._dir = TmpDir()
        adms_path = os.path.abspath(os.path.join(SELFDIR, 'adms'))
        os.environ['ADM_PATH'] = adms_path
        if not os.path.isdir(adms_path):
            raise RuntimeError(f'The ADM path does not exist at {adms_path}')

    def test_cborhex_content(self):
        cbor_dec = ari_cbor.Decoder()
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            buffer_in = io.StringIO(cborhex_in)
            for line_in in buffer_in:
                line_in = line_in.strip()
                LOGGER.info('Testing cborhex %s', line_in)
                cbor_in = cborutil.from_hexstr(line_in)
                ari = cbor_dec.decode(io.BytesIO(cbor_in))
                self.assertIsInstance(ari, ARI)
                if isinstance(ari, ReferenceARI):
                    LOGGER.debug('Got ARI: %s', ari.ident)
                    self.assertIsInstance(ari.ident.namespace, int)
                    self.assertIsInstance(ari.ident.name, bytes)

    def test_text_to_cborhex(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            LOGGER.info('Testing text %s', text_in)

            args = argparse.Namespace()
            args.inform = 'text'
            args.input = '-'
            args.outform = 'cborhex'
            args.output = '-'
            args.must_nickname = True

            sys.stdin = io.StringIO(text_in)
            sys.stdout = io.StringIO()
            ace_ari.run(args)
            cborhex_out = sys.stdout.getvalue()
            LOGGER.info('Got encoded %s', cborhex_out)
            self.assertEqual(cborhex_in.casefold(), cborhex_out.casefold())

    def test_cborhex_to_text(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            LOGGER.info('Testing cborhex %s', cborhex_in)

            args = argparse.Namespace()
            args.inform = 'cborhex'
            args.input = '-'
            args.outform = 'text'
            args.output = '-'
            args.must_nickname = True

            sys.stdin = io.StringIO(cborhex_in)
            sys.stdout = io.StringIO()
            ace_ari.run(args)
            text_out = sys.stdout.getvalue()
            LOGGER.info('Got text %s', text_out)
            self.assertEqual(text_in, text_out)

    INVALID_DATAS = (
        ('0x03\n', ''),
        # partial handling
        ('0x03F5\n0x03', 'true\n')
    )

    def test_cborhex_to_text_invalid(self):
        for cborhex_in, part_out in self.INVALID_DATAS:
            LOGGER.info('Testing cborhex %s', cborhex_in)

            args = argparse.Namespace()
            args.inform = 'cborhex'
            args.input = '-'
            args.outform = 'text'
            args.output = '-'
            args.must_nickname = True

            sys.stdin = io.StringIO(cborhex_in)
            sys.stdout = io.StringIO()
            with self.assertRaises(ari_cbor.ParseError):
                ace_ari.run(args)
            text_out = sys.stdout.getvalue()
            LOGGER.info('Got text %s', text_out)
            self.assertEqual(part_out, text_out)

    INVALID_TEXTS = (
        ('ari\n', ''),
        ('ari:/some\n', ''),
        ('true\n\nother\n', '0x03F5\n'),
    )

    def test_text_to_cborhex_invalid(self):
        for text_in, part_out in self.INVALID_TEXTS:
            LOGGER.info('Testing text %s', text_in)

            args = argparse.Namespace()
            args.inform = 'text'
            args.input = '-'
            args.outform = 'cborhex'
            args.output = '-'
            args.must_nickname = True

            sys.stdin = io.StringIO(text_in)
            sys.stdout = io.StringIO()
            with self.assertRaises(ari_text.ParseError):
                ace_ari.run(args)
            cborhex_out = sys.stdout.getvalue()
            LOGGER.info('Got encoded %s', cborhex_out)
            self.assertEqual(part_out.casefold(), cborhex_out.casefold())
