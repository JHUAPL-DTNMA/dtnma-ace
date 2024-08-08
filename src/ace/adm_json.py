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
''' CODEC for converting ADM to and from JSON form.
'''

from datetime import datetime
import io
import json
import logging
import os
from typing import BinaryIO
from ace.models import (
    TypeNameList, TypeNameItem, Expr, ARI, AriAP, AC,
    AdmFile, AdmUses, 
    Mdat, Const, Ctrl, Edd, Mac, Oper, OperParm, Rptt, Tblt, Var
)
from ace.util import normalize_ident


LOGGER = logging.getLogger(__name__)

#: JSON key for each object type in the ADM
SECNAMES = {
    Mdat: 'Mdat',
    Const: 'Const',
    Ctrl: 'Ctrl',
    Edd: 'Edd',
    Mac: 'Mac',
    Oper: 'Oper',
    Rptt: 'Rptt',
    Tblt: 'Tblt',
    Var: 'Var',
}

#: JSON object keys for each object class (by lower name)
ATTRMAP = {
    Mdat: ['name', 'enum', 'description', 'type', 'value'],
    Const: ['name', 'enum', 'description', 'type', 'value'],
    Ctrl: ['name', 'enum', 'description', 'parmspec'],
    Edd: ['name', 'enum', 'description', 'parmspec', 'type'],
    Mac: ['name', 'enum', 'description', 'parmspec', 'action'],
    Oper: ['name', 'enum', 'description', 'result-type', 'in-type'],
    Rptt: ['name', 'enum', 'description', 'parmspec', 'definition'],
    Tblt: ['name', 'enum', 'description', 'columns'],
    Var: ['name', 'enum', 'description', 'type', 'initializer'],
}


def attr_to_member(name):
    ''' Convert a JSON attribute name into a valid python instance variable
    name using underscores.
    '''
    return name.replace('-', '_')


class Decoder:
    ''' The decoder portion of this CODEC.
    '''

    def __init__(self, db_sess=None):
        self._db_sess = db_sess

    @staticmethod
    def _read_keys_insensitive(pairs):
        return {key.casefold(): val for (key, val) in pairs}

    def _get_ac(self, json_list):
        obj = AC()

        for json_obj in json_list:
            ari = ARI(
                ns=json_obj['ns'],
                nm=json_obj['nm'],
            )
            for json_ap in json_obj.get('ap', []):
                ari.ap.append(AriAP(
                    type=json_ap['type'],
                    value=json_ap['value'],
                ))
            obj.items.append(ari)

        return obj

    def from_json_obj(self, cls, json_obj):
        ''' Construct an ORM object from a decoded JSON object.

        :param cls: The ORM class to instantiate.
        :param json_obj: The decoded JSON to read from.
        :return: The ORM object.
        '''
        obj = cls()
    
        json_keys = ATTRMAP[cls]
        for key in json_keys:
            if key not in json_obj:
                continue
            json_val = json_obj.get(key)

            # Special handling of common keys
            if key in {'parmspec', 'columns'}:
                # Type TN pairs
                orm_val = TypeNameList()
                for json_parm in json_val:
                    item = TypeNameItem(
                        type=json_parm['type'],
                        name=json_parm['name'],
                    )
                    orm_val.items.append(item)

            elif key in {'initializer'}:
                # Type EXPR
                orm_val = Expr(
                    type=json_val['type'],
                    postfix=self._get_ac(json_val['postfix-expr']),
                )

            elif key in {'action', 'definition'}:
                # Type AC
                orm_val = self._get_ac(json_val)

            elif key == 'in-type':
                orm_val = [
                    OperParm(type=type_name)
                    for type_name in json_val
                ]

            else:
                orm_val = json_val

            setattr(obj, attr_to_member(key), orm_val)

        return obj

    def get_file_time(self, file_path: str):
        ''' Get a consistent file modified time.

        :param file_path: The pathto the file to inspect.
        :return: The modified time object.
        :rtype: :class:`datetime.dateteime`
        '''
        return datetime.fromtimestamp(os.path.getmtime(file_path))


    def _get_section(self, obj_list, orm_cls, json_adm):
        ''' Extract a section from the file '''
        sec_key = SECNAMES[orm_cls].casefold()

        enum = 0
        for json_obj in json_adm.get(sec_key, []):
            obj = self.from_json_obj(orm_cls, json_obj)
            # set derived attributes based on context
            if obj.name is not None:
                obj.norm_name = normalize_ident(obj.name)

            obj.enum = enum
            enum += 1

            obj_list.append(obj)

    def decode(self, buf: BinaryIO) -> AdmFile:
        ''' Decode a single ADM from file.

        :param buf: The buffer to read from.
        :return: The decoded ORM root object.
        '''
        json_adm = json.load(buf, object_pairs_hook=Decoder._read_keys_insensitive)
        adm = AdmFile()

        if hasattr(buf, 'name'):
            adm.abs_file_path = buf.name
            adm.last_modified = self.get_file_time(buf.name)
        
        for ns in json_adm.get('uses', []):
            adm.uses.append(AdmUses(
                namespace=ns,
                norm_namespace=normalize_ident(ns)
            ))
        
        self._get_section(adm.mdat, Mdat, json_adm)
        self._get_section(adm.const, Const, json_adm)
        self._get_section(adm.ctrl, Ctrl, json_adm)
        self._get_section(adm.edd, Edd, json_adm)
        self._get_section(adm.mac, Mac, json_adm)
        self._get_section(adm.oper, Oper, json_adm)
        self._get_section(adm.rptt, Rptt, json_adm)
        self._get_section(adm.tblt, Tblt, json_adm)
        self._get_section(adm.var, Var, json_adm)
         
        # Normalize the intrinsic ADM name
        items = [mdat.value for mdat in adm.mdat if mdat.name == 'name']
        if items:
            adm.norm_name = normalize_ident(items[0])

        items = [mdat.value for mdat in adm.mdat if mdat.name == 'namespace']
        if items:
            adm.norm_namespace = normalize_ident(items[0])
            adm.adm_ns = items[0]

        items = [mdat.value for mdat in adm.mdat if mdat.name == 'enum']
        if items:
            # coerce text if needed
            adm.enum = int(items[0])

        return adm


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def encode(self, adm: AdmFile, buf: BinaryIO, indent=None):
        ''' Decode a single ADM from file.

        :param adm: The ORM root object.
        :param buf: The buffer to write into.
        :param indent: The JSON indentation size or None.
        '''
        json_adm = {}

        if adm.uses:
            json_adm['uses'] = [use.namespace for use in adm.uses]

        self._put_section(adm.mdat, Mdat, json_adm)
        self._put_section(adm.const, Const, json_adm)
        self._put_section(adm.ctrl, Ctrl, json_adm)
        self._put_section(adm.edd, Edd, json_adm)
        self._put_section(adm.mac, Mac, json_adm)
        self._put_section(adm.oper, Oper, json_adm)
        self._put_section(adm.rptt, Rptt, json_adm)
        self._put_section(adm.tblt, Tblt, json_adm)
        self._put_section(adm.var, Var, json_adm)

        wrap = io.TextIOWrapper(buf, encoding='utf-8')
        try:
            json.dump(json_adm, wrap, indent=indent)
        finally:
            wrap.flush()
            wrap.detach()

    def _put_section(self, obj_list, orm_cls, json_adm):
        ''' Insert a section to the file '''
        if not obj_list:
            # Don't add empty sections
            return

        sec_key = SECNAMES[orm_cls]
        json_list = []
        for obj in obj_list:
            json_list.append(self.to_json_obj(obj))
        json_adm[sec_key] = json_list

    def to_json_obj(self, obj) -> object:
        ''' Construct a encoded JSON object from an ORM object.

        :param obj: The ORM object to read from.
        :return: The JSON-able object.
        '''
        json_obj = {}
        json_keys = ATTRMAP[type(obj)]
        for key in json_keys:
            if key == 'enum':
                continue
            orm_val = getattr(obj, attr_to_member(key))
            if orm_val is None:
                continue

            # Special handling of common keys
            if key in {'parmspec', 'columns'}:
                # Type TN pairs
                json_list = []
                for item in orm_val.items:
                    json_item = {
                        'type': item.type,
                        'name': item.name,
                    }
                    json_list.append(json_item)
                json_val = json_list

            elif key in {'initializer'}:
                # Type EXPR
                json_val = {
                    'type': orm_val.type,
                    'postfix-expr': self._get_ac(orm_val.postfix),
                }

            elif key in {'action', 'definition'}:
                # Type AC
                json_val = self._get_ac(orm_val)

            elif key == 'in-type':
                json_val = [parm.type for parm in orm_val]

            else:
                json_val = orm_val

            json_obj[key] = json_val

        return json_obj

    def _get_ac(self, obj):
        json_list = []
        for ari in obj.items:
            json_list.append(self.to_json_ari(ari))
        return json_list

    def to_json_ari(self, ari: ARI) -> object:
        ''' Construct an encoded JSON ARI from an ORM ARI.

        :param ari: The ARI to encode.
        :return the JSON-able object.
        '''
        obj = {
            'ns': ari.ns,
            'nm': ari.nm,
        }
        if ari.ap:
            obj['ap'] = [{'type': ap.type, 'value': ap.value} for ap in ari.ap]
        return obj
