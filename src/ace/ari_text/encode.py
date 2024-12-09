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
''' CODEC for converting ARI to and from text URI form.
'''
import base64
from dataclasses import dataclass
import logging
from typing import TextIO, Union
import urllib.parse
import cbor2
from ace.ari import (
    StructType, ARI, LiteralARI, ReferenceARI,
    ExecutionSet, ReportSet, Report, DTN_EPOCH
)
from ace.cborutil import to_diag
from .util import t_identity, SINGLETONS

LOGGER = logging.getLogger(__name__)


def quote(text):
    ''' URL-escape each ID and value segment

    :param text: The text to escape.
    :return: The percent-encoded text.
    '''
    return urllib.parse.quote(text, safe='.+')


def encode_datetime(value):
    if value.microsecond:
        fmt = '%Y%m%dT%H%M%S.%fZ'
    else:
        fmt = '%Y%m%dT%H%M%SZ'
    text = value.strftime(fmt)
    return text


def encode_timedelta(value):
    neg = value.days < 0
    diff = -value if neg else value

    days = diff.days
    secs = diff.seconds
    hours = secs // 3600
    secs = secs % 3600
    minutes = secs // 60
    secs = secs % 60

    usec = diff.microseconds
    pad = 6
    while usec and usec % 10 == 0:
        usec //= 10
        pad -= 1

    text = ''
    if neg:
        text += '-'
    text += 'P'
    if days:
        text += f'{days}D'
    text += 'T'
    if hours:
        text += f'{hours}H'
    if minutes:
        text += f'{minutes}M'
    if usec:
        text += f'{secs}.{usec:0>{pad}}S'
    elif secs:
        text += f'{secs}S'
    return text


def can_unquote(text):
    ''' Determine if text can match an identity pattern. '''
    try:
        SINGLETONS(text)
        return False
    except:
        pass
    return t_identity.regex.fullmatch(text) is not None


@dataclass
class EncodeOptions:
    ''' Preferences for text encoding variations. '''

    scheme_prefix:bool = True
    ''' True if the scheme is present at the start. '''
    int_base:int = 10
    ''' One of 2, 10, or 16 '''
    float_form:str = 'g'
    ''' One of 'f' or 'g' for standard format, or 'x' for raw hex'''
    text_identity:bool = True
    ''' True if specific text can be left unquoted. '''
    time_text:bool = True
    ''' True if time values should be in text form. '''
    cbor_diag:bool = False
    ''' True if CBOR values should be in diagnostic form. '''


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def __init__(self, options:EncodeOptions=None, **kwargs):
        self._options = options or EncodeOptions(**kwargs)

    def encode(self, obj:ARI, buf: TextIO):
        ''' Encode an ARI into UTF8 text.

        :param obj: The ARI object to encode.
        :param buf: The buffer to write into.
        '''
        self._encode_obj(buf, obj, prefix=self._options.scheme_prefix)

    def _encode_obj(self, buf: TextIO, obj:ARI, prefix:bool=False):
        if isinstance(obj, LiteralARI):
            LOGGER.debug('Encode literal %s', obj)
            if prefix:
                buf.write('ari:')
            if obj.type_id is not None:
                buf.write('/')
                buf.write(obj.type_id.name)
                buf.write('/')

            if obj.type_id is StructType.AC:
                self._encode_list(buf, obj.value)
            elif obj.type_id is StructType.AM:
                self._encode_map(buf, obj.value)
            elif obj.type_id is StructType.TBL:
                self._encode_tbl(buf, obj.value)
            elif obj.type_id is StructType.TP:
                if self._options.time_text:
                    text = encode_datetime(obj.value)
                    buf.write(quote(text))
                else:
                    diff = (obj.value - DTN_EPOCH).total_seconds()
                    buf.write(f'{diff:.6f}')
            elif obj.type_id is StructType.TD:
                if self._options.time_text:
                    text = encode_timedelta(obj.value)
                    buf.write(quote(text))
                else:
                    diff = obj.value.total_seconds()
                    buf.write(f'{diff:.6f}')
            elif obj.type_id is StructType.LABEL:
                # no need to quote identity
                buf.write(obj.value)
            elif obj.type_id is StructType.CBOR:
                if self._options.cbor_diag:
                    buf.write(quote('<<'))
                    buf.write(quote(to_diag(cbor2.loads(obj.value))))
                    buf.write(quote('>>'))
                else:
                    buf.write(quote(to_diag(obj.value)))
            elif obj.type_id is StructType.ARITYPE:
                buf.write(obj.value.name)
            elif isinstance(obj.value, ExecutionSet):
                params = {
                    'n': to_diag(obj.value.nonce),
                }
                self._encode_struct(buf, params)
                self._encode_list(buf, obj.value.targets)
            elif isinstance(obj.value, ReportSet):
                params = {
                    'n': to_diag(obj.value.nonce),
                    'r': encode_datetime(obj.value.ref_time),
                }
                self._encode_struct(buf, params)
                self._encode_list(buf, obj.value.reports)
            else:
                if isinstance(obj.value, int) and not isinstance(obj.value, bool):
                    if self._options.int_base == 2:
                        fmt = '0b{0:b}'
                    elif self._options.int_base == 16:
                        fmt = '0x{0:x}'
                    else:
                        fmt = '{0:d}'
                    buf.write(fmt.format(obj.value))
                    return
                elif isinstance(obj.value, float):
                    if self._options.float_form == 'x':
                        # CBOR efficient length encoding
                        data = cbor2.dumps(obj.value, canonical=True)
                        buf.write('0fx')
                        buf.write(base64.b16encode(data[1:]).decode('ascii').casefold())
                        return
                    elif self._options.float_form in {'f', 'e'}:
                        buf.write(f'{{0:{self._options.float_form}}}'.format(obj.value))
                        return
                elif isinstance(obj.value, str):
                    if can_unquote(obj.value) and self._options.text_identity:
                        # Shortcut for identity text
                        buf.write(obj.value)
                        return

                buf.write(quote(to_diag(obj.value)))

        elif isinstance(obj, ReferenceARI):
            if prefix:
                buf.write('ari:')
            if obj.ident.ns_id is None:
                buf.write('.')
            else:
                buf.write('//')
                buf.write(str(obj.ident.ns_id))
            if obj.ident.ns_rev is not None:
                buf.write('@')
                buf.write(obj.ident.ns_rev)
            buf.write('/')

            if obj.ident.type_id and obj.ident.obj_id:
                buf.write(obj.ident.type_id.name)
                buf.write('/')
                buf.write(str(obj.ident.obj_id))
                if obj.params is not None:
                    self._encode_list(buf, obj.params)

        # FIXME: special cases for recursion
        elif isinstance(obj, Report):
            params = {
                't': encode_timedelta(obj.rel_time),
                's': obj.source,
            }
            self._encode_struct(buf, params)
            self._encode_list(buf, obj.items)

        else:
            raise TypeError(f'Unhandled object type {type(obj)} instance: {obj}')

    def _encode_list(self, buf, items):
        buf.write('(')

        first = True
        if items:
            for part in items:
                if not first:
                    buf.write(',')
                first = False
                self._encode_obj(buf, part)

        buf.write(')')

    def _encode_map(self, buf, mapobj):
        buf.write('(')

        first = True
        if mapobj:
            for key, val in mapobj.items():
                if not first:
                    buf.write(',')
                first = False

                self._encode_obj(buf, key)
                buf.write('=')
                self._encode_obj(buf, val)

        buf.write(')')

    def _encode_tbl(self, buf, array:'numpy.ndarray'):
        params = {
            'c': str(array.shape[1]),
        }
        self._encode_struct(buf, params)
        for row_ix in range(array.shape[0]):
            self._encode_list(buf, array[row_ix,:].flat)

    def _encode_struct(self, buf, obj:Union[ARI, str]):
        for key, val in obj.items():
            buf.write(key)
            buf.write('=')
            if isinstance(val, ARI):
                self._encode_obj(buf, val, False)
            else:
                buf.write(quote(val))
            buf.write(';')
