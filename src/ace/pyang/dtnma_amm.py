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
''' DTNMA-AMM Plugin
Copyright (c) 2023-2025 The Johns Hopkins University Applied Physics
Laboratory LLC.

This plugin implements the DTNMA Application Management Model (AMM) from
[I-D.ietf-dtn-adm-yang] as a collection of extensions and the module itself.
'''
from dataclasses import dataclass, field
import io
from typing import List, Tuple
from pyang import plugin, context, statements, syntax, grammar, error
from pyang.util import keyword_to_str

# Use ARI processing library when possible
try:
    from ace import ari_text, ReferenceARI
except ImportError:
    ari_text = None

MODULE_NAME = 'ietf-amm'
''' Extension module name to hook onto '''
MODULE_PREFIX = 'amm'
''' Extension prefix '''


class DtnmaAmmPlugin(plugin.PyangPlugin):
    ''' This plugin is just validation. '''


def pyang_plugin_init():
    ''' Called by plugin framework to initialize this plugin.
    '''
    plugin.register_plugin(DtnmaAmmPlugin())

    # Register that we handle extensions from the associated YANG module
    grammar.register_extension_module(MODULE_NAME)
    # Extension argument types
    syntax.add_arg_type('ARI', AriChecker())

    for ext in MODULE_EXTENSIONS:
        name = (MODULE_NAME, ext.keyword)
        grammar.add_stmt(name, (ext.typename, ext.subs))
        if ext.subs:
            statements.add_keyword_with_children(name)

    # ADM enumeration only at module level and optional
    # allowing for non-ADM YANG modules
    grammar.add_to_stmts_rules(
        ['module', 'organization'],
        [((MODULE_NAME, 'enum'), '?')],
    )

    # AMM object extensions with preferred canonicalization order
    grammar.add_to_stmts_rules(
        ['module', 'submodule'],
        [('$interleave', [(name, '*') for name in AMM_OBJ_NAMES])],
    )
    # order of semantic type statements must be preserved because union and
    # dlist both depend on order
    for name in (AMM_OBJ_NAMES + AMM_ORDERED_NAMES):
        grammar.data_def_stmts.append((name, '*'))

    # Allow these to be present in "grouping" and for "uses"
    grammar.add_to_stmts_rules(
        ['grouping'],
        [(name, '*') for name in AMM_GROUPING_NAMES]
    )
    for name in AMM_GROUPING_NAMES:
        statements.add_data_keyword(name)

    statements.add_validation_fun(
        'grammar',
        ['namespace'],
        _stmt_check_namespace
    )
    statements.add_validation_fun(
        'grammar',
        ['module'],
        _stmt_check_module_enums
    )
    statements.add_validation_fun(
        'grammar',
        AMM_OBJ_NAMES,
        _stmt_check_obj_enum
    )
    statements.add_validation_fun(
        'grammar',
        ['module', 'submodule'],
        _stmt_check_module_objs
    )
    statements.add_validation_fun(
        'grammar',
        [(MODULE_NAME, 'int-labels')],
        _stmt_check_intlabels
    )
    statements.add_validation_fun(
        'grammar',
        # Statements with 'ARI' type above
        [
            (MODULE_NAME, 'type'),
            (MODULE_NAME, 'base'),
            (MODULE_NAME, 'init-value'),
            (MODULE_NAME, 'action'),
            (MODULE_NAME, 'condition'),
            (MODULE_NAME, 'period'),
            (MODULE_NAME, 'start'),
            (MODULE_NAME, 'min-interval'),
            (MODULE_NAME, 'init-enabled'),
            (MODULE_NAME, 'max-count'),
            (MODULE_NAME, 'default')
        ],
        _stmt_check_ari_import_use
    )
    statements.add_validation_fun(
        'unique_name',
        ['module'],
        _stmt_check_enum_unique
    )
    statements.add_validation_fun(
        'grammar',
        AMM_OBJ_NAMES
        +(
            (MODULE_NAME, 'parameter'),
            (MODULE_NAME, 'operand'),
            (MODULE_NAME, 'result'),
        ),
        _stmt_check_documentation
    )

    # Register special error codes
    error.add_error_code(
        'AMM_MODULE_NS_ARI', 1,  # critical
        "An ADM module must have an ARI namespace , not %s"
    )
    error.add_error_code(
        'AMM_MODULE_NAME_NS', 1,  # critical
        "The ADM module name \"%s\" does not agree with the module namespace \"%s\""
    )
    error.add_error_code(
        'AMM_MODULE_OBJS', 1,  # critical
        "An ADM module cannot contain a statement %r named \"%s\""
    )
    error.add_error_code(
        'AMM_ORG_ENUM', 4,  # warning
        "The ADM module \"%s\" must contain an organization with an amm:enum statement"
    )
    error.add_error_code(
        'AMM_MODEL_ENUM', 4,  # warning
        "The ADM module \"%s\" must contain an amm:enum statement"
    )
    error.add_error_code(
        'AMM_OBJ_ENUM', 4,  # warning
        "The ADM object %s named \"%s\" should contain an amm:enum statement"
    )
    error.add_error_code(
        'AMM_OBJ_ENUM_UNIQUE', 1,  # critical
        "An amm:enum must be unique among all %s objects, has value %s"
    )
    error.add_error_code(
        'AMM_INTLABELS', 1,  # critical
        "An amm:int-labels must have either 'enum' or 'bit' substatements in \"%s\""
    )
    error.add_error_code(
        'AMM_INTLABELS_ENUM_VALUE', 1,  # critical
        "An amm:int-labels 'enum' statement %r must have a unique 'value'"
    )
    error.add_error_code(
        'AMM_INTLABELS_BIT_VALUE', 1,  # critical
        "An amm:int-labels 'bit' statement %r must have a unique 'position'"
    )
    error.add_error_code(
        'AMM_DOC_DESCRIPTION', 4,  # warning
        "A description should be present under %s statement \"%s\""
    )
    error.add_error_code(
        'AMM_DOC_REFERENCE', 4,  # warning
        "A reference should be present under %s statement \"%s\""
    )


@dataclass
class Ext:
    ''' Define an extension schema.

    :param keyword: Keyword name.
    :param occurrence: Occurrence flag
    :param typename: Argument type name (or None)
    :param subs: sub-statement keywords
    '''
    keyword: str
    typename: str
    subs: List[Tuple[object]] = field(default_factory=list)


OBJ_SUBS_PRE = [
    ('if-feature', '?'),
    ((MODULE_NAME, 'enum'), '?'),
    ('status', '?'),
    ('description', '?'),
    ('reference', '?'),
]
''' Substatements at the front of object definitions. '''

AMM_OBJ_NAMES = (
    (MODULE_NAME, 'typedef'),
    (MODULE_NAME, 'ident'),
    (MODULE_NAME, 'const'),
    (MODULE_NAME, 'edd'),
    (MODULE_NAME, 'var'),
    (MODULE_NAME, 'ctrl'),
    (MODULE_NAME, 'oper'),
    (MODULE_NAME, 'sbr'),
    (MODULE_NAME, 'tbr'),
)
''' AMM object types at the module/submodule level. '''

AMM_ORDERED_NAMES = (
    # definition statements must preserve order
    (MODULE_NAME, 'parameter'),
    (MODULE_NAME, 'operand'),
    (MODULE_NAME, 'result'),
    # semantic type statements
    (MODULE_NAME, 'type'),
    (MODULE_NAME, 'ulist'),
    (MODULE_NAME, 'dlist'),
    (MODULE_NAME, 'umap'),
    (MODULE_NAME, 'tblt'),
    (MODULE_NAME, 'column'),
    (MODULE_NAME, 'union'),
    (MODULE_NAME, 'seq'),
)
''' All data-like keywords to preserve order in canonical encoding. '''

AMM_GROUPING_NAMES = tuple(AMM_ORDERED_NAMES)
''' Extensions allowed in "grouping" statements. '''
AMM_USES_PARENTS = AMM_OBJ_NAMES + (
    (MODULE_NAME, 'parameter'),
    (MODULE_NAME, 'default'),
    (MODULE_NAME, 'operand'),
    (MODULE_NAME, 'result'),
)
''' Extensions containing "uses" statements. '''

MODULE_STMT_ALLOW = (
    '_comment',
    'contact',
    'description',
    'extension',
    'feature',
    'grouping',
    'import',
    'include',
    'namespace',
    'organization',
    'prefix',
    'reference',
    'revision',
    'yang-version',
    (MODULE_NAME, 'enum'),
) + AMM_OBJ_NAMES
''' Allowed statements at the ADM module level. '''


def type_use(parent:str) -> List:
    ''' Get a list of type-use substatements for a particular parent.

    :param parent: The parent statement keyword.
    :return: Choice of semantic type substatements.
    '''
    opts = [
        [('uses', '1')],
        [((MODULE_NAME, 'type'), '1')],
        [((MODULE_NAME, 'ulist'), '1')],
        [((MODULE_NAME, 'dlist'), '1')],
        [((MODULE_NAME, 'umap'), '1')],
        [((MODULE_NAME, 'tblt'), '1')],
        [((MODULE_NAME, 'union'), '1')],
    ]
    if parent in ('dlist', 'parameter', 'operand'):
        opts.append(
            [((MODULE_NAME, 'seq'), '*')]
        )
    return [
        ('$choice', opts),
    ]


# List of extension statements defined by the module
MODULE_EXTENSIONS = (
    # ARI enum assignment
    Ext('enum', 'non-negative-integer'),

    # Type structure extensions
    Ext('type', 'ARI',
        subs=[
            ('$interleave', [
                ('units', '?'),
                ((MODULE_NAME, 'display-hint'), '?'),
                ((MODULE_NAME, 'int-labels'), '?'),
                ('range', '?'),
                ('pattern', '*'),
                ('length', '?'),
                ((MODULE_NAME, 'cddl'), '?'),
                ((MODULE_NAME, 'base'), '*'),
            ]),
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    Ext('ulist', None,
        subs=(
            [
                ('description', '?'),
                ('reference', '?'),
                ('min-elements', '?'),
                ('max-elements', '?'),
            ]
            +type_use('ulist')
        ),
    ),
    Ext('dlist', None,
        subs=[
            ('description', '?'),
            ('reference', '?'),
            ('$interleave', type_use('dlist')),
        ],
    ),
    Ext('seq', None,
        subs=(
            [
                ('description', '?'),
                ('reference', '?'),
                ('min-elements', '?'),
                ('max-elements', '?'),
            ]
            +type_use('seq')
        ),
    ),
    Ext('umap', None,
        subs=[
            ('description', '?'),
            ('reference', '?'),
            ((MODULE_NAME, 'keys'), '?'),
            ((MODULE_NAME, 'values'), '?'),
        ]
    ),
    Ext('keys', None,
        subs=(
            [
                ('description', '?'),
                ('reference', '?'),
            ]
            +type_use('keys')
        )
    ),
    Ext('values', None,
        subs=(
            [
                ('description', '?'),
                ('reference', '?'),
            ]
            +type_use('values')
        )
    ),
    Ext('tblt', None,
        subs=[
            ('description', '?'),
            ('reference', '?'),
            ('$interleave', [
                ('min-elements', '?'),
                ('max-elements', '?'),
                ((MODULE_NAME, 'key'), '?'),
                ((MODULE_NAME, 'unique'), '*'),
                ((MODULE_NAME, 'column'), '*'),
            ]),
        ],
    ),
    Ext('column', 'identifier',
        subs=(
            [
                ('if-feature', '?'),
                ('description', '?'),
                ('reference', '?'),
            ]
            +type_use('column')
        ),
    ),
    Ext('key', 'string'),
    Ext('unique', 'string'),
    Ext('union', None,
        subs=[
            ('description', '?'),
            ('reference', '?'),
            ('$interleave', type_use('union')),
        ],
    ),
    # Type narrowing extensions
    Ext('display-hint', 'ARI'),
    Ext('cddl', 'string'),
    Ext('int-labels', None,
        subs=[
            ('enum', '*'),
            ('bit', '*'),
        ],
    ),

    Ext('parameter', 'identifier',
        subs=(
            [
                ('description', '?'),
                ('reference', '?'),
                ((MODULE_NAME, 'default'), '?'),
            ]
            +type_use('parameter')
        ),
    ),
    Ext('default', 'ARI',
        subs=[
            ('description', '?'),
            ('reference', '?'),
        ],
    ),

    # managed objects
    Ext('typedef', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +type_use('typedef')
        ),
    ),

    Ext('ident', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +[
                ('$interleave', [
                    ((MODULE_NAME, 'parameter'), '*'),
                    ('uses', '*'),
                ]),
                ((MODULE_NAME, 'abstract'), '*'),
                ((MODULE_NAME, 'base'), '*'),
            ]
        ),
    ),
    Ext('abstract', 'boolean'),
    Ext('base', 'ARI'),

    Ext('const', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +[
                ('$interleave', [
                    ((MODULE_NAME, 'parameter'), '*'),
                    ('uses', '*'),
                ]),
                ((MODULE_NAME, 'init-value'), '1'),
            ]
            +type_use('const')
        ),
    ),
    Ext('init-value', 'ARI'),

    Ext('edd', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +[
                ('$interleave', [
                    ((MODULE_NAME, 'parameter'), '*'),
                    ('uses', '*'),
                ]),
            ]
            +type_use('edd')
        ),
    ),

    Ext('var', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +type_use('var')
            +[
                ('$interleave', [
                    ((MODULE_NAME, 'parameter'), '*'),
                    ('uses', '*'),
                ]),
                ((MODULE_NAME, 'init-value'), '?'),
            ]
        ),
    ),

    Ext('ctrl', 'identifier',
        subs=(
            OBJ_SUBS_PRE + [
                ('$interleave', [
                    ((MODULE_NAME, 'parameter'), '*'),
                    ('uses', '*'),
                ]),
                ((MODULE_NAME, 'result'), '?'),
            ]
        ),
    ),
    Ext('result', 'identifier',
        subs=(
            [
                ('description', '?'),
                ('reference', '?'),
            ]
            +type_use('result')
        ),
    ),

    Ext('oper', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +[
                ('$interleave', [
                    ((MODULE_NAME, 'parameter'), '*'),
                    ('uses', '*'),
                ]),
                ('$interleave', [
                    ((MODULE_NAME, 'operand'), '*'),
                    ('uses', '*'),
                ]),
                ((MODULE_NAME, 'result'), '?'),  # can be provided via uses
            ]
        ),
    ),
    Ext('operand', 'identifier',
        subs=(
            [
                ('description', '?'),
                ('reference', '?'),
            ]
            +type_use('operand')
        ),
    ),
    Ext('sbr', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +[
                ((MODULE_NAME, 'action'), '1'),
                ((MODULE_NAME, 'condition'), '1'),
                ((MODULE_NAME, 'min-interval'), '?'),
                ((MODULE_NAME, 'max-count'), '?'),
                ((MODULE_NAME, 'init-enabled'), '?'),
            ]
        ),
    ),
    Ext('tbr', 'identifier',
        subs=(
            OBJ_SUBS_PRE
            +[
                ((MODULE_NAME, 'action'), '1'),
                ((MODULE_NAME, 'start'), '?'),
                ((MODULE_NAME, 'period'), '1'),
                ((MODULE_NAME, 'max-count'), '?'),
                ((MODULE_NAME, 'init-enabled'), '?'),
            ]
        ),
    ),
    Ext('action', 'ARI'),
    Ext('condition', 'ARI'),
    Ext('period', 'ARI'),
    Ext('start', 'ARI'),
    Ext('min-interval', 'ARI'),
    Ext('init-enabled', 'boolean'),
    Ext('max-count', 'integer'),
)


class AriChecker:
    ''' Verify that text is a well-formed ARI.

    If the :py:mod:`ace` module is not available this assumes any ARI is valid.
    '''

    def __init__(self):
        if ari_text:
            self._dec = ari_text.Decoder()
        else:
            self._dec = None

    def __call__(self, val:str) -> bool:
        if self._dec is None:
            return True

        buf = io.StringIO(val)
        try:
            self._dec.decode(buf)
            return True
        except:
            return False


def _stmt_check_namespace(ctx:context.Context, stmt:statements.Statement):
    ''' Verify namespace conforms to to an ADM module. '''
    if not ari_text:
        return
    if not stmt.arg.startswith('ari:'):
        return

    try:
        ns_ref = ari_text.Decoder().decode(io.StringIO(stmt.arg))
    except ari_text.ParseError:
        ns_ref = None

    # check that it is a namespace reference
    if (not isinstance(ns_ref, ReferenceARI)
        or ns_ref.ident.type_id is not None
        or ns_ref.ident.obj_id is not None):
        error.err_add(ctx.errors, stmt.pos, 'AMM_MODULE_NS_ARI',
                      (stmt.arg))

    # check that it agrees with module name
    module_name = stmt.main_module().arg
    if ns_ref and ns_ref.ident.module_name != module_name.casefold():
        error.err_add(ctx.errors, stmt.pos, 'AMM_MODULE_NAME_NS',
                      (module_name, stmt.arg))


def _stmt_check_ari_import_use(ctx:context.Context, stmt:statements.Statement):
    ''' Check that referenced modules exist and
    mark those modules as used based on ARI content. '''
    if not ari_text:
        return

    mod_stmt = stmt.main_module()
    if mod_stmt is None:
        raise RuntimeError('No main module available')

    # only imported modules
    mod_map = {
        name: key
        for key, (name, _rev) in mod_stmt.i_prefixes.items()
    }

    def visitor(ari):
        # only care about references with absolute namespace
        if not isinstance(ari, ReferenceARI):
            return
        if ari.ident.model_id is None:
            return

        mod_prefix = mod_map.get(ari.ident.ns_id)
        if mod_prefix:
            if mod_prefix in mod_stmt.i_unused_prefixes:
                del mod_stmt.i_unused_prefixes[mod_prefix]
        else:
            mod_stmt.i_missing_prefixes[ari.ident.ns_id] = True

    ari = ari_text.Decoder().decode(io.StringIO(stmt.arg))
    ari.visit(visitor)


def _stmt_check_module_enums(ctx:context.Context, stmt:statements.Statement):
    ''' Check the model and org enum values for an ADM module. '''
    enum_stmt = stmt.search_one((MODULE_NAME, 'enum'))
    if not enum_stmt:
        error.err_add(ctx.errors, stmt.pos, 'AMM_MODEL_ENUM',
                      (stmt.arg))

    org_stmt = stmt.search_one('organization')
    enum_stmt = org_stmt.search_one((MODULE_NAME, 'enum')) if org_stmt else None
    if not enum_stmt:
        error.err_add(ctx.errors, stmt.pos, 'AMM_ORG_ENUM',
                      (stmt.arg))


def _stmt_check_module_objs(ctx:context.Context, stmt:statements.Statement):
    ''' Verify only AMP objects are present in the module. '''
    if stmt.keyword != 'module':
        return
    ns_stmt = stmt.search_one('namespace')
    if ns_stmt is None or not ns_stmt.arg.startswith('ari:'):
        return

    allowed = frozenset(MODULE_STMT_ALLOW)
    for sub in stmt.substmts:
        if sub.keyword not in allowed:
            error.err_add(ctx.errors, sub.pos, 'AMM_MODULE_OBJS',
                          (keyword_to_str(sub.keyword), sub.arg))


def _stmt_check_obj_enum(ctx:context.Context, stmt:statements.Statement):
    ''' Check an enum value for an ADM object. '''
    enum_stmt = stmt.search_one((MODULE_NAME, 'enum'))
    if not enum_stmt:
        error.err_add(ctx.errors, stmt.pos, 'AMM_OBJ_ENUM',
                      (stmt.raw_keyword[1], stmt.arg))


def _stmt_check_intlabels(ctx:context.Context, stmt:statements.Statement):
    ''' Verify either enum or bit but not both are present. '''
    has_enum = stmt.search_one('enum') is not None
    has_bit = stmt.search_one('bit') is not None
    if not has_enum and not has_bit:
        error.err_add(ctx.errors, stmt.pos, 'AMM_INTLABELS',
                      (''))
    elif has_enum and has_bit:
        error.err_add(ctx.errors, stmt.pos, 'AMM_INTLABELS',
                      ('but not both'))

    seen = set()
    for enum_stmt in stmt.search('enum'):
        val_stmt = enum_stmt.search_one('value')
        if val_stmt is None:
            error.err_add(ctx.errors, enum_stmt.pos, 'AMM_INTLABELS_ENUM_VALUE',
                          enum_stmt.arg)
        else:
            got = int(val_stmt.arg)
            if got in seen:
                error.err_add(ctx.errors, enum_stmt.pos, 'AMM_INTLABELS_ENUM_VALUE',
                              enum_stmt.arg)
            seen.add(got)

    seen = set()
    for enum_stmt in stmt.search('bit'):
        pos_stmt = enum_stmt.search_one('position')
        if pos_stmt is None:
            error.err_add(ctx.errors, enum_stmt.pos, 'AMM_INTLABELS_BIT_VALUE',
                          enum_stmt.arg)
        else:
            got = int(pos_stmt.arg)
            if got in seen:
                error.err_add(ctx.errors, enum_stmt.pos, 'AMM_INTLABELS_BIT_VALUE',
                              enum_stmt.arg)
            seen.add(got)


def _stmt_check_enum_unique(ctx:context.Context, stmt:statements.Statement):
    for obj_kywd in AMM_OBJ_NAMES:
        seen_enum = set()
        for obj_stmt in stmt.search(obj_kywd):
            enum_stmt = obj_stmt.search_one((MODULE_NAME, 'enum'))
            if enum_stmt is None:
                continue
            enum_val = int(enum_stmt.arg)
            if enum_val in seen_enum:
                error.err_add(ctx.errors, obj_stmt.pos, 'AMM_OBJ_ENUM_UNIQUE',
                              (obj_kywd[1], enum_stmt.arg))
            seen_enum.add(enum_val)


def _stmt_check_documentation(ctx:context.Context, stmt:statements.Statement):
    if stmt.search_one('description') is None:
        error.err_add(ctx.errors, stmt.pos, 'AMM_DOC_DESCRIPTION',
                      (keyword_to_str(stmt.keyword), stmt.arg))
    if stmt.search_one('reference') is None and False:
        error.err_add(ctx.errors, stmt.pos, 'AMM_DOC_REFERENCE',
                      (keyword_to_str(stmt.keyword), stmt.arg))
