''' Utilities for text processing.
'''
import base64
import datetime
import logging
import re
import struct
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


@TypeMatch.apply(r'undefined')
def t_undefined(_found):
    return UNDEFINED.value


@TypeMatch.apply(r'null')
def t_null(_found):
    return None


@TypeMatch.apply(r'true|false')
def t_bool(found):
    return (found[0] == 'true')


@TypeMatch.apply(r'([+-])?(\d*)\.(\d*)')
def t_decfrac(found):
    return float(found[0])


# float either contains a decimal point or exponent or both
@TypeMatch.apply(r'[+-]?((\d+|\d*\.\d*)([eE][+-]?\d+)|\d*\.\d*|Infinity)|NaN')
def t_float(found):
    return float(found[0])


FLOAT_FORM = {
    2: '!e',
    4: '!f',
    8: '!d',
}
''' Map from IEEE-754 encoded size and `struct` format char. '''


# float as hex-encoded IEEE-754 binary
@TypeMatch.apply(r'(?P<sign>[+-])?0fx(?P<raw>[0-9a-fA-F]+)')
def t_floatraw(found):
    neg = found.group('sign') == '-'
    data = base64.b16decode(found['raw'], casefold=True)

    try:
        form = FLOAT_FORM[len(data)]
    except KeyError:
        raise ValueError('Raw floating point is not sized to 2, 4, or 8 bytes')
    val = struct.unpack(form, data)[0]
    if neg:
        val = -val
    return val


# int is decimal, binary, or hexadecimal
@TypeMatch.apply(r'[+-]?(0b[01]+|0x[0-9a-fA-F]+|\d+)')
def t_int(found):
    return int(found[0], 0)


@TypeMatch.apply(r'[a-zA-Z_][a-zA-Z0-9_\-\.]*')
def t_identity(found):
    return found[0]


@TypeMatch.apply(r'(?P<name>\!?[a-zA-Z_][a-zA-Z0-9_\-\.]*)(@(?P<rev>\d{4}-\d{2}-\d{2}))?')
def t_modid(found):
    return (found['name'], found['rev'])


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
        txt += char
    return txt


@TypeMatch.apply(r'"(?P<val>(?:[^"]|\\.)*)"')
def t_tstr(found):
    return unescape(found['val'])


@TypeMatch.apply(r'(?P<enc>h|b32|h32|b64)?\'(?P<val>(?:[^\']|\\.)*)\'')
def t_bstr(found):
    enc = found['enc']
    val = found['val']
    if enc == 'h':
        return base64.b16decode(val, casefold=True)
    elif enc == 'b32':
        rem = len(val) % 8
        if rem in {2, 4, 5, 7}:
            val += '=' * (8 - rem)
        return base64.b32decode(val, casefold=True)
    elif enc == 'h32':
        raise NotImplementedError
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
    LOGGER.debug('TP %s', found.groups())
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
    LOGGER.debug('TD %s', found.groups())
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

MODID = TypeSeq([t_int, t_modid])
''' Module namespace identity. '''

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
    t_float, t_floatraw,
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
    StructType.REAL32: TypeSeq([t_float, t_floatraw]),
    StructType.REAL64: TypeSeq([t_float, t_floatraw]),
    StructType.TEXTSTR: TypeSeq([t_identity, t_tstr]),
    StructType.BYTESTR: TypeSeq([t_bstr]),
    StructType.TP: TypeSeq([t_timepoint, t_decfrac, t_int]),
    StructType.TD: TypeSeq([t_timeperiod, t_decfrac, t_int]),
    StructType.LABEL: TypeSeq([t_identity]),
    StructType.CBOR: TypeSeq([t_bstr, t_cbor_diag]),
    StructType.ARITYPE: get_structtype,
}
''' Map from literal types to value parsers. '''

AMKEY = TypeSeq([t_int, t_identity, t_tstr])
''' Allowed AM key literals. '''

STRUCTKEY = TypeSeq([t_identity])

NONCE = TypeSeq([t_null, t_int, t_bstr])
