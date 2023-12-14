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
''' CODEC for converting ARI to and from text URI form.
'''
import datetime
import logging
from typing import TextIO
from urllib.parse import quote
from ace.ari import (
    StructType, ARI, LiteralARI, ReferenceARI,
    ExecutionSet, ReportSet, Report
)
from ace.cborutil import to_diag
from .util import t_identity

LOGGER = logging.getLogger(__name__)


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


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def __init__(self):
        pass

    def encode(self, obj:ARI, buf: TextIO):
        ''' Encode an ARI into UTF8 text.

        :param obj: The ARI object to encode.
        :param buf: The buffer to write into.
        '''
        self._encode_obj(buf, obj, root=True)

    def _encode_obj(self, buf: TextIO, obj:ARI, root:bool=False):
        if isinstance(obj, LiteralARI):
            LOGGER.debug('Encode literal %s', obj)
            if obj.type_enum is not None:
                buf.write('/' + obj.type_enum.name + '/')

            if obj.type_enum is StructType.AC:
                self._encode_list(buf, obj.value)
            elif obj.type_enum is StructType.AM:
                self._encode_map(buf, obj.value)
            elif obj.type_enum is StructType.TBL:
                self._encode_tbl(buf, obj.value)
            elif obj.type_enum is StructType.TP or isinstance(obj.value, datetime.datetime):
                self._encode_tp(buf, obj.value)
            elif obj.type_enum is StructType.TD or isinstance(obj.value, datetime.timedelta):
                self._encode_td(buf, obj.value)
            elif obj.type_enum is StructType.LABEL:
                # no need to quote identity
                buf.write(obj.value)
            elif isinstance(obj.value, ExecutionSet):
                params = {
                    'n': obj.value.nonce,
                }
                self._encode_struct(buf, params)
                self._encode_list(buf, obj.value.targets)
            elif isinstance(obj.value, ReportSet):
                params = {
                    'n': obj.value.nonce,
                    'r': encode_datetime(obj.value.ref_time),
                }
                self._encode_struct(buf, params)
                self._encode_list(buf, obj.value.reports)
            else:
                if (isinstance(obj.value, str)
                    and t_identity.regex.fullmatch(obj.value) is not None):
                    # Shortcut for identity text
                    buf.write(obj.value)
                else:
                    buf.write(quote(to_diag(obj.value), safe='.+'))

        elif isinstance(obj, ReferenceARI):
            if root:
                buf.write('ari:')
            buf.write(quote(f'/{obj.ident.namespace}'))
            buf.write(f'/{obj.ident.type_enum.name}')
            buf.write(quote(f'/{obj.ident.name}'))
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
        elif isinstance(obj, str):
            buf.write(obj)

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

    def _encode_tbl(self, buf, array):
        params = {
            'c': LiteralARI(array.shape[1]),
        }
        self._encode_struct(buf, params)
        for row_ix in range(array.shape[0]):
            self._encode_list(buf, array[row_ix,:].flat)

    def _encode_struct(self, buf, obj):
        for key, val in obj.items():
            buf.write(key)
            buf.write('=')
            self._encode_obj(buf, val, False)
            buf.write(';')

    def _encode_tp(self, buf, value):
        text = encode_datetime(value)
        buf.write(quote(text))

    def _encode_td(self, buf, value):
        text = encode_timedelta(value)
        buf.write(quote(text))
