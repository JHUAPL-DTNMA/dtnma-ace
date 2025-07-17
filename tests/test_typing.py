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
'''Test the mod:`ace.typing` module.
'''
import logging
import unittest
import portion
from ace.typing import (
    BUILTINS, type_walk,
    NullType, BoolType, NumericType, StringType,
    TypeUse, TypeUnion, UniformList, DiverseList, UniformMap,
    TableTemplate, TableColumn, Sequence
)
from ace.adm_yang import range_from_text
from ace.type_constraint import (
    NumericRange, StringLength, TextPattern, IntegerEnums
)
from ace.ari import (
    StructType, Table, LiteralARI, ReferenceARI, Identity,
    UNDEFINED, NULL, TRUE, FALSE
)
from .util import TypeSummary

LOGGER = logging.getLogger(__name__)


class TestTyping(unittest.TestCase):

    def test_builtin_get_undefined(self):
        for name, typ in BUILTINS.items():
            LOGGER.info('Testing %s: %s', name, typ)
            self.assertIsNone(typ.get(UNDEFINED))

    def test_builtin_convert_undefined(self):
        for name, typ in BUILTINS.items():
            LOGGER.info('Testing %s: %s', name, typ)
            self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))

    def test_bool_get(self):
        typ = BUILTINS['bool']

        self.assertIsNone(typ.get(NULL))
        self.assertEqual(TRUE, typ.get(TRUE))
        self.assertEqual(FALSE, typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('')))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(b'')))
        self.assertIsNone(typ.get(LiteralARI(b'hi')))
        self.assertIsNone(typ.get(LiteralARI(0)))
        self.assertIsNone(typ.get(LiteralARI(123)))

    def test_bool_convert(self):
        typ = BUILTINS['bool']

        self.assertEqual(TRUE, typ.convert(TRUE))
        self.assertEqual(FALSE, typ.convert(FALSE))
        self.assertEqual(FALSE, typ.convert(NULL))
        self.assertEqual(FALSE, typ.convert(LiteralARI('')))
        self.assertEqual(TRUE, typ.convert(LiteralARI('hi')))
        self.assertEqual(FALSE, typ.convert(LiteralARI(b'')))
        self.assertEqual(TRUE, typ.convert(LiteralARI(b'hi')))
        self.assertEqual(FALSE, typ.convert(LiteralARI(0)))
        self.assertEqual(TRUE, typ.convert(LiteralARI(123)))

    def test_int_get(self):
        typ = BUILTINS['int']

        self.assertIsNone(typ.get(NULL))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('')))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(b'')))
        self.assertIsNone(typ.get(LiteralARI(b'hi')))
        self.assertEqual(LiteralARI(0), typ.get(LiteralARI(0)))
        self.assertEqual(LiteralARI(123), typ.get(LiteralARI(123)))
        self.assertEqual(LiteralARI(-123), typ.get(LiteralARI(-123)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.UINT)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.VAST)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.UVAST)))

    def test_int_convert(self):
        typ = BUILTINS['int']

        self.assertEqual(LiteralARI(0, StructType.INT), typ.convert(NULL))
        self.assertEqual(LiteralARI(1, StructType.INT), typ.convert(TRUE))
        self.assertEqual(LiteralARI(0, StructType.INT), typ.convert(FALSE))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(''))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI('hi'))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(b''))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(b'hi'))

        # in domain
        self.assertEqual(LiteralARI(0, StructType.INT), typ.convert(LiteralARI(0)))
        self.assertEqual(LiteralARI(123, StructType.INT), typ.convert(LiteralARI(123)))
        self.assertEqual(LiteralARI(-123, StructType.INT), typ.convert(LiteralARI(-123)))
        self.assertEqual(LiteralARI(0, StructType.INT), typ.convert(LiteralARI(0, StructType.UINT)))
        self.assertEqual(LiteralARI(0, StructType.INT), typ.convert(LiteralARI(0, StructType.VAST)))
        self.assertEqual(LiteralARI(0, StructType.INT), typ.convert(LiteralARI(0, StructType.UVAST)))

        # domain limits
        typ.convert(LiteralARI(2 ** 31 - 1))
        typ.convert(LiteralARI(2 ** 31 - 1, StructType.UVAST))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(2 ** 31))
        typ.convert(LiteralARI(-(2 ** 31)))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(-(2 ** 31) - 1))

    def test_textstr_get(self):
        typ = BUILTINS['textstr']

        self.assertIsNone(typ.get(NULL))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))
        self.assertEqual(LiteralARI(''), typ.get(LiteralARI('')))
        self.assertEqual(LiteralARI('hi'), typ.get(LiteralARI('hi')))
        self.assertEqual(LiteralARI('hi', StructType.TEXTSTR), typ.get(LiteralARI('hi', StructType.TEXTSTR)))
        self.assertIsNone(typ.get(LiteralARI(b'')))
        self.assertIsNone(typ.get(LiteralARI(b'hi')))
        self.assertIsNone(typ.get(LiteralARI(0)))
        self.assertIsNone(typ.get(LiteralARI(123)))
        self.assertIsNone(typ.get(LiteralARI(-123)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.UINT)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.VAST)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.UVAST)))

    def test_textstr_convert(self):
        typ = BUILTINS['textstr']

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))
        with self.assertRaises(TypeError):
            typ.convert(NULL)
        with self.assertRaises(TypeError):
            typ.convert(TRUE)
        with self.assertRaises(TypeError):
            typ.convert(FALSE)
        self.assertEqual(LiteralARI('', StructType.TEXTSTR), typ.convert(LiteralARI('')))
        self.assertEqual(LiteralARI('hi', StructType.TEXTSTR), typ.convert(LiteralARI('hi')))
        self.assertEqual(LiteralARI('hi', StructType.TEXTSTR), typ.convert(LiteralARI('hi', StructType.TEXTSTR)))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(b''))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(b'hi'))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(0))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(123))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(-123))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(0, StructType.UINT))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(0, StructType.VAST))
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(0, StructType.UVAST))

    def test_edd_get(self):
        typ = BUILTINS['edd']

        self.assertIsNone(typ.get(NULL))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(b'hi')))
        self.assertIsNone(typ.get(LiteralARI(123)))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.get(ref))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.CTRL, obj_id='name'))
        self.assertIsNone(typ.get(ref))

    def test_edd_convert(self):
        typ = BUILTINS['edd']

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))
        with self.assertRaises(TypeError):
            typ.convert(NULL)
        with self.assertRaises(TypeError):
            typ.convert(TRUE)
        with self.assertRaises(TypeError):
            typ.convert(FALSE)
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI('hi'))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.convert(ref))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.CTRL, obj_id='name'))
        with self.assertRaises(ValueError):
            typ.convert(ref)

    def test_literal_get(self):
        typ = BUILTINS['literal']

        self.assertEqual(NULL, typ.get(NULL))
        self.assertEqual(TRUE, typ.get(TRUE))
        self.assertEqual(FALSE, typ.get(FALSE))
        self.assertEqual(LiteralARI('hi'), typ.get(LiteralARI('hi')))
        self.assertEqual(LiteralARI(10, StructType.INT), typ.get(LiteralARI(10, StructType.INT)))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertIsNone(typ.get(ref))

        ref = ReferenceARI(Identity(type_id=StructType.EDD, obj_id='name'))
        self.assertIsNone(typ.get(ref))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod'))
        self.assertIsNone(typ.get(ref))

    def test_literal_convert(self):
        typ = BUILTINS['literal']

        self.assertEqual(NULL, typ.convert(NULL))
        self.assertEqual(TRUE, typ.convert(TRUE))
        self.assertEqual(FALSE, typ.convert(FALSE))
        self.assertEqual(LiteralARI('hi'), typ.convert(LiteralARI('hi')))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        with self.assertRaises(TypeError):
            typ.convert(ref)

        ref = ReferenceARI(Identity(type_id=StructType.EDD, obj_id='name'))
        with self.assertRaises(TypeError):
            typ.convert(ref)

        ref = ReferenceARI(Identity(org_id='example', model_id='mod'))
        with self.assertRaises(TypeError):
            typ.convert(ref)

    def test_object_get(self):
        typ = BUILTINS['object']

        self.assertIsNone(typ.get(NULL))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(10, StructType.INT)))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.get(ref))
        # relative
        ref = ReferenceARI(Identity(model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.get(ref))
        ref = ReferenceARI(Identity(type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.get(ref))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod'))
        self.assertIsNone(typ.get(ref))
        # relative
        ref = ReferenceARI(Identity(model_id='mod'))
        self.assertIsNone(typ.get(ref))
        ref = ReferenceARI(Identity())
        self.assertIsNone(typ.get(ref))

    def test_object_convert(self):
        typ = BUILTINS['object']

        with self.assertRaises(TypeError):
            typ.convert(NULL)
        with self.assertRaises(TypeError):
            typ.convert(TRUE)
        with self.assertRaises(TypeError):
            typ.convert(FALSE)
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI('hi'))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.convert(ref))
        # relative
        ref = ReferenceARI(Identity(model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.convert(ref))
        ref = ReferenceARI(Identity(type_id=StructType.EDD, obj_id='name'))
        self.assertEqual(ref, typ.convert(ref))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod'))
        with self.assertRaises(TypeError):
            typ.convert(ref)
        # relative
        ref = ReferenceARI(Identity(model_id='mod'))
        with self.assertRaises(TypeError):
            typ.convert(ref)
        ref = ReferenceARI(Identity())
        with self.assertRaises(TypeError):
            typ.convert(ref)

    def test_namespace_get(self):
        typ = BUILTINS['namespace']

        self.assertIsNone(typ.get(NULL))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(10, StructType.INT)))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertIsNone(typ.get(ref))
        # relative
        ref = ReferenceARI(Identity(model_id='mod', type_id=StructType.EDD, obj_id='name'))
        self.assertIsNone(typ.get(ref))
        ref = ReferenceARI(Identity(type_id=StructType.EDD, obj_id='name'))
        self.assertIsNone(typ.get(ref))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod'))
        self.assertEqual(ref, typ.get(ref))
        # relative
        ref = ReferenceARI(Identity(model_id='mod'))
        self.assertEqual(ref, typ.get(ref))
        ref = ReferenceARI(Identity())
        self.assertEqual(ref, typ.get(ref))

    def test_namespace_convert(self):
        typ = BUILTINS['namespace']

        with self.assertRaises(TypeError):
            typ.convert(NULL)
        with self.assertRaises(TypeError):
            typ.convert(TRUE)
        with self.assertRaises(TypeError):
            typ.convert(FALSE)
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI('hi'))

        ref = ReferenceARI(Identity(org_id='example', model_id='mod', type_id=StructType.EDD, obj_id='name'))
        with self.assertRaises(TypeError):
            typ.convert(ref)
        # relative
        ref = ReferenceARI(Identity(model_id='mod', type_id=StructType.EDD, obj_id='name'))
        with self.assertRaises(TypeError):
            typ.convert(ref)
        ref = ReferenceARI(Identity(type_id=StructType.EDD, obj_id='name'))
        with self.assertRaises(TypeError):
            typ.convert(ref)

        ref = ReferenceARI(Identity(org_id='example', model_id='mod'))
        self.assertEqual(ref, typ.convert(ref))
        # relative
        ref = ReferenceARI(Identity(model_id='mod'))
        self.assertEqual(ref, typ.convert(ref))
        ref = ReferenceARI(Identity())
        self.assertEqual(ref, typ.convert(ref))

    def test_typeuse_int_range_get(self):
        typ = TypeUse(
            base=BUILTINS['int'],
            constraints=[
                NumericRange(portion.closed(1, 10) | portion.closed(20, 25))
            ]
        )

        self.assertIsNone(typ.get(UNDEFINED))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))

        for val in range(-10, 1):
            self.assertIsNone(typ.get(LiteralARI(val)))
        for val in range(1, 11):
            self.assertEqual(LiteralARI(val), typ.get(LiteralARI(val)))
        for val in range(11, 20):
            self.assertIsNone(typ.get(LiteralARI(val)))
        for val in range(20, 26):
            self.assertEqual(LiteralARI(val), typ.get(LiteralARI(val)))
        for val in range(26, 30):
            self.assertIsNone(typ.get(LiteralARI(val)))

    def test_typeuse_int_range_convert(self):
        typ = TypeUse(
            base=BUILTINS['int'],
            constraints=[
                NumericRange(portion.closed(1, 10) | portion.closed(20, 25))
            ]
        )

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))
        self.assertEqual(LiteralARI(1, StructType.INT), typ.convert(TRUE))

        for val in range(-10, 1):
            with self.assertRaises(ValueError):
                typ.convert(LiteralARI(val))
        for val in range(1, 11):
            self.assertEqual(LiteralARI(val, StructType.INT), typ.convert(LiteralARI(val)))
        for val in range(11, 20):
            with self.assertRaises(ValueError):
                typ.convert(LiteralARI(val))
        for val in range(20, 26):
            self.assertEqual(LiteralARI(val, StructType.INT), typ.convert(LiteralARI(val)))
        for val in range(26, 30):
            with self.assertRaises(ValueError):
                typ.convert(LiteralARI(val))

    def test_union_get(self):
        typ = TypeUnion(types=[
            BUILTINS['bool'],
            BUILTINS['null']
        ])

        self.assertIsNone(typ.get(UNDEFINED))
        self.assertEqual(TRUE, typ.get(TRUE))
        self.assertEqual(FALSE, typ.get(FALSE))
        self.assertEqual(NULL, typ.get(NULL))
        # non-matching types
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(123)))

    def test_union_convert(self):
        typ = TypeUnion(types=[
            BUILTINS['bool'],
            BUILTINS['null']
        ])

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))

        self.assertEqual(TRUE, typ.convert(TRUE))
        self.assertEqual(FALSE, typ.convert(FALSE))
        self.assertEqual(NULL, typ.convert(NULL))
        # force the output type (in union order)
        self.assertEqual(TRUE, typ.convert(LiteralARI('hi')))
        self.assertEqual(FALSE, typ.convert(LiteralARI('')))
        self.assertEqual(TRUE, typ.convert(LiteralARI(123)))
        self.assertEqual(FALSE, typ.convert(LiteralARI(0)))

    def test_ulist_get(self):
        typ = UniformList(
            base=BUILTINS['textstr'],
            min_elements=1,
            max_elements=3,
        )

        self.assertIsNone(typ.get(UNDEFINED))

        self.assertEqual(
            LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('hi')
            ]),
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('hi')
            ]))
        )
        self.assertIsNotNone(
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('one'),
                LiteralARI('two'),
                LiteralARI('three'),
            ]))
        )
        # non-matching types
        self.assertIsNone(typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(123)))
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123)
            ]))
        )
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AC, value=[]))
        )
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('one'),
                LiteralARI('two'),
                LiteralARI('three'),
                LiteralARI('four'),
            ]))
        )

    def test_ulist_convert(self):
        typ = UniformList(
            base=BUILTINS['textstr'],
            min_elements=1,
            max_elements=3,
        )

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))

        self.assertEqual(
            LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('hi', StructType.TEXTSTR)
            ]),
            typ.convert(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('hi')
            ]))
        )
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('one'),
                LiteralARI('two'),
                LiteralARI('three'),
                LiteralARI('four'),
            ]))

    def test_dlist_get(self):
        typ = DiverseList(parts=[
            BUILTINS['int'],
            Sequence(
                base=BUILTINS['textstr'],
                max_elements=1,
            )
        ])

        self.assertIsNone(typ.get(UNDEFINED))

        self.assertEqual(
            LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123)
            ]),
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123)
            ]))
        )
        self.assertEqual(
            LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123),
                LiteralARI('hi'),
            ]),
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123),
                LiteralARI('hi'),
            ]))
        )
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AC, value=[]))
        )
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('hi')
            ]))
        )
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123),
                LiteralARI('hi'),
                LiteralARI('hi'),
            ]))
        )

    def test_dlist_convert(self):
        typ = DiverseList(parts=[
            BUILTINS['int'],
            Sequence(
                base=BUILTINS['textstr'],
                max_elements=1,
            )
        ])

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))

        self.assertEqual(
            LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123, StructType.INT)
            ]),
            typ.convert(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123)
            ]))
        )
        self.assertEqual(
            LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123, StructType.INT),
                LiteralARI('hi', StructType.TEXTSTR),
            ]),
            typ.convert(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123),
                LiteralARI('hi'),
            ]))
        )
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(type_id=StructType.AC, value=[]))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI('hi'),
            ]))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(type_id=StructType.AC, value=[
                LiteralARI(123),
                LiteralARI('hi'),
                LiteralARI('hi'),
            ]))

    def test_umap_get(self):
        typ = UniformMap(
            kbase=BUILTINS['uint'],
            vbase=BUILTINS['textstr'],
        )

        self.assertIsNone(typ.get(UNDEFINED))

        self.assertEqual(
            LiteralARI(type_id=StructType.AM, value={}),
            typ.get(LiteralARI(type_id=StructType.AM, value={}))
        )
        self.assertEqual(
            LiteralARI(type_id=StructType.AM, value={
                LiteralARI(3): LiteralARI('hi')
            }),
            typ.get(LiteralARI(type_id=StructType.AM, value={
                LiteralARI(3): LiteralARI('hi')
            }))
        )
        self.assertIsNotNone(
            typ.get(LiteralARI(type_id=StructType.AM, value={
                LiteralARI(1): LiteralARI('one'),
                LiteralARI(2): LiteralARI('two'),
                LiteralARI(3): LiteralARI('three'),
            }))
        )
        # non-matching types
        self.assertIsNone(typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(123)))
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AM, value={
                LiteralARI(3): LiteralARI(123),
            }))
        )
        self.assertIsNone(
            typ.get(LiteralARI(type_id=StructType.AM, value={
                LiteralARI('hi'): LiteralARI('hello'),
            }))
        )

    def test_umap_convert(self):
        typ = UniformMap(
            kbase=BUILTINS['uint'],
            vbase=BUILTINS['textstr'],
        )

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))

        self.assertEqual(
            LiteralARI(type_id=StructType.AM, value={
                LiteralARI(3): LiteralARI('hi', StructType.TEXTSTR)
            }),
            typ.convert(LiteralARI(type_id=StructType.AM, value={
                LiteralARI(3): LiteralARI('hi')
            }))
        )
        with self.assertRaises(TypeError):
            typ.convert(LiteralARI(type_id=StructType.AM, value={
                LiteralARI(3): LiteralARI(123),
            }))
        with self.assertRaises(ValueError):
            typ.convert(LiteralARI(type_id=StructType.AM, value={
                LiteralARI('hi'): LiteralARI('hello'),
            }))

    def test_tblt_get(self):
        typ = TableTemplate(columns=[
            TableColumn(name='one', base=BUILTINS['int']),
            TableColumn(name='two', base=BUILTINS['textstr']),
            TableColumn(name='three', base=BUILTINS['bool']),
        ])

        self.assertIsNone(typ.get(NULL))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))
        self.assertIsNone(typ.get(LiteralARI('')))
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI('hi', StructType.TEXTSTR)))
        self.assertIsNone(typ.get(LiteralARI(b'')))
        self.assertIsNone(typ.get(LiteralARI(b'hi')))
        self.assertIsNone(typ.get(LiteralARI(0)))
        self.assertIsNone(typ.get(LiteralARI(123)))
        self.assertIsNone(typ.get(LiteralARI(-123)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.UINT)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.VAST)))
        self.assertIsNone(typ.get(LiteralARI(0, StructType.UVAST)))

        inarray = Table((0, 3))
        LOGGER.info('array %s', inarray)
        got = typ.get(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        self.assertEqual(inarray, got.value)

        inarray = Table.from_rows([
            [LiteralARI(1), LiteralARI('hi'), LiteralARI(True)],
        ])
        LOGGER.info('in %s', inarray)
        got = typ.get(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        LOGGER.info('out %s', got.value)
        self.assertEqual(inarray, got.value)

        # mismatched value type in last column
        self.assertEqual(LiteralARI(True), inarray[0, 2])
        inarray[0, 2] = LiteralARI(3)
        LOGGER.info('in %s', inarray)
        got = typ.get(LiteralARI(inarray, StructType.TBL))
        self.assertIsNone(got)

    def test_tblt_convert(self):
        typ = TableTemplate(columns=[
            TableColumn(name='one', base=BUILTINS['int']),
            TableColumn(name='two', base=BUILTINS['textstr']),
            TableColumn(name='three', base=BUILTINS['bool']),
        ])

        inarray = Table.from_rows([
            [LiteralARI(1), LiteralARI('hi'), LiteralARI(True)],
        ])
        LOGGER.info('in %s', inarray)
        got = typ.convert(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        LOGGER.info('out %s', got.value)
        outarray = Table.from_rows([
            [
                LiteralARI(1, StructType.INT),
                LiteralARI('hi', StructType.TEXTSTR),
                LiteralARI(True, StructType.BOOL)
            ],
        ])
        self.assertEqual(outarray, got.value)

        inarray = Table.from_rows([
            [LiteralARI(1), LiteralARI('hi'), LiteralARI('hi')],
        ])
        LOGGER.info('in %s', inarray)
        got = typ.convert(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        LOGGER.info('out %s', got.value)
        outarray = Table.from_rows([
            [
                LiteralARI(1, StructType.INT),
                LiteralARI('hi', StructType.TEXTSTR),
                LiteralARI(True, StructType.BOOL)
            ],
        ])
        self.assertEqual(outarray, got.value)

    def test_seq_take(self):
        typ = Sequence(
            base=BUILTINS['textstr'],
            max_elements=1,
        )

        items = [
            LiteralARI(1),
            LiteralARI('hi'),
        ]
        got = typ.take(items)
        self.assertEqual(0, len(got))
        self.assertEqual(2, len(items))

        items = [
            LiteralARI('hi'),
            LiteralARI(1),
        ]
        got = typ.take(items)
        self.assertEqual(1, len(got))
        self.assertEqual(1, len(items))
        self.assertEqual([LiteralARI('hi')], got)

        items = [
            LiteralARI('hi'),
            LiteralARI('oh'),  # don't care
        ]
        got = typ.take(items)
        self.assertEqual(1, len(got))
        self.assertEqual(1, len(items))
        self.assertEqual([LiteralARI('hi')], got)

    TYPE_WALK = (
        (
            BUILTINS['int'],
            [
                TypeSummary(NumericType, StructType.INT),
            ]
        ),
        (
            TypeUnion(types=[BUILTINS['bool'], BUILTINS['null']]),
            [
                TypeSummary(TypeUnion, None),
                TypeSummary(BoolType, StructType.BOOL),
                TypeSummary(NullType, StructType.NULL),
            ]
        ),
        (
            TableTemplate(columns=[
                TableColumn(name='one', base=BUILTINS['int']),
                TableColumn(name='two', base=BUILTINS['textstr']),
                TableColumn(name='three', base=BUILTINS['bool']),
            ]),
            [
                TypeSummary(TableTemplate, None),
                TypeSummary(NumericType, StructType.INT),
                TypeSummary(StringType, StructType.TEXTSTR),
                TypeSummary(BoolType, StructType.BOOL),
            ]
        ),
    )

    def test_type_walk(self):
        for row in self.TYPE_WALK:
            with self.subTest(f'{row}'):
                root, expect = row
                got = [
                    TypeSummary.from_type(obj)
                    for obj in type_walk(root)
                ]
                self.assertEqual(expect, got)
