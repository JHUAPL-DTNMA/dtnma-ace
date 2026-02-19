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
''' Verify behavior of the :mod:`ace.ari` module.
'''
import logging
import unittest
from ace.ari import (
    ARI, Identity, ReferenceARI, LiteralARI, StructType,
    ObjectRefPattern, apiIntInterval
)

LOGGER = logging.getLogger(__name__)


class Counter:

    def __init__(self):
        self.count = 0
        self.seen = []

    def __call__(self, ari: ARI) -> None:
        self.count += 1
        self.seen.append(ari)


class IdentityMapper:

    def __call__(self, ari: ARI) -> ARI:
        return ari


class TestAri(unittest.TestCase):

    def test_visit_simple(self):
        ari = LiteralARI(3)
        ctr = Counter()
        ari.visit(ctr)
        self.assertEqual(1, ctr.count)

    def test_visit_container(self):
        ari = LiteralARI(3)
        ctr = Counter()
        ari.visit(ctr)
        self.assertEqual(1, ctr.count)

    def test_visit_params_list(self):
        ari = ReferenceARI(
            ident=Identity(org_id='example', model_id='hi', type_id=StructType.EDD, obj_id='there'),
            params=[
                LiteralARI(3),
                LiteralARI('hello'),
            ]
        )
        ctr = Counter()
        ari.visit(ctr)
        self.assertEqual(3, ctr.count)

    def test_visit_params_map(self):
        ari = ReferenceARI(
            ident=Identity(org_id='example', model_id='hi', type_id=StructType.EDD, obj_id='there'),
            params={
                LiteralARI(3): LiteralARI('hello'),
            }
        )
        ctr = Counter()
        ari.visit(ctr)
        self.assertEqual(3, ctr.count)

    def test_map_simple(self):
        ari = LiteralARI(3)
        got = ari.map(IdentityMapper())
        self.assertEqual(ari, got)

    def test_map_params_list(self):
        ari = ReferenceARI(
            ident=Identity(org_id='example', model_id='hi', type_id=StructType.EDD, obj_id='there'),
            params=[
                LiteralARI(3),
                LiteralARI('hello'),
            ]
        )
        got = ari.map(IdentityMapper())
        self.assertEqual(ari, got)

    def test_map_params_map(self):
        ari = ReferenceARI(
            ident=Identity(org_id='example', model_id='hi', type_id=StructType.EDD, obj_id='there'),
            params={
                LiteralARI(3): LiteralARI('hello'),
            }
        )
        got = ari.map(IdentityMapper())
        self.assertEqual(ari, got)


class TestPatternLogic(unittest.TestCase):
    ''' Simple verification of OBJPAT internal logic '''

    def test_match_any(self):
        pat = ObjectRefPattern(
            org_pat=True,
            model_pat=True,
            type_pat=True,
            obj_pat=True,
        )

        ident = Identity(org_id=65535, model_id=10, type_id=StructType.EDD, obj_id=1234)
        self.assertTrue(pat.is_match(ident))

    def test_match_ranges(self):
        pat = ObjectRefPattern(
            org_pat=apiIntInterval.singleton(65535),
            model_pat=(apiIntInterval.closed(ObjectRefPattern.DOMAIN_MIN, -1) | apiIntInterval.singleton(1)),
            type_pat=True,
            obj_pat=apiIntInterval.closed(10, 100),
        )

        ident = Identity(org_id=65535, model_id=1, type_id=StructType.EDD, obj_id=12)
        self.assertTrue(pat.is_match(ident))

        ident = Identity(org_id=65536, model_id=1, type_id=StructType.EDD, obj_id=12)
        self.assertFalse(pat.is_match(ident))

        ident = Identity(org_id=65535, model_id=0, type_id=StructType.EDD, obj_id=12)
        self.assertFalse(pat.is_match(ident))

        ident = Identity(org_id=65535, model_id=1, type_id=StructType.EDD, obj_id=9)
        self.assertFalse(pat.is_match(ident))
