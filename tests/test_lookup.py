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
''' Test the :mod:`ace.lookup` module.
'''
import io
import logging
import os
import unittest
from ace import ari, typing, ari_text, lookup

SELFDIR = os.path.dirname(__file__)
LOGGER = logging.getLogger(__name__)


class TestActualParameterSet(unittest.TestCase):

    def setUp(self):
        unittest.TestCase.setUp(self)

        self._ari_dec = ari_text.Decoder()

        self._fparams = {}

        self._fparams['no_params'] = []

        # Equivalent to:
        # amm:parameter one {
        #   amm:type "/ARITYPE/INT";
        # }
        # amm:parameter two {
        #   amm:type "/ARITYPE/INT";
        # }
        # amm:parameter three {
        #   amm:type "/ARITYPE/INT";
        #   amm:default "5";
        # }
        self._fparams['many_params'] = [
            lookup.FormalParameter(
                name='one',
                index=0,
                typeobj=typing.TypeUse(
                    base=typing.BUILTINS['int'],
                ),
            ),
            lookup.FormalParameter(
                name='two',
                index=1,
                typeobj=typing.TypeUse(
                    base=typing.BUILTINS['int'],
                ),
            ),
            lookup.FormalParameter(
                name='three',
                index=2,
                typeobj=typing.TypeUse(
                    base=typing.BUILTINS['int'],
                ),
                default=ari.LiteralARI(5),
            ),
        ]

        # Equivalent to:
        # amm:parameter one {
        #   amm:type "/ARITYPE/INT";
        # }
        # amm:parameter args {
        #   amm:seq {
        #     amm:type "/ARITYPE/INT";
        #   }
        # }
        self._fparams['greedy_param'] = [
            lookup.FormalParameter(
                name='one',
                index=0,
                typeobj=typing.TypeUse(
                    base=typing.BUILTINS['int'],
                ),
            ),
            lookup.FormalParameter(
                name='args',
                index=1,
                typeobj=typing.Sequence(
                    base=typing.BUILTINS['int'],
                ),
            ),
        ]

    def _process(self, text:str) -> lookup.ActualParameterSet:
        ref = self._ari_dec.decode(io.StringIO(text))
        return lookup.ActualParameterSet(ref.params, self._fparams[ref.ident.obj_id])

    def test_params_none(self):
        aparams = self._process('//example/test-mod/EDD/no_params')
        self.assertEqual(
            [],
            list(aparams)
        )
        aparams = self._process('//example/test-mod/EDD/many_params')
        self.assertEqual(
            [
                ari.UNDEFINED,
                ari.UNDEFINED,
                ari.LiteralARI(5, ari.StructType.INT),  # from default
            ],
            list(aparams)
        )

    def catch_error(self, ari, etype = lookup.ParameterError):
        with self.assertRaises(etype):
            aparams = self._process(ari)

    def test_params_error(self):
        #too many
        self.catch_error('//example/test-mod/EDD/no_params(1)')
        self.catch_error('//example/test-mod/EDD/many_params(1,2,3,4)')

        #value cannot be coerced
        self.catch_error('//example/test-mod/EDD/many_params(0=test)')


    def test_params_empty(self):
        aparams = self._process('//example/test-mod/EDD/no_params()')
        self.assertEqual(
            [],
            list(aparams)
        )
        
        aparams = self._process('//example/test-mod/EDD/many_params()')
        self.assertEqual(
            [
                ari.UNDEFINED,
                ari.UNDEFINED,
                ari.LiteralARI(5, ari.StructType.INT),  # from default
            ],
            list(aparams)
        )

    def test_params_list(self):
        aparams = self._process('//example/test-mod/EDD/many_params(1,2)')
        self.assertEqual(
            [
                ari.LiteralARI(1, ari.StructType.INT),
                ari.LiteralARI(2, ari.StructType.INT),
                ari.LiteralARI(5, ari.StructType.INT),  # from default
            ],
            list(aparams)
        )

    def test_params_map_ord(self):
        aparams = self._process('//example/test-mod/EDD/many_params(0=1,2=3)')
        self.assertEqual(
            [
                ari.LiteralARI(1, ari.StructType.INT),
                ari.UNDEFINED,
                ari.LiteralARI(3, ari.StructType.INT),
            ],
            list(aparams)
        )

    def test_params_map_name(self):
        aparams = self._process('//example/test-mod/EDD/many_params(one=1,three=3)')
        self.assertEqual(
            [
                ari.LiteralARI(1, ari.StructType.INT),
                ari.UNDEFINED,
                ari.LiteralARI(3, ari.StructType.INT),
            ],
            list(aparams)
        )

    def test_params_seq_vals(self):
        aparams = self._process('//example/test-mod/EDD/greedy_param(1,2,3,4,5)')
        self.assertEqual(
            [
                ari.LiteralARI(1, ari.StructType.INT),
                ari.LiteralARI(type_id=ari.StructType.AC, value=[
                    ari.LiteralARI(2, ari.StructType.INT),
                    ari.LiteralARI(3, ari.StructType.INT),
                    ari.LiteralARI(4, ari.StructType.INT),
                    ari.LiteralARI(5, ari.StructType.INT),
                ]),
            ],
            list(aparams)
        )

    def test_params_seq_empty(self):
        aparams = self._process('//example/test-mod/EDD/greedy_param()')
        self.assertEqual(
            [
                ari.UNDEFINED,
                ari.LiteralARI(type_id=ari.StructType.AC, value=[]),
            ],
            list(aparams)
        )

    def test_params_seq_frommap(self):
        aparams = self._process('//example/test-mod/EDD/greedy_param(0=1,1=/AC/(2,3))')
        self.assertEqual(
            [
                ari.LiteralARI(1, ari.StructType.INT),
                ari.LiteralARI(type_id=ari.StructType.AC, value=[
                    ari.LiteralARI(2, ari.StructType.INT),
                    ari.LiteralARI(3, ari.StructType.INT),
                ]),
            ],
            list(aparams)
        )
