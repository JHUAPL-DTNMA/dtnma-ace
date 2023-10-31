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
import optparse
import os
import re
from typing import TextIO, List
import pyang
import pyang.plugin
import pyang.context
import pyang.repository
import pyang.translators.yang
from ace.models import (
    TypeNameList, TypeNameItem, Expr, ARI, AriAP, AC,
    MetadataList, MetadataItem, AdmRevision,
    AdmFile, AdmUses, TypeUse, ParamMixin, TypeUseMixin, AdmObjMixin,
    Typedef, Const, Ctrl, Edd, Oper, Var
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

MOD_META_KYWDS = {
    'prefix',
    'organization',
    'contact',
    'description',
    'reference',
}


class Decoder:
    ''' The decoder portion of this CODEC.
    '''

    def __init__(self, modpath: List[str]=None):
        # Initializer copied from pyang.scripts.pyang_tool.run()
        if not pyang.plugin.plugins:
            plugindirs = [os.path.join(SELFDIR, 'pyang')]
            pyang.plugin.init(plugindirs)

        optparser = optparse.OptionParser('', add_help_option=False)
        for p in pyang.plugin.plugins:
            p.add_opts(optparser)
        (opts, _args) = optparser.parse_args([])

        if not modpath:
            modpath = []
        path = os.pathsep.join(modpath)
        repos = pyang.repository.FileRepository(path, verbose=True)
        self._ctx = pyang.context.Context(repos)
        self._ctx.strict = True
        self._ctx.opts = opts
        for p in pyang.plugin.plugins:
            p.setup_ctx(self._ctx)
            p.pre_load_modules(self._ctx)
        
        # Set to an object while processing a top-level module
        self._module = None
        self._obj_pos = 0

    def _get_typeuse(self, obj: TypeUseMixin, stmt: pyang.statements.Statement):
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
        typeuse = TypeUse()
        if kywd_name == 'type':
            refinements = list(filter(None, [
                type_stmt.search_one(kywd)
                for kywd in TYPE_REFINE_KWDS
            ]))
            if not refinements:
                # Unrefined type use
                if ':' in type_stmt.arg:
                    adm_prefix, type_name = type_stmt.arg.split(':', 2)
                    # resolve yang prefix to module name
                    type_ns = self._module.i_prefixes[adm_prefix]
                    print('no refinement on typedef', type_stmt.arg, type_ns, type_name)
                    typeuse.type_ns = type_ns
                    typeuse.type_name = type_name
                else:
                    print('no refinement on built-in', type_stmt.arg)
                    typeuse.type_name = type_stmt.arg
            else:
                print(stmt, refinements)

        elif kywd_name == 'ulist':
            pass  # FIXME: implement
        elif kywd_name == 'dlist':
            pass  # FIXME: implement
        elif kywd_name == 'umap':
            pass  # FIXME: implement

        elif kywd_name == 'tblt':
            key_stmt = type_stmt.search_one((AMM_MOD, 'key'))
            column_stmts = type_stmt.search((AMM_MOD, 'column'))
            print(stmt, key_stmt, column_stmts)

        elif kywd_name == 'union':
            pass  # FIXME: implement
        
        obj.typeuse = typeuse

    def from_stmt(self, cls, stmt:pyang.statements.Statement) -> AdmObjMixin:
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

        if issubclass(cls, AdmObjMixin):
            obj.norm_name = normalize_ident(obj.name)
            
            enum_stmt = stmt.search_one((AMM_MOD, 'enum'))
            if enum_stmt:
                obj.enum = int(enum_stmt.arg) 

        if issubclass(cls, ParamMixin):
            orm_val = TypeNameList()
            for param_stmt in stmt.search((AMM_MOD, 'parameter')):
                item = TypeNameItem(
                    name=param_stmt.arg,
                )
                self._get_typeuse(item, param_stmt)
                orm_val.items.append(item)
            
            obj.parameters = orm_val

        if issubclass(cls, TypeUseMixin):
            self._get_typeuse(obj, stmt)

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

        module = self._ctx.add_module(file_path or '<text>', buf.read(), primary_module=True)
        LOGGER.debug('Loaded %s', module)
        self._module = module
        self._obj_pos = 0
        
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

        if file_path:
            adm.abs_file_path = file_path
            adm.last_modified = self.get_file_time(file_path)
        
        adm.name = module.arg
        # Normalize the intrinsic ADM name
        adm.norm_name = normalize_ident(adm.name)

        enum_stmt = module.search_one((AMM_MOD, 'enum'))
        if enum_stmt:
            adm.enum = int(enum_stmt.arg) 

        adm.metadata_list = MetadataList()
        for kywd in MOD_META_KYWDS:
            meta_stmt = module.search_one(kywd)
            if meta_stmt:
                adm.metadata_list.items.append(MetadataItem(
                    name=meta_stmt.keyword,
                    arg=meta_stmt.arg,
                ))

        for rev_stmt in module.search('revision'):
            desc = pyang.statements.get_description(rev_stmt)
            ref_stmt = rev_stmt.search_one('reference')
            adm.revisions.append(AdmRevision(
                name=rev_stmt.arg,
                description=desc,
                reference=(ref_stmt.arg if ref_stmt else None)
            ))

        self._get_section(adm.typedef, Typedef, module)
        self._get_section(adm.const, Const, module)
        self._get_section(adm.ctrl, Ctrl, module)
        self._get_section(adm.edd, Edd, module)
        self._get_section(adm.oper, Oper, module)
        self._get_section(adm.var, Var, module)

        self._module = None
        return adm


class Encoder:
    ''' The encoder portion of this CODEC. '''

    def __init__(self):
        modpath = []
        
        optparser = optparse.OptionParser('', add_help_option=False)
        for p in pyang.plugin.plugins:
            p.add_opts(optparser)
        (opts, _args) = optparser.parse_args([])

        # opts.yang_canonical = True

        path = os.pathsep.join(modpath)
        repos = pyang.repository.FileRepository(path, verbose=True)
        self._ctx = pyang.context.Context(repos)
        self._ctx.strict = True
        self._ctx.opts = opts

        self._module = None

    def encode(self, adm: AdmFile, buf: TextIO):
        ''' Decode a single ADM from file.

        :param adm: The ORM root object.
        :param buf: The buffer to write into.
        '''
        module = pyang.statements.new_statement(None, None, None, 'module', adm.name)
        pyang.statements.v_init_module(self._ctx, module)
        self._module = module

        self._add_substmt(module, 'namespace', f'ari:/{adm.name}/')
        self._add_substmt(module, (AMM_MOD, 'enum'), str(adm.enum))

        imp_stmt = self._add_substmt(module, 'import', 'ietf-amm')
        self._add_substmt(imp_stmt, 'prefix', 'amm')
        module.i_prefixes['amm'] = 'ietf-amm'
        denorm_prefixes = {}
        denorm_prefixes['ietf-amm'] = 'amm'

        for item in adm.metadata_list.items:
            self._add_substmt(module, item.name, item.arg)

        for rev in adm.revisions:
            rev_stmt = self._add_substmt(module, 'revision', rev.name)
            if rev.description:
                self._add_substmt(rev_stmt, 'description', rev.description)
            if rev.reference:
                self._add_substmt(rev_stmt, 'reference', rev.reference)

        self._put_section(adm.typedef, Typedef, module)
        self._put_section(adm.const, Const, module)
        self._put_section(adm.edd, Edd, module)
        self._put_section(adm.var, Var, module)
        self._put_section(adm.ctrl, Ctrl, module)
        self._put_section(adm.oper, Oper, module)

        def denorm(stmt):
            if pyang.util.is_prefixed(stmt.raw_keyword):
                prefix, name = stmt.raw_keyword
                if prefix in denorm_prefixes:
                    stmt.raw_keyword = (denorm_prefixes[prefix], name)

            for sub_stmt in stmt.substmts:
                denorm(sub_stmt)

        denorm(module)

        pyang.translators.yang.emit_yang(self._ctx, module, buf)
        self._module = None

    def _add_substmt(self, parent, keyword, arg=None):
        sub_stmt = pyang.statements.new_statement(self._module, parent, None, keyword, arg)
        parent.substmts.append(sub_stmt)
        return sub_stmt

    def _put_section(self, obj_list, orm_cls, module:pyang.statements.ModSubmodStatement):
        ''' Insert a section to the file '''
        for obj in obj_list:
            self.to_stmt(obj, module)

    def to_stmt(self, obj:AdmObjMixin, module) -> pyang.statements.Statement:
        ''' Construct a YANG statement from an ORM object.

        :param obj: The ORM object to read from.
        :return: The pyang object.
        '''
        cls = type(obj)
        kywd = KEYWORDS[cls]
        obj_stmt = self._add_substmt(module, kywd, obj.name)

        if issubclass(cls, ParamMixin):
            for param in obj.parameters.items:
                param_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'parameter'), param.name)
                self._put_typeuse(param, param_stmt)

        if issubclass(cls, TypeUseMixin):
            self._put_typeuse(obj, obj_stmt)

        if issubclass(cls, AdmObjMixin):
            self._add_substmt(obj_stmt, 'description', obj.description)
            
            if obj.enum:
                self._add_substmt(obj_stmt, (AMM_MOD, 'enum'), str(obj.enum))

        '''
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
        '''

        return obj_stmt

    def _put_typeuse(self, obj:TypeUseMixin, parent:pyang.statements.Statement) -> pyang.statements.Statement:
        print('use', obj.typeuse)
        if obj.typeuse.type_name:
            if obj.typeuse.type_ns:
                name = f'{obj.typeuse.type_ns}:{obj.typeuse.type_name}'
            else:
                name = obj.typeuse.type_name
            self._add_substmt(parent, (AMM_MOD, 'type'), name)
