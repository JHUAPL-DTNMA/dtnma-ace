''' Implementation of semantic typing logic for ADMs and ARI processing.
'''
from dataclasses import dataclass, field
import datetime
import logging
import math
import re
from typing import List, Optional, Set, Tuple, Iterator, Union
import numpy
from portion import Interval
from .ari import (
    DTN_EPOCH, StructType, Table,
    ARI, LiteralARI, ReferenceARI, is_undefined, NULL, TRUE
)

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

    ranges:Interval
    ''' The Interval representing valid lengths. '''

    def applicable(self) -> Set[StructType]:
        return set([StructType.TEXTSTR, StructType.BYTESTR, StructType.CBOR])

    def is_valid(self, obj:ARI) -> bool:
        if isinstance(obj.value, (str, bytes)):
            return len(obj.value) in self.ranges
        else:
            raise TypeError(f'limit cannot be applied to {obj}')


@dataclass
class Pattern(Constraint):
    ''' Limit the content of text string values.
    '''

    pattern:str
    ''' The regular expression pattern. '''

    def applicable(self) -> Set[StructType]:
        return set([StructType.TEXTSTR])

    def is_valid(self, obj:ARI) -> bool:
        if isinstance(obj.value, (str, bytes)):
            got = re.fullmatch(self.pattern, obj.value)
            return got is not None
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

    def children(self) -> List['BaseType']:
        ''' Get the set of child types under this type object.

        The base type returns an empty list.

        :return: Any child type objects.
        '''
        return []

    def type_ids(self) -> Set[StructType]:
        ''' Extract the set of ARI types available for this type. '''
        raise NotImplementedError()

    def get(self, obj:ARI) -> ARI:
        raise NotImplementedError()

    def convert(self, obj:ARI) -> ARI:
        ''' Force a literal conversion to this target type.

        :param obj: The input ARI.
        :return: The converted ARI.
        :raise TypeError: if something is wrong with the input type.
        :raise ValueError: if something is wrong with the input value.
        '''
        raise NotImplementedError()

    def simplify(self, obj:ARI) -> ARI:
        ''' Perform type simplification to avoid duplicate literal typing.

        The base type returns itself.

        :param obj: The input ARI.
        :return: The converted ARI.
        '''
        return obj


class BuiltInType(BaseType):
    ''' Behavior related to built-in types.

    :param type_id: The :cls:`StructType` value related to the instance.
    '''

    def __init__(self, type_id:StructType):
        self.type_id = type_id

    def __repr__(self):
        return f'{type(self).__name__}(type_id={self.type_id!r})'

    def type_ids(self) -> Set[StructType]:
        return set(self.type_id)


class NullType(BuiltInType):
    ''' The null type is trivial and will convert all values into null
    except for the undefined value.
    '''

    def __init__(self):
        super().__init__(StructType.NULL)

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id is not None and obj.type_id != self.type_id:
            return None
        if obj.value is not None:
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        return NULL


class BoolType(BuiltInType):

    def __init__(self):
        super().__init__(StructType.BOOL)

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id is not None and obj.type_id != self.type_id:
            return None
        if not (obj.value is True or obj.value is False):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj)
        elif not isinstance(obj, LiteralARI):
            # Any object reference is truthy
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

    def __init__(self, type_id, dom_min, dom_max):
        super().__init__(type_id)
        self.dom_min = dom_min
        self.dom_max = dom_max

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id is not None and obj.type_id != self.type_id:
            return None
        if not self._in_domain(obj.value):
            return None
        return LiteralARI(obj.value, self.type_id)

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj)
        elif not isinstance(obj, LiteralARI):
            raise TypeError('Cannot convert an object-reference to numeric type')

        if obj.value is False or obj.value is None:
            return LiteralARI(0, self.type_id)
        if obj.value is True:
            return LiteralARI(1, self.type_id)

        if not self._in_domain(obj.value):
            raise ValueError(f'Numeric value outside domain [{self.dom_min},{self.dom_max}]: {obj.value}')
        # force the specific type wanted
        return LiteralARI(
            value=self.VALUE_CLS[self.type_id](obj.value),
            type_id=self.type_id
        )

    def _in_domain(self, value):
        if not isinstance(value, (int, float)):
            return False
        if self.VALUE_CLS[self.type_id] is float:
            if math.isnan(value) or math.isinf(value):
                return True

        return value >= self.dom_min and value <= self.dom_max


class StringType(BuiltInType):

    VALUE_CLS = {
        StructType.TEXTSTR: str,
        StructType.BYTESTR: bytes,
        StructType.LABEL: str,
        StructType.CBOR: bytes,
        StructType.ARITYPE: (str, int),
    }
    ''' Required value type for target string type. '''

    def get(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id is not None and obj.type_id != self.type_id:
            return None
        if not isinstance(obj.value, self.VALUE_CLS[self.type_id]):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj)
        elif not isinstance(obj, LiteralARI):
            raise TypeError(f'Cannot convert to string type: {obj}')

        if obj.type_id is not None and obj.type_id != self.type_id:
            # something besides text string
            raise TypeError
        if not isinstance(obj.value, self.VALUE_CLS[self.type_id]):
            raise TypeError

        return LiteralARI(obj.value, self.type_id)


class TimeType(BuiltInType):
    ''' Times as offsets from absolute or relative epochs. '''

    # FIXME should get and convert normalize to datetime values?
    VALUE_CLS = {
        StructType.TP: (datetime.datetime, int, float),
        StructType.TD: (datetime.timedelta, int, float),
    }
    ''' Required value type for target time type. '''

    def get(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id is not None and obj.type_id != self.type_id:
            return None
        if not isinstance(obj.value, self.VALUE_CLS[self.type_id]):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj)
        elif not isinstance(obj, LiteralARI):
            raise TypeError(f'Cannot convert to numeric type: {obj}')

        if obj.type_id is not None and obj.type_id != self.type_id:
            raise TypeError
        typlist = self.VALUE_CLS[self.type_id]
        if not isinstance(obj.value, typlist):
            raise TypeError

        # coerce to native value class
        newval = obj.value
        if self.type_id == StructType.TP:
            if not isinstance(obj.value, datetime.datetime):
                newval = DTN_EPOCH + datetime.timedelta(seconds=obj.value)
        elif self.type_id == StructType.TD:
            if not isinstance(obj.value, datetime.timedelta):
                newval = datetime.timedelta(seconds=obj.value)

        return LiteralARI(newval, self.type_id)


class ContainerType(BuiltInType):
    ''' ARI containers. '''
    VALUE_CLS = {
        StructType.AC: list,
        StructType.AM: dict,
        StructType.TBL: numpy.ndarray
    }
    ''' Required value type for target time type. '''

    def get(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id is not None and obj.type_id != self.type_id:
            return None
        if not isinstance(obj.value, self.VALUE_CLS[self.type_id]):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj)
        elif not isinstance(obj, LiteralARI):
            raise TypeError(f'Cannot convert to numeric type: {obj}')

        if obj.type_id is not None and obj.type_id != self.type_id:
            # something besides text string
            raise TypeError
        typ = self.VALUE_CLS[self.type_id]
        value = typ(obj.value)

        return LiteralARI(value, self.type_id)


class ObjRefType(BuiltInType):

    def __init__(self, type_id=None):
        super().__init__(type_id)

    def get(self, obj:ARI) -> ARI:
        if not isinstance(obj, ReferenceARI):
            return None
        if self.type_id is not None and obj.ident.type_id != self.type_id:
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ReferenceARI):
            raise TypeError(f'Cannot convert to an object-reference type: {obj}')

        if self.type_id is not None and obj.ident.type_id != self.type_id:
            raise ValueError()
        return obj


class AnyType(BuiltInType):
    ''' Special non-union aggregation built-in types. '''

    VALUE_CLS = {
        StructType.LITERAL: LiteralARI,
        StructType.OBJECT: ReferenceARI,
    }
    ''' Required value type for target time type. '''

    def get(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return None
        typ = self.VALUE_CLS[self.type_id]
        if not isinstance(obj, typ):
            return None
        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        typ = self.VALUE_CLS[self.type_id]
        if not isinstance(obj, typ):
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

    'tp': TimeType(StructType.TP),
    'td': TimeType(StructType.TD),

    'label': StringType(StructType.LABEL),
    'cbor': StringType(StructType.CBOR),
    'aritype': StringType(StructType.ARITYPE),

    'ac': ContainerType(StructType.AC),
    'am': ContainerType(StructType.AM),
    'tbl': ContainerType(StructType.TBL),
}
''' Literal types, including ARI containers. '''
OBJREFS = {
    'typedef': ObjRefType(StructType.TYPEDEF),
    'const': ObjRefType(StructType.CONST),
    'edd': ObjRefType(StructType.EDD),
    'var': ObjRefType(StructType.VAR),
    'ctrl': ObjRefType(StructType.CTRL),
    'oper': ObjRefType(StructType.OPER),
    'sbr': ObjRefType(StructType.SBR),
    'tbr': ObjRefType(StructType.TBR),
}
''' Object reference types. '''
ANY = {
    'literal': AnyType(StructType.LITERAL),
    'object': AnyType(StructType.OBJECT),
}
''' Special reserved types and behavior. '''
BUILTINS = LITERALS | OBJREFS | ANY
''' All builtin types by name. '''
BUILTINS_BY_ENUM = {
    typ.type_id: typ
    for typ in BUILTINS.values()
}
''' Builtin types by enumeration. '''


class SemType(BaseType):
    ''' Base class for all semantic type structures.
    '''


@dataclass
class TypeUse(SemType):
    ''' Use of and optional restriction on an other type. '''

    type_ns:Optional[str] = None
    ''' Module-name of the base type, or None if a built-in type. '''
    type_name:Optional[str] = None
    ''' Name of the :ivar:`base` type to bind to, or None. '''

    base:Optional[BaseType] = None
    ''' The bound type being used. '''

    units:Optional[str] = None
    ''' Optional unit name for this use. '''

    constraints:List[Constraint] = field(default_factory=list)
    ''' Optional value constraints on this use. '''

    def children(self) -> List['BaseType']:
        if self.base:
            return [self.base]
        else:
            return []

    def type_ids(self) -> Set[StructType]:
        return self.base.type_ids()

    def get(self, obj:ARI) -> Optional[ARI]:
        # extract the value before checks
        got = self.base.get(obj)
        if got is not None:
            invalid = self._constrain(got)
            if invalid:
                err = ', '.join(invalid)
                LOGGER.debug('TypeUse.get() invalid constraints: %s', err)
                return None
        return got

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        got = self.base.convert(obj)
        invalid = self._constrain(got)
        if invalid:
            err = ', '.join(invalid)
            raise ValueError(f'TypeUse.convert() invalid constraints: {err}')
        return got

    def _constrain(self, obj:ARI) -> List[str]:
        ''' Check constraints on a value.

        :param obj: The value to check.
        :return: A list of violated constraints.
        '''
        invalid = [
            str(con)
            for con in self.constraints
            if not con.is_valid(obj)
        ]
        return invalid


@dataclass(unsafe_hash=True)
class TypeUnion(SemType):
    ''' A union of other types. '''

    types:Tuple[SemType] = field(default_factory=tuple)
    ''' The underlying types, with significant order. '''

    def children(self) -> List['BaseType']:
        return [typ for typ in self.types]

    def type_ids(self) -> Set[StructType]:
        # set constructor will de-duplicate
        return set([typ.type_ids() for typ in self.types])

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
        if is_undefined(obj):
            return obj

        # try subtype get first then convert as a fallback
        got = self.get(obj)
        if got is not None:
            return got

        for typ in self.types:
            try:
                return typ.convert(obj)
            except (TypeError, ValueError):
                continue

        raise TypeError('convert() failed to match a union type')


@dataclass
class UniformList(SemType):
    ''' A list with uniform-typed items. '''

    base:BaseType
    ''' Type for all items. '''

    min_elements:Optional[int] = None
    ''' Lower limit on the size of the list. '''
    max_elements:Optional[int] = None
    ''' Upper limit on the size of the list. '''

    def children(self) -> List['BaseType']:
        if self.base:
            return [self.base]
        else:
            return []

    def type_ids(self) -> Set[StructType]:
        # only one value type is valid
        return self.base.type_ids()

    def get(self, obj:ARI) -> Optional[ARI]:
        if is_undefined(obj):
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id != StructType.AC:
            return None

        invalid = self._constrain(obj)
        if invalid:
            err = ', '.join(invalid)
            LOGGER.debug('UniformList.get() invalid constraints: %s', err)
            return None

        for val in obj.value:
            if self.base.get(val) is None:
                return None

        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj, type_id=StructType.AC)
        elif not isinstance(obj, LiteralARI):
            raise TypeError()
        if obj.type_id != StructType.AC:
            raise TypeError(f'Value to convert is not AC, it is {obj.type_id.name}')

        invalid = self._constrain(obj)
        if invalid:
            err = ', '.join(invalid)
            raise ValueError(f'UniformList.convert() invalid constraints: {err}')

        rvalue = []
        for ival in obj.value:
            rvalue.append(self.base.convert(ival))

        return LiteralARI(rvalue, StructType.AC)

    def _constrain(self, obj:ARI) -> List[str]:
        ''' Check constraints on the list.
        '''
        invalid = []
        if self.min_elements is not None and len(obj.value) < self.min_elements:
            invalid.append(f'Size of list {len(obj.value)} is smaller than the minimum of {self.min_elements}')
        if self.max_elements is not None and len(obj.value) > self.max_elements:
            invalid.append(f'Size of list {len(obj.value)} is larger than the maximum of {self.max_elements}')
        return invalid


@dataclass
class DiverseSeq:
    ''' A sequence within a :cls:`DiverseList` object. '''

    base:BaseType

    min_elements:int
    ''' Lower limit on the size of the sequence. '''
    max_elements:int
    ''' Upper limit on the size of the sequence. '''


@dataclass
class DiverseList(SemType):
    ''' A list with non-uniform-typed items. '''

    parts:List[Union[BaseType, DiverseSeq]]
    ''' Type for each item or sequence. '''

    def children(self) -> List['BaseType']:
        types = []
        for part in self.parts:
            if isinstance(part, BaseType):
                return types.append(part)
            elif isinstance(part, DiverseSeq):
                return types.append(part.base)
        return types

    def type_ids(self) -> Set[StructType]:
        return set([typeobj.type_ids() for typeobj in self.children()])

    def get(self, obj:ARI) -> Optional[ARI]:
        if is_undefined(obj):
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id != StructType.AC:
            return None

        # mutable copy of the list
        remain = list(obj.value)
        for part in self.parts:
            if isinstance(part, BaseType):
                try:
                    val = remain.pop(0)
                except IndexError:
                    return None
                if part.get(val) is None:
                    return None

            elif isinstance(part, DiverseSeq):
                if len(remain) < part.min_elements:
                    return None
                max_elem = part.max_elements
                got = 0
                while remain and got < max_elem:
                    # attempt a match
                    val = remain[0]
                    if part.base.get(val) is None:
                        break

                    remain.pop(0)
                    got += 1

        if remain:
            # some items not captured
            return None

        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj, type_id=StructType.AC)
        elif not isinstance(obj, LiteralARI):
            raise TypeError()
        if obj.type_id != StructType.AC:
            raise TypeError(f'Value to convert is not AC, it is {obj.type_id.name}')

        rvalue = []
        # mutable copy of the list
        remain = list(obj.value)
        for part in self.parts:
            if isinstance(part, BaseType):
                try:
                    ival = remain.pop(0)
                except IndexError:
                    raise ValueError('list too short for dlist item')
                rvalue.append(part.convert(ival))

            elif isinstance(part, DiverseSeq):
                if len(remain) < part.min_elements:
                    raise ValueError('list too short for dlist sequence')
                max_elem = part.max_elements
                got = 0
                while remain and got < max_elem:
                    # attempt a match
                    val = remain[0]
                    try:
                        rvalue.append(part.base.convert(val))
                    except (TypeError, ValueError):
                        break

                    remain.pop(0)
                    got += 1

        if remain:
            # some items not converted
            raise ValueError('list too long for dlist type')

        return LiteralARI(rvalue, StructType.AC)


@dataclass
class UniformMap(SemType):
    ''' A map with uniform-typed items. '''

    kbase:Optional[BaseType] = None
    ''' Type for all keys. '''
    vbase:Optional[BaseType] = None
    ''' Type for all values. '''

    def children(self) -> List['BaseType']:
        return list(filter(None, [self.kbase, self.vbase]))

    def type_ids(self) -> Set[StructType]:
        return set([typeobj.type_ids() for typeobj in self.children()])

    def get(self, obj:ARI) -> Optional[ARI]:
        if is_undefined(obj):
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id != StructType.AM:
            return None

        for key, val in obj.value.items():
            if self.kbase is not None and self.kbase.get(key) is None:
                return None
            if self.vbase is not None and self.vbase.get(val) is None:
                return None

        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, ARI):
            obj = LiteralARI(value=obj, type_id=StructType.AC)
        elif not isinstance(obj, LiteralARI):
            raise TypeError()
        if obj.type_id != StructType.AM:
            raise TypeError(f'Value to convert is not AM, it is {obj.type_id.name}')

        rvalue = {}
        for key, val in obj.value.items():
            if self.kbase is not None:
                rkey = self.kbase.convert(key)
            else:
                rkey = key
            rkey = LiteralARI(value=rkey.value)  # enforce that AM uses untyped keys

            if self.vbase is not None:
                rval = self.vbase.convert(val)
            else:
                rval = val
            rvalue[rkey] = rval

        return LiteralARI(rvalue, StructType.AM)


@dataclass
class TableColumn:
    ''' Each column of a TableTemplate object. '''

    name:str
    ''' Unique name of this column. '''
    base:BaseType
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

    def children(self) -> List['BaseType']:
        return [col.base for col in self.columns]

    def type_ids(self) -> Set[StructType]:
        # only one value type is valid
        return set([StructType.TBL])

    def get(self, obj:ARI) -> Optional[ARI]:
        if is_undefined(obj):
            return None
        if not isinstance(obj, LiteralARI):
            return None
        if obj.type_id != StructType.TBL:
            return None

        if obj.value.ndim != 2:
            return None
        nrows, ncols = obj.value.shape
        if ncols != len(self.columns):
            return None
        # check each value against column schema
        for row_ix in range(nrows):
            for col_ix, col in enumerate(self.columns):
                if col.base.get(obj.value[row_ix, col_ix]) is None:
                    return None

        return obj

    def convert(self, obj:ARI) -> ARI:
        if is_undefined(obj):
            return obj
        if not isinstance(obj, LiteralARI):
            raise TypeError()
        if obj.type_id != StructType.TBL:
            raise TypeError(f'Value to convert is not TBL, it is {obj.type_id.name}')

        if obj.value.ndim != 2:
            raise ValueError(f'TBL value must be a 2-dimensional array, is {obj.value.ndim}')
        nrows, ncols = obj.value.shape
        if ncols != len(self.columns):
            raise ValueError(f'TBL value has wrong number of columns: should be {len(self.columns)} is {ncols}')

        rvalue = Table(obj.value.shape)
        for row_ix in range(nrows):
            irow = obj.value[row_ix,:]
            badcols = []
            for col_ix, col in enumerate(self.columns):
                try:
                    rvalue[row_ix, col_ix] = col.base.convert(irow[col_ix])
                except Exception as err:
                    LOGGER.warning('Failed to convert col %s %s value %s: %s', col.name, col.base, irow[col_ix], err)
                    badcols.append(col.name)
            if badcols:
                raise ValueError(f'Failed to convert columns {",".join(badcols)} for row {row_ix}: {irow}')

        return LiteralARI(rvalue, StructType.TBL)


def type_walk(root:BaseType) -> Iterator:
    ''' Walk all type objects in a tree,
    ignoring duplicates in cases of circular references.

    :param root: The starting type to walk.
    :return: an iterator over all unique type objects.
    '''

    seen = set()

    def walk(typeobj:BaseType) -> None:
        if id(typeobj) in seen:
            LOGGER.warning('type_walk() already seen %s', typeobj)
            return

        seen.add(id(typeobj))
        yield typeobj

        for child in typeobj.children():
            yield from walk(child)

    yield from walk(root)
