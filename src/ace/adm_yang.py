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
import math
import optparse
import os
from typing import TextIO, Tuple
import portion
import pyang.plugin
import pyang.context
import pyang.repository
import pyang.syntax
import pyang.translators.yang
from ace import ari_text
from ace.ari import ARI, ReferenceARI
from ace.typing import (
    Length, Pattern, Range,
    SemType, TypeUse, TypeUnion, UniformList, DiverseList,
    UniformMap, TableTemplate, TableColumn, Sequence
)
from ace.models import (
    TypeNameList, TypeNameItem,
    MetadataList, MetadataItem, AdmRevision, Feature,
    AdmSource, AdmModule, AdmImport, ParamMixin, TypeUseMixin, AdmObjMixin,
    Typedef, Const, Ctrl, Edd, Oper, Var
)
from ace.util import normalize_ident

LOGGER = logging.getLogger(__name__)

SELFDIR = os.path.dirname(__file__)
''' Directory containing this file '''

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


def range_from_text(text:str) -> portion.Interval:
    ''' Parse a YANG "range" statement argument.
    '''
    parts = [part.strip() for part in text.split('|')]

    def from_num(text:str):
        try:
            return int(text)
        except (ValueError, OverflowError):
            return float(text)

    ranges = portion.Interval()
    for part in parts:
        if '..' in part:
            lower, upper = part.split('..', 2)
            if lower == 'min':
                lower = -float('inf')
            if upper == 'max':
                upper = float('inf')
            ranges |= portion.closed(from_num(lower), from_num(upper))
        else:
            ranges |= portion.singleton(from_num(part))

    return ranges


def range_to_text(ranges:portion.Interval) -> str:
    ''' Construct a YANG "range" statement argument.
    '''
    parts = []
    for port in ranges:
        if port.lower == port.upper:
            parts.append(f'{port.lower}')
        else:
            lower = 'min' if math.isinf(port.lower) else port.lower
            upper = 'max' if math.isinf(port.upper) else port.upper
            parts.append(f'{lower}..{upper}')

    return ' | '.join(parts)


class EmptyRepos(pyang.repository.Repository):

    def get_modules_and_revisions(self, ctx):
        return []


class Decoder:
    ''' The decoder portion of this CODEC.
    '''

    def __init__(self, repos:pyang.repository.Repository):
        # Initializer copied from pyang.scripts.pyang_tool.run()
        if not pyang.plugin.plugins:
            plugindirs = [os.path.join(SELFDIR, 'pyang')]
            pyang.plugin.init(plugindirs)

        optparser = optparse.OptionParser('', add_help_option=False)
        for p in pyang.plugin.plugins:
            p.add_opts(optparser)
        (opts, _args) = optparser.parse_args([])

        self._ctx = pyang.context.Context(repos)
        self._ctx.strict = True
        self._ctx.opts = opts
        for p in pyang.plugin.plugins:
            p.setup_ctx(self._ctx)
            p.pre_load_modules(self._ctx)

        self._ari_dec = ari_text.Decoder()

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
            (AMM_MOD, 'seq'): self._handle_seq,
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
        LOGGER.debug('Got type for %s: %s', type_stmt.keyword, typeobj)
        return typeobj

    _TYPE_REFINE_KWDS = (
        'units',
        'length',
        'pattern',
        'range',
        (AMM_MOD, 'int-labels'),
        (AMM_MOD, 'cddl'),
    )

    def _check_ari(self, ari:ARI):
        ''' Verify ARI references only imported modules. '''
        if isinstance(ari, ReferenceARI):
            imports = [mod[0] for mod in self._module.i_prefixes.values()]
            if ari.ident.ns_id is not None and ari.ident.ns_id not in imports:
                raise ValueError(f'ARI references module {ari.ident.ns_id} that is not imported')

    def _get_namespace(self, text:str) -> Tuple[str, str]:
        ''' Resolve a possibly qualified identifier into a module name and statement name.
        '''
        if ':' in text:
            adm_prefix, stmt_name = text.split(':', 2)
            # resolve yang prefix to module name
            stmt_ns = self._module.i_prefixes[adm_prefix][0]  # Just the module name, not revision
            stmt_ns = normalize_ident(stmt_ns)
            stmt_name = normalize_ident(stmt_name)
        else:
            stmt_ns = None
            stmt_name = normalize_ident(text)
        return (stmt_ns, stmt_name)

    def _handle_type(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = TypeUse()

        typeobj.type_ns, typeobj.type_name = self._get_namespace(stmt.arg)

        # keep constraints in the same order as refinement statements
        refinements = list(filter(None, [
            search_one_exp(stmt, kywd)
            for kywd in self._TYPE_REFINE_KWDS
        ]))
        for rfn in refinements:
            if rfn.keyword == 'units':
                typeobj.units = rfn.arg.strip()
            elif rfn.keyword == 'length':
                ranges = range_from_text(rfn.arg)
                typeobj.constraints.append(Length(ranges=ranges))
            elif rfn.keyword == 'pattern':
                typeobj.constraints.append(Pattern(pattern=rfn.arg))
            elif rfn.keyword == 'range':
                ranges = range_from_text(rfn.arg)
                typeobj.constraints.append(Range(ranges=ranges))

        return typeobj

    def _handle_ulist(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = UniformList(
            base=self._get_typeobj(stmt)
        )

        size_stmt = search_one_exp(stmt, 'min-elements')
        if size_stmt:
            typeobj.min_elements = int(size_stmt.arg)

        size_stmt = search_one_exp(stmt, 'max-elements')
        if size_stmt:
            typeobj.max_elements = int(size_stmt.arg)

        return typeobj

    def _handle_dlist(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = DiverseList(
            parts=[],  # FIXME populate
        )
        return typeobj

    def _handle_umap(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = UniformMap()

        sub_stmt = search_one_exp(stmt, (AMM_MOD, 'keys'))
        if sub_stmt:
            typeobj.kbase = self._get_typeobj(sub_stmt)

        sub_stmt = search_one_exp(stmt, (AMM_MOD, 'values'))
        if sub_stmt:
            typeobj.vbase = self._get_typeobj(sub_stmt)

        return typeobj

    def _handle_tblt(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = TableTemplate()

        col_names = set()
        for col_stmt in search_all_exp(stmt, (AMM_MOD, 'column')):
            col = TableColumn(
                name=col_stmt.arg,
                base=self._get_typeobj(col_stmt)
            )
            if isinstance(col.base, TableTemplate):
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
        found_type_stmts = [
            type_stmt for type_stmt in stmt.substmts
            if type_stmt.keyword in self._type_handlers
        ]

        types = []
        for type_stmt in found_type_stmts:
            subtype = self._type_handlers[type_stmt.keyword](type_stmt)
            types.append(subtype)

        return TypeUnion(types=tuple(types))

    def _handle_seq(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = Sequence(
            base=self._get_typeobj(stmt)
        )

        size_stmt = search_one_exp(stmt, 'min-elements')
        if size_stmt:
            typeobj.min_elements = int(size_stmt.arg)

        size_stmt = search_one_exp(stmt, 'max-elements')
        if size_stmt:
            typeobj.max_elements = int(size_stmt.arg)

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

            feat_stmt = search_one_exp(stmt, 'if-feature')
            if feat_stmt:
                expr = pyang.syntax.parse_if_feature_expr(feat_stmt.arg)

                def resolve(val):
                    ''' resolve import prefix to module name '''
                    if isinstance(val, str):
                        return self._get_namespace(val)
                    else:
                        op, arg1, arg2 = val
                        arg1 = resolve(arg1)
                        arg2 = resolve(arg2)
                        return (op, arg1, arg2)

                obj.if_feature_expr = resolve(expr)

        if issubclass(cls, ParamMixin):
            orm_val = TypeNameList()
            for param_stmt in search_all_exp(stmt, (AMM_MOD, 'parameter')):
                item = TypeNameItem(
                    name=param_stmt.arg,
                    typeobj=self._get_typeobj(param_stmt)
                )
                def_stmt = search_one_exp(param_stmt, (AMM_MOD, 'default'))
                if def_stmt:
                    item.default_value = def_stmt.arg
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

                # actually check the content
                ari = self._ari_dec.decode(io.StringIO(value_stmt.arg))
                ari.visit(self._check_ari)

        elif issubclass(cls, Ctrl):
            result_stmt = search_one_exp(stmt, (AMM_MOD, 'result'))
            if result_stmt:
                obj.result = TypeNameItem(
                    name=result_stmt.arg,
                    typeobj=self._get_typeobj(result_stmt)
                )

        elif issubclass(cls, Oper):
            obj.operands = TypeNameList()
            for opnd_stmt in search_all_exp(stmt, (AMM_MOD, 'operand')):
                obj.operands.items.append(TypeNameItem(
                    name=opnd_stmt.arg,
                    typeobj=self._get_typeobj(opnd_stmt)
                ))

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

    def decode(self, buf: TextIO) -> AdmModule:
        ''' Decode a single ADM from file.

        :param buf: The buffer to read from.
        :return: The decoded ORM root object.
        '''
        file_path = buf.name if hasattr(buf, 'name') else None
        file_text = buf.read()

        # clear internal cache
        for mod in tuple(self._ctx.modules.values()):
            self._ctx.del_module(mod)

        module = self._ctx.add_module(file_path or '<text>', file_text, primary_module=True)
        LOGGER.debug('Loaded %s', module)
        if module is None:
            raise RuntimeError(f'Failed to load module: {self._ctx.errors}')
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

        # LOGGER.debug('errors: %s', [(e[0].ref, e[0].line) for e in self._ctx.errors])
        self._ctx.errors.sort(key=lambda e: (str(e[0].ref), e[0].line))
        for epos, etag, eargs in self._ctx.errors:
            elevel = pyang.error.err_level(etag)
            if pyang.error.is_warning(elevel):
                kind = logging.WARNING
            else:
                kind = logging.ERROR
            emsg = pyang.error.err_to_str(etag, eargs)
            LOGGER.log(kind, '%s: %s', epos.label(True), emsg)

        src = AdmSource()
        src.file_text = file_text
        if file_path:
            src.abs_file_path = file_path
            src.last_modified = self.get_file_time(file_path)

        adm = AdmModule()
        adm.source = src
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

        optparser = optparse.OptionParser('', add_help_option=False)
        for p in pyang.plugin.plugins:
            p.add_opts(optparser)
        (opts, _args) = optparser.parse_args([])

        # Consistent ordering
        opts.yang_canonical = True

        repos = EmptyRepos()
        self._ctx = pyang.context.Context(repos)
        self._ctx.strict = True
        self._ctx.opts = opts

        self._module = None
        self._denorm_prefixes = None

    def encode(self, adm: AdmModule, buf: TextIO) -> None:
        ''' Decode a single ADM from file.

        :param adm: The ORM root object.
        :param buf: The buffer to write into.
        '''
        module = pyang.statements.new_statement(None, None, None, 'module', adm.name)
        self._module = module
        self._denorm_prefixes = {}

        self._add_substmt(module, 'yang-version', '1.1')
        self._add_substmt(module, 'namespace', f'ari:/{adm.name}/')

        for item in adm.metadata_list.items:
            self._add_substmt(module, item.name, item.arg)

        for imp in adm.imports:
            imp_stmt = self._add_substmt(module, 'import', imp.name)
            self._add_substmt(imp_stmt, 'prefix', imp.prefix)

        # init after local prefix and imports defined
        pyang.statements.v_init_module(self._ctx, module)

        # local bookkeeping
        for prefix, modtup in module.i_prefixes.items():
            modname = modtup[0]
            self._denorm_prefixes[modname] = prefix

        # prefixed keyword after v_init_module
        self._add_substmt(module, (AMM_MOD, 'enum'), str(adm.enum))

        for rev in adm.revisions:
            sub_stmt = self._add_substmt(module, 'revision', rev.name)
            if rev.description:
                self._add_substmt(sub_stmt, 'description', rev.description)

        for feat in adm.feature:
            sub_stmt = self._add_substmt(module, 'feature', feat.name)
            if feat.description:
                self._add_substmt(sub_stmt, 'description', feat.description)

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

    def _denorm_tuple(self, val:Tuple[str, str]) -> Tuple[str, str]:
        prefix, name = val
        if prefix in self._denorm_prefixes:
            prefix = self._denorm_prefixes[prefix]
        return (prefix, name)

    def _add_substmt(self, parent:pyang.statements.Statement, keyword:str, arg:str=None) -> pyang.statements.Statement:
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
            if obj.enum is not None:
                self._add_substmt(obj_stmt, (AMM_MOD, 'enum'), str(obj.enum))
            if obj.description is not None:
                self._add_substmt(obj_stmt, 'description', obj.description)

            if obj.if_feature_expr:

                def construct(item) -> str:
                    if len(item) == 2:
                        ns, name = self._denorm_tuple(item)
                        if ns:
                            return f'{ns}:{name}'
                        else:
                            return name
                    elif len(item) == 3:
                        op, arg1, arg2 = item
                        arg1 = construct(arg1)
                        arg2 = construct(arg2)
                        return f'{arg1} {op} {arg2}'

                self._add_substmt(obj_stmt, 'if-feature', construct(obj.if_feature_expr))

        if issubclass(cls, ParamMixin):
            for param in obj.parameters.items:
                param_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'parameter'), param.name)
                self._put_typeobj(param.typeobj, param_stmt)
                if param.default_value:
                    self._add_substmt(param_stmt, (AMM_MOD, 'default'), param.default_value)

        if issubclass(cls, TypeUseMixin):
            self._put_typeobj(obj.typeobj, obj_stmt)

        if issubclass(cls, (Const, Var)):
            if obj.init_value:
                self._add_substmt(obj_stmt, (AMM_MOD, 'init-value'), obj.init_value)

        elif issubclass(cls, Ctrl):
            if obj.result:
                res_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'result'), obj.result.name)
                self._put_typeobj(obj.result.typeobj, res_stmt)

        elif issubclass(cls, Oper):
            for operand in obj.operands.items:
                opnd_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'operand'), operand.name)
                self._put_typeobj(operand.typeobj, opnd_stmt)

            if obj.result:
                res_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'result'), obj.result.name)
                self._put_typeobj(obj.result.typeobj, res_stmt)

        return obj_stmt

    def _put_typeobj(self, typeobj:SemType, parent:pyang.statements.Statement) -> pyang.statements.Statement:
        if isinstance(typeobj, TypeUse):
            if typeobj.type_ns:
                ns, name = self._denorm_tuple((typeobj.type_ns, typeobj.type_name))
                name = f'{ns}:{name}'
            else:
                name = typeobj.type_name
            type_stmt = self._add_substmt(parent, (AMM_MOD, 'type'), name)

            if typeobj.units:
                self._add_substmt(type_stmt, 'units', typeobj.units)

            for cnst in typeobj.constraints:
                if isinstance(cnst, Length):
                    self._add_substmt(type_stmt, 'length', range_to_text(cnst.ranges))
                elif isinstance(cnst, Pattern):
                    self._add_substmt(type_stmt, 'pattern', cnst.pattern)
                elif isinstance(cnst, Range):
                    self._add_substmt(type_stmt, 'range', range_to_text(cnst.ranges))

        elif isinstance(typeobj, UniformList):
            ulist_stmt = self._add_substmt(parent, (AMM_MOD, 'ulist'))
            self._put_typeobj(typeobj.base, ulist_stmt)

            if typeobj.min_elements is not None:
                self._add_substmt(ulist_stmt, 'min-elements', str(typeobj.min_elements))
            if typeobj.max_elements is not None:
                self._add_substmt(ulist_stmt, 'max-elements', str(typeobj.max_elements))

        elif isinstance(typeobj, DiverseList):
            dlist_stmt = self._add_substmt(parent, (AMM_MOD, 'dlist'))

            for part in typeobj.parts:
                self._put_typeobj(part, dlist_stmt)

        elif isinstance(typeobj, UniformMap):
            umap_stmt = self._add_substmt(parent, (AMM_MOD, 'umap'))

            if typeobj.kbase:
                sub_stmt = self._add_substmt(umap_stmt, (AMM_MOD, 'keys'))
                self._put_typeobj(typeobj.kbase, sub_stmt)

            if typeobj.vbase:
                sub_stmt = self._add_substmt(umap_stmt, (AMM_MOD, 'values'))
                self._put_typeobj(typeobj.vbase, sub_stmt)

        elif isinstance(typeobj, TableTemplate):
            tblt_stmt = self._add_substmt(parent, (AMM_MOD, 'tblt'))

            for col in typeobj.columns:
                col_stmt = self._add_substmt(tblt_stmt, (AMM_MOD, 'column'), col.name)
                self._put_typeobj(col.base, col_stmt)

            if typeobj.key is not None:
                self._add_substmt(tblt_stmt, (AMM_MOD, 'key'), typeobj.key)
            for uniq in typeobj.unique:
                self._add_substmt(tblt_stmt, (AMM_MOD, 'unique'), uniq)

        elif isinstance(typeobj, TypeUnion):
            union_stmt = self._add_substmt(parent, (AMM_MOD, 'union'))

            for sub in typeobj.types:
                self._put_typeobj(sub, union_stmt)

        elif isinstance(typeobj, Sequence):
            seq_stmt = self._add_substmt(parent, (AMM_MOD, 'seq'))
            self._put_typeobj(typeobj.base, seq_stmt)

            if typeobj.min_elements is not None:
                self._add_substmt(seq_stmt, 'min-elements', str(typeobj.min_elements))
            if typeobj.max_elements is not None:
                self._add_substmt(seq_stmt, 'max-elements', str(typeobj.max_elements))

        else:
            raise TypeError(f'Unhandled type object: {typeobj}')
