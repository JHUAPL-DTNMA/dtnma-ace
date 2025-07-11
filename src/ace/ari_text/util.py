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
''' Utilities for text processing.
'''
import base64
import datetime
import logging
import re
from typing import List
import cbor_diag
from ace.ari import UNDEFINED, StructType

LOGGER = logging.getLogger(__name__)


class TypeMatch:
    ''' Container for each literal leaf type.
    '''

    def __init__(self, pattern, parser):
        self.regex = re.compile(pattern)
        self.parser = parser

    @staticmethod
    def apply(pattern):
        ''' Decorator for parsing functions. '''

        def wrap(func):
            return TypeMatch(pattern, func)

        return wrap


class TypeSeq:
    ''' An ordered list of TypeMatch to check against.
    '''

    def __init__(self, matchers:List[TypeMatch]):
        self._matchers = matchers

    def __call__(self, text):
        ''' Apply matchers in order, first one wins and parses. '''
        for obj in self._matchers:
            found = obj.regex.fullmatch(text)
            if found is not None:
                return obj.parser(found)
        raise ValueError(f'No possible literal type matched text: {text}')


@TypeMatch.apply(r'(?i)undefined')
def t_undefined(_found):
    return UNDEFINED.value


@TypeMatch.apply(r'(?i)null')
def t_null(_found):
    return None


@TypeMatch.apply(r'(?i)true|false')
def t_bool(found):
    return (found[0].casefold() == 'true')


@TypeMatch.apply(r'([+-])?(\d*)\.(\d*)')
def t_decfrac(found):
    return float(found[0])


# float either contains a decimal point or exponent or both
@TypeMatch.apply(r'(?i)[+-]?((\d+|\d*\.\d*)([eE][+-]?\d+)|\d*\.\d*|Infinity)|NaN')
def t_float(found):
    return float(found[0])


# float as hex-encoded IEEE-754 binary
@TypeMatch.apply(r'[+-]?0x([0-9a-fA-F]+|[0-9a-fA-F]*\.[0-9a-fA-F]*)[pP]([+-][0-9a-fA-F]+)')
def t_floathex(found):
    return float.fromhex(found[0])


# int is decimal, binary, or hexadecimal
@TypeMatch.apply(r'[+-]?(0[bB][01]+|0[xX][0-9a-fA-F]+|\d+)')
def t_int(found):
    return int(found[0], 0)


@TypeMatch.apply(r'!?[a-zA-Z_][a-zA-Z0-9_\-\.]*')
def t_identity(found):
    return found[0]


@TypeMatch.apply(r'(?P<name>\!?[a-zA-Z_][a-zA-Z0-9_\-\.]*|[+-]?\d+)(@(?P<rev>\d{4}-\d{2}-\d{2}))?')
def t_modseg(found):
    mod_id = found['name']
    if mod_id[0].isdigit() or mod_id[0] in {'+', '-'}:
        mod_id = int(mod_id)

    mod_rev = found['rev']
    if mod_rev is not None:
        mod_rev = datetime.date.fromisoformat(mod_rev)

    return (mod_id, mod_rev)


def unescape(esc:str) -> str:
    ''' unescape tstr/bstr text
    '''
    esc_it = iter(esc)
    txt = ''
    while True:
        try:
            char = next(esc_it)
        except StopIteration:
            break
        if char == '\\':
            char = next(esc_it)
            if char == 'b':
                char = "\b"
            elif char == 'f':
                char = "\f"
            elif char == 'n':
                char = "\n"
            elif char == 'r':
                char = "\r"
            elif char == 't':
                char = "\t"
            elif char == 'u':
                buf = ''
                while len(buf) < 4:
                    try:
                        buf += next(esc_it)
                    except StopIteration:
                        break
                char = decode_unicode(buf)
        txt += char
    return txt


def decode_unicode(hex_str):
    code_point = int(hex_str, 16)
    return chr(code_point)


@TypeMatch.apply(r'"(?P<val>(?:[^"]|\\.)*)"')
def t_tstr(found):
    return unescape(found['val'])


@TypeMatch.apply(r'(?P<enc>h|b64)?\'(?P<val>(?:[^\']|\\.)*)\'')
def t_bstr(found):
    enc = found['enc']
    val = found['val']
    if enc == 'h':
        return base64.b16decode(val, casefold=True)
    elif enc == 'b64':
        rem = len(val) % 4
        if rem in {2, 3}:
            val += '=' * (4 - rem)
        return base64.b64decode(val)
    else:
        return bytes(unescape(val), 'ascii')


@TypeMatch.apply(r'<<.*>>')
def t_cbor_diag(found):
    import cbor2
    data = cbor2.loads(cbor_diag.diag2cbor(found[0]))
    # workaround least-length float encoding from cbor_diag
    val = cbor2.dumps(cbor2.loads(data), canonical=True)
    return val


def part_to_int(digits):
    ''' Convert a text time part into integer, defaulting to zero. '''
    if digits:
        return int(digits)
    else:
        return 0


def subsec_to_microseconds(digits):
    ''' Convert subseconds text into microseconds, defaulting to zero. '''
    if digits:
        usec = int(digits) * 10 ** (6 - len(digits))
    else:
        usec = 0
    return usec


@TypeMatch.apply(r'(?P<yr>\d{4})\-?(?P<mon>\d{2})\-?(?P<dom>\d{2})T(?P<H>\d{2}):?(?P<M>\d{2}):?(?P<S>\d{2})(\.(?P<SS>\d{1,6}))?Z')
def t_timepoint(found):
    value = datetime.datetime(
        year=part_to_int(found.group('yr')),
        month=part_to_int(found.group('mon')),
        day=part_to_int(found.group('dom')),
        hour=part_to_int(found.group('H')),
        minute=part_to_int(found.group('M')),
        second=part_to_int(found.group('S')),
        microsecond=subsec_to_microseconds(found.group('SS'))
    )
    return value


@TypeMatch.apply(r'(?P<sign>[+-])?P((?P<D>\d+)D)?T((?P<H>\d+)H)?((?P<M>\d+)M)?((?P<S>\d+)(\.(?P<SS>\d{1,6}))?S)?')
def t_timeperiod(found):
    neg = found.group('sign') == '-'
    day = part_to_int(found.group('D'))
    hour = part_to_int(found.group('H'))
    minute = part_to_int(found.group('M'))
    second = part_to_int(found.group('S'))
    usec = subsec_to_microseconds(found.group('SS'))
    value = datetime.timedelta(
        days=day,
        hours=hour,
        minutes=minute,
        seconds=second,
        microseconds=usec
    )
    if neg:
        value = -value
    return value


IDSEGMENT = TypeSeq([t_int, t_identity])
''' Either an integer or identity text. '''

MODSEGMENT = TypeSeq([t_modseg])
''' Model namespace segment as a tuple of ID and revision. '''

SINGLETONS = TypeSeq([
    t_undefined,
    t_null,
    t_bool,
])
''' Types that match singleton values. '''


def get_structtype(text:str) -> StructType:
    value = IDSEGMENT(text)
    if isinstance(value, int):
        return StructType(value)
    else:
        return StructType[value.upper()]


PRIMITIVE = TypeSeq([
    t_undefined,
    t_null,
    t_bool,
    t_float, t_floathex,
    t_int,
    t_identity, t_tstr,
    t_bstr
])
''' Any untyped literal value '''

TYPEDLIT = {
    StructType.NULL: TypeSeq([t_null]),
    StructType.BOOL: TypeSeq([t_bool]),
    StructType.BYTE: TypeSeq([t_int]),
    StructType.INT: TypeSeq([t_int]),
    StructType.UINT: TypeSeq([t_int]),
    StructType.VAST: TypeSeq([t_int]),
    StructType.UVAST: TypeSeq([t_int]),
    StructType.REAL32: TypeSeq([t_float, t_floathex]),
    StructType.REAL64: TypeSeq([t_float, t_floathex]),
    StructType.TEXTSTR: TypeSeq([t_identity, t_tstr]),
    StructType.BYTESTR: TypeSeq([t_bstr]),
    StructType.TP: TypeSeq([t_timepoint, t_decfrac, t_int]),
    StructType.TD: TypeSeq([t_timeperiod, t_decfrac, t_int]),
    StructType.LABEL: TypeSeq([t_identity, t_int]),
    StructType.CBOR: TypeSeq([t_bstr, t_cbor_diag]),
    StructType.ARITYPE: get_structtype,
}
''' Map from literal types to value parsers. '''

AMKEY = TypeSeq([t_int, t_identity, t_tstr])
''' Allowed AM key literals. '''

STRUCTKEY = TypeSeq([t_identity])
''' Keys of struct parameters '''
