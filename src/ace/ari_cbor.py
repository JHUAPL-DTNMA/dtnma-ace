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
''' CODEC for converting ARI to and from CBOR form.
'''
import datetime
import enum
import logging
import struct
from typing import BinaryIO
import cbor2
from ace.ari import (
    ARI, Identity, ReferenceARI, LiteralARI, StructType
)
from ace.cborutil import to_diag
from ace.util import is_printable

LOGGER = logging.getLogger(__name__)

DTN_EPOCH = datetime.datetime(2000, 1, 1, 0, 0, 0)


@enum.unique
class AriFlag(enum.IntFlag):
    ''' Flags at the front of an ARI. '''
    HAS_NN = 0x80
    HAS_PARAMS = 0x40
    HAS_ISS = 0x20
    HAS_TAG = 0x10


@enum.unique
class TnvcFlag(enum.IntFlag):
    ''' Flgas at the front of a TNVC. '''
    MIXED = 0x8
    TYPE = 0x4
    NAME = 0x2
    VALUE = 0x1


class ParseError(RuntimeError):
    ''' Indicate an error in ARI parsing. '''


class Decoder:
    ''' The decoder portion of this CODEC. '''

    def decode(self, buf: BinaryIO) -> ARI:
        ''' Decode an ARI from CBOR bytestring.

        :param buf: The buffer to read from.
        :return: The decoded ARI.
        '''
        cbordec = cbor2.CBORDecoder(buf)
        try:
            item = cbordec.decode()
        except Exception as err:
            raise ParseError(f'Failed to decode CBOR: {err}') from err
        if buf.tell() != len(buf.getbuffer()):
            LOGGER.warning('ARI decoder handled only the first %d octets of %s',
                           buf.tell(), to_diag(buf.getvalue()))

        try:
            res = self._item_to_obj(item)
        except cbor2.CBORDecodeEOF as err:
            raise ParseError(f'Failed to decode ARI: {err}') from err

        return res

    def _item_to_obj(self, item:object):
        LOGGER.debug('Got ARI item: %s', item)

        if isinstance(item, list):
            if len(item) >= 3:
                # Object reference
                ident = Identity(
                    namespace=item[0],
                    type_enum=StructType(item[1]),
                    name=item[2],
                )

                params = None
                if len(item) >= 4:
                    params = [
                        self._item_to_obj(param_item)
                        for param_item in item[3]
                    ]

                res = ReferenceARI(ident=ident, params=params)

            elif len(item) == 2:
                # Typed literal
                type_enum = StructType(item[0])
                res = LiteralARI(
                    type_enum=type_enum,
                    value=self._item_to_val(item[1], type_enum)
                )
            else:
                raise ParseError(f'Invalid ARI CBOR item: {item}')
        else:
            # Untyped literal
            res = LiteralARI(value=self._item_to_val(item, None))

        return res

    def _item_to_val(self, item, type_enum):
        if type_enum == StructType.AC:
            value = [self._item_to_obj(sub_item) for sub_item in item]
        elif type_enum == StructType.AM:
            value = {key: self._item_to_obj(sub_item) for key, sub_item in item.items()}
        elif type_enum == StructType.TP:
            value = self._item_to_timeval(item) + DTN_EPOCH
        elif type_enum == StructType.TD:
            value = self._item_to_timeval(item)
        else:
            value = item
        return value

    def _item_to_timeval(self, item):
        if isinstance(item, int):
            return datetime.timedelta(seconds=item)
        elif isinstance(item, list):
            mant, exp = item
            total_usec = mant * 10 ** (exp + 6)
            return datetime.timedelta(microseconds=total_usec)
        else:
            raise TypeError(f'Bad timeval type: {type(item)}')


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def encode(self, obj: ARI, buf: BinaryIO):
        ''' Encode an ARI into CBOR bytestring.

        :param obj: The ARI object to encode.
        :param buf: The buffer to write into.
        '''
        cborenc = cbor2.CBOREncoder(buf)
        item = self._obj_to_item(obj)
        LOGGER.debug('ARI to item %s', item)
        cborenc.encode(item)

    def _obj_to_item(self, obj:ARI) -> object:
        ''' Convert an ARI object into a CBOR item. '''
        item = None
        if isinstance(obj, ReferenceARI):
            item = [
                obj.ident.namespace,
                int(obj.ident.type_enum),
                obj.ident.name,
            ]
    
            if obj.params is not None:
                item.append([
                    self._obj_to_item(param)
                    for param in obj.params
                ])

        elif isinstance(obj, LiteralARI):
            if obj.type_enum is not None:
                item = [obj.type_enum.value, self._val_to_item(obj.value)]
            else:
                item = self._val_to_item(obj.value)

        else:
            raise TypeError(f'Unhandled object type {type(obj)} for: {obj}')

        return item

    def _val_to_item(self, value):
        ''' Convert a non-typed value into a CBOR item. '''
        if isinstance(value, list):
            item = [self._obj_to_item(obj) for obj in value]
        elif isinstance(value, map):
            item = {key: self._obj_to_item(obj) for key, obj in value.items()}
        elif isinstance(value, datetime.datetime):
            diff = value - DTN_EPOCH
            item = self._timeval_to_item(diff)
        elif isinstance(value, datetime.timedelta):
            item = self._timeval_to_item(value)
        else:
            item = value
        return item

    def _timeval_to_item(self, diff):
        total_usec = (diff.days * 24 * 3600 + diff.seconds) * 10 ** 6 + diff.microseconds
        mant = total_usec
        exp = -6
        while mant and mant % 10 == 0:
            mant //= 10
            exp += 1

        if exp:
            # use decimal fraction
            item = [mant, exp]
        else:
            item = mant
        return item
