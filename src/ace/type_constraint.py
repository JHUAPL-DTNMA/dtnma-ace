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
from dataclasses import dataclass
import re
from typing import Optional, Set, Dict
import cbor2
import portion
from sqlalchemy.orm.session import object_session
from .ari import StructType, ARI, ReferenceARI
from .typing import Constraint
from .lookup import dereference
from .models import Ident


class IntInterval(portion.AbstractDiscreteInterval):
    ''' An integer-domain interval class '''
    _step = 1


apiIntInterval = portion.create_api(IntInterval)
''' Utility functions for :py:cls:`IntInterval` '''


@dataclass
class StringLength(Constraint):
    ''' Limit the length of string values.
    For textstr this is a count of characters, for bytestr this is a
    count of bytes.
    '''

    ranges: portion.Interval
    ''' The Interval representing valid lengths. '''

    def applicable(self) -> Set[StructType]:
        return set([StructType.TEXTSTR, StructType.BYTESTR, StructType.CBOR])

    def is_valid(self, obj: ARI) -> bool:
        if isinstance(obj.value, (str, bytes)):
            return len(obj.value) in self.ranges
        else:
            return False


@dataclass
class TextPattern(Constraint):
    ''' Limit the content of text string values.
    '''

    pattern: str
    ''' The regular expression pattern. '''

    def applicable(self) -> Set[StructType]:
        return set([StructType.TEXTSTR])

    def is_valid(self, obj: ARI) -> bool:
        if isinstance(obj.value, (str, bytes)):
            got = re.fullmatch(self.pattern, obj.value)
            return got is not None
        else:
            return False


@dataclass
class NumericRange(Constraint):
    ''' Limit the range of numeric values.
    '''

    ranges: portion.Interval
    ''' The Interval representing valid ranges, integers or floats. '''

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

    def is_valid(self, obj: ARI) -> bool:
        if isinstance(obj.value, (int, float)):
            return obj.value in self.ranges
        else:
            return False


@dataclass
class IntegerEnums(Constraint):
    ''' Named enumerated values.
    '''

    values: Dict[int, str]
    ''' Named values. '''

    def as_value_range(self) -> IntInterval:
        ''' Convert the valid set of values into an numeric range,
        ignoring names.
        '''
        accum = IntInterval()
        for val in self.values.keys():
            accum |= apiIntInterval.singleton(val)
        return accum

    def applicable(self) -> Set[StructType]:
        return set([
            StructType.BYTE,
            StructType.INT,
            StructType.UINT,
            StructType.VAST,
            StructType.UVAST,
        ])

    def is_valid(self, obj: ARI) -> bool:
        if isinstance(obj.value, int):
            return obj.value in self.values
        else:
            return False


@dataclass
class IntegerBits(Constraint):
    ''' Label enumerated values and bit positions.
    '''

    positions: Dict[int, str]
    ''' Named bit positions. '''
    mask: int
    ''' Mask for all named bits. '''

    def applicable(self) -> Set[StructType]:
        return set([
            StructType.BYTE,
            StructType.INT,
            StructType.UINT,
            StructType.VAST,
            StructType.UVAST,
        ])

    def is_valid(self, obj: ARI) -> bool:
        if isinstance(obj.value, int):
            # no unknown bits
            return (obj.value & ~self.mask) == 0
        else:
            return False


@dataclass
class CborCddl(Constraint):
    ''' CDDL pattern for embedded CBOR item.
    '''

    text: str
    ''' CDDL expression. '''

    def applicable(self) -> Set[StructType]:
        return set([StructType.CBOR])

    def is_valid(self, obj: ARI) -> bool:
        if isinstance(obj.value, bytes):
            try:
                cbor2.loads(obj.value)
            except cbor2.CBORDecodeError:
                return False
            return True  # FIXME: interpret CDDL
        else:
            return False


@dataclass
class IdentRefBase(Constraint):
    ''' Limit the base of Ident object references.
    '''

    base_text: str
    ''' Original required base text. '''
    base_ari: ReferenceARI
    ''' The  base object reference. '''
    base_ident: Optional[Ident] = None
    ''' ADM object lookup session '''

    def applicable(self) -> Set[StructType]:
        return set([StructType.IDENT])

    def is_valid(self, obj: ARI) -> bool:
        if isinstance(obj, ReferenceARI) and obj.ident.type_id == StructType.IDENT:
            if self.base_ident is None:
                return False
            db_sess = object_session(self.base_ident)

            def match_base(ref: ARI):
                print('check base', ref)
                try:
                    got_ident = dereference(ref, db_sess)
                except TypeError:
                    got_ident = None
                if got_ident is None:
                    return False
                if got_ident.id == self.base_ident.id:
                    return True

                for sub_base in got_ident.bases:
                    if match_base(sub_base.base_ari):
                        return True

            return match_base(obj)

        return False
