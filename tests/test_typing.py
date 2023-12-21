'''Test the mod:`ace.typing` module.
'''
import logging
import unittest
import portion
from ace.typing import *
from ace.ari import LiteralARI, ReferenceARI, UNDEFINED, NULL, TRUE, FALSE

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
        self.assertEqual(LiteralARI(0, StructType.INT), typ.get(LiteralARI(0)))
        self.assertEqual(LiteralARI(123, StructType.INT), typ.get(LiteralARI(123)))
        self.assertEqual(LiteralARI(-123, StructType.INT), typ.get(LiteralARI(-123)))
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

    def test_typeuse_int_range_get(self):
        typ = TypeUse(base=BUILTINS['int'], constraints=[
            Range(portion.closed(1, 10) | portion.closed(20, 25))
        ])

        self.assertIsNone(typ.get(UNDEFINED))
        self.assertIsNone(typ.get(TRUE))
        self.assertIsNone(typ.get(FALSE))

        for val in range(-10, 1):
            self.assertIsNone(typ.get(LiteralARI(val)))
        for val in range(1, 11):
            self.assertEqual(LiteralARI(val, StructType.INT), typ.convert(LiteralARI(val)))
        for val in range(11, 20):
            self.assertIsNone(typ.get(LiteralARI(val)))
        for val in range(20, 26):
            self.assertEqual(LiteralARI(val, StructType.INT), typ.convert(LiteralARI(val)))
        for val in range(26, 30):
            self.assertIsNone(typ.get(LiteralARI(val)))

    def test_typeuse_int_range_convert(self):
        typ = TypeUse(base=BUILTINS['int'], constraints=[
            Range(portion.closed(1, 10) | portion.closed(20, 25))
        ])

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
        typ = TypeUnion(types=[BUILTINS['bool'], BUILTINS['null']])

        self.assertIsNone(typ.get(UNDEFINED))
        self.assertEqual(TRUE, typ.get(TRUE))
        self.assertEqual(FALSE, typ.get(FALSE))
        self.assertEqual(NULL, typ.get(NULL))
        # non-matching types
        self.assertIsNone(typ.get(LiteralARI('hi')))
        self.assertIsNone(typ.get(LiteralARI(123)))

    def test_union_convert(self):
        typ = TypeUnion(types=[BUILTINS['bool'], BUILTINS['null']])

        self.assertEqual(UNDEFINED, typ.convert(UNDEFINED))

        self.assertEqual(TRUE, typ.convert(TRUE))
        self.assertEqual(FALSE, typ.convert(FALSE))
        self.assertEqual(NULL, typ.convert(NULL))
        # force the output type (in union order)
        self.assertEqual(TRUE, typ.convert(LiteralARI('hi')))
        self.assertEqual(FALSE, typ.convert(LiteralARI('')))
        self.assertEqual(TRUE, typ.convert(LiteralARI(123)))
        self.assertEqual(FALSE, typ.convert(LiteralARI(0)))

    def test_tblt_get(self):
        typ = TableTemplate(columns=[
            TableColumn(name='one', type=BUILTINS['int']),
            TableColumn(name='two', type=BUILTINS['textstr']),
            TableColumn(name='three', type=BUILTINS['bool']),
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

        inarray = numpy.ndarray((0, 3), dtype=ARI)
        LOGGER.info('array %s', inarray)
        got = typ.get(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        self.assertTrue(
            numpy.array_equal(inarray, got.value),
            msg=f'expect {inarray} got {got.value}'
        )

        inarray = numpy.array([
            [LiteralARI(1), LiteralARI('hi'), LiteralARI(True)],
        ], dtype=ARI)
        LOGGER.info('in %s', inarray)
        got = typ.get(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        LOGGER.info('out %s', got.value)
        self.assertTrue(
            numpy.array_equal(inarray, got.value),
            msg=f'expect {inarray} got {got.value}'
        )

        # mismatched value type in last column
        self.assertEqual(LiteralARI(True), inarray[0, 2])
        inarray[0, 2] = LiteralARI(3)
        LOGGER.info('in %s', inarray)
        got = typ.get(LiteralARI(inarray, StructType.TBL))
        self.assertIsNone(got)

    def test_tblt_convert(self):
        typ = TableTemplate(columns=[
            TableColumn(name='one', type=BUILTINS['int']),
            TableColumn(name='two', type=BUILTINS['textstr']),
            TableColumn(name='three', type=BUILTINS['bool']),
        ])

        inarray = numpy.array([
            [LiteralARI(1), LiteralARI('hi'), LiteralARI(True)],
        ], dtype=ARI)
        LOGGER.info('in %s', inarray)
        got = typ.convert(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        LOGGER.info('out %s', got.value)
        outarray = numpy.array([
            [
                LiteralARI(1, StructType.INT),
                LiteralARI('hi', StructType.TEXTSTR),
                LiteralARI(True, StructType.BOOL)
            ],
        ], dtype=ARI)
        self.assertTrue(
            numpy.array_equal(outarray, got.value),
            msg=f'expect {outarray} got {got.value}'
        )

        inarray = numpy.array([
            [LiteralARI(1), LiteralARI('hi'), LiteralARI('hi')],
        ], dtype=ARI)
        LOGGER.info('in %s', inarray)
        got = typ.convert(LiteralARI(inarray, StructType.TBL))
        self.assertIsNotNone(got)
        self.assertEqual(StructType.TBL, got.type_id)
        LOGGER.info('out %s', got.value)
        outarray = numpy.array([
            [
                LiteralARI(1, StructType.INT),
                LiteralARI('hi', StructType.TEXTSTR),
                LiteralARI(True, StructType.BOOL)
            ],
        ], dtype=ARI)
        self.assertTrue(
            numpy.array_equal(outarray, got.value),
            msg=f'expect {outarray} got {got.value}'
        )
