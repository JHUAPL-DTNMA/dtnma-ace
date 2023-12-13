''' Implementation of semantic typing logic for ADMs and ARI processing.
'''
from dataclasses import dataclass, field
import datetime
import logging
import math
from typing import Callable, List, Optional, Set
import numpy
from portion import Interval
from .ari import (DTN_EPOCH, StructType, ARI, LiteralARI, ReferenceARI, UNDEFINED, NULL, TRUE)

LOGGER = logging.getLogger(__name__)


class Constraint:
    ''' Base class for all type constraints.
    '''

    def applicable(self) -> Set[StructType]:
        ''' Determine for which built-in types this constraint is applicable.
        '''
        raise NotImplementedError

    def is_valid(self, obj:ARI) -> bool:
        ''' Determine if a specific AMM value meets this constraint.
        '''
        raise NotImplementedError


@dataclass
class Length(Constraint):
    ''' Limit the length of string values.
    For textstr this is a count of characters, for bytestr this is a
    count of bytes.
    '''

    limit:int
    ''' The largest valid length. '''

    def applicable(self) -> Set[StructType]:
        return set([StructType.TEXTSTR, StructType.BYTESTR, StructType.CBOR])

    def is_valid(self, obj:ARI) -> bool:
        if isinstance(obj.value, (str, bytes)):
            return len(obj.value) <= self.limit
        else:
            raise TypeError(f'limit cannot be applied to {obj}')


@dataclass
class Range(Constraint):
    ''' Limit the range of numeric values.
    '''

    ranges:Interval
    ''' The Interval representing valid ranges. '''

    def applicable(self) -> Set[StructType]:
        return set([
            StructType.BYTE,
            StructType.INT,
            StructType.UINT,
            StructType.VAST,
            StructType.UVAST,
            StructType.REAL32,
            StructType.REAL64,
        ])

    def is_valid(self, obj:ARI) -> bool:
        if isinstance(obj.value, (int, float)):
            return obj.value in self.ranges
        else:
            raise TypeError(f'limit cannot be applied to {obj}')


class BaseType:
    ''' Base interface class for all type-defining classes.
    '''

    def visit(self, visitor:Callable[['BaseType'], None]):
        ''' Call a visitor on each type in a hierarchy of nested uses.

        The base type calls the visitor on itself, so only composing types
        need to override this function.

        :param visitor: The callable visitor for each type object.
        '''
        visitor(self)

    def type_enums(self) -> Set[StructType]:
        ''' Extract the set of ARI types available for this type. '''
        raise NotImplementedError()

    def get(self, obj:ARI) -> ARI:
        raise NotImplementedError()

    def convert(self, obj:ARI) -> ARI:
        raise NotImplementedError()


class BuiltInType(BaseType):
    ''' Behavior related to built-in types.

    :param type_enum: The :cls:`StructType` value related to the instance.
    '''

    def __init__(self, type_enum:StructType):
        self.type_enum = type_enum

    def __repr__(self):
        return f'{type(self).__name__}(type_enum={self.type_enum!r})'

    def type_enums(self) -> Set[StructType]:
        return set(self.type_enum)


class NullType(BuiltInType):
    ''' The null type is trivial and will convert all values into null
    except for the undefined value.
    '''

    def __init__(self):
        super().__init__(StructType.NULL)

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            return None
        if obj.value is not None:
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        return NULL


class BoolType(BuiltInType):

    def __init__(self):
        super().__init__(StructType.BOOL)

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            return None
        if not (obj.value is True or obj.value is False):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        if not isinstance(obj, LiteralARI):
            # Any obj-ref is truthy
            return TRUE

        # FIXME compare Python logic with AMM requirements
        return LiteralARI(bool(obj.value), StructType.BOOL)


class NumericType(BuiltInType):

    VALUE_CLS = {
        StructType.BYTE: int,
        StructType.INT: int,
        StructType.UINT: int,
        StructType.VAST: int,
        StructType.UVAST: int,
        StructType.REAL32: float,
        StructType.REAL64: float,
    }

    def __init__(self, type_enum, dom_min, dom_max):
        super().__init__(type_enum)
        self.dom_min = dom_min
        self.dom_max = dom_max

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            return None
        if not self._in_domain(obj.value):
            return None
        return LiteralARI(obj.value, self.type_enum)

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        if not isinstance(obj, LiteralARI):
            raise TypeError('Cannot convert an object-reference to numeric type')

        if obj.value is False or obj.value is None:
            return LiteralARI(0, self.type_enum)
        if obj.value is True:
            return LiteralARI(1, self.type_enum)

        if not self._in_domain(obj.value):
            raise ValueError(f'Numeric value outside domain [{self.dom_min},{self.dom_max}]: {obj.value}')
        # force the specific type wanted
        return LiteralARI(self.VALUE_CLS[self.type_enum](obj.value), self.type_enum)

    def _in_domain(self, value):
        if not isinstance(value, (int, float)):
            return False
        if self.VALUE_CLS[self.type_enum] is float:
            if math.isnan(value) or math.isinf(value):
                return True

        return value >= self.dom_min and value <= self.dom_max


class StringType(BuiltInType):

    VALUE_CLS = {
        StructType.TEXTSTR: str,
        StructType.BYTESTR: bytes,
        StructType.LABEL: str,
        StructType.CBOR: bytes,
    }
    ''' Required value type for target string type. '''

    def get(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            return None
        if not isinstance(obj.value, self.VALUE_CLS[self.type_enum]):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        if not isinstance(obj, LiteralARI):
            raise TypeError(f'Cannot convert to numeric type: {obj}')

        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            # something besides text string
            raise TypeError
        if not isinstance(obj.value, self.VALUE_CLS[self.type_enum]):
            raise TypeError

        return LiteralARI(obj.value, self.type_enum)


class TimeType(BuiltInType):
    ''' Times as offsets from absolute or relative epochs. '''

    # FIXME should get and convert normalize to datetime values?
    VALUE_CLS = {
        StructType.TP: (datetime.datetime, int, float),
        StructType.TD: (datetime.timedelta, int, float),
    }
    ''' Required value type for target time type. '''

    def get(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            return None
        if not isinstance(obj.value, self.VALUE_CLS[self.type_enum]):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        if not isinstance(obj, LiteralARI):
            raise TypeError(f'Cannot convert to numeric type: {obj}')

        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            raise TypeError
        typlist = self.VALUE_CLS[self.type_enum]
        if not isinstance(obj.value, typlist):
            raise TypeError

        # coerce to native value class
        newval = obj.value
        if self.type_enum == StructType.TP:
            if not isinstance(obj.value, datetime.datetime):
                newval = DTN_EPOCH + datetime.timedelta(seconds=obj.value)
        elif self.type_enum == StructType.TD:
            if not isinstance(obj.value, datetime.timedelta):
                newval = datetime.timedelta(seconds=obj.value)

        return LiteralARI(newval, self.type_enum)


class ContainerType(BuiltInType):
    ''' ARI containers. '''
    VALUE_CLS = {
        StructType.AC: list,
        StructType.AM: dict,
        StructType.TBL: numpy.ndarray
    }
    ''' Required value type for target time type. '''

    def get(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            return None
        if not isinstance(obj.value, self.VALUE_CLS[self.type_enum]):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        if not isinstance(obj, LiteralARI):
            raise TypeError(f'Cannot convert to numeric type: {obj}')

        if obj.type_enum is not None and obj.type_enum != self.type_enum:
            # something besides text string
            raise TypeError
        typ = self.VALUE_CLS[self.type_enum]
        value = typ(obj.value)

        return LiteralARI(value, self.type_enum)


class ObjRefType(BuiltInType):

    def __init__(self, type_enum=None):
        super().__init__(type_enum)

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, ReferenceARI):
            return None
        if self.type_enum is not None and obj.ident.type_enum != self.type_enum:
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        if not isinstance(obj, ReferenceARI):
            raise TypeError(f'Cannot convert to an object-reference type: {obj}')

        if self.type_enum is not None and obj.ident.type_enum != self.type_enum:
            raise ValueError()
        return obj


class AnyType(BuiltInType):
    ''' Special non-union aggregation built-in types. '''

    def __init__(self, cls):
        super().__init__(None)
        self.cls = cls

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, self.cls):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        if not isinstance(obj, self.cls):
            raise TypeError(f'Cannot convert type: {obj}')
        return obj


LITERALS = {
    'null': NullType(),
    'bool': BoolType(),
    'byte': NumericType(StructType.BYTE, 0, 2 ** 8 - 1),
    'int': NumericType(StructType.INT, -2 ** 31, 2 ** 31 - 1),
    'uint': NumericType(StructType.UINT, 0, 2 ** 32 - 1),
    'vast': NumericType(StructType.VAST, -2 ** 63, 2 ** 63 - 1),
    'uvast': NumericType(StructType.UVAST, 0, 2 ** 64 - 1),
    # from: numpy.finfo(numpy.float32).max
    'real32': NumericType(StructType.REAL32, -3.4028235e+38, 3.4028235e+38),
    # from: numpy.finfo(numpy.float32).max
    'real64': NumericType(StructType.REAL64,
                          -1.7976931348623157e+308, 1.7976931348623157e+308),
    'textstr': StringType(StructType.TEXTSTR),
    'bytestr': StringType(StructType.BYTESTR),

    'label': StringType(StructType.LABEL),
    'cbor': StringType(StructType.CBOR),
    'tp': TimeType(StructType.TP),
    'td': TimeType(StructType.TD),

    'ac': ContainerType(StructType.AC),
    'am': ContainerType(StructType.AM),
    'tbl': ContainerType(StructType.TBL),
}
LITERALS_BY_ENUM = {
    typ.type_enum: typ for typ in LITERALS.values()
}
OBJREFS = {
    'typedef': ObjRefType(StructType.TYPEDEF),
    'const': ObjRefType(StructType.CONST),
    'edd': ObjRefType(StructType.EDD),
    'var': ObjRefType(StructType.VAR),
    'ctrl': ObjRefType(StructType.CTRL),
    'oper': ObjRefType(StructType.OPER),
}
ANY = {
    'lit': AnyType(LiteralARI),
    'obj-ref': AnyType(ReferenceARI),
}
BUILTINS = LITERALS | OBJREFS | ANY


class SemType(BaseType):
    ''' Base class for all semantic type structures.
    '''


@dataclass
class TypeUse(SemType):
    ''' Use of and optional restriction on an other type. '''

    type_ns:Optional[str] = None
    ''' Namespace of the base type, or None if a built-in type. '''
    type_name:Optional[str] = None
    ''' Name of the :ivar:`base` type to bind to, or None. '''

    base:Optional[BaseType] = None
    ''' The bound type being used. '''

    units:Optional[str] = None
    ''' Optional unit name for this use. '''

    constraints:List[Constraint] = field(default_factory=list)
    ''' Optional value constraints on this use. '''

    def visit(self, visitor:Callable[['BaseType'], None]):
        if self.base:
            visitor(self.base)
        super().visit(visitor)

    def type_enums(self) -> Set[StructType]:
        return self.base.type_enums()

    def get(self, obj:ARI) -> Optional[ARI]:
        # extract the value before checks
        got = self.base.get(obj)
        if got is not None:
            invalid = self._constrain(got)
            if invalid:
                LOGGER.debug('TypeUse.get() invalid constraints: %s', invalid)
                return None
        return got

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        got = self.base.convert(obj)
        invalid = self._constrain(got)
        if invalid:
            raise ValueError(f'TypeUse.convert() invalid constraints: {invalid}')
        return got

    def _constrain(self, obj):
        ''' Check constraints on a value.

        :param obj: The value to check.
        :return: A list of violated constraints.
        '''
        invalid = [
            con
            for con in self.constraints
            if not con.is_valid(obj)
        ]
        return invalid


@dataclass
class TypeUnion(SemType):
    ''' A union of other types. '''

    types:List[SemType] = field(default_factory=list)
    ''' The underlying types, with significant order. '''

    def visit(self, visitor:Callable[['BaseType'], None]):
        for typ in self.types:
            typ.visit(visitor)
        super().visit(visitor)

    def type_enums(self) -> Set[StructType]:
        # set constructor will de-duplicate
        return set([typ.type_enums() for typ in self.types])

    def get(self, obj:ARI) -> Optional[ARI]:
        for typ in self.types:
            try:
                got = typ.get(obj)
            except (TypeError, ValueError):
                continue
            if got is not None:
                return got
        return None

    def convert(self, obj:ARI) -> ARI:
        if obj == UNDEFINED:
            return obj
        for typ in self.types:
            try:
                return typ.convert(obj)
            except (TypeError, ValueError):
                continue
        raise TypeError('convert() failed to match a union type')


@dataclass
class UniformList(SemType):
    ''' A list with uniform-typed items. '''

    type:SemType
    ''' Type for all items. '''

    # FIXME list size limits?

    def visit(self, visitor:Callable[['BaseType'], None]):
        self.type.visit(visitor)
        super().visit(visitor)

    def type_enums(self) -> Set[StructType]:
        # only one value type is valid
        return self.type.type_enums()

    def get(self, obj:ARI) -> Optional[ARI]:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is None and obj == UNDEFINED:
            return None
        if obj.type_enum != StructType.AC:
            return None

        for val in self.value:
            if self.type.get(val) is None:
                return None

        return obj

    def convert(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            raise TypeError()
        if obj.type_enum is None and obj == UNDEFINED:
            return obj
        if obj.type_enum != StructType.AC:
            raise TypeError(f'Value to convert is not AC, it is {obj.type_enum}')

        rval = []
        for ival in self.value:
            rval.append(self.type.convert(ival))

        return LiteralARI(rval, StructType.AC)


@dataclass
class TableColumn:
    ''' Each column of a TableTemplate object. '''

    name:str
    ''' Unique name of this column. '''
    type:SemType
    ''' Type for this column. '''


@dataclass
class TableTemplate(SemType):
    ''' A template for specific table (TBL) structure. '''

    columns:List[TableColumn] = field(default_factory=list)
    ''' Column definitions, with significant order. '''

    key:Optional[str] = None
    ''' Name of the key column. '''
    unique:List[List[str]] = field(default_factory=list)
    ''' Names of unique column tuples. '''

    def visit(self, visitor:Callable[['BaseType'], None]):
        for col in self.columns:
            col.type.visit(visitor)
        super().visit(visitor)

    def type_enums(self) -> Set[StructType]:
        # only one value type is valid
        return set([StructType.TBL])

    def get(self, obj:ARI) -> Optional[ARI]:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_enum is None and obj == UNDEFINED:
            return None
        if obj.type_enum != StructType.TBL:
            return None

        if obj.value.ndim != 2:
            return None
        nrows, ncols = obj.value.shape
        if ncols != len(self.columns):
            return None
        # check each value against column schema
        for row_ix in range(nrows):
            for col_ix, col in enumerate(self.columns):
                if col.type.get(obj.value[row_ix, col_ix]) is None:
                    return None

        return obj

    def convert(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            raise TypeError()
        if obj.type_enum is None and obj == UNDEFINED:
            return obj
        if obj.type_enum != StructType.TBL:
            raise TypeError(f'Value to convert is not TBL, it is {obj.type_enum}')

        if obj.value.ndim != 2:
            raise ValueError(f'TBL value must be a 2-dimensional array, is {obj.value.ndim}')
        nrows, ncols = obj.value.shape
        if ncols != len(self.columns):
            raise ValueError(f'TBL value has wrong number of columns: should be {len(self.columns)} is {ncols}')

        rval = numpy.ndarray(obj.value.shape, dtype=ARI)
        for row_ix in range(nrows):
            for col_ix, col in enumerate(self.columns):
                rval[row_ix, col_ix] = col.type.convert(obj.value[row_ix, col_ix])

        return LiteralARI(rval, StructType.TBL)

