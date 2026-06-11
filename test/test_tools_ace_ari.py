#
# Copyright (c) 2020-2026 The Johns Hopkins University Applied Physics
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
from contextlib import redirect_stdout
import io
import logging
import os
import sys
import unittest
from ace.tools import ace_ari
from ace import ari_text, ari_cbor, cborutil
from ace.ari import ARI
from .util import TmpDir

LOGGER = logging.getLogger(__name__)
# : Directory containing this file
SELFDIR = os.path.dirname(__file__)


class TestAriRoundtrip(unittest.TestCase):

    CANONICAL_PAIRS = [
        # Untyped literals
        ('ari:undefined\n', '0xF7\n'),
        ('ari:null\n', '0xF6\n'),
        ('ari:true\n', '0xF5\n'),
        ('ari:false\n', '0xF4\n'),
        ('ari:10\n', '0x0A\n'),
        # Typed literals
        ('ari:/BYTE/10\n', '0x82020A\n'),
        ('ari:/INT/10\n', '0x82040A\n'),
        ('ari:/UINT/10\n', '0x82050A\n'),
        ('ari:/VAST/10\n', '0x82060A\n'),
        ('ari:/UVAST/10\n', '0x82070A\n'),
        # Reference ARIs

    ]

    @classmethod
    def setUpClass(cls):
        cls._dir = TmpDir()
        adms_path = os.path.abspath(os.path.join(SELFDIR, 'adms'))
        os.environ['ADM_PATH'] = adms_path

    def _cborhex_to_bytes(self, text: str) -> bytes:
        data = b''
        for line in text.split('\n'):
            data += bytes.fromhex(line[2:])
        return data

    def test_cborhex_valid_input(self):
        cbor_dec = ari_cbor.Decoder()
        for _text_in, cborhex_in in self.CANONICAL_PAIRS:
            with self.subTest(cborhex_in):
                buffer_in = io.StringIO(cborhex_in)
                for line_in in buffer_in:
                    line_in = line_in.strip()
                    cbor_in = cborutil.from_hexstr(line_in)
                    ari = cbor_dec.decode(io.BytesIO(cbor_in))
                    self.assertIsInstance(ari, ARI)

    def test_text_to_cborhex(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            with self.subTest(text_in):
                args = argparse.Namespace(
                    inform='uri',
                    input='-',
                    outform='cborhex',
                    output='-',
                    must_nickname=True,
                )
                sys.stdin = io.StringIO(text_in)
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    ace_ari.run(args)
                cborhex_out = stdout.getvalue()
                LOGGER.info('Got encoded %s', cborhex_out)
                self.assertEqual(cborhex_in.casefold(), cborhex_out.casefold())

    def test_text_to_cbor(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            with self.subTest(text_in):
                args = argparse.Namespace(
                    inform='uri',
                    input='-',
                    outform='cbor',
                    output='-',
                    must_nickname=True,
                )
                sys.stdin = io.StringIO(text_in)
                stdout = io.StringIO()
                stdout.buffer = io.BytesIO()
                with redirect_stdout(stdout):
                    ace_ari.run(args)
                cbor_out = stdout.buffer.getvalue()
                expect_cbor = self._cborhex_to_bytes(cborhex_in)
                self.assertEqual(expect_cbor.hex(), cbor_out.hex())

    def test_cborhex_to_text(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            with self.subTest(cborhex_in):
                args = argparse.Namespace(
                    inform='cborhex',
                    input='-',
                    outform='uri',
                    output='-',
                    must_nickname=True,
                )
                sys.stdin = io.StringIO(cborhex_in)
                stdout = io.StringIO()
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    ace_ari.run(args)
                text_out = stdout.getvalue()
                LOGGER.info('Got text %s', text_out)
                self.assertEqual(text_in, text_out)

    def test_cbor_to_text(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            with self.subTest(cborhex_in):
                args = argparse.Namespace(
                    inform='cbor',
                    input='-',
                    outform='uri',
                    output='-',
                    must_nickname=True,
                )
                sys.stdin = io.StringIO()
                sys.stdin.buffer = io.BufferedReader(
                    io.BytesIO(self._cborhex_to_bytes(cborhex_in))
                )
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    ace_ari.run(args)
                text_out = stdout.getvalue()
                LOGGER.info('Got text %s', text_out)
                self.assertEqual(text_in, text_out)

    def test_auto_from_text(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            with self.subTest(text_in):
                args = argparse.Namespace(
                    inform='auto',
                    input='-',
                    outform='auto',
                    output='-',
                    must_nickname=True,
                )
                sys.stdin = io.StringIO(text_in)
                sys.stdin.buffer = io.BufferedReader(
                    io.BytesIO(text_in.encode('utf8'))
                )
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    ace_ari.run(args)
                cborhex_out = stdout.getvalue()
                LOGGER.info('Got encoded %s', cborhex_out)
                self.assertEqual(cborhex_in.casefold(), cborhex_out.casefold())

    def test_auto_from_cbor(self):
        for text_in, cborhex_in in self.CANONICAL_PAIRS:
            with self.subTest(cborhex_in):
                args = argparse.Namespace(
                    inform='auto',
                    input='-',
                    outform='auto',
                    output='-',
                    must_nickname=True,
                )
                sys.stdin = io.StringIO()
                sys.stdin.buffer = io.BufferedReader(
                    io.BytesIO(self._cborhex_to_bytes(cborhex_in))
                )
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    ace_ari.run(args)
                text_out = stdout.getvalue()
                LOGGER.info('Got text %s', text_out)
                self.assertEqual(text_in, text_out)

    INVALID_DATAS = (
        ('0x81\n', ''),
        # partial handling, not recoverable
        ('0xF5\n0x81\n', 'ari:true\n'),
        # partial handling, not recoverable
        ('0x81\n0xF5', ''),
    )

    def test_cborhex_to_text_invalid(self):
        for cborhex_in, part_out in self.INVALID_DATAS:
            with self.subTest(cborhex_in):
                args = argparse.Namespace(
                    inform='cborhex',
                    input='-',
                    outform='uri',
                    output='-',
                    must_nickname=True,
                )
                sys.stdin = io.StringIO(cborhex_in)
                stdout = io.StringIO()
                with redirect_stdout(stdout), self.assertRaises(ari_cbor.ParseError):
                    ace_ari.run(args)
                text_out = stdout.getvalue()
                LOGGER.info('Got text %s', text_out)
                self.assertEqual(part_out, text_out)

    INVALID_TEXTS = (
        ('ari:/some\n', ''),
        ('true\n0x\n', '0xF5\n'),
    )

    def test_text_to_cborhex_invalid(self):
        for text_in, part_out in self.INVALID_TEXTS:
            LOGGER.info('Testing text %s', text_in)

            args = argparse.Namespace(
                inform='uri',
                input='-',
                outform='cborhex',
                output='-',
                must_nickname=True,
            )
            sys.stdin = io.StringIO(text_in)
            stdout = io.StringIO()
            with redirect_stdout(stdout), self.assertRaises(ari_text.ParseError):
                ace_ari.run(args)
            cborhex_out = stdout.getvalue()
            LOGGER.info('Got encoded %s', cborhex_out)
            self.assertEqual(part_out.casefold(), cborhex_out.casefold())
