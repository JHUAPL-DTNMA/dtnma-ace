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
''' CODEC for converting ARI to and from text URI form.
'''
import datetime
import logging
import os
from typing import TextIO
from urllib.parse import quote
import xdg_base_dirs
from ace.ari import (
    StructType, ARI, LiteralARI, ReferenceARI
)
from ace.cborutil import to_diag
from .lexmod import new_lexer
from .parsemod import new_parser
from .encode import Encoder, EncodeOptions, quote

__all__ = (
    'Encoder', 'EncodeOptions', 'quote',
    'Decoder',
)

LOGGER = logging.getLogger(__name__)


class ParseError(RuntimeError):
    ''' Indicate an error in ARI parsing. '''


class Decoder:
    ''' The decoder portion of this CODEC. '''

    def __init__(self):
        self._cache_path = os.path.join(xdg_base_dirs.xdg_cache_home(), 'ace', 'ply')
        if not os.path.exists(self._cache_path):
            os.makedirs(self._cache_path)
        LOGGER.debug('cache at %s', self._cache_path)
        self._pickle_path = os.path.join(self._cache_path, 'parse.pickle')

    def decode(self, buf: TextIO) -> ARI:
        ''' Decode an ARI from UTF8 text.

        :param buf: The buffer to read from.
        :return: The decoded ARI.
        :throw ParseError: If there is a problem with the input text.
        '''
        text = buf.read()

        if LOGGER.isEnabledFor(logging.DEBUG):
            lexer = new_lexer()
            lexer.input(text)
            while True:
                tok = lexer.token()
                if tok is None:
                    break
                LOGGER.debug('TOKEN %s', tok)

        lexer = new_lexer()
        parser = new_parser(
            debug=False,
            outputdir=self._cache_path,
            picklefile=self._pickle_path
        )
        try:
            res = parser.parse(text, lexer=lexer)
        except Exception as err:
            raise ParseError(f'Failed to parse "{text}": {err}') from err

        return res

