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
''' Lexer configuration for ARI text decoding.
'''
import base64
import logging
import re
from ply import lex
from ace.ari import StructType, LITERAL_TYPES

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
    'COMMA',
    'LPAREN',
    'RPAREN',
    'EQ',
    'BOOL',
    'INT',
    'FLOAT',
    'IDENT',
    'TSTR',
    'BSTR',
)

# Function tokens are searched in declaration order
# pylint: disable=invalid-name disable=missing-function-docstring


def t_ARI_PREFIX(tok):
    r'ari:'
    return tok


def t_BOOL(tok):
    r'true|false'
    tok.value = (tok.value == 'true')
    return tok


def t_FLOAT(tok):
    r'[+-]?((\d+|\d*\.\d*)([eE][+-]?\d+)|\d*\.\d*|Infinity)|NaN'
    # float either contains a decimal point or exponent or both
    tok.value = float(tok.lexer.lexmatch[0])
    return tok


def t_INT(tok):
    r'[+-]?(0b[01]+|0x[0-9a-fA-F]+|\d+)'
    tok.value = int(tok.lexer.lexmatch[0], 0)
    return tok


def t_TSTR(tok):
    r'"(?P<val>[^\"]*)"'
    tok.value = tok.lexer.lexmatch['val']
    return tok


def t_BSTR(tok):
    r'(?P<enc>h|b32|h32|b64)?\'(?P<val>[^\']*)\''
    enc = tok.lexer.lexmatch['enc']
    val = tok.lexer.lexmatch['val']
    if enc == 'h':
        tok.value = base64.b16decode(val, casefold=True)
    elif enc == 'b32':
        rem = len(val) % 8
        if rem in {2, 4, 5, 7}:
            val += '=' * (8 - rem)
        tok.value = base64.b32decode(val, casefold=True)
    elif enc == 'h32':
        raise NotImplementedError
    elif enc == 'b64':
        rem = len(val) % 4
        if rem in {2, 3}:
            val += '=' * (4 - rem)
        tok.value = base64.b64decode(val)
    else:
        tok.value = bytes(val, 'ascii')
    return tok


# Regular expression rules for simple tokens
t_SLASH = r'/'
t_COMMA = r','
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_EQ = r'='
t_IDENT = r'[a-zA-Z_][a-zA-Z0-9_\-\.]+'

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
