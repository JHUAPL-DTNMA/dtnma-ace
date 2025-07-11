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
''' The logical data model for an ARI and associated AMP data.
This is distinct from the ORM in :mod:`models` used for ADM introspection.
'''
import datetime
from dataclasses import dataclass
import enum
import math
from typing import Callable, Dict, List, Optional, Tuple, Union
import cbor2
import numpy

DTN_EPOCH = datetime.datetime(2000, 1, 1, 0, 0, 0)
''' Reference for absolute time points '''


class Table(numpy.ndarray):
    ''' Wrapper class to overload some numpy behavior. '''

    def __new__(self, shape:tuple):
        return super().__new__(self, shape, dtype=ARI)

    def __eq__(self, other:'Table'):
        return numpy.array_equal(self, other)

    @staticmethod
    def from_rows(rows:List[List]) -> 'Table':
        ''' Construct and initialize a table from a list of rows.

        :param rows: A row-major list of lists.
        :return: A new Table object.
        '''
        if rows:
            shape = (len(rows), len(rows[0]))
        else:
            shape = (0, 0)
        obj = Table(shape)
        for row_ix, row in enumerate(rows):
            obj[row_ix,:] = row
        return obj


@dataclass(eq=True, frozen=True)
class ExecutionSet:
    ''' Internal representation of Execution-Set data. '''
    nonce:'LiteralARI'
    ''' Optional nonce value '''
    targets:List['ARI']
    ''' The targets to execute '''


@dataclass(eq=True, frozen=True)
class Report:
    ''' Internal representation of Report data. '''
    rel_time:datetime.timedelta
    ''' Time of the report relative to the parent :ivar:`ReportSet.ref_time`
    value. '''
    source:'ARI'
    ''' Source of the report, either a RPTT or CTRL. '''
    items:List['ARI']
    ''' Items of the report. '''


@dataclass
class ReportSet:
    ''' Internal representation of Report-Set data. '''
    nonce:'LiteralARI'
    ''' Optional nonce value '''
    ref_time:datetime.datetime
    ''' The reference time for all contained Report relative-times. '''
    reports:List['Report']
    ''' The contained Reports '''


@enum.unique
class StructType(enum.IntEnum):
    ''' The enumeration of ARI value types from Section 10.3 of ARI draft.
    '''
    LITERAL = 255
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
    # Complex types
    TP = 12
    TD = 13
    LABEL = 14
    CBOR = 15
    ARITYPE = 16
    # ARI containers
    AC = 17
    AM = 18
    TBL = 19
    # Specialized containers
    EXECSET = 20
    RPTSET = 21

    OBJECT = -256
    NAMESPACE = -255
    # AMM object types
    TYPEDEF = -12
    IDENT = -1
    CONST = -2
    EDD = -4
    VAR = -11
    CTRL = -3
    OPER = -6
    SBR = -8
    TBR = -10


class ARI:
    ''' Base class for all forms of ARI. '''

    def visit(self, visitor:Callable[['ARI'], None]) -> None:
        ''' Call a visitor on this ARI and each child ARI.

        The base type calls the visitor on itself, so only composing types
        need to override this function.

        :param visitor: The callable visitor for each type object.
        '''
        visitor(self)

    def map(self, func:Callable[['ARI'], 'ARI']) -> 'ARI':
        ''' Call a mapping on this ARI (after each child ARI if present).

        :param func: The callable visitor for each type object.
        '''
        raise NotImplementedError


@dataclass(eq=True, frozen=True)
class LiteralARI(ARI):
    ''' A literal value in the form of an ARI.
    '''
    value:object = cbor2.undefined
    ''' Literal value specific to :attr:`type_id` '''
    type_id:Optional[StructType] = None
    ''' ADM type of this value '''

    def __eq__(self, other:'LiteralARI') -> bool:
        # check attributes in specific order
        return (
            isinstance(other, LiteralARI)
            and self.type_id == other.type_id
            and (
                (self.value == other.value)
                or (math.isnan(self.value) and math.isnan(other.value))
            )
        )

    def visit(self, visitor:Callable[['ARI'], None]) -> None:
        if isinstance(self.value, list):
            for item in self.value:
                item.visit(visitor)
        elif isinstance(self.value, dict):
            for key, item in self.value.items():
                key.visit(visitor)
                item.visit(visitor)
        elif isinstance(self.value, Table):
            func = lambda item: item.visit(visitor)
            numpy.vectorize(func)(self.value)
        super().visit(visitor)

    def map(self, func:Callable[['ARI'], 'ARI']) -> 'ARI':
        lfunc = lambda item: item.map(func)

        result = None
        if isinstance(self.value, list):
            rvalue = list(map(lfunc, self.value))
            result = LiteralARI(rvalue, self.type_id)

        elif isinstance(self.value, dict):
            rvalue = {
                lfunc(key): lfunc(val)
                for key, val in self.value.items()
            }
            result = LiteralARI(rvalue, self.type_id)

        elif isinstance(self.value, Table):
            rvalue = numpy.vectorize(lfunc)(self.value)
            result = LiteralARI(rvalue, self.type_id)

        elif isinstance(self.value, ExecutionSet):
            rtargets = list(map(lfunc, self.value.targets))
            rvalue = ExecutionSet(
                nonce=self.value.nonce,
                targets=rtargets
            )
            result = LiteralARI(rvalue, self.type_id)

        elif isinstance(self.value, ReportSet):
            rpt_func = lambda ireport: Report(
                rel_time=ireport.rel_time,
                source=lfunc(ireport.source),
                items=list(map(lfunc, ireport.items))
            )
            rreports = list(map(rpt_func, self.value.reports))
            rvalue = ReportSet(
                nonce=self.value.nonce,
                ref_time=self.value.ref_time,
                reports=rreports,
            )
            result = LiteralARI(rvalue, self.type_id)

        else:
            result = self

        return func(result)


UNDEFINED = LiteralARI(value=cbor2.undefined)
''' The undefined value of the AMM '''
NULL = LiteralARI(value=None, type_id=StructType.NULL)
''' The null value of the AMM '''

TRUE = LiteralARI(value=True, type_id=StructType.BOOL)
''' The true value of the AMM '''
FALSE = LiteralARI(value=False, type_id=StructType.BOOL)
''' The false value of the AMM '''


def is_undefined(val:ARI) -> bool:
    ''' Logic to compare against the UNDEFINED value.

    :param val: The value to check.
    :return: True if equivalent to :obj:`UNDEFINED`.
     '''
    return (
        isinstance(val, LiteralARI)
        and val.value == UNDEFINED.value
    )


def is_null(val:ARI) -> bool:
    ''' Logic to compare against the NULL value.

    :param val: The value to check.
    :return: True if equivalent to :obj:`NULL`.
     '''
    return (
        isinstance(val, LiteralARI)
        and val.value == NULL.value
    )


def as_bool(val:ARI) -> bool:
    if isinstance(val, LiteralARI) and val.value in (True, False):
        return val.value
    raise ValueError('as_bool given non-boolean value')


@dataclass(frozen=True)
class Identity:
    ''' The identity of an object reference as a unique identifer-set.
    '''

    org_id:Union[str, int, None] = None
    ''' The None value indicates an org-relative path. '''
    model_id:Union[str, int, None] = None
    ''' The None value indicates an model-relative path. '''
    model_rev:Optional[datetime.date] = None
    ''' For the text-form ARI a specific ADM revision date. '''
    type_id:Optional[StructType] = None
    ''' ADM type of the referenced object '''
    obj_id:Union[str, int, None] = None
    ''' Name with the type removed '''

    @property
    def ns_id(self) -> Tuple:
        ''' Get a tuple representing the namespace. '''
        return (self.org_id, self.model_id, self.model_rev)

    @property
    def module_name(self) -> Optional[str]:
        ''' Get the ADM module name associated with this namespace. '''
        if self.org_id is None or self.model_id is None:
            return None
        return f'{self.org_id}-{self.model_id}'

    def __str__(self) -> str:
        ''' Pretty format the identity similar to URI text encoding.
        '''
        text = ''
        if self.org_id is None:
            if self.model_id is None:
                text += '.'
            else:
                text += '..'
        else:
            text += f'/{self.org_id}'
        if self.model_id is not None:
            text += f'/{self.model_id}'
        if self.model_rev:
            text += f'@{self.model_rev}'
        text += f'/{self.type_id.name}'
        text += f'/{self.obj_id}'
        return text


@dataclass
class ReferenceARI(ARI):
    ''' The data content of an ARI.
    '''
    ident: Identity
    ''' Identity of the referenced object '''
    params: Union[List[ARI], Dict[LiteralARI, ARI], None] = None
    ''' Optional paramerization, None is different than empty list '''

    def visit(self, visitor:Callable[['ARI'], None]) -> None:
        if isinstance(self.params, list):
            for val in self.params:
                val.visit(visitor)
        elif isinstance(self.params, dict):
            for key, val in self.params.items():
                key.visit(visitor)
                val.visit(visitor)
        super().visit(visitor)

    def map(self, func:Callable[['ARI'], 'ARI']) -> 'ARI':
        lfunc = lambda item: item.map(func)

        rparams = None
        if isinstance(self.params, list):
            rparams = list(map(lfunc, self.params))
        elif isinstance(self.params, dict):
            rparams = {
                lfunc(key): lfunc(val)
                for key, val in self.params.items()
            }

        result = ReferenceARI(self.ident, rparams)
        return func(result)
