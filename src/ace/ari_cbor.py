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
import logging
from typing import BinaryIO
import cbor2
from ace.ari import (
    DTN_EPOCH, ARI, Identity, ReferenceARI, LiteralARI, StructType,
    Table, ExecutionSet, ReportSet, Report
)
from ace.cborutil import to_diag

LOGGER = logging.getLogger(__name__)


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
            res = self._item_to_ari(item)
        except cbor2.CBORDecodeEOF as err:
            raise ParseError(f'Failed to decode ARI: {err}') from err

        return res

    def _item_to_ari(self, item:object):
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
                        self._item_to_ari(param_item)
                        for param_item in item[3]
                    ]

                res = ReferenceARI(ident=ident, params=params)

            elif len(item) == 2:
                # Typed literal
                type_enum = StructType(item[0])
                value = self._item_to_val(item[1], type_enum)
                res = LiteralARI(
                    type_enum=type_enum,
                    value=value
                )
            else:
                raise ParseError(f'Invalid ARI CBOR item: {item}')

        else:
            # Untyped literal
            value = self._item_to_val(item, None)
            res = LiteralARI(value=value)

        return res

    def _item_to_val(self, item, type_enum):
        ''' Decode a CBOR item into an ARI value. '''
        if type_enum == StructType.AC:
            value = [self._item_to_ari(sub_item) for sub_item in item]
        elif type_enum == StructType.AM:
            value = {self._item_to_ari(key): self._item_to_ari(sub_item) for key, sub_item in item.items()}
        elif type_enum == StructType.TBL:
            item_it = iter(item)

            ncol = next(item_it)
            nrow = (len(item) - 1) // ncol
            value = Table((nrow, ncol))

            for row_ix in range(nrow):
                for col_ix in range(ncol):
                    value[row_ix, col_ix] = self._item_to_ari(next(item_it))

        elif type_enum == StructType.TP:
            value = self._item_to_timeval(item) + DTN_EPOCH
        elif type_enum == StructType.TD:
            value = self._item_to_timeval(item)
        elif type_enum == StructType.EXECSET:
            value = ExecutionSet(
                nonce=self._item_to_ari(item[0]),
                targets=[self._item_to_ari(sub) for sub in item[1:]]
            )
        elif type_enum == StructType.RPTSET:
            rpts = []
            for rpt_item in item[2:]:
                rpt = Report(
                    rel_time=self._item_to_timeval(rpt_item[0]),
                    source=self._item_to_ari(rpt_item[1]),
                    items=list(map(self._item_to_ari, rpt_item[2:]))
                )
                rpts.append(rpt)

            value = ReportSet(
                nonce=self._item_to_ari(item[0]),
                ref_time=(DTN_EPOCH + self._item_to_timeval(item[1])),
                reports=rpts
            )
        else:
            value = item
        return value

    def _item_to_timeval(self, item) -> datetime.timedelta:
        ''' Extract a time offset value from CBOR item. '''
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

    def encode(self, ari: ARI, buf: BinaryIO):
        ''' Encode an ARI into CBOR bytestring.

        :param ari: The ARI object to encode.
        :param buf: The buffer to write into.
        '''
        cborenc = cbor2.CBOREncoder(buf)
        item = self._ari_to_item(ari)
        LOGGER.debug('ARI to item %s', item)
        cborenc.encode(item)

    def _ari_to_item(self, obj:ARI) -> object:
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
                    self._ari_to_item(param)
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
            item = [self._ari_to_item(obj) for obj in value]
        elif isinstance(value, dict):
            item = {self._ari_to_item(key): self._ari_to_item(obj) for key, obj in value.items()}
        elif isinstance(value, Table):
            item = [value.shape[1]] + list(map(self._ari_to_item, value.flat))
        elif isinstance(value, datetime.datetime):
            diff = value - DTN_EPOCH
            item = self._timeval_to_item(diff)
        elif isinstance(value, datetime.timedelta):
            item = self._timeval_to_item(value)
        elif isinstance(value, ExecutionSet):
            item = [
                self._ari_to_item(value.nonce)
            ] + list(map(self._ari_to_item, value.targets))
        elif isinstance(value, ReportSet):
            rpts_item = []
            for rpt in value.reports:
                rpt_item = [
                    self._val_to_item(rpt.rel_time),
                    self._ari_to_item(rpt.source),
                ] + list(map(self._ari_to_item, rpt.items))
                rpts_item.append(rpt_item)
            item = [
                self._ari_to_item(value.nonce),
                self._val_to_item(value.ref_time)
            ] + rpts_item
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
