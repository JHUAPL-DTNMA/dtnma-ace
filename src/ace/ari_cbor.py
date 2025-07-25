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
from ace.typing import BUILTINS_BY_ENUM, NONCE
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

        if hasattr(buf, 'tell') and hasattr(buf, 'getbuffer'):
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
            if len(item) in {4, 5, 6}:
                idx = 2
                if isinstance(item[idx], datetime.date):
                    if len(item) < 5:
                        raise ParseError(f'Invalid ARI CBOR item containing model revision, too few segments: {item}')

                    model_rev = item[idx]
                    idx += 1
                else:
                    model_rev = None
            
                for item_idx in (0,1,idx,idx+1):
                    if not (item[item_idx] == None or isinstance(item[item_idx], int) or isinstance(item[item_idx], str)):
                        raise ParseError(f'{item} segment {item_idx} has unexpected type {type(item[idx])}')

                ident = Identity(
                    org_id=item[0],
                    model_id=item[1],
                    model_rev=model_rev,
                    type_id=StructType(item[idx]) if item[idx] else None,
                    obj_id=item[idx+1],
                )
                idx += 2

                params = None
                if len(item) == idx+1:
                    if isinstance(item[idx], list):
                        params = [
                            self._item_to_ari(param_item)
                            for param_item in item[idx]
                        ]
                    elif isinstance(item[idx], dict):
                        mapobj = {}
                        for key, val in item[idx].items():
                          k = self._item_to_ari(key)
                          v = self._item_to_ari(val)
                          mapobj[k] = v
                        params = mapobj
                    else:
                        raise ParseError(f'Invalid parameter format: {item} segment {idx} should be a list or dictionary')
                elif len(item) > idx+1:
                    raise ParseError(f'Invalid ARI CBOR item, too many segments: {item}')

                res = ReferenceARI(ident=ident, params=params)

            elif len(item) == 2:
                # Typed literal
                type_id = StructType(item[0])
                value = self._item_to_val(item[1], type_id)
                res = LiteralARI(
                    type_id=type_id,
                    value=value
                )
            else:
                raise ParseError(f'Invalid ARI CBOR item, unexpected number of segments: {item}')
        
        elif isinstance(item, dict):
            raise ParseError(f'Invalid ARI CBOR major type: {item}')
        
        else:
            # Untyped literal
            value = self._item_to_val(item, None)
            res = LiteralARI(value=value)

        return res

    def _item_to_val(self, item, type_id):
        ''' Decode a CBOR item into an ARI value. '''
        if type_id == StructType.AC:
            value = [self._item_to_ari(sub_item) for sub_item in item]
        elif type_id == StructType.AM:
            value = {self._item_to_ari(key): self._item_to_ari(sub_item) for key, sub_item in item.items()}
        elif type_id == StructType.TBL:
            item_it = iter(item)

            ncol = next(item_it, None)
            if ncol == None:
                raise ParseError(f'No column number provided for TBL: {item}')
            elif not isinstance(ncol, int):
                raise ParseError(f'Invalid column provided for TBL: {ncol}')
            if ncol == 0:
                nrow = 0
            else:
                nrow = (len(item) - 1) // ncol
            if len(item) != nrow*ncol+1:
                raise ParseError(f'Number of columns does not match number of values: {item[1:]} cannot be split among {ncol} columns')
            value = Table((nrow, ncol))
            LOGGER.debug(f'Processing TBL with {nrow} rows and {ncol} columns...')
            for row_ix in range(nrow):
                for col_ix in range(ncol):
                    value[row_ix, col_ix] = self._item_to_ari(next(item_it))

        elif type_id == StructType.TP:
            value = self._item_to_timeval(item) + DTN_EPOCH
        elif type_id == StructType.TD:
            value = self._item_to_timeval(item)
        elif type_id == StructType.LABEL:
            if not isinstance(item, str) and not isinstance(item, int):
                raise TypeError(f'invalid label: {item} shoud be string or int')
            value=item
        elif type_id == StructType.EXECSET:
            nonce = NONCE.get(LiteralARI(item[0]))
            if nonce is None:
                raise ValueError(f'invalid nonce: {item[0]}')
            value = ExecutionSet(
                nonce=nonce,
                targets=[self._item_to_ari(sub) for sub in item[1:]]
            )
        elif type_id == StructType.RPTSET:
            nonce = NONCE.get(LiteralARI(item[0]))
            if nonce is None:
                raise ValueError(f'invalid nonce: {item[0]}')

            ref_time = (DTN_EPOCH + self._item_to_timeval(item[1]))

            rpts = []
            for rpt_item in item[2:]:
                rpt = Report(
                    rel_time=self._item_to_timeval(rpt_item[0]),
                    source=self._item_to_ari(rpt_item[1]),
                    items=list(map(self._item_to_ari, rpt_item[2:]))
                )
                rpts.append(rpt)

            value = ReportSet(
                nonce=nonce,
                ref_time=ref_time,
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
            exp, mant = map(int, item)
            if exp < -9 or exp > 9:
                raise ValueError(f'Decimal fraction exponent outside valid range [-9,9]')
            total_usec = mant * 10 ** (exp + 6)
            return datetime.timedelta(microseconds=total_usec)
        else:
            raise TypeError(f'Bad timeval type: {item} is type {type(item)}')


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def encode(self, ari: ARI, buf: BinaryIO):
        ''' Encode an ARI into CBOR bytestring.

        :param ari: The ARI object to encode.
        :param buf: The buffer to write into.
        '''
        cborenc = cbor2.CBOREncoder(buf, canonical=True)
        item = self._ari_to_item(ari)
        LOGGER.debug('ARI to item %s', item)
        cborenc.encode(item)

    def _ari_to_item(self, obj:ARI) -> object:
        ''' Convert an ARI object into a CBOR item. '''
        item = None
        LOGGER.debug('ARI: %s', obj)
        if isinstance(obj, ReferenceARI):
            type_id = int(obj.ident.type_id) if obj.ident.type_id is not None else None
            item = [
                obj.ident.org_id,
                obj.ident.model_id,
            ]
            if obj.ident.model_rev is not None:
                # Be explicit about CBOR tag
                item.append(cbor2.CBORTag(1004, obj.ident.model_rev.isoformat()))
            item += [
                type_id,
                obj.ident.obj_id,
            ]

            if isinstance(obj.params, list):
                item.append([
                    self._ari_to_item(param)
                    for param in obj.params
                ])
            elif isinstance(obj.params, dict):
                mapobj = {}
                for key, val in obj.params.items():
                  k = self._ari_to_item(key)
                  v = self._ari_to_item(val)
                  mapobj[k] = v
                item.append(mapobj)

        elif isinstance(obj, LiteralARI):
            if obj.type_id is not None:
                item = [obj.type_id.value, self._val_to_item(obj.value)]
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
            item = [exp, mant]
        else:
            item = mant
        return item
