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
''' The logical data model for an ARI Pattern.
This is distinct from the encoded forms of a pattern.
'''

from dataclasses import dataclass, field
import enum
import re
from typing import Dict, List, Optional, Set, Union
import cbor2
import portion
from .ari import ARI, ReferenceARI, StructType


class ARIPattern:
    ''' Base class for all forms of ARI Pattern. '''

    def is_match(self, val: ARI) -> bool:
        ''' Determine if an ARI value matches this pattern.

        :param func: The callable visitor for each type object.
        '''
        raise NotImplementedError


@dataclass
class ComponentPattern:
    ''' Pattern for one reference identifier component. '''

    text: Optional[Set[str]] = None
    ''' Match specific text labels '''
    enum: Optional[portion.Interval] = None
    ''' Match specific integer range '''
    special: Optional[bool] = None
    ''' The True value indicates match-all wildcard. '''

    def is_match(self, id_val: Union[str, int, None]) -> bool:
        ''' Determine if one component matches this pattern. '''
        if self.special is True:
            return id_val is not None
        elif self.text is not None:
            return id_val in self.text
        elif self.enum is not None:
            try:
                return id_val in self.enum
            except TypeError:
                return False
        else:
            return id_val is None


@dataclass
class ReferenceARIPattern(ARIPattern):
    ''' Pattern for matching object reference ARIs. '''

    org_id: ComponentPattern = field(default_factory=ComponentPattern)
    model_id: ComponentPattern = field(default_factory=ComponentPattern)
    type_id: ComponentPattern = field(default_factory=ComponentPattern)
    obj_id: ComponentPattern = field(default_factory=ComponentPattern)

    def is_match(self, val: ARI) -> bool:
        if not isinstance(val, ReferenceARI):
            return False
        return (
            self.org_id.is_match(val.ident.org_id)
            and self.model_id.is_match(val.ident.model_id)
            and self.type_id.is_match(val.ident.type_id)
            and self.obj_id.is_match(val.ident.obj_id)
        )


def from_cbor(data: bytes) -> ARIPattern:
    ''' Decode from a binary form of ARI Pattern '''
    items = cbor2.loads(data)
    if len(items) == 4:
        return ReferenceARIPattern(
            org_id=_comp_from_cbor(items[0]),
            model_id=_comp_from_cbor(items[1]),
            type_id=_comp_from_cbor(items[2]),
            obj_id=_comp_from_cbor(items[3]),
        )
    else:
        raise ValueError('invalid input')


def _comp_from_cbor(item) -> ComponentPattern:
    if item is True:
        return ComponentPattern(special=True)
    elif item is None:
        return ComponentPattern()

    textset = None
    accum = None

    if isinstance(item, int):
        accum = portion.singleton(item)
    elif isinstance(item, str):
        textset = set([item])
    elif isinstance(item[0], int):
        curs = 0
        accum = portion.empty()
        while item:
            start = curs + item.pop(0)
            length = item.pop(0)
            end = start + length
            if length == 1:
                accum = accum | portion.singleton(start)
            else:
                accum = accum | portion.closedopen(start, end)
            curs = end
    elif isinstance(item[0], str):
        textset = frozenset(item)

    if textset is not None:
        return ComponentPattern(text=textset)
    elif accum is not None:
        return ComponentPattern(enum=accum)
    else:
        raise TypeError


def to_cbor(pat: ARIPattern) -> bytes:
    ''' Encode to binary form of ARI Pattern. '''
    if isinstance(pat, ReferenceARIPattern):
        items = list(map(_comp_to_cbor, [pat.org_id, pat.model_id, pat.type_id, pat.obj_id]))
        return cbor2.dumps(items)
    else:
        raise TypeError


def _comp_to_cbor(pat: ComponentPattern) -> object:
    if pat.special is True:
        return True
    elif pat.text is not None:
        items = list(pat.text)
        if len(items) == 1:
            items = items[0]
        return items
    elif pat.enum is not None:
        # only singletons have closed right side
        if pat.enum.atomic and pat.enum.right == portion.CLOSED:
            return pat.enum.lower
        else:
            curs = 0
            offsets = []
            for intvl in pat.enum:
                offsets += [intvl.lower - curs, intvl.upper - intvl.lower]
                curs = intvl.upper
            return offsets
    else:
        return None


NSREF_PAT = re.compile(r'^(?:ari:)?//([^/]+)/([^/]+)/$')
OBJREF_PAT = re.compile(r'^(?:ari:)?//([^/]+)/([^/]+)/([^/]+)/([^/]+)$')
''' From the ARI Pattern `objref-pat` rule '''
ID_RANGE_PAT = re.compile(r'^\[(.+)\]$')
''' From the ARI Pattern `id-range` rule '''
ID_TEXT_PAT = re.compile(r'^[a-zA-Z_][a-zA-Z_\-\.]*$')
''' From the ARI `id-text` rule '''


def from_text(text: str) -> ARIPattern:
    ''' Decode from a text form of ARI Pattern '''
    nsref_match = NSREF_PAT.match(text)
    if nsref_match is not None:
        return ReferenceARIPattern(
            org_id=_comp_from_text(nsref_match.group(1)),
            model_id=_comp_from_text(nsref_match.group(2)),
        )
    objref_match = OBJREF_PAT.match(text)
    if objref_match is not None:
        return ReferenceARIPattern(
            org_id=_comp_from_text(objref_match.group(1)),
            model_id=_comp_from_text(objref_match.group(2)),
            type_id=_comp_from_text(objref_match.group(3), StructType),
            obj_id=_comp_from_text(objref_match.group(4)),
        )
    else:
        raise ValueError('invalid input')


def _comp_from_text(text: str, ecls: Optional[enum.IntEnum] = None) -> ComponentPattern:
    if text == '*':
        return ComponentPattern(special=True)

    textset = None
    accum = None

    range_match = ID_RANGE_PAT.match(text)
    if range_match is not None:
        for part in range_match.group(1).split(','):
            id_text_match = ID_TEXT_PAT.match(part)
            if id_text_match is not None:
                if accum:
                    raise ValueError('Cannot mix text and integer range')
                if textset is None:
                    textset = set()
                textset.add(part)
            else:
                if textset:
                    raise ValueError('Cannot mix text and integer range')
                if accum is None:
                    accum = portion.empty()
                if '..' in part:
                    start, last = map(int, part.split('..'))
                    accum = accum | portion.closedopen(start, last + 1)
                else:
                    accum = accum | portion.singleton(int(part))
    else:
        id_text_match = ID_TEXT_PAT.match(text)
        if id_text_match is not None:
            textset = set([text])
        else:
            accum = portion.singleton(int(text))

    # special case preference for integers
    if textset and ecls:
        accum = portion.empty()
        for text in textset:
            try:
                accum = accum | portion.singleton(ecls[text])
            except KeyError:
                accum = None
                break
        if accum is not None:
            textset = None

    if textset:
        return ComponentPattern(text=textset)
    elif accum:
        return ComponentPattern(enum=accum)
    else:
        raise TypeError


def to_text(pat: ARIPattern) -> str:
    ''' Encode to text form of ARI Pattern. '''
    if isinstance(pat, ReferenceARIPattern):
        comps = list(map(_comp_to_text, [pat.org_id, pat.model_id, pat.type_id, pat.obj_id]))
        if comps[2] is None:
            return 'ari://' + '/'.join(comps[0:2]) + '/'
        else:
            return 'ari://' + '/'.join(comps)
    else:
        raise TypeError


def _comp_to_text(pat: ComponentPattern) -> str:
    if pat.special is True:
        return '*'

    parts = []
    if pat.text is not None:
        parts = sorted(list(pat.text))
    elif pat.enum is not None:
        for intvl in pat.enum:
            # only singletons have closed right side
            if intvl.right == portion.CLOSED:
                parts.append(str(intvl.lower))
            else:
                last = intvl.upper - 1
                parts.append(f'{intvl.lower}..{last}')
    else:
        return None

    if len(parts) == 1:
        return parts[0]
    else:
        return '[' + ','.join(parts) + ']'
