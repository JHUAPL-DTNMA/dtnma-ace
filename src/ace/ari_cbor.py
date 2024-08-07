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
''' CODEC for converting ARI to and from CBOR form.
'''

import enum
import logging
import struct
from typing import BinaryIO
import cbor2
from ace.ari import (
    ARI, AC, EXPR, TNVC, Identity, ReferenceARI, LiteralARI,
    StructType, LITERAL_TYPES
)
from ace.cborutil import to_diag
from ace.util import is_printable


LOGGER = logging.getLogger(__name__)


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
            res = self._decode_ari(cbordec)
        except cbor2.CBORDecodeEOF as err:
            raise ParseError(f'Failed to decode ARI: {err}') from err
        if buf.tell() != len(buf.getbuffer()):
            LOGGER.warning('ARI decoder handled only the first %d octets of %s',
                           buf.tell(), to_diag(buf.getvalue()))
        return res

    def _decode_ari(self, cbordec):
        flags, = struct.unpack('!B', cbordec.read(1))
        LOGGER.debug('Got flags: 0x%02x', flags)
        str_type = StructType(flags & 0x0F)

        if str_type == StructType.LIT:
            try:
                val = cbordec.decode()
            except Exception as err:
                raise ParseError(f'Failed to decode literal value: {err}') from err

            type_enum = StructType((flags >> 4) + StructType.BOOL)
            res = LiteralARI(type_enum=type_enum, value=val)

        else:
            obj_nn = cbordec.decode() if flags & AriFlag.HAS_NN else None
            LOGGER.debug('Got nickname: %s', obj_nn)

            name = cbordec.decode()
            LOGGER.debug('Got name: %s', to_diag(name))
            if not isinstance(name, (bytes, str)):
                raise ParseError(f'Decoded name is not bytes or str, got {type(name)}')
            if isinstance(name, bytes) and is_printable(name):
                name = name.decode('utf-8')

            params = self._decode_tnvc(cbordec) if flags & AriFlag.HAS_PARAMS else None

            issuer = cbordec.decode() if flags & AriFlag.HAS_ISS else None
            LOGGER.debug('Got issuer: %s', to_diag(issuer))
            if issuer is not None and not isinstance(issuer, bytes):
                raise ParseError(f'Decoded issuer is not bytes, got {type(issuer)}')

            tag = cbordec.decode() if flags & AriFlag.HAS_TAG else None
            LOGGER.debug('Got tag: %s', to_diag(issuer))
            if tag is not None and not isinstance(tag, bytes):
                raise ParseError(f'Decoded tag is not bytes, got {type(tag)}')

            ident = Identity(
                namespace=obj_nn,
                type_enum=str_type,
                name=name,
                issuer=issuer,
                tag=tag
            )
            res = ReferenceARI(ident=ident, params=params)

        return res

    def _decode_tnvc(self, cbordec):
        ''' From the document:
            +--------+---------+----------+----------+----------+----------+
            | Flags  | # Items |  Types   |  Names   |  Values  |  Mixed   |
            | [BYTE] |  [UINT] | [OCTETS] | [OCTETS] | [OCTETS] | [OCTETS] |
            |        |  (Opt)  |  (Opt)   |  (Opt)   |  (Opt)   |  (Opt)   |
            +--------+---------+----------+----------+----------+----------+
        '''

        flags, = struct.unpack('!B', cbordec.read(1))

        count = cbordec.decode() if flags else 0

        type_enums = []
        if flags & TnvcFlag.TYPE:
            for _idx in range(count):
                type_id = struct.unpack('!B', cbordec.read(1))[0]
                type_enums.append(StructType(type_id))

        if flags & TnvcFlag.NAME:
            raise NotImplementedError

        values = []
        if flags & TnvcFlag.VALUE:
            for idx in range(count):
                LOGGER.debug('Decoding TNVC item %d type %s',
                             idx, type_enums[idx])
                values.append(self._decode_obj(type_enums[idx], cbordec))
        return values

    def _decode_ac_items(self, cbordec):
        # FIXME: workaorund! doesn't scale up
        item = ord(cbordec.read(1))
        count = item & 0x1F
        LOGGER.debug('AC with count %d', count)
        items = []
        for _ in range(count):
            items.append(self._decode_ari(cbordec))
        return items

    def _decode_obj(self, type_enum, cbordec):
        if type_enum == StructType.ARI:
            obj = self._decode_ari(cbordec)

        elif type_enum == StructType.AC:
            obj = AC(
                items=self._decode_ac_items(cbordec)
            )

        elif type_enum == StructType.EXPR:
            obj = EXPR(
                type_enum=StructType(cbordec.decode()),
                items=self._decode_ac_items(cbordec)
            )

        elif type_enum == StructType.TNVC:
            # FIXME: there is no distinction in text between AC and TNVC
            obj = AC(items=self._decode_tnvc(cbordec))

        elif type_enum in LITERAL_TYPES:
            item = cbordec.decode()
            obj = LiteralARI(type_enum=type_enum, value=item)

        else:
            raise ValueError(f'Unhandled param object type: {type_enum}')

        return obj


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def encode(self, obj: ARI, buf: BinaryIO):
        ''' Encode an ARI into CBOR bytestring.

        :param obj: The ARI object to encode.
        :param buf: The buffer to write into.
        '''
        cborenc = cbor2.CBOREncoder(buf)
        self._encode_obj(obj, cborenc, True)

    def _encode_obj(self, obj, cborenc, as_ari):
        if isinstance(obj, ReferenceARI):
            self._encode_ref_ari(obj, cborenc)

        elif isinstance(obj, AC):
            # FIXME: workaorund! doesn't scale up
            head = bytes([0x80 | len(obj.items)])
            LOGGER.debug('AC encoding header %s', to_diag(head))
            cborenc.write(head)
            for ari in obj.items:
                self._encode_ref_ari(ari, cborenc)

        elif isinstance(obj, EXPR):
            cborenc.encode(obj.type_enum.value)
            # FIXME: workaorund! doesn't scale up
            head = bytes([0x80 | len(obj.items)])
            LOGGER.debug('EXPR encoding type %s, header %s',
                         obj.type_enum.value, to_diag(head))
            cborenc.write(head)
            for ari in obj.items:
                self._encode_ref_ari(ari, cborenc)

        elif isinstance(obj, TNVC):
            self._encode_tnvc(obj.items, cborenc)

        elif isinstance(obj, LiteralARI):
            if obj.type_enum == StructType.BSTR:
                cborenc.encode(obj.value)
                return

            if as_ari:
                flags = (
                    ((obj.type_enum - StructType.BOOL) << 4)
                    | StructType.LIT
                )
                cborenc.write(struct.pack('!B', flags))
            cborenc.encode(obj.value)

        else:
            raise TypeError(f'Unhandled object type {type(obj)} for: {obj}')

    def _encode_ref_ari(self, obj, cborenc):
        flags = int(obj.ident.type_enum)
        if obj.ident.namespace is not None:
            flags |= AriFlag.HAS_NN
        if obj.params is not None:
            flags |= AriFlag.HAS_PARAMS
        if obj.ident.issuer is not None:
            flags |= AriFlag.HAS_ISS
        if obj.ident.tag is not None:
            flags |= AriFlag.HAS_TAG
        LOGGER.debug('ReferenceARI encoding flags %s', to_diag(flags))
        cborenc.write(struct.pack('!B', flags))

        if obj.ident.namespace is not None:
            cborenc.encode(obj.ident.namespace)
        
        # amp is expecting a bytestring
        cborenc.encode(
            obj.ident.name if isinstance(obj.ident.name, bytes)
            else str(obj.ident.name).encode('utf-8')
        )
        
        if obj.params is not None:
            self._encode_tnvc(obj.params, cborenc)
        if obj.ident.issuer is not None:
            cborenc.encode(obj.ident.issuer)
        if obj.ident.tag is not None:
            cborenc.encode(obj.ident.tag)

    def _encode_tnvc(self, params, cborenc):
        LOGGER.debug('TNVC encoding count %s', len(params))
        flags = 0
        if params:
            flags |= TnvcFlag.TYPE | TnvcFlag.VALUE
        cborenc.write(struct.pack('!B', flags))

        if flags:
            cborenc.encode(len(params))

        for param in params:
            if isinstance(param, ReferenceARI):
                type_enum = StructType.ARI
            elif isinstance(param, AC):
                type_enum = StructType.AC
            elif isinstance(param, EXPR):
                type_enum = StructType.EXPR
            elif isinstance(param, TNVC):
                type_enum = StructType.TNVC
            elif isinstance(param, LiteralARI):
                type_enum = param.type_enum
            else:
                LOGGER.warning(
                    'Unhandled parameter type %s for: %s',
                    type(param), param
                )
            cborenc.write(struct.pack('!B', type_enum))

        for param in params:
            LOGGER.debug('TNVC encoding item %s', param)
            self._encode_obj(param, cborenc, as_ari=False)
