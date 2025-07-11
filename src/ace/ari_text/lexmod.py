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
''' Lexer configuration for ARI text decoding.
'''
import logging
import re
from urllib.parse import unquote
from ply import lex

# make linters happy
__all__ = [
    'tokens',
    'new_lexer',
]

LOGGER = logging.getLogger(__name__)

# List of token names.   This is always required
tokens = (
    'ARI_PREFIX',
    'SLASH',
    'DOT',
    'COMMA',
    'SC',
    'LPAREN',
    'RPAREN',
    'EQ',
    'AC',
    'AM',
    'TBL',
    'EXECSET',
    'RPTSET',
    'VALSEG',
)

# Function tokens are searched in declaration order
# pylint: disable=invalid-name disable=missing-function-docstring


def t_ARI_PREFIX(tok):
    r'ari:'
    return tok


def t_AC(tok):
    r'(AC|17)/'
    return tok


def t_AM(tok):
    r'(AM|18)/'
    return tok


def t_TBL(tok):
    r'(TBL|19)/'
    return tok


def t_EXECSET(tok):
    r'(EXECSET|20)/'
    return tok


def t_RPTSET(tok):
    r'(RPTSET|21)/'
    return tok


def t_DOT(tok):
    r'\.'
    return tok


# This is the same as RFC 3986 'segment-nz' production with some excluded
# for AC/AM recursion: "(" ")" ";" "="
def t_VALSEG(tok):
    r'([a-zA-Z0-9\-\._~\!\'\*\+\:@]|%[0-9a-fA-F]{2})+'
    tok.value = unquote(tok.value)
    return tok


# Regular expression rules for simple tokens
t_SLASH = r'/'
t_COMMA = r','
t_SC = r';'
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_EQ = r'='

# All space is ignored for lexing purposes
t_ignore = ' \t\n'


def t_error(t):
    # Error handling rule
    LOGGER.error("Illegal character '%s'", t.value[0])
    t.lexer.skip(1)

# pylint: enable=invalid-name


def new_lexer(**kwargs):
    kwargs.setdefault('reflags', re.IGNORECASE)
    obj = lex.lex(**kwargs)
    return obj
