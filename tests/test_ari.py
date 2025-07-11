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
''' Verify behavior of the ace.ari module.
'''
import logging
import math
import unittest
import numpy
from ace.ari import (
    ARI, Identity, ReferenceARI, LiteralARI, StructType, UNDEFINED,
    ExecutionSet, ReportSet, Report
)

LOGGER = logging.getLogger(__name__)


class Counter:

    def __init__(self):
        self.count = 0
        self.seen = []

    def __call__(self, ari:ARI) -> None:
        self.count += 1
        self.seen.append(ari)


class IdentityMapper:

    def __call__(self, ari:ARI) -> ARI:
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
            ident=Identity('hi', StructType.EDD, 'there'),
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
            ident=Identity('hi', StructType.EDD, 'there'),
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
            ident=Identity('hi', StructType.EDD, 'there'),
            params=[
                LiteralARI(3),
                LiteralARI('hello'),
            ]
        )
        got = ari.map(IdentityMapper())
        self.assertEqual(ari, got)

    def test_map_params_map(self):
        ari = ReferenceARI(
            ident=Identity('hi', StructType.EDD, 'there'),
            params={
                LiteralARI(3): LiteralARI('hello'),
            }
        )
        got = ari.map(IdentityMapper())
        self.assertEqual(ari, got)
