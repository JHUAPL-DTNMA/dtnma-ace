#
# Copyright (c) 2020-2024 The Johns Hopkins University Applied Physics
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
''' The logical data model for an ARI and associated AMP data.
This is distinct from the ORM in :mod:`models` used for ADM introspection.
'''
import math
from dataclasses import dataclass, field
import enum
from typing import List, Optional, Union


@enum.unique
class StructType(enum.IntEnum):
    ''' The enumeration of ADM data types from Section 5.4 of ADM draft.
    '''
    MDAT = -1  # FIXME: not a real type!

    # AMM object types
    CONST = 0
    CTRL = 1
    EDD = 2
    LIT = 3
    MAC = 4
    OPER = 5
#    RPT = 6
    RPTT = 7
    SBR = 8
#    TBL = 9
    TBLT = 10
    TBR = 11
    VAR = 12

    # Primitive data types
    BOOL = 16
    BYTE = 17
    STR = 18  # FIXME: shoudl be TSTR
    INT = 19
    UINT = 20
    VAST = 21
    UVAST = 22
    REAL32 = 23
    REAL64 = 24
    UNK = -25 # not formally defined in ADM spec 

    # Compound types
    TV = 32
    TS = 33
#    TNV = 34
    TNVC = 35
    ARI = 36
    AC = 37
    EXPR = 38
    BSTR = 39  # Really a primitive type


#: All literal struct types
LITERAL_TYPES = {
    StructType.BOOL,
    StructType.BYTE,
    StructType.INT,
    StructType.UINT,
    StructType.VAST,
    StructType.UVAST,
    StructType.REAL32,
    StructType.REAL64,
    StructType.UNK,
    StructType.STR,
    StructType.BSTR,  # FIXME: not really
    StructType.TV,
    StructType.TS,
}

#: Required label struct types
# Those that have ambiguous text encoding
LITERAL_LABEL_TYPES = {
    StructType.BYTE,
    StructType.INT,
    StructType.UINT,
    StructType.VAST,
    StructType.UVAST,
    StructType.REAL32,
    StructType.REAL64,
    StructType.UNK,
    StructType.TV,
    StructType.TS,
}

NUMERIC_LIMITS = {
    StructType.BYTE: (0, 2**8 - 1),
    StructType.INT: (-2**31, 2**31 - 1),
    StructType.UINT: (0, 2**32 - 1),
    StructType.VAST: (-2**63, 2**63 - 1),
    StructType.UVAST: (0, 2**64 - 1),
    # from: numpy.finfo(numpy.float32).max
    StructType.REAL32: (-3.4028235e+38, 3.4028235e+38),
    # from: numpy.finfo(numpy.float32).max
    StructType.REAL64: (-1.7976931348623157e+308, 1.7976931348623157e+308),
    StructType.UNK: (0, 0),
    StructType.TV: (0, 2**64 - 1),
    StructType.TS: (0, 2**64 - 1),
}


class ARI:
    ''' Base class for all forms of ARI. '''


@dataclass
class LiteralARI(ARI):
    ''' A literal value in the form of an ARI.
    '''
    #: ADM type of this value
    type_enum: StructType
    #: Literal value
    value: object

    def check_type(self):
        ''' Validate the :py:attr:`value` against the :py:attr:`type_enum`
        of this object.
        '''
        if self.type_enum == StructType.BOOL:
            if self.value not in (False, True):
                raise ValueError('Literal boolean type without boolean value')
        elif self.type_enum in NUMERIC_LIMITS:
            lim = NUMERIC_LIMITS[self.type_enum]
            if math.isfinite(self.value) and (self.value < lim[0] or self.value > lim[1]):
                raise ValueError('Literal integer vaue outside of valid range')
        elif self.type_enum == StructType.STR:
            if not isinstance(self.value, str):
                raise ValueError('Literal text string with non-text value')
        elif self.type_enum == StructType.BSTR:
            if not isinstance(self.value, bytes):
                raise ValueError('Literal byte string with non-bytes value')


@dataclass
class Identity:
    ''' The identity of a reference ARI as a unique name-set.
    '''

    #: The None value indicates the absense of a URI path component
    namespace: Union[str, int, None] = None
    #: ADM type of the referenced object
    type_enum: Optional[StructType] = None
    #: Name with the type removed
    name: Union[bytes, int, None] = None

    issuer: Optional[bytes] = None
    tag: Optional[bytes] = None

    def strip_name(self):
        ''' If present, strip parameters off of the name portion.
        '''
        if '(' in self.name:
            #FIXME: Big assumptions about structure here, should use ARI text decoder
            self.name,extra = self.name.split('(', 1)
            parms = extra.split(')', 1)[0].split(',')
            return parms
        else:
            return None


@dataclass
class ReferenceARI(ARI):
    ''' The data content of an ARI.
    '''
    #: Identity of the referenced object
    ident: Identity
    #: Optional paramerization, None is different than empty list
    params: List[Union['ARI', 'AC', 'EXPR', 'TNVC']] = None


@dataclass
class AC:
    ''' An ARI Collection (AC).
    '''
    # Ordered list of ARIs
    items: List[Union['ARI', 'AC', 'EXPR']] = field(default_factory=list)


@dataclass
class EXPR:
    ''' An Expression (EXPR).
    '''
    #: ADM type of the result value
    type_enum: StructType
    # RPN expression items
    items: List['ARI'] = field(default_factory=list)


@dataclass
class TNVC:
    ''' A pseudo-class based on ADM requirements, but not representable as text ARI.
    In text form this is really an AC and gets converted by nickname handling.
    '''
    # Ordered list of ARIs
    items: List[Union['ARI', 'AC', 'EXPR']] = field(default_factory=list)
