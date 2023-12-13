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
import logging
import optparse
import os
from typing import TextIO, List
import pyang.plugin
import pyang.context
import pyang.repository
import pyang.translators.yang
from ace.models import (
    TypeNameList, TypeNameItem,
    MetadataList, MetadataItem, AdmRevision, Feature,
    AdmFile, AdmImport, ParamMixin, TypeUseMixin, AdmObjMixin,
    Typedef, Const, Ctrl, Edd, Oper, Var
)
from ace.typing import (
    SemType, TypeUse, TypeUnion, UniformList, TableTemplate, TableColumn
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


def search_one_exp(stmt, kywd):
    ''' Search-one within uses-expanded substatements. '''
    found = stmt.search_one(kywd)
    if found is not None:
        return found
    subs = getattr(stmt, 'i_children', None)
    return stmt.search_one(kywd, children=subs)


def search_all_exp(stmt, kywd):
    ''' Search-one within uses-expanded substatements. '''
    # FIXME combine substatemnts with children
    # found = stmt.search(kywd)

    subs = getattr(stmt, 'i_children', None)
    return stmt.search(kywd, children=subs)


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

        self._type_handlers = {
            (AMM_MOD, 'type'): self._handle_type,
            (AMM_MOD, 'ulist'): self._handle_ulist,
            (AMM_MOD, 'dlist'): self._handle_dlist,
            (AMM_MOD, 'umap'): self._handle_umap,
            (AMM_MOD, 'tblt'): self._handle_tblt,
            (AMM_MOD, 'union'): self._handle_union,
        }

    def _get_typeobj(self, parent: pyang.statements.Statement) -> SemType:
        # Only one type statement is valid
        found_type_stmts = [
            type_stmt for type_stmt in parent.substmts
            if type_stmt.keyword in self._type_handlers
        ]
        if not found_type_stmts:
            raise RuntimeError('No type present where required')
        elif len(found_type_stmts) > 1:
            raise RuntimeError('Too many types present where one required')
        type_stmt = found_type_stmts[0]

        typeobj = self._type_handlers[type_stmt.keyword](type_stmt)
        LOGGER.debug('Got type %s', typeobj)
        return typeobj

    _TYPE_REFINE_KWDS = (
        'units',
        'length',
        'pattern',
        'range',
        (AMM_MOD, 'int-labels'),
        (AMM_MOD, 'cddl'),
    )

    def _handle_type(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = TypeUse()

        if ':' in stmt.arg:
            adm_prefix, type_name = stmt.arg.split(':', 2)
            # resolve yang prefix to module name
            type_ns = self._module.i_prefixes[adm_prefix][0]  # Just the module name, not revision
            typeobj.type_ns = normalize_ident(type_ns)
            typeobj.type_name = normalize_ident(type_name)
        else:
            typeobj.type_name = normalize_ident(stmt.arg)

        refinements = list(filter(None, [
            search_one_exp(stmt, kywd)
            for kywd in self._TYPE_REFINE_KWDS
        ]))
        for rfn in refinements:
            if rfn.keyword == 'units':
                typeobj.units = rfn.arg.strip()
            elif rfn.keyword == 'length':
                pass  # FIXME
            elif rfn.keyword == 'pattern':
                pass  # FIXME
            elif rfn.keyword == 'range':
                pass  # FIXME

        return typeobj

    def _handle_ulist(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = UniformList(
            type=self._get_typeobj(stmt)
        )
        return typeobj

    def _handle_dlist(self, stmt:pyang.statements.Statement) -> SemType:
        pass

    def _handle_umap(self, stmt:pyang.statements.Statement) -> SemType:
        pass

    def _handle_tblt(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = TableTemplate()

        col_names = set()
        for col_stmt in search_all_exp(stmt, (AMM_MOD, 'column')):
            col = TableColumn(
                name=col_stmt.arg,
                type=self._get_typeobj(col_stmt)
            )
            if isinstance(col.type, TableTemplate):
                LOGGER.warn('A table column is typed to contain another table')
            if col.name in col_names:
                LOGGER.warn('A duplicate column name is present: %s', col)

            typeobj.columns.append(col)
            col_names.add(col.name)

        key_stmt = search_one_exp(stmt, (AMM_MOD, 'key'))
        if key_stmt:
            typeobj.key = key_stmt.arg

        for unique_stmt in search_all_exp(stmt, (AMM_MOD, 'unique')):
            col_names = [
                name.strip()
                for name in unique_stmt.arg.split(',')
            ]
            typeobj.unique.append(col_names)

        return typeobj

    def _handle_union(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = TypeUnion()

        found_type_stmts = [
            type_stmt for type_stmt in stmt.substmts
            if type_stmt.keyword in self._type_handlers
        ]

        for type_stmt in found_type_stmts:
            subtype = self._type_handlers[type_stmt.keyword](type_stmt)
            typeobj.types.append(subtype)

        return typeobj

    def from_stmt(self, cls, stmt:pyang.statements.Statement) -> AdmObjMixin:
        ''' Construct an ORM object from a decoded YANG statement.

        :param cls: The ORM class to instantiate.
        :param stmt: The decoded YANG to read from.
        :return: The ORM object.
        '''
        obj = cls(
            name=stmt.arg,
            description=pyang.statements.get_description(stmt),
        )

        if issubclass(cls, AdmObjMixin):
            obj.norm_name = normalize_ident(obj.name)

            enum_stmt = search_one_exp(stmt, (AMM_MOD, 'enum'))
            if enum_stmt:
                obj.enum = int(enum_stmt.arg)

        if issubclass(cls, ParamMixin):
            orm_val = TypeNameList()
            for param_stmt in search_all_exp(stmt, (AMM_MOD, 'parameter')):
                item = TypeNameItem(
                    name=param_stmt.arg,
                    typeobj=self._get_typeobj(param_stmt)
                )
                orm_val.items.append(item)

            obj.parameters = orm_val

        if issubclass(cls, TypeUseMixin):
            obj.typeobj = self._get_typeobj(stmt)

        if issubclass(cls, (Const, Var)):
            value_stmt = search_one_exp(stmt, (AMM_MOD, 'init-value'))
            if not value_stmt:
                LOGGER.warning('const is missing init-value substatement')
            else:
                obj.init_value = value_stmt.arg

        elif issubclass(cls, Ctrl):
            result_stmt = search_one_exp(stmt, (AMM_MOD, 'result'))
            if result_stmt:
                obj.result = TypeNameItem(
                    name=result_stmt.arg,
                    typeobj=self._get_typeobj(result_stmt)
                )

        elif issubclass(cls, Oper):
            # FIXME populate these
            obj.operands = TypeNameList()

            result_stmt = search_one_exp(stmt, (AMM_MOD, 'result'))
            if result_stmt:
                obj.result = TypeNameItem(
                    name=result_stmt.arg,
                    typeobj=self._get_typeobj(result_stmt)
                )

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
        for yang_stmt in search_all_exp(module, sec_kywd):
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

        for sub_stmt in module.search('import'):
            prefix_stmt = search_one_exp(sub_stmt, 'prefix')
            adm.imports.append(AdmImport(
                name=sub_stmt.arg,
                prefix=prefix_stmt.arg,
            ))

        adm.metadata_list = MetadataList()
        for kywd in MOD_META_KYWDS:
            meta_stmt = search_one_exp(module, kywd)
            if meta_stmt:
                adm.metadata_list.items.append(MetadataItem(
                    name=meta_stmt.keyword,
                    arg=meta_stmt.arg,
                ))

        for sub_stmt in module.search('revision'):
            adm.revisions.append(AdmRevision(
                name=sub_stmt.arg,
                description=pyang.statements.get_description(sub_stmt),
            ))

        for sub_stmt in module.search('feature'):
            adm.feature.append(Feature(
                name=sub_stmt.arg,
                description=pyang.statements.get_description(sub_stmt),
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

        # Consistent ordering
        opts.yang_canonical = True

        path = os.pathsep.join(modpath)
        repos = pyang.repository.FileRepository(path, verbose=True)
        self._ctx = pyang.context.Context(repos)
        self._ctx.strict = True
        self._ctx.opts = opts

        self._module = None
        self._denorm_prefixes = None

    def encode(self, adm: AdmFile, buf: TextIO):
        ''' Decode a single ADM from file.

        :param adm: The ORM root object.
        :param buf: The buffer to write into.
        '''
        module = pyang.statements.new_statement(None, None, None, 'module', adm.name)
        pyang.statements.v_init_module(self._ctx, module)
        self._module = module
        self._denorm_prefixes = {}

        self._add_substmt(module, 'namespace', f'ari:/{adm.name}/')
        self._add_substmt(module, (AMM_MOD, 'enum'), str(adm.enum))

        for imp in adm.imports:
            imp_stmt = self._add_substmt(module, 'import', imp.name)
            self._add_substmt(imp_stmt, 'prefix', imp.prefix)

            # local bookkeeping
            module.i_prefixes[imp.prefix] = imp.name
            self._denorm_prefixes[imp.name] = imp.prefix

        for item in adm.metadata_list.items:
            self._add_substmt(module, item.name, item.arg)

        for rev in adm.revisions:
            rev_stmt = self._add_substmt(module, 'revision', rev.name)
            if rev.description:
                self._add_substmt(rev_stmt, 'description', rev.description)

        for feat in adm.feature:
            rev_stmt = self._add_substmt(module, 'feature', feat.name)
            if feat.description:
                self._add_substmt(rev_stmt, 'description', feat.description)

        self._put_section(adm.typedef, Typedef, module)
        self._put_section(adm.const, Const, module)
        self._put_section(adm.edd, Edd, module)
        self._put_section(adm.var, Var, module)
        self._put_section(adm.ctrl, Ctrl, module)
        self._put_section(adm.oper, Oper, module)

        def denorm(stmt):
            if pyang.util.is_prefixed(stmt.raw_keyword):
                stmt.raw_keyword = self._denorm_tuple(stmt.raw_keyword)

            for sub_stmt in stmt.substmts:
                denorm(sub_stmt)

        denorm(module)

        pyang.translators.yang.emit_yang(self._ctx, module, buf)
        self._module = None
        self._denorm_prefixes = None

    def _denorm_tuple(self, val):
        prefix, name = val
        if prefix in self._denorm_prefixes:
            prefix = self._denorm_prefixes[prefix]
        return (prefix, name)

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

        if issubclass(cls, AdmObjMixin):
            if obj.enum:
                self._add_substmt(obj_stmt, (AMM_MOD, 'enum'), str(obj.enum))
            if obj.description:
                self._add_substmt(obj_stmt, 'description', obj.description)
            if obj.if_feature_expr:
                self._add_substmt(obj_stmt, 'if-feature', obj.if_feature_expr)

        if issubclass(cls, ParamMixin):
            for param in obj.parameters.items:
                param_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'parameter'), param.name)
                self._put_typeuse(param, param_stmt)

        if issubclass(cls, TypeUseMixin):
            self._put_typeuse(obj, obj_stmt)

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
        print('use', obj.typeobj)
        if isinstance(obj.typeobj, TypeUse):
            if obj.typeobj.type_name:
                if obj.typeobj.type_ns:
                    ns, name = self._denorm_tuple((obj.typeobj.type_ns, obj.typeobj.type_name))
                    name = f'{ns}:{name}'
                else:
                    name = obj.typeobj.type_name
                self._add_substmt(parent, (AMM_MOD, 'type'), name)
        else:
            raise TypeError(f'Unhandled type object: {obj.typeobj}')
