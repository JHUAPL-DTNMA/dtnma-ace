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
''' CODEC for converting ADM to and from YANG form.
'''

from datetime import datetime
import io
import logging
import os
import re
from typing import TextIO, List
import pyang
import pyang.plugin
import pyang.context
import pyang.repository
from ace.models import (
    TypeNameList, TypeNameItem, Expr, ARI, AriAP, AC,
    AdmFile, AdmUses, SemType,
    Typedef, Const, Ctrl, Edd, Oper, OperParm, Var
)
from ace.util import normalize_ident

LOGGER = logging.getLogger(__name__)
# : Directory containing this file
SELFDIR = os.path.dirname(__file__)

AMM_MOD = 'ietf-amm'

# : YANG keyword for each object type in the ADM
KEYWORDS = {
    Typedef: (AMM_MOD, 'typedef'),
    Const: (AMM_MOD, 'const'),
    Ctrl: (AMM_MOD, 'ctrl'),
    Edd: (AMM_MOD, 'edd'),
    Oper: (AMM_MOD, 'oper'),
    Var: (AMM_MOD, 'var'),
}


def attr_to_member(name):
    ''' Convert a JSON attribute name into a valid python instance variable
    name using underscores.
    '''
    return name.replace('-', '_')


class Decoder:
    ''' The decoder portion of this CODEC.
    '''

    def __init__(self, modpath: List[str], db_sess=None):
        self._db_sess = db_sess
        
        # Initializer copied from pyang.scripts.pyang_tool.run()
        plugindirs = [os.path.join(SELFDIR, 'pyang')]
        pyang.plugin.init(plugindirs)

        import optparse
        optparser = optparse.OptionParser('', add_help_option=False)
        optparser.version = '%prog ' + pyang.__version__
        for p in pyang.plugin.plugins:
            p.add_opts(optparser)
        (opts, args) = optparser.parse_args([])

        path = os.pathsep.join(modpath)
        repos = pyang.repository.FileRepository(path, verbose=True)
        self._ctx = pyang.context.Context(repos)
        self._ctx.strict = True
        self._ctx.opts = opts
        for p in pyang.plugin.plugins:
            p.setup_ctx(self._ctx)
            p.pre_load_modules(self._ctx)

    def _get_semtype(self, stmt):
        TYPE_KYWDS = (
            (AMM_MOD, 'type'),
            (AMM_MOD, 'ulist'),
            (AMM_MOD, 'dlist'),
            (AMM_MOD, 'umap'),
            (AMM_MOD, 'tblt'),
            (AMM_MOD, 'union'),
        )
        TYPE_REFINE_KWDS = (
            'length',
            'pattern',
            'range',
            (AMM_MOD, 'int-labels'),
            (AMM_MOD, 'cddl'),
        )

        # Only one type statement is valid
        found_types = list(filter(
            None,
            [
                stmt.search_one(kywd)
                for kywd in TYPE_KYWDS
            ]
        ))
        if not found_types:
            raise RuntimeError('No type present where required')
        elif len(found_types) > 1:
            raise RuntimeError('Too many types present where one required')
        type_stmt = found_types[0]
        kywd_name = type_stmt.keyword[1]

        # Process refining substatements
        if kywd_name == 'type':
            refinements = list(filter(None, [
                type_stmt.search_one(kywd)
                for kywd in TYPE_REFINE_KWDS
            ]))
            if not refinements:
                # Unrefined type use
                if ':' in type_stmt.arg:
                    admname, typename = type_stmt.arg.split(':', 2)
                    semtype = (
                        self._db_sess.query(SemType)
                            .join(Typedef).join(AdmFile)
                            .filter(
                                AdmFile.name == admname,
                                Typedef.name == typename
                            )
                    ).one_or_none()
                    print('no refinement on typedef', type_stmt.arg, semtype)
                else:
                    print('no refinement on built-in', type_stmt.arg)
            print(stmt, refinements)

        elif kywd_name == 'tblt':
            key_stmt = type_stmt.search_one((AMM_MOD, 'key'))
            column_stmts = type_stmt.search((AMM_MOD, 'column'))
            print(stmt, key_stmt, column_stmts)

    def from_stmt(self, cls, stmt):
        ''' Construct an ORM object from a decoded YANG statement.

        :param cls: The ORM class to instantiate.
        :param stmt: The decoded YANG to read from.
        :return: The ORM object.
        '''
        desc = pyang.statements.get_description(stmt)
        if desc:
            desc = re.sub(r'[\r\n]+s*', ' ', desc)

        obj = cls(
            name=stmt.arg,
            description=desc
        )
    
        if cls in (Const, Edd, Var):
            obj.type = self._get_semtype(stmt)
    
        '''
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
            '''

        return obj

    def get_file_time(self, file_path: str):
        ''' Get a consistent file modified time.

        :param file_path: The pathto the file to inspect.
        :return: The modified time object.
        :rtype: :class:`datetime.dateteime`
        '''
        return datetime.fromtimestamp(os.path.getmtime(file_path))

    def _get_section(self, obj_list, orm_cls, module):
        ''' Extract a section from the file '''
        sec_kywd = KEYWORDS[orm_cls]

        enum = 0
        for yang_stmt in module.search(sec_kywd):
            obj = self.from_stmt(orm_cls, yang_stmt)
            # set derived attributes based on context
            if obj.name is not None:
                obj.norm_name = normalize_ident(obj.name)

            # FIXME: check for duplicates
            if obj.enum is None:
                obj.enum = enum
            enum += 1

            obj_list.append(obj)

    def decode(self, buf: TextIO) -> AdmFile:
        ''' Decode a single ADM from file.

        :param buf: The buffer to read from.
        :return: The decoded ORM root object.
        '''
        file_path = buf.name if hasattr(buf, 'name') else None
        module = self._ctx.add_module(file_path, buf.read(), primary_module=True)
        LOGGER.debug('Loaded %s', module)
        modules = [module]
        
        # Same post-load steps from pyang

        for p in pyang.plugin.plugins:
            p.pre_validate_ctx(self._ctx, modules)

        # for obj in xform_and_emit_objs:
        #     obj.pre_validate(ctx, modules)

        self._ctx.validate()
        for m_ in modules:
            m_.prune()

        for p in pyang.plugin.plugins:
            p.post_validate_ctx(self._ctx, modules)

        self._ctx.errors.sort(key=lambda e: (e[0].ref, e[0].line))
        for epos, etag, eargs in self._ctx.errors:
            elevel = pyang.error.err_level(etag)
            if pyang.error.is_warning(elevel):
                kind = logging.WARNING
            else:
                kind = logging.ERROR
            emsg = pyang.error.err_to_str(etag, eargs)
            LOGGER.log(kind, '%s: %s', epos.label(True), emsg)

        adm = AdmFile()

        if hasattr(buf, 'name'):
            adm.abs_file_path = buf.name
            adm.last_modified = self.get_file_time(buf.name)
        
        # Normalize the intrinsic ADM name
        adm.norm_name = normalize_ident(module.arg)
        adm.norm_namespace = adm.adm_ns = adm.norm_name
        
        self._get_section(adm.const, Const, module)
        self._get_section(adm.ctrl, Ctrl, module)
        self._get_section(adm.edd, Edd, module)
        self._get_section(adm.oper, Oper, module)
        self._get_section(adm.var, Var, module)

        return adm


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def encode(self, adm: AdmFile, buf: TextIO, indent=None):
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

        sec_key = KEYWORDS[orm_cls]
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
