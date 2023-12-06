#
# Copyright (c) 2023 The Johns Hopkins University Applied Physics
# Laboratory LLC.
#
# This file is part of the Asynchronous Network Managment System (ANMS).
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
# This work was performed for the Jet Propulsion Laboratory, California
# Institute of Technology, sponsored by the United States Government under
# the prime contract 80NM0018D0004 between the Caltech and NASA under
# subcontract 1658085.
#
''' The logical data model for an ARI and associated AMP data.
This is distinct from the ORM in :mod:`models` used for ADM introspection.
'''
import datetime
import math
from dataclasses import dataclass
import enum
from typing import List, Dict, Optional, Union
import cbor2

DTN_EPOCH = datetime.datetime(2000, 1, 1, 0, 0, 0)
''' Reference for absolute time points '''


@dataclass(eq=True, frozen=True)
class ExecutionSet:
    ''' Internal representation of Execution-Set data. '''
    nonce:Union[None, int, bytes]
    ''' Optional nonce value '''
    targets:List['ARI']
    ''' The targets to execute '''


@dataclass(eq=True, frozen=True)
class Report:
    ''' Internal representation of Report data. '''
    rel_time:datetime.timedelta
    source:'ARI'
    items:List['ARI']


@dataclass(eq=True, frozen=True)
class ReportSet:
    ''' Internal representation of Report-Set data. '''
    nonce:Union[None, int, bytes]
    ''' Optional nonce value '''
    ref_time:datetime.datetime
    reports:List['Report']
    ''' The contained Reports '''


@enum.unique
class StructType(enum.IntEnum):
    ''' The enumeration of ADM data types from Section 10.3 of ARI draft.
    '''
    # Primitive types
    NULL = 0
    BOOL = 1
    BYTE = 2
    INT = 4
    UINT = 5
    VAST = 6
    UVAST = 7
    REAL32 = 8
    REAL64 = 9
    TEXTSTR = 10
    BYTESTR = 11
    # Compound types
    TP = 12
    TD = 13
    LABEL = 14
    CBOR = 15
    LITTYPE = 16
    # ARI containers
    AC = 17
    AM = 18
    # Specialized containers
    EXECSET = 19
    RPTSET = 20

    # AMM object types
    CONST = -2
    CTRL = -3
    EDD = -4
    OPER = -6
    SBR = -8
    TBR = -10
    VAR = -11
    TYPEDEF = -12


# All literal struct types
LITERAL_TYPES = {
    typ for typ in StructType
    if typ.value >= 0
}

# Required label struct types
# Those that have ambiguous text encoding
LITERAL_LABEL_TYPES = {
    StructType.BYTE,
    StructType.INT,
    StructType.UINT,
    StructType.VAST,
    StructType.UVAST,
    StructType.REAL32,
    StructType.REAL64,
    StructType.TP,
    StructType.TD,
}

NUMERIC_LIMITS = {
    StructType.BYTE: (0, 2 ** 8 - 1),
    StructType.INT: (-2 ** 31, 2 ** 31 - 1),
    StructType.UINT: (0, 2 ** 32 - 1),
    StructType.VAST: (-2 ** 63, 2 ** 63 - 1),
    StructType.UVAST: (0, 2 ** 64 - 1),
    # from: numpy.finfo(numpy.float32).max
    StructType.REAL32: (-3.4028235e+38, 3.4028235e+38),
    # from: numpy.finfo(numpy.float32).max
    StructType.REAL64: (-1.7976931348623157e+308, 1.7976931348623157e+308),
}
''' Valid domains for numeric literal values. '''


class ARI:
    ''' Base class for all forms of ARI. '''


@dataclass(eq=True, frozen=True)
class LiteralARI(ARI):
    ''' A literal value in the form of an ARI.
    '''
    value: object
    ''' Literal value specific to :attr:`type_enum` '''
    type_enum: Union[StructType, None] = None
    ''' ADM type of this value '''

    @staticmethod
    def coerce(value, type_enum:Union[StructType, None]):
        ''' Coerce a value based on a desired type.

        :param value: The value provided.
        :param type_enum: The desired type of the literal.
        '''
        if type_enum == StructType.BOOL:
            if value not in (False, True):
                raise ValueError(f'Literal boolean type with non-boolean value: {value!r}')
        elif type_enum in NUMERIC_LIMITS:
            lim = NUMERIC_LIMITS[type_enum]
            if math.isfinite(value) and (value < lim[0] or value > lim[1]):
                raise ValueError(f'Literal integer outside of valid range {lim}, value: {value!r}')
        elif type_enum == StructType.TEXTSTR:
            if not isinstance(value, str):
                raise ValueError(f'Literal text string with non-text value: {value!r}')
        elif type_enum == StructType.BYTESTR:
            if not isinstance(value, bytes):
                raise ValueError(f'Literal byte string with non-bytes value: {value!r}')
        elif type_enum == StructType.AC:
            try:
                value = list(value)
            except TypeError:
                raise ValueError(f'Literal AC with non-array value: {value!r}')
        elif type_enum == StructType.AM:
            try:
                value = dict(value)
            except TypeError:
                raise ValueError(f'Literal AM with non-map value: {value!r}')
        elif type_enum == StructType.TP:
            if isinstance(value, (int, float)):
                value = DTN_EPOCH + datetime.timedelta(seconds=value)
        elif type_enum == StructType.TD:
            if isinstance(value, (int, float)):
                value = datetime.timedelta(seconds=value)
        elif type_enum == StructType.LABEL:
            if not isinstance(value, str):
                raise ValueError(f'LABEL with non-text value: {value!r}')
        elif type_enum == StructType.CBOR:
            if not isinstance(value, bytes):
                raise ValueError(f'CBOR with non-bytes value: {value!r}')

        return LiteralARI(value=value, type_enum=type_enum)


UNDEFINED = LiteralARI(value=cbor2.undefined)
''' The undefined value of the AMM '''
NULL = LiteralARI(value=None)
''' The null value of the AMM '''

TRUE = LiteralARI(value=True)
''' The true value of the AMM '''
FALSE = LiteralARI(value=False)
''' The false value of the AMM '''


def coerce_literal(val):
    ''' Coerce a Python value into a Literal ARI

    :param val: The Python value.
    :return: The ARI value.
    '''
    import copy
    if isinstance(val, LiteralARI):
        val = copy.copy(val)
    else:
        if isinstance(val, (tuple, list)):
            return LiteralARI(value=val, type_enum=StructType.AC)
        elif isinstance(val, dict):
            return LiteralARI(value=val, type_enum=StructType.AM)
        else:
            return LiteralARI(value=val)

    # Recurse for containers
    if val.type_enum == StructType.AC:
        val.value = map(coerce_literal, val.value)
    elif val.type_enum == StructType.AM:
        val.value = {
            coerce_literal(key): coerce_literal(subval)
            for key, subval in val.items()
        }


@dataclass(eq=True, frozen=True)
class Identity:
    ''' The identity of a reference ARI as a unique name-set.
    '''

    namespace: Union[str, int, None] = None
    ''' The None value indicates the absense of a URI path component '''
    type_enum: Optional[StructType] = None
    ''' ADM type of the referenced object '''
    name: Union[str, int, None] = None
    ''' Name with the type removed '''

    def strip_name(self):
        ''' If present, strip parameters off of the name portion.
        '''
        if '(' in self.name:
            # FIXME: Big assumptions about structure here, should use ARI text decoder
            self.name, extra = self.name.split('(', 1)
            parms = extra.split(')', 1)[0].split(',')
            return parms
        else:
            return None


@dataclass(eq=True, frozen=True)
class ReferenceARI(ARI):
    ''' The data content of an ARI.
    '''
    ident: Identity
    ''' Identity of the referenced object '''
    params: Union[List[ARI], None] = None
    ''' Optional paramerization, None is different than empty list '''
