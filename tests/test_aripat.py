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
''' Verify behavior of the :mod:`ace.aripat` module.
'''
import cbor2
import logging
import portion
import unittest
from ace import ari, aripat
from ace.ari import (
    ARI, Identity, ReferenceARI, LiteralARI, StructType, UNDEFINED,
)
from ace.aripat import (
    ReferenceARIPattern, ComponentPattern
)

LOGGER = logging.getLogger(__name__)


class TestComponentPattern(unittest.TestCase):

    def test_match_wild(self):
        pat = ComponentPattern(special=True)
        # no way to get a false from this

        VALUES = (
            ('hi', True),
            ('', True),
            (4, True),
            (0, True),
            (-5, True),
        )
        for comp_val, expect in VALUES:
            with self.subTest(str(comp_val)):
                self.assertEqual(expect, pat.is_match(comp_val))

    def test_match_text(self):
        pat = ComponentPattern(text={'hi'})

        VALUES = (
            ('hi', True),
            ('hit', False),
            ('ohi', False),
            ('', False),
            (-5, False),
            (0, False),
            (4, False),
        )
        for comp_val, expect in VALUES:
            with self.subTest(str(comp_val)):
                self.assertEqual(expect, pat.is_match(comp_val))

    def test_match_range(self):
        pat = ComponentPattern(enum=portion.closed(5, 10))

        VALUES = (
            ('hi', False),
            ('', False),
            (-5, False),
            (0, False),
            (5, True),
            (10, True),
            (11, False),
        )
        for comp_val, expect in VALUES:
            with self.subTest(str(comp_val)):
                self.assertEqual(expect, pat.is_match(comp_val))


class TestAriPatternMatch(unittest.TestCase):

    def test_match_all_wild(self):
        pat = ReferenceARIPattern(
            org_id=ComponentPattern(special=True),
            model_id=ComponentPattern(special=True),
            type_id=ComponentPattern(special=True),
            obj_id=ComponentPattern(special=True),
        )

        ari = ReferenceARI(ident=Identity(
            org_id=65535,
            model_id=12,
            type_id=StructType.CTRL,
            obj_id=1234,
        ))
        self.assertEqual(True, pat.is_match(ari))

        # Only namespace
        ari = ReferenceARI(ident=Identity(
            org_id=65535,
            model_id=12,
        ))
        self.assertEqual(False, pat.is_match(ari))

    def test_match_all_exact_enum(self):
        pat = ReferenceARIPattern(
            org_id=ComponentPattern(enum=portion.singleton(65535)),
            model_id=ComponentPattern(enum=portion.singleton(12)),
            type_id=ComponentPattern(enum=portion.singleton(-3)),
            obj_id=ComponentPattern(enum=portion.singleton(1234)),
        )

        baseident = Identity(
            org_id=65535,
            model_id=12,
            type_id=StructType.CTRL,
            obj_id=1234,
        )

        ari = ReferenceARI(ident=baseident)
        self.assertEqual(True, pat.is_match(ari))

        for offset in {-1, 1}:
            ari = ReferenceARI(ident=Identity(
                org_id=baseident.org_id - 1,
                model_id=baseident.model_id,
                type_id=baseident.type_id,
                obj_id=baseident.obj_id,
            ))
            with self.subTest(str(ari.ident)):
                self.assertEqual(False, pat.is_match(ari))

            ari = ReferenceARI(ident=Identity(
                org_id=baseident.org_id,
                model_id=baseident.model_id + offset,
                type_id=baseident.type_id,
                obj_id=baseident.obj_id,
            ))
            with self.subTest(str(ari.ident)):
                self.assertEqual(False, pat.is_match(ari))

            ari = ReferenceARI(ident=Identity(
                org_id=baseident.org_id,
                model_id=baseident.model_id,
                type_id=StructType(baseident.type_id + offset),
                obj_id=baseident.obj_id,
            ))
            with self.subTest(str(ari.ident)):
                self.assertEqual(False, pat.is_match(ari))

            ari = ReferenceARI(ident=Identity(
                org_id=baseident.org_id,
                model_id=baseident.model_id,
                type_id=baseident.type_id,
                obj_id=baseident.obj_id + offset,
            ))
            with self.subTest(str(ari.ident)):
                self.assertEqual(False, pat.is_match(ari))

        # Only namespace
        ari = ReferenceARI(ident=Identity(
            org_id=baseident.org_id,
            model_id=baseident.model_id,
        ))
        self.assertEqual(False, pat.is_match(ari))


class TestAriPatternCbor(unittest.TestCase):

    def test_decode_all_wild(self):
        data = cbor2.dumps([True, True, True, True])
        pat = aripat.from_cbor(data)
        self.assertIsInstance(pat, ReferenceARIPattern)
        self.assertEqual(True, pat.org_id.special)
        self.assertEqual(True, pat.model_id.special)
        self.assertEqual(True, pat.type_id.special)
        self.assertEqual(True, pat.obj_id.special)

    def test_decode_enum_ranges(self):
        # //65535/[10..19]/CTRL/[1000..1999]
        data = cbor2.dumps([65535, [10, 10], -3, [1000, 1000]])
        pat = aripat.from_cbor(data)
        self.assertIsInstance(pat, ReferenceARIPattern)
        self.assertEqual(portion.singleton(65535), pat.org_id.enum)
        self.assertEqual(portion.closedopen(10, 20), pat.model_id.enum)
        self.assertEqual(portion.singleton(StructType.CTRL), pat.type_id.enum)
        self.assertEqual(portion.closedopen(1000, 2000), pat.obj_id.enum)

    def test_loopback(self):
        VALUES = (
            cbor2.dumps([True, True, True, True]),
            cbor2.dumps([65535, [10, 10], -3, [1000, 1000]]),
            # namespace only
            cbor2.dumps([True, True, None, None]),
            cbor2.dumps([65535, 'hi', None, None]),
        )
        for data in VALUES:
            with self.subTest(data.hex()):
                pat = aripat.from_cbor(data)
                LOGGER.info('decoded %s', pat)
                got = aripat.to_cbor(pat)
                self.assertEqual(data.hex(), got.hex())

    def test_decode_invalid(self):
        VALUES = (
            cbor2.dumps('hi'),
            cbor2.dumps([65535, 'hi']),
            cbor2.dumps([65535, 'hi', None]),
        )
        for data in VALUES:
            with self.subTest(data.hex()):
                with self.assertRaises(ValueError):
                    aripat.from_cbor(data)


class TestAriPatternText(unittest.TestCase):

    def test_decode_all_wild(self):
        pat = aripat.from_text('ari://*/*/*/*')
        self.assertIsInstance(pat, ReferenceARIPattern)
        self.assertEqual(True, pat.org_id.special)
        self.assertEqual(True, pat.model_id.special)
        self.assertEqual(True, pat.type_id.special)
        self.assertEqual(True, pat.obj_id.special)

    def test_decode_enum_ranges(self):
        pat = aripat.from_text('//65535/[10..19]/CTRL/[1000..1999]')
        self.assertIsInstance(pat, ReferenceARIPattern)
        self.assertEqual(portion.singleton(65535), pat.org_id.enum)
        self.assertEqual(portion.closedopen(10, 20), pat.model_id.enum)
        self.assertEqual(portion.singleton(StructType.CTRL), pat.type_id.enum)
        self.assertEqual(portion.closedopen(1000, 2000), pat.obj_id.enum)

    def test_loopback(self):
        VALUES = (
            'ari://*/*/',
            'ari://*/*/*/*',
            'ari://hi/-123/[hi,ho]/[-1..20,50..100]',
        )
        for text in VALUES:
            with self.subTest(text):
                pat = aripat.from_text(text)
                LOGGER.info('decoded %s', pat)
                got = aripat.to_text(pat)
                self.assertEqual(text, got)

    def test_decode_invalid(self):
        VALUES = (
            'hello',
            '//hi/',
            '//1/',
            '//1/2/3/4/',
            '//1/2/3/4/5',
        )
        for text in VALUES:
            with self.subTest(text):
                with self.assertRaises(ValueError):
                    aripat.from_text(text)
