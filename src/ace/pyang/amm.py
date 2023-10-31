
from dataclasses import dataclass, field
import re
import logging
from typing import List, Tuple
import pyang
from pyang.error import err_add

logger = logging.getLogger(__name__)

# : Extension module name to hook onto
MODULE_NAME = 'ietf-amm'
MODULE_PREFIX = 'amm'


@dataclass
class Ext:
    ''' Define an extension schema.
    
    :param keyword: Keyword name.
    :param occurrence: Occurrence flag
    :param typename: Argument type name (or None)
    :param subs: sub-statement keywords
    :param parents: Tuple of: parent-statement keywords, and occurrence flags
    '''
    keyword: str
    typename: str
    subs: List[Tuple[object]] = field(default_factory=list)
    parents: List[Tuple[object]] = field(default_factory=list)


# : substatements in standard YANG order followed by new 'enum'
obj_subs_pre = [
    ('if-feature', '?'),
    ((MODULE_NAME, 'enum'), '?'),
]
obj_subs_post = [
    ('status', '?'),
    ('description', '?'),
    ('reference', '?'),
]

AMP_OBJ_NAMES = (
    (MODULE_NAME, 'typedef'),
    (MODULE_NAME, 'ident'),
    (MODULE_NAME, 'const'),
    (MODULE_NAME, 'edd'),
    (MODULE_NAME, 'var'),
    (MODULE_NAME, 'ctrl'),
    (MODULE_NAME, 'oper'),
)
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
) + AMP_OBJ_NAMES

TYPE_USE = [
    ('$choice', [
        [((MODULE_NAME, 'type'), '1')],
        [((MODULE_NAME, 'ulist'), '1')],
        [((MODULE_NAME, 'dlist'), '1')],
        [((MODULE_NAME, 'umap'), '1')],
        [((MODULE_NAME, 'tblt'), '1')],
        [((MODULE_NAME, 'union'), '1')],
    ]),
]

# : List of extension statements defined by the module
MODULE_EXTENSIONS = (
    # : ARI enum assignment
    Ext('enum', 'uint64',
        parents=([
            ('module', '1'),
        ] + [(name, '?') for name in AMP_OBJ_NAMES])
    ),

    # : Type structure extensions
    Ext('type', 'identifier-ref',
        subs=[
            ('length', '?'),
            ('pattern', '?'),
            ('range', '?'),
            ((MODULE_NAME, 'int-labels'), '?'),
            ((MODULE_NAME, 'cddl'), '?'),
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    Ext('ulist', None,
        subs=[
            ((MODULE_NAME, 'type'), '1'),
            ('min-elements', '?'),
            ('max-elements', '?'),
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    Ext('dlist', None,
        subs=[
            ((MODULE_NAME, 'type'), '*'),
            ((MODULE_NAME, 'seq'), '*'),
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    Ext('seq', None,
        subs=[
            ((MODULE_NAME, 'type'), '1'),
            ('min-elements', '?'),
            ('max-elements', '?'),
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    Ext('tblt', None,
        subs=[
            ((MODULE_NAME, 'column'), '*'),
            ((MODULE_NAME, 'key'), '?'),
            ((MODULE_NAME, 'unique'), '*'),
            ('min-elements', '?'),
            ('max-elements', '?'),
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    Ext('column', 'identifier',
        subs=(
            TYPE_USE
            +[
                ('description', '?'),
                ('reference', '?'),
            ]
        ),
    ),
    Ext('key', 'string'),
    Ext('unique', 'string'),
    Ext('union', None,
        subs=[
            ((MODULE_NAME, 'type'), '*'),
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    # : Type narrowing extensions
    Ext('cddl', 'string',
        parents=[((MODULE_NAME, 'type'), '?')]
    ),
    Ext('int-labels', None,
        subs=[
            ('enum', '*'),
            ('bit', '*'),
        ],
        parents=[((MODULE_NAME, 'type'), '?')]
    ),

    # : managed objects
    Ext('typedef', 'identifier',
        subs=(
            obj_subs_pre
            +TYPE_USE
            +obj_subs_post
        ),
        parents=[('module', '*')]
    ),
    Ext('ident', 'identifier',
        subs=(
            obj_subs_pre
            +[
              ((MODULE_NAME, 'base'), '1'),
            ] + obj_subs_post
        ),
        parents=[('module', '*')]
    ),
    Ext('const', 'identifier',
        subs=(
            obj_subs_pre
            +TYPE_USE
            +[
                ((MODULE_NAME, 'parameter'), '*'),
                ((MODULE_NAME, 'init-value'), '1'),
                ('uses', '*'),
            ] + obj_subs_post
        ),
        parents=[('module', '*')]
    ),

    Ext('edd', 'identifier',
        subs=(
            obj_subs_pre + [
                ((MODULE_NAME, 'parameter'), '*'),
                ('uses', '*'),
            ]
            +TYPE_USE
            +obj_subs_post
        ),
        parents=[('module', '*')]
    ),

    Ext(
        'var', 'identifier',
        subs=(
            obj_subs_pre
            +TYPE_USE + [
                ((MODULE_NAME, 'parameter'), '*'),
                ('$choice', [
                    [((MODULE_NAME, 'init-value'), '?')],
                    [((MODULE_NAME, 'init-expr'), '?')],
                ]),
                ('uses', '*'),
            ] + obj_subs_post
        ),
        parents=[('module', '*')]
    ),
    Ext('init-value', 'ARI',
        parents=[
            ((MODULE_NAME, 'var'), '?'),
        ]
    ),
    Ext('init-expr', 'EXPR',
        parents=[
            ((MODULE_NAME, 'var'), '?'),
        ]
    ),

    Ext('ctrl', 'identifier',
        subs=(
            obj_subs_pre + [
                ((MODULE_NAME, 'parameter'), '*'),
                ((MODULE_NAME, 'result'), '?'),
                ('uses', '*'),
            ] + obj_subs_post
        ),
        parents=[('module', '*')]
    ),
    Ext('parameter', 'identifier',
        subs=(
            TYPE_USE
            +[
                ((MODULE_NAME, 'default'), '?'),
                ('description', '?'),
                ('reference', '?'),
            ]
        ),
        parents=[('grouping', '*')],
    ),
    Ext('default', 'ARI',
        subs=[
            ('description', '?'),
            ('reference', '?'),
        ],
    ),
    Ext('result', 'identifier',
        subs=(
            TYPE_USE
            +[
                ('description', '?'),
                ('reference', '?'),
            ]
        ),
        parents=[('grouping', '*')],
    ),
    
    Ext('oper', 'identifier',
        subs=(
            obj_subs_pre + [
                ((MODULE_NAME, 'parameter'), '*'),
                ((MODULE_NAME, 'operand'), '*'),
                ((MODULE_NAME, 'result'), '?'),  # can be provided via uses
                ('uses', '*'),
            ] + obj_subs_post
        ),
        parents=[('module', '*')]
    ),
    Ext('operand', 'identifier',
        subs=(
            TYPE_USE
            +[
                ('description', '?'),
                ('reference', '?'),
            ]
        ),
        parents=[('grouping', '*')],
    ),
)


def check_int(min_val, max_val):
    ''' Verify numeric statement argument. '''

    def checker(val):
        try:
            val = int(val)
            return (val >= min_val and val <= max_val)
        except TypeError:
            return False

    return checker


def check_objref(val):
    ''' Verify the syntax for an OBJ-REF ARI. '''
    logger.debug('Verifying OBJ-REF for %s', val)
    return True


def check_ari(val):
    ''' Verify the text is an ARI. '''
    return True


def check_expr(val):
    ''' Verify the text is an EXPR-constrained AC. '''
    return True


def _stmt_check_namespace(ctx, stmt):
    ''' Verify namespace is conformant to an ADM. '''
    RE_NS_PAT = r'ari:/([a-zA-Z].*)/?'
    RE_NS = re.compile(RE_NS_PAT)
    if RE_NS.match(stmt.arg) is None:
        err_add(ctx.errors, stmt.pos, 'AMP_MODULE_NS',
                (stmt.arg))


def _stmt_check_enum(ctx, stmt):
    ''' Apply an enum value to an ADM object. '''
    enum_stmt = stmt.search_one((MODULE_NAME, 'enum'))
    if enum_stmt:
        logger.debug('Applying enum %s to %s named "%s"', enum_stmt.arg, stmt.keyword, stmt.arg)


def _stmt_check_module_objs(ctx, stmt):
    ''' Verify only AMP objects are present in the module. '''
    if stmt.keyword == 'module':
        ns_stmt = stmt.search_one('namespace')
        if ns_stmt and ns_stmt.arg.startswith('ari:'):
            allowed = frozenset(MODULE_STMT_ALLOW)
            for sub in stmt.substmts:
                if sub.keyword not in allowed:
                    err_add(ctx.errors, sub.pos, 'AMP_MODULE_OBJS',
                            (sub.keyword, sub.arg))


def _stmt_check_acitems(ctx, stmt):
    ''' Verify the contents of an ac-items extension. '''
    if stmt.parent.arg != 'AC':
        err_add(ctx.errors, stmt.pos, 'AMP_ACITEMS_INTYPE',
                ())


def _stmt_check_intlabels(ctx, stmt):
    ''' Verify either enum or bit but not both are present. '''
    has_enum = stmt.search_one('enum') is not None
    has_bit = stmt.search_one('bit') is not None
    if not has_enum and not has_bit:
        err_add(ctx.errors, stmt.pos, 'AMP_INTLABELS',
                (''))
    elif has_enum and has_bit:
        err_add(ctx.errors, stmt.pos, 'AMP_INTLABELS',
                ('but not both'))


def _stmt_check_objref(ctx, stmt):
    ''' Verify OBJ-REF reference itself is valid. '''
    return True


def _stmt_check_enum_value(ctx, stmt):
    ''' Verify all enum have an associated value. '''
    if (stmt.parent.keyword == (MODULE_NAME, 'int-label')
        and stmt.search_one('value') is None):
        err_add(ctx.errors, stmt.pos, 'AMP_ENUM_VALUE',
                (stmt.arg))


def _stmt_check_enum_unique(ctx, stmt):
    for name in AMP_OBJ_NAMES:
        seen_enum = set()
        for obj_stmt in stmt.search(name):
            enum_stmt = obj_stmt.search_one((MODULE_NAME, 'enum'))
            if enum_stmt is None:
                continue
            enum_val = int(enum_stmt.arg)
            if enum_val in seen_enum:
                err_add(ctx.errors, stmt.pos, 'AMP_ENUM_UNIQUE',
                        (name,))
            seen_enum.add(enum_val)


def _stmt_add_amm_children(ctx, stmt):
    ''' Add AMM objects to iterable children of a module. '''
    for name in AMP_OBJ_NAMES:
        for obj_stmt in stmt.search(name):
            stmt.i_children.append(obj_stmt)
            
            pyang.statements.v_init_has_children(ctx, obj_stmt)
            pyang.statements.v_expand_1_children(ctx, obj_stmt)
#            logger.debug('expand %s %s', obj_stmt, obj_stmt.i_children)


def _stmt_check_oper_result(ctx, stmt):
    logger.debug('oper %s %s', stmt, stmt.search_one((MODULE_NAME, 'result'), children=stmt.i_children))


def pyang_plugin_init():
    ''' Called by plugin framework to initialize this plugin.
    '''
    import sys
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    # Register that we handle extensions from the associated YANG module
    pyang.grammar.register_extension_module(MODULE_NAME)
    # Extension argument types
    pyang.syntax.add_arg_type('uint64', check_int(0, 2 ** 64 - 1))
    pyang.syntax.add_arg_type('OBJ-REF', check_objref)
    pyang.syntax.add_arg_type('ARI', check_ari)
    pyang.syntax.add_arg_type('EXPR', check_expr)
    
    for ext in MODULE_EXTENSIONS:
        sub_stmts = ext.subs
        pyang.grammar.add_stmt((MODULE_NAME, ext.keyword), (ext.typename, sub_stmts))
    for ext in MODULE_EXTENSIONS:
        for (name, occurr) in ext.parents:
            try:
                pyang.grammar.add_to_stmts_rules([name], [((MODULE_NAME, ext.keyword), occurr)])
            except Exception as err:
                print('Failed to add substatement "%s" "%s": %s' % (name, ext.keyword, err))
                raise

    pyang.statements.data_keywords += [
        (MODULE_NAME, 'parameter'),
        (MODULE_NAME, 'operand'),
        (MODULE_NAME, 'result'),
    ]

    # Add validation step, stages are listed in :mod:`pyang.statements`
#    pyang.statements.add_validation_var(
#        '$amp_enum',
#        lambda keyword: keyword in AMP_OBJ_NAMES
#    )
    pyang.statements.add_validation_fun(
        'grammar',
        ['namespace'],
        _stmt_check_namespace
    )
    pyang.statements.add_validation_fun(
        'grammar',
        AMP_OBJ_NAMES,
        _stmt_check_enum
    )
    pyang.statements.add_validation_fun(
        'grammar',
        ['module', 'submodule'],
        _stmt_check_module_objs
    )
    pyang.statements.add_validation_fun(
        'type_2',
        [(MODULE_NAME, 'ac-items')],
        _stmt_check_acitems
    )
    pyang.statements.add_validation_fun(
        'grammar',
        [(MODULE_NAME, 'int-labels')],
        _stmt_check_intlabels
    )
    pyang.statements.add_validation_fun(
        'grammar',
        ['enum'],
        _stmt_check_enum_value
    )
    pyang.statements.add_validation_fun(
        'unique_name',
        ['module'],
        _stmt_check_enum_unique
    )
    pyang.statements.add_validation_fun(
        'expand_1',
        ['module', 'submodule'],
        _stmt_add_amm_children
    )
    pyang.statements.add_validation_fun(
        'expand_2',
        [(MODULE_NAME, 'oper')],
        _stmt_check_oper_result
    )
#    pyang.statements.add_validation_fun(
#        'reference_1',
#        [(MODULE_NAME, 'item')],
#        _stmt_check_objref
#    )

    # Register special error codes
    pyang.error.add_error_code(
        'AMP_MODULE_NS', 1,
        "An ADM module must have an ARI namespace, not %s"
    )
    pyang.error.add_error_code(
        'AMP_MODULE_OBJS', 1,
        "An ADM module cannot contain a statement %r named %r"
    )
    pyang.error.add_error_code(
        'AMP_ACITEMS_INTYPE', 1,
        "An ac-items can only be present within an AC type"
    )
    pyang.error.add_error_code(
        'AMP_INTLABELS', 1,
        "An int-label must have either 'enum' or 'bit' statements %s"
    )
    pyang.error.add_error_code(
        'AMP_ENUM_VALUE', 1,
        "An enumeration 'enum' statement %r must have a 'value'"
    )
    pyang.error.add_error_code(
        'AMP_ENUM_UNIQUE', 1,
        "Statement 'enum' must be unique among all %s"
    )
