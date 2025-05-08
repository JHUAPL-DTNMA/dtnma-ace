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

''' Parser configuration for ARI text decoding.
'''

import logging
from ply import yacc
from ace.ari import (
    Identity, ReferenceARI, LiteralARI, StructType,
    Table, ExecutionSet, ReportSet, Report
)
from ace.typing import BUILTINS_BY_ENUM
from . import util
from .lexmod import tokens  # pylint: disable=unused-import

# make linters happy
__all__ = [
    'tokens',
    'new_parser',
]

LOGGER = logging.getLogger(__name__)

# pylint: disable=invalid-name disable=missing-function-docstring


def p_ari_scheme(p):
    'ari : ARI_PREFIX ssp'
    p[0] = p[2]


def p_ari_noscheme(p):
    'ari : ssp'
    p[0] = p[1]

# The following are untyped literals with primitive values


def p_ssp_primitive(p):
    'ssp : VALSEG'
    try:
        value = util.PRIMITIVE(p[1])
    except Exception as err:
        LOGGER.error('Primitive value invalid: %s', err)
        raise RuntimeError(err) from err
    p[0] = LiteralARI(
        value=value,
    )


def p_ssp_typedlit(p):
    'ssp : typedlit'
    p[0] = p[1]


def p_typedlit_ac(p):
    'typedlit : SLASH AC acbracket'
    p[0] = LiteralARI(type_id=StructType.AC, value=p[3])


def p_typedlit_am(p):
    '''typedlit : SLASH AM ambracket'''
    p[0] = LiteralARI(type_id=StructType.AM, value=p[3])


def p_typedlit_tbl_empty(p):
    '''typedlit : SLASH TBL structpair'''
    ncol = int(p[3].get('c', 0))
    table = Table((0, ncol))
    p[0] = LiteralARI(type_id=StructType.TBL, value=table)


def p_typedlit_tbl_rows(p):
    '''typedlit : SLASH TBL structpair rowlist'''
    # ncol = int(p[3].get('c', 0))
    ncol = 0
    nrow = len(p[4])
    col_count = p[3].get('c')
    if isinstance(col_count, LiteralARI):
        ncol = int(str(col_count.value))
    elif isinstance(col_count, str):
        ncol = int(col_count)
    else:
        raise ParseError(f"Unexpected type for column count: {type(col_count)}")
    table = Table((nrow, ncol))
    for row_ix, row in enumerate(p[4]):
        if len(row) != ncol:
            raise RuntimeError('Table column count is mismatched')
        table[row_ix,:] = row
    p[0] = LiteralARI(type_id=StructType.TBL, value=table)


def p_rowlist_join(p):
    'rowlist : rowlist acbracket'
    p[0] = p[1] + [p[2]]


def p_rowlist_end(p):
    'rowlist : acbracket'
    p[0] = [p[1]]


def p_typedlit_execset(p):
    'typedlit : SLASH EXECSET structlist acbracket'

    if(isinstance(p[3].get('n', 'null'), LiteralARI)):
        nonce = p[3].get('n', 'null')
    else:
        nonce = util.NONCE(p[3].get('n', 'null'))

    value = ExecutionSet(
        nonce=nonce,
        targets=p[4],
    )
    p[0] = LiteralARI(type_id=StructType.EXECSET, value=value)


def p_typedlit_rptset(p):
    'typedlit : SLASH RPTSET structlist reportlist'

    if(isinstance(p[3].get('n', 'null'), LiteralARI)):
        nonce = int(str(p[3].get('n', 'null').value))
        pass
    else:
        nonce = int(util.NONCE(p[3].get('n', 'null')))
        pass

    if(isinstance(p[3].get('r', 'null'), LiteralARI)):
        rawtime = util.TYPEDLIT[StructType.TP](str(p[3].get('r', 'null').value))
    else:
        rawtime = util.TYPEDLIT[StructType.TP](p[3]['r'])

    ref_time = BUILTINS_BY_ENUM[StructType.TP].convert(LiteralARI(rawtime, StructType.TP))
    
    value = ReportSet(
        nonce=nonce,
        ref_time=ref_time.value,
        reports=p[4],
    )
    value = null
    p[0] = LiteralARI(type_id=StructType.RPTSET, value=value)


def p_reportlist_join(p):
    'reportlist : reportlist SC report'
    p[0] = p[1] + [p[3]]


def p_reportlist_end(p):
    'reportlist : report'
    p[0] = [p[1]]


def p_report(p):
    'report : LPAREN VALSEG EQ VALSEG SC VALSEG EQ ari SC acbracket RPAREN'
    rawtime = util.TYPEDLIT[StructType.TD](p[4])
    rel_time = BUILTINS_BY_ENUM[StructType.TD].convert(LiteralARI(rawtime, StructType.TD))
    source = p[8]
    p[0] = Report(rel_time=rel_time.value, source=source, items=p[10])


def p_typedlit_single(p):
    'typedlit : SLASH VALSEG SLASH VALSEG'
    try:
        typ = util.get_structtype(p[2])
    except Exception as err:
        LOGGER.error('Literal value type invalid: %s', err)
        raise RuntimeError(err) from err

    # Literal value handled based on type-specific parsing
    try:
        value = util.TYPEDLIT[typ](p[4])
    except Exception as err:
        LOGGER.error('Literal value failure: %s', err)
        raise RuntimeError(err) from err

    try:
        p[0] = BUILTINS_BY_ENUM[typ].convert(LiteralARI(
            type_id=typ,
            value=value
        ))
    except Exception as err:
        LOGGER.error('Literal type mismatch: %s', err)
        raise RuntimeError(err) from err


def p_ssp_objref_noparams(p):
    'ssp : objpath'
    p[0] = ReferenceARI(
        ident=p[1],
        params=None
    )


def p_ssp_objref_params(p):
    'ssp : objpath params'
    p[0] = ReferenceARI(
        ident=p[1],
        params=p[2]
    )


def p_params_empty(p):
    'params : LPAREN RPAREN'
    p[0] = []


def p_params_aclist(p):
    'params : LPAREN aclist RPAREN'
    p[0] = p[2]


def p_params_amlist(p):
    'params : LPAREN amlist RPAREN'
    p[0] = p[2]


def p_objpath_only_ns(p):
    '''objpath : SLASH SLASH VALSEG SLASH VALSEG
               | SLASH SLASH VALSEG SLASH VALSEG SLASH'''
    org = util.IDSEGMENT(p[3])
    mod = util.MODSEGMENT(p[5])
    if not isinstance(mod, tuple):
        mod = (mod, None)

    p[0] = Identity(
        org_id=org,
        model_id=mod[0],
        model_rev=mod[1],
        type_id=None,
        obj_id=None,
    )


def p_objpath_with_ns(p):
    'objpath : SLASH SLASH VALSEG SLASH VALSEG SLASH VALSEG SLASH VALSEG'
    org = util.IDSEGMENT(p[3])
    mod = util.MODSEGMENT(p[5])
    if not isinstance(mod, tuple):
        mod = (mod, None)

    try:
        typ = util.get_structtype(p[7])
    except Exception as err:
        LOGGER.error('Object type invalid: %s', err)
        raise RuntimeError(err) from err
    # Reference are only allowed with AMM types
    if typ >= 0 or typ == StructType.OBJECT:
        raise RuntimeError("Invalid AMM type")

    obj = util.IDSEGMENT(p[9])

    p[0] = Identity(
        org_id=org,
        model_id=mod[0],
        model_rev=mod[1],
        type_id=typ,
        obj_id=obj,
    )


def p_objpath_relative(p):
    '''objpath : DOT SLASH VALSEG SLASH VALSEG
               | DOT DOT SLASH VALSEG SLASH VALSEG SLASH VALSEG'''
    got = len(p)

    if got > 6:
        mod = util.MODSEGMENT(p[got - 5])
        if not isinstance(mod, tuple):
            mod = (mod, None)
    else:
        mod = (None, None)

    try:
        typ = util.get_structtype(p[got - 3])
    except Exception as err:
        LOGGER.error('Object type invalid: %s', err)
        raise RuntimeError(err) from err
    # Reference are only allowed with AMM types
    if typ >= 0 or typ == StructType.OBJECT:
        raise RuntimeError("Invalid AMM type")

    obj = util.IDSEGMENT(p[got - 1])

    p[0] = Identity(org_id=None, model_id=mod[0], model_rev=mod[1], type_id=typ, obj_id=obj)


def p_acbracket(p):
    '''acbracket : LPAREN RPAREN
                 | LPAREN aclist RPAREN'''
    p[0] = p[2] if len(p) == 4 else []


def p_aclist_join(p):
    'aclist : aclist COMMA ari'
    p[0] = p[1] + [p[3]]


def p_aclist_end(p):
    'aclist : ari'
    p[0] = [p[1]]


def p_ambracket(p):
    '''ambracket : LPAREN RPAREN
                 | LPAREN amlist RPAREN'''
    p[0] = p[2] if len(p) == 4 else {}


def p_amlist_join(p):
    'amlist : amlist COMMA ampair'
    p[0] = p[1] | p[3]  # merge dicts


def p_amlist_end(p):
    'amlist : ampair'
    p[0] = p[1]


def p_ampair(p):
    'ampair : ari EQ ari'
    p[0] = {p[1]: p[3]}


def p_structlist_join(p):
    'structlist : structlist structpair'
    p[0] = p[1] | p[2]  # merge dicts


def p_structlist_end(p):
    'structlist : structpair'
    p[0] = p[1]


def p_structpair(p):
    # Keys are case-insensitive so get folded to lower case
    '''structpair : VALSEG EQ VALSEG SC 
                  | VALSEG EQ typedlit SC'''

    key = util.STRUCTKEY(p[1]).casefold()
    p[0] = {key: p[3]}


def p_error(p):
    # Error rule for syntax errors
    msg = f'Syntax error in input at: {p}'
    LOGGER.error(msg)
    raise RuntimeError(msg)

# pylint: enable=invalid-name


def new_parser(**kwargs):
    obj = yacc.yacc(**kwargs)
    return obj
