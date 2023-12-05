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
''' Parser configuration for ARI text decoding.
'''
import logging
from ply import yacc
from ace.ari import (Identity, ReferenceARI, LiteralARI, StructType)
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
    'ssp : SEGMENT'
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
    '''typedlit : SLASH AC LPAREN RPAREN
                | SLASH AC LPAREN aclist RPAREN'''
    value = p[4] if len(p) == 6 else []
    p[0] = LiteralARI(type_enum=StructType.AC, value=value)


def p_typedlit_am(p):
    '''typedlit : SLASH AM LPAREN RPAREN
                | SLASH AM LPAREN amlist RPAREN'''
    value = p[4] if len(p) == 6 else {}
    p[0] = LiteralARI(type_enum=StructType.AM, value=value)


def p_typedlit_single(p):
    'typedlit : SLASH SEGMENT SLASH SEGMENT'
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
        p[0] = LiteralARI.coerce(
            type_enum=typ,
            value=value
        )
    except Exception as err:
        LOGGER.error('Literal type mismatch: %s', err)
        raise RuntimeError(err) from err


def p_ssp_objref(p):
    '''ssp : ident
           | ident LPAREN RPAREN
           | ident LPAREN aclist RPAREN
           | ident LPAREN amlist RPAREN'''
    if len(p) == 2:
        params = None
    elif len(p) == 4:
        params = []
    else:
        params = p[3]
    p[0] = ReferenceARI(
        ident=p[1],
        params=params
    )


def p_ident_with_ns(p):
    'ident : SLASH SEGMENT SLASH SEGMENT SLASH SEGMENT'
    try:
        typ = util.get_structtype(p[4])
    except Exception as err:
        LOGGER.error('Object type invalid: %s', err)
        raise RuntimeError(err) from err

    p[0] = Identity(
        namespace=util.IDSEGMENT(p[2]),
        type_enum=typ,
        name=util.IDSEGMENT(p[6]),
    )


def p_aclist_join(p):
    'aclist : aclist COMMA ari'
    p[0] = p[1] + [p[3]]


def p_aclist_end(p):
    'aclist : ari'
    p[0] = [p[1]]


def p_amlist_join(p):
    'amlist : amlist COMMA ampair'
    p[0] = p[1] | p[3]  # merge dicts


def p_amlist_end(p):
    'amlist : ampair'
    p[0] = p[1]


def p_amlist_pair(p):
    'ampair : ari EQ ari'
    p[0] = {p[1]: p[3]}


def p_error(p):
    # Error rule for syntax errors
    msg = f'Syntax error in input at: {p}'
    LOGGER.error(msg)
    raise RuntimeError(msg)

# pylint: enable=invalid-name


def new_parser(**kwargs):
    obj = yacc.yacc(**kwargs)
    return obj
