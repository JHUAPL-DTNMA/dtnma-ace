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
from ace.ari import AC, EXPR, Identity, ReferenceARI, LiteralARI, StructType
from ace.util import is_printable
from .lexmod import tokens  # pylint: disable=unused-import


# make linters happy
__all__ = [
    'tokens',
    'new_parser',
]


LOGGER = logging.getLogger(__name__)


# pylint: disable=invalid-name disable=missing-function-docstring

def p_ari_explicit(p):
    'ari : ARI_PREFIX ssp'
    p[0] = p[2]


def p_ssp_literal(p):
    'ssp : literal'
    p[0] = p[1]


def p_ari_literal(p):
    'ari : literal'
    p[0] = p[1]


def p_literal_without_type(p):
    'literal : litvalue'
    p[0] = p[1]


def p_literal_with_type(p):
    'literal : TYPEDOT litvalue'
    p[0] = LiteralARI(
        type_enum=p[1],
        value=p[2].value
    )
    try:
        p[0].check_type()
    except Exception as err:
        LOGGER.error('Literal type mismatch: %s', err)
        raise RuntimeError(err) from err


def p_litvalue_bool(p):
    'litvalue : BOOL'
    p[0] = LiteralARI(
        type_enum=StructType.BOOL,
        value=p[1],
    )


def p_litvalue_int(p):
    'litvalue : INT'
    p[0] = LiteralARI(
        type_enum=StructType.VAST,
        value=p[1],
    )


def p_litvalue_float(p):
    'litvalue : FLOAT'
    p[0] = LiteralARI(
        type_enum=StructType.REAL64,
        value=p[1],
    )


def p_litvalue_tstr(p):
    'litvalue : TSTR'
    p[0] = LiteralARI(
        type_enum=StructType.STR,
        value=p[1],
    )


def p_litvalue_bstr(p):
    'litvalue : BSTR'
    p[0] = LiteralARI(
        type_enum=StructType.BSTR,
        value=p[1],
    )


def p_ssp_without_params(p):
    'ssp : ident'
    p[0] = ReferenceARI(
        ident=p[1]
    )


def p_ssp_empty_params(p):
    'ssp : ident LPAREN RPAREN'
    p[0] = ReferenceARI(
        ident=p[1],
        params=[],
    )


def p_ssp_with_params(p):
    'ssp : ident LPAREN paramlist RPAREN'
    p[0] = ReferenceARI(
        ident=p[1],
        params=p[3],
    )


def p_paramlist_join(p):
    'paramlist : paramlist COMMA paramitem'
    obj = p[1]
    obj.append(p[3])
    p[0] = obj


def p_paramlist_end(p):
    'paramlist : paramitem'
    p[0] = [p[1]]


def p_paramitem_ari(p):
    'paramitem : ari'
    p[0] = p[1]


def p_paramitem_acempty(p):
    'paramitem : LSQRB RSQRB'
    p[0] = AC()


def p_paramitem_expr(p):
    'paramitem : TYPENAME LSQRB aclist RSQRB'
    p[0] = EXPR(type_enum=p[1], items=p[3].items)


def p_paramitem_aclist(p):
    'paramitem : LSQRB aclist RSQRB'
    p[0] = p[2]


def p_aclist_join(p):
    'aclist : aclist COMMA ari'
    obj = p[1]
    obj.items.append(p[3])
    p[0] = obj


def p_aclist_end(p):
    'aclist : ari'
    p[0] = AC(items=[p[1]])


def p_ident_with_ns(p):
    'ident : SLASH nsid SLASH TYPEDOT objid'
    p[0] = Identity(
        namespace=p[2],
        type_enum=p[4],
        name=p[5],
    )


#FIXME: this is not a valid path but it is used by js-amp.me
def p_ident_empty_ns(p):
    'ident : SLASH SLASH TYPEDOT objid'
    p[0] = Identity(
        type_enum=p[3],
        name=p[4],
    )


def p_ident_without_ns(p):
    'ident : SLASH TYPEDOT objid'
    p[0] = Identity(
        type_enum=p[2],
        name=p[3],
    )


def p_nsid_int(p):
    'nsid : INT'
    p[0] = p[1]


def p_nsid_name(p):
    'nsid : NAME'
    p[0] = p[1]


def p_objid_bstr(p):
    'objid : BSTR'
    name = p[1]
    # Preserve text names
    if is_printable(name):
        name = name.decode('utf-8')
    p[0] = name


def p_objid_name(p):
    'objid : NAME'
    p[0] = p[1]


def p_error(p):
    # Error rule for syntax errors
    msg = f'Syntax error in input at: {p}'
    LOGGER.error(msg)
    raise RuntimeError(msg)

# pylint: enable=invalid-name


def new_parser(**kwargs):
    obj = yacc.yacc(**kwargs)
    return obj
