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
''' CODEC for converting ADM to and from YANG form.
'''

from datetime import datetime, date
import io
import logging
import math
import optparse
import os
from typing import TextIO, Tuple, Union
import portion
import pyang.plugin
import pyang.context
import pyang.repository
import pyang.syntax
import pyang.translators.yang
from ace import ari_text
from ace.ari import ARI, LiteralARI, ReferenceARI, StructType
from ace.typing import (
    SemType, TypeUse, TypeUnion, UniformList, DiverseList,
    UniformMap, TableTemplate, TableColumn, Sequence
)
from ace.type_constraint import (
    StringLength, TextPattern, NumericRange, IntegerEnums, IntegerBits,
    CborCddl, IdentRefBase,
)
from ace.lookup import RelativeResolver
from ace.models import (
    TypeNameList, TypeNameItem,
    MetadataList, MetadataItem, AdmRevision, Feature,
    AdmSource, AdmModule, AdmImport, ParamMixin, TypeUseMixin, AdmObjMixin,
    Typedef, Ident, IdentBase, Const, Ctrl, Edd, Oper, Var, Sbr, Tbr
)
from ace.util import normalize_ident

LOGGER = logging.getLogger(__name__)

SELFDIR = os.path.dirname(__file__)
''' Directory containing this file '''

AMM_MOD = 'ietf-amm'

# : YANG keyword for each object type in the ADM
KEYWORDS = {
    Typedef: (AMM_MOD, 'typedef'),
    Ident: (AMM_MOD, 'ident'),
    Const: (AMM_MOD, 'const'),
    Ctrl: (AMM_MOD, 'ctrl'),
    Edd: (AMM_MOD, 'edd'),
    Oper: (AMM_MOD, 'oper'),
    Var: (AMM_MOD, 'var'),
    Sbr: (AMM_MOD, 'sbr'),
    Tbr: (AMM_MOD, 'tbr'),
}

MOD_META_KYWDS = {
    'prefix',
    'organization',
    'contact',
    'description',
    'reference',
}


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


class AriTextDecoder:
    ''' Wrapper for :cls:`ari_text.Decoder` '''

    def __init__(self):
        self._ari_dec = ari_text.Decoder()
        self._ns_id = None

    def set_namespace(self, org_id: Union[str, int], model_id: Union[str, int]):
        ''' Set the ID of the current ADM for resolving relative ARIs.
        '''
        self._ns_id = (org_id, model_id)

    def decode(self, text:str) -> ARI:
        ''' Decode ARI text and resolve any relative reference.
        '''
        ari = self._ari_dec.decode(io.StringIO(text))
        if self._ns_id is not None:
            ari = ari.map(RelativeResolver(*self._ns_id))
        return ari


class TypingDecoder:
    ''' Decoder for just semantic typing structures. '''

    _TYPE_REFINE_KWDS = (
        'units',
        'length',
        'pattern',
        'range',
        (AMM_MOD, 'int-labels'),
        (AMM_MOD, 'cddl'),
        (AMM_MOD, 'base'),
    )

    def __init__(self, ari_dec: AriTextDecoder):
        self._type_handlers = {
            (AMM_MOD, 'type'): self._handle_type,
            (AMM_MOD, 'ulist'): self._handle_ulist,
            (AMM_MOD, 'dlist'): self._handle_dlist,
            (AMM_MOD, 'umap'): self._handle_umap,
            (AMM_MOD, 'tblt'): self._handle_tblt,
            (AMM_MOD, 'union'): self._handle_union,
            (AMM_MOD, 'seq'): self._handle_seq,
        }
        self._ari_dec = ari_dec

    def _get_ari(self, text:str) -> ARI:
        ''' Decode ARI text and resolve any relative reference.
        '''
        ari = self._ari_dec.decode(text)
        return ari

    def decode(self, parent: pyang.statements.Statement) -> SemType:
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

    def _handle_type(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = TypeUse()

        typeobj.type_text = stmt.arg

        ari = self._get_ari(stmt.arg)
        if not (
            (isinstance(ari, LiteralARI) and ari.type_id == StructType.ARITYPE)
            or (isinstance(ari, ReferenceARI) and ari.ident.type_id == StructType.TYPEDEF)
        ):
            raise ValueError(f'Type reference must be either ARITYPE or LITERAL, got: {stmt.arg}')
        typeobj.type_ari = ari

        # keep constraints in the same order as refinement statements
        refinements = list(filter(None, [
            stmt.search_one(kywd)
            for kywd in self._TYPE_REFINE_KWDS
        ]))
        for rfn in refinements:
            if rfn.keyword == 'units':
                typeobj.units = rfn.arg.strip()
            elif rfn.keyword == 'length':
                ranges = range_from_text(rfn.arg)
                typeobj.constraints.append(StringLength(ranges=ranges))
            elif rfn.keyword == 'pattern':
                typeobj.constraints.append(TextPattern(pattern=rfn.arg))
            elif rfn.keyword == 'range':
                ranges = range_from_text(rfn.arg)
                typeobj.constraints.append(NumericRange(ranges=ranges))
            elif rfn.keyword == (AMM_MOD, 'int-labels'):
                enum_stmts = rfn.search('enum')
                bit_stmts = rfn.search('bit')
                if enum_stmts and bit_stmts:
                    raise RuntimeError('Cannot specify both enum and bit values')
                if enum_stmts:
                    labels = {
                        int(stmt.search_one('value').arg): stmt.arg
                        for stmt in enum_stmts
                    }
                    typeobj.constraints.append(IntegerEnums(values=labels))
                if bit_stmts:
                    labels = {
                        int(stmt.search_one('position').arg): stmt.arg
                        for stmt in bit_stmts
                    }
                    mask = sum((1 << pos) for pos in labels.keys())
                    typeobj.constraints.append(IntegerBits(labels, mask))
            elif rfn.keyword == (AMM_MOD, 'cddl'):
                typeobj.constraints.append(CborCddl(text=rfn.arg))
            elif rfn.keyword == (AMM_MOD, 'base'):
                text = rfn.arg
                ari = self._get_ari(text)
                typeobj.constraints.append(IdentRefBase(
                    base_text=text,
                    base_ari=ari
                ))

        return typeobj

    def _handle_ulist(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = UniformList(
            base=self.decode(stmt)
        )

        size_stmt = stmt.search_one('min-elements')
        if size_stmt:
            typeobj.min_elements = int(size_stmt.arg)

        size_stmt = stmt.search_one('max-elements')
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

        sub_stmt = stmt.search_one((AMM_MOD, 'keys'))
        if sub_stmt:
            typeobj.kbase = self.decode(sub_stmt)

        sub_stmt = stmt.search_one((AMM_MOD, 'values'))
        if sub_stmt:
            typeobj.vbase = self.decode(sub_stmt)

        return typeobj

    def _handle_tblt(self, stmt:pyang.statements.Statement) -> SemType:
        typeobj = TableTemplate()

        col_names = set()
        for col_stmt in stmt.search((AMM_MOD, 'column'), children=stmt.i_children):
            col = TableColumn(
                name=col_stmt.arg,
                base=self.decode(col_stmt)
            )
            if col.name in col_names:
                LOGGER.warn('A duplicate column name is present: %s', col)

            typeobj.columns.append(col)
            col_names.add(col.name)

        key_stmt = stmt.search_one((AMM_MOD, 'key'))
        if key_stmt:
            typeobj.key = key_stmt.arg

        for unique_stmt in stmt.search((AMM_MOD, 'unique')):
            col_names = [
                name.strip()
                for name in unique_stmt.arg.split(',')
            ]
            typeobj.unique.append(col_names)

        size_stmt = stmt.search_one('min-elements')
        if size_stmt:
            typeobj.min_elements = int(size_stmt.arg)

        size_stmt = stmt.search_one('max-elements')
        if size_stmt:
            typeobj.max_elements = int(size_stmt.arg)

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
            base=self.decode(stmt)
        )

        size_stmt = stmt.search_one('min-elements')
        if size_stmt:
            typeobj.min_elements = int(size_stmt.arg)

        size_stmt = stmt.search_one('max-elements')
        if size_stmt:
            typeobj.max_elements = int(size_stmt.arg)

        return typeobj


class EmptyRepos(pyang.repository.Repository):

    def get_modules_and_revisions(self, _ctx:pyang.context.Context):
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

        self._ari_dec = AriTextDecoder()
        self._type_dec = TypingDecoder(self._ari_dec)

        # Set to an object while processing a top-level module
        self._module = None
        self._obj_pos = 0
        self._adm = None

    def _get_typeobj(self, parent: pyang.statements.Statement) -> SemType:
        return self._type_dec.decode(parent)

    def _check_ari(self, ari:ARI):
        ''' Verify ARI references only imported modules. '''
        if isinstance(ari, ReferenceARI):
            if ari.ident.module_name == self._module.arg:
                return
            imports = [mod[0] for mod in self._module.i_prefixes.values()]
            if ari.ident.module_name is not None and ari.ident.module_name not in imports:
                raise ValueError(f'ARI references module {ari.ident.module_name} that is not imported')

    def _get_ari(self, text:str) -> ARI:
        ''' Decode ARI text and resolve any relative reference.
        '''
        ari = self._ari_dec.decode(text)
        ari.visit(self._check_ari)
        return ari

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

            enum_stmt = stmt.search_one((AMM_MOD, 'enum'))
            if enum_stmt:
                obj.enum = int(enum_stmt.arg)

            feat_stmt = stmt.search_one('if-feature')
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
            for param_stmt in stmt.search((AMM_MOD, 'parameter'), children=stmt.i_children):
                try:
                    item = TypeNameItem(
                        name=param_stmt.arg,
                        description=pyang.statements.get_description(param_stmt),
                        typeobj=self._get_typeobj(param_stmt)
                    )

                    def_stmt = param_stmt.search_one((AMM_MOD, 'default'))
                    if def_stmt:
                        item.default_value = def_stmt.arg
                        # actually check the content
                        item.default_ari = self._get_ari(def_stmt.arg)
                except Exception as err:
                    raise RuntimeError(f'Failure handling parameter "{param_stmt.arg}": {err}') from err;

                orm_val.items.append(item)

            obj.parameters = orm_val

        if issubclass(cls, TypeUseMixin):
            obj.typeobj = self._get_typeobj(stmt)

        if issubclass(cls, Ident):
            abs_stmt = stmt.search_one((AMM_MOD, 'abstract'))
            if abs_stmt:
                obj.abstract = (abs_stmt.arg == 'true')

            for base_stmt in stmt.search((AMM_MOD, 'base')):
                base = IdentBase()
                base.base_text = base_stmt.arg
                # actually check the content
                ari = self._get_ari(base_stmt.arg)
                if not (
                    isinstance(ari, ReferenceARI) and ari.ident.type_id == StructType.IDENT
                ):
                    raise ValueError('Ident base must be another Ident')
                base.base_ari = ari

                obj.bases.append(base)

        elif issubclass(cls, (Const, Var)):
            value_stmt = stmt.search_one((AMM_MOD, 'init-value'))
            if value_stmt:
                obj.init_value = value_stmt.arg
                # actually check the content
                obj.init_ari = self._get_ari(value_stmt.arg)
            elif cls is Const:
                LOGGER.warning('const "%s" is missing init-value substatement', stmt.arg)

        elif issubclass(cls, Sbr):
            action_stmt = stmt.search_one((AMM_MOD, 'action'))
            if action_stmt:
                obj.action_value = action_stmt.arg
                obj.action_ari = self._get_ari(action_stmt.arg)
            else:
                LOGGER.warning('sbr "%s" is missing action substatement', stmt.arg)

            condition_stmt = stmt.search_one((AMM_MOD, 'condition'))
            if condition_stmt:
                obj.condition_value = condition_stmt.arg
                obj.condition_ari = self._get_ari(condition_stmt.arg)
            else:
                LOGGER.warning('sbr "%s" is missing condition substatement', stmt.arg)

            min_interval_stmt = stmt.search_one((AMM_MOD, 'min-interval'))
            if min_interval_stmt:
                obj.min_interval_value = min_interval_stmt.arg
                obj.min_interval_ari = self._get_ari(min_interval_stmt.arg)
            else:
                obj.min_interval_value = "/TD/PT0S"  # 0 sec default
                obj.min_interval_ari = self._get_ari(obj.min_interval_value)

            max_count_stmt = stmt.search_one((AMM_MOD, 'max-count'))
            if max_count_stmt:
                obj.max_count = int(max_count_stmt.arg)
            else:
                obj.max_count = 0

            enabled_stmt = stmt.search_one((AMM_MOD, 'init-enabled'))
            if enabled_stmt:
                obj.init_enabled = (enabled_stmt.arg == 'true')
            else:
                obj.init_enabled = True

        elif issubclass(cls, Tbr):
            action_stmt = stmt.search_one((AMM_MOD, 'action'))
            if action_stmt:
                obj.action_value = action_stmt.arg
                obj.action_ari = self._get_ari(action_stmt.arg)
            else:
                LOGGER.warning('tbr "%s" is missing action substatement', stmt.arg)

            period_stmt = stmt.search_one((AMM_MOD, 'period'))
            if period_stmt:
                obj.period_value = period_stmt.arg
                obj.period_ari = self._get_ari(period_stmt.arg)
            else:
                LOGGER.warning('tbr "%s" is missing period substatement', stmt.arg)

            start_stmt = stmt.search_one((AMM_MOD, 'start'))
            if start_stmt:
                obj.start_value = start_stmt.arg
                obj.start_ari = self._get_ari(start_stmt.arg)
            else:
                obj.start_value = "/TD/PT0S"  # 0 sec default
                obj.start_ari = self._get_ari(obj.start_value)

            max_count_stmt = stmt.search_one((AMM_MOD, 'max-count'))
            if max_count_stmt:
                obj.max_count = int(max_count_stmt.arg)
            else:
                obj.max_count = 0

            enabled_stmt = stmt.search_one((AMM_MOD, 'init-enabled'))
            if enabled_stmt:
                obj.init_enabled = (enabled_stmt.arg == 'true')
            else:
                obj.init_enabled = True

        elif issubclass(cls, Ctrl):
            result_stmt = stmt.search_one((AMM_MOD, 'result'), children=stmt.i_children)
            if result_stmt:
                try:
                    obj.result = TypeNameItem(
                        name=result_stmt.arg,
                        description=pyang.statements.get_description(result_stmt),
                        typeobj=self._get_typeobj(result_stmt)
                    )
                except Exception as err:
                    raise RuntimeError(f'Failure handling result "{result_stmt.arg}": {err}') from err;

        elif issubclass(cls, Oper):
            obj.operands = TypeNameList()
            for opnd_stmt in stmt.search((AMM_MOD, 'operand'), children=stmt.i_children):
                try:
                    obj.operands.items.append(TypeNameItem(
                        name=opnd_stmt.arg,
                        description=pyang.statements.get_description(opnd_stmt),
                        typeobj=self._get_typeobj(opnd_stmt)
                    ))
                except Exception as err:
                    raise RuntimeError(f'Failure handling operand "{opnd_stmt.arg}": {err}') from err;

            result_stmt = stmt.search_one((AMM_MOD, 'result'), children=stmt.i_children)
            if result_stmt:
                try:
                    obj.result = TypeNameItem(
                        name=result_stmt.arg,
                        description=pyang.statements.get_description(result_stmt),
                        typeobj=self._get_typeobj(result_stmt)
                    )
                except Exception as err:
                    raise RuntimeError(f'Failure handling result "{result_stmt.arg}": {err}') from err;

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
            try:
                obj = self.from_stmt(orm_cls, yang_stmt)
            except Exception as err:
                raise RuntimeError(f'Failure handling definition for {yang_stmt.keyword} "{yang_stmt.arg}": {err}') from err;

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

        module = self._ctx.add_module(file_path or '<text>', file_text, primary_module=True, in_format='yang')
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
            if isinstance(epos.ref, tuple):
                epos.ref = epos.ref[1]
            try:
                LOGGER.log(kind, '%s: %s', epos.label(True), emsg)
            except Exception as e: 
                LOGGER.error('Error %s, while printing msg %s .', e, emsg)
                
        src = AdmSource()
        src.file_text = file_text
        if file_path:
            src.abs_file_path = file_path
            src.last_modified = self.get_file_time(file_path)

        adm = AdmModule()
        adm.source = src
        adm.module_name = module.arg
        # Normalize the intrinsic ADM name
        adm.norm_name = normalize_ident(adm.module_name)
        self._adm = adm

        ns_stmt = module.search_one('namespace')
        if ns_stmt is None:
            raise RuntimeError('ADM module is missing "namespace" statement')
        ns_ari = self._ari_dec.decode(ns_stmt.arg)
        self._ari_dec.set_namespace(ns_ari.ident.org_id, ns_ari.ident.model_id)
        adm.ns_org_name = ns_ari.ident.org_id.casefold()
        adm.ns_model_name = ns_ari.ident.model_id.casefold()

        org_stmt = module.search_one('organization')
        if org_stmt:
            enum_stmt = org_stmt.search_one((AMM_MOD, 'enum'))
            if enum_stmt:
                adm.ns_org_enum = int(enum_stmt.arg)

        enum_stmt = module.search_one((AMM_MOD, 'enum'))
        if enum_stmt:
            adm.ns_model_enum = int(enum_stmt.arg)

        for sub_stmt in module.search('import'):
            prefix_stmt = sub_stmt.search_one('prefix')
            adm.imports.append(AdmImport(
                name=sub_stmt.arg,
                prefix=prefix_stmt.arg,
            ))

        adm.metadata_list = MetadataList()
        for kywd in MOD_META_KYWDS:
            meta_stmt = module.search_one(kywd)
            if meta_stmt:
                adm.metadata_list.items.append(MetadataItem(
                    name=meta_stmt.keyword,
                    arg=meta_stmt.arg,
                ))

        for sub_stmt in module.search('revision'):
            adm.revisions.append(AdmRevision(
                name=sub_stmt.arg,
                date=date.fromisoformat(sub_stmt.arg),
                description=pyang.statements.get_description(sub_stmt),
            ))

        for sub_stmt in module.search('feature'):
            adm.feature.append(Feature(
                name=sub_stmt.arg,
                description=pyang.statements.get_description(sub_stmt),
            ))

        try:
            self._get_section(adm.typedef, Typedef, module)
            self._get_section(adm.ident, Ident, module)
            self._get_section(adm.const, Const, module)
            self._get_section(adm.ctrl, Ctrl, module)
            self._get_section(adm.edd, Edd, module)
            self._get_section(adm.oper, Oper, module)
            self._get_section(adm.var, Var, module)
            self._get_section(adm.sbr, Sbr, module)
            self._get_section(adm.tbr, Tbr, module)
        except Exception as err:
            raise RuntimeError(f'Failure processing object definitions from ADM "{adm.module_name}": {err}') from err

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
        module = pyang.statements.new_statement(None, None, None, 'module', adm.module_name)
        self._module = module
        self._denorm_prefixes = {}

        self._add_substmt(module, 'yang-version', '1.1')
        self._add_substmt(module, 'namespace', f'ari://{adm.ns_org_name}/{adm.ns_model_name}/')

        for item in adm.metadata_list.items:
            item_stmt = self._add_substmt(module, item.name, item.arg)
            if item.name == 'organization' and adm.ns_org_enum is not None:
                self._add_substmt(item_stmt, (AMM_MOD, 'enum'), str(adm.ns_org_enum))

        for imp in adm.imports:
            imp_stmt = self._add_substmt(module, 'import', imp.name)
            self._add_substmt(imp_stmt, 'prefix', imp.prefix)

        # init after local prefix and imports defined
        pyang.statements.v_init_module(self._ctx, module)

        # local bookkeeping
        for prefix, modtup in module.i_prefixes.items():
            modname = modtup[0]
            self._denorm_prefixes[modname] = prefix

        if adm.ns_model_enum is not None:
            # prefixed keyword after v_init_module
            self._add_substmt(module, (AMM_MOD, 'enum'), str(adm.ns_model_enum))

        for rev in adm.revisions:
            sub_stmt = self._add_substmt(module, 'revision', rev.name)
            if rev.description:
                self._add_substmt(sub_stmt, 'description', rev.description)

        for feat in adm.feature:
            sub_stmt = self._add_substmt(module, 'feature', feat.name)
            if feat.description:
                self._add_substmt(sub_stmt, 'description', feat.description)

        self._put_section(adm.typedef, Typedef, module)
        self._put_section(adm.ident, Ident, module)
        self._put_section(adm.const, Const, module)
        self._put_section(adm.edd, Edd, module)
        self._put_section(adm.var, Var, module)
        self._put_section(adm.ctrl, Ctrl, module)
        self._put_section(adm.oper, Oper, module)
        self._put_section(adm.sbr, Sbr, module)
        self._put_section(adm.tbr, Tbr, module)

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
                if param.description is not None:
                    self._add_substmt(param_stmt, 'description', param.description)
                self._put_typeobj(param.typeobj, param_stmt)
                if param.default_value is not None:
                    self._add_substmt(param_stmt, (AMM_MOD, 'default'), param.default_value)

        if issubclass(cls, TypeUseMixin):
            self._put_typeobj(obj.typeobj, obj_stmt)

        if issubclass(cls, Ident):
            if obj.abstract is not None:
                self._add_substmt(obj_stmt, (AMM_MOD, 'abstract'), 'true' if obj.abstract else 'false')

            for base in obj.bases:
                self._add_substmt(obj_stmt, (AMM_MOD, 'base'), base.base_text)

        elif issubclass(cls, (Const, Var)):
            if obj.init_value is not None:
                self._add_substmt(obj_stmt, (AMM_MOD, 'init-value'), obj.init_value)

        # TODO: elif issubclass(cls, Sbr):
        # TODO: elif issubclass(cls, Tbr):

        elif issubclass(cls, Ctrl):
            if obj.result:
                res_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'result'), obj.result.name)
                if obj.result.description is not None:
                    self._add_substmt(res_stmt, 'description', obj.result.description)
                self._put_typeobj(obj.result.typeobj, res_stmt)

        elif issubclass(cls, Oper):
            for operand in obj.operands.items:
                opnd_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'operand'), operand.name)
                if operand.description is not None:
                    self._add_substmt(opnd_stmt, 'description', operand.description)
                self._put_typeobj(operand.typeobj, opnd_stmt)

            if obj.result:
                res_stmt = self._add_substmt(obj_stmt, (AMM_MOD, 'result'), obj.result.name)
                if obj.result.description is not None:
                    self._add_substmt(res_stmt, 'description', obj.result.description)
                self._put_typeobj(obj.result.typeobj, res_stmt)

        return obj_stmt

    def _put_typeobj(self, typeobj:SemType, parent:pyang.statements.Statement) -> pyang.statements.Statement:
        if isinstance(typeobj, TypeUse):
            type_stmt = self._add_substmt(parent, (AMM_MOD, 'type'), typeobj.type_text)

            if typeobj.units is not None:
                self._add_substmt(type_stmt, 'units', typeobj.units)

            for cnst in typeobj.constraints:
                if isinstance(cnst, StringLength):
                    self._add_substmt(type_stmt, 'length', range_to_text(cnst.ranges))
                elif isinstance(cnst, TextPattern):
                    self._add_substmt(type_stmt, 'pattern', cnst.pattern)
                elif isinstance(cnst, NumericRange):
                    self._add_substmt(type_stmt, 'range', range_to_text(cnst.ranges))
                elif isinstance(cnst, IntegerEnums):
                    lab_stmt = self._add_substmt(type_stmt, (AMM_MOD, 'int-labels'))
                    for val, name in cnst.values.items():
                        enum_stmt = self._add_substmt(lab_stmt, 'enum', name)
                        self._add_substmt(enum_stmt, 'value', str(val))
                elif isinstance(cnst, IntegerBits):
                    lab_stmt = self._add_substmt(type_stmt, (AMM_MOD, 'int-labels'))
                    for pos, name in cnst.positions.items():
                        enum_stmt = self._add_substmt(lab_stmt, 'bit', name)
                        self._add_substmt(enum_stmt, 'position', str(pos))
                elif isinstance(cnst, CborCddl):
                    self._add_substmt(type_stmt, (AMM_MOD, 'cddl'), cnst.text)
                elif isinstance(cnst, IdentRefBase):
                    self._add_substmt(type_stmt, (AMM_MOD, 'base'), cnst.base_text)

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

            if typeobj.min_elements is not None:
                self._add_substmt(tblt_stmt, 'min-elements', str(typeobj.min_elements))
            if typeobj.max_elements is not None:
                self._add_substmt(tblt_stmt, 'max-elements', str(typeobj.max_elements))

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
