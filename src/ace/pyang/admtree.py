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
''' Plugin to display the contents of an ADM module as an object tree.
'''

from dataclasses import dataclass, field
import optparse
import io
import logging
from typing import List, Tuple
import pyang
from pyang.context import Context
from pyang.statements import Statement
from pyang.error import err_add
try:
    from ace.adm_yang import AriTextDecoder, TypingDecoder
    from ace.typing import TypeUse
    from ace.ari_text import Encoder as AriEncoder
except ImportError:
    AriTextDecoder = None
    TypingDecoder = None
    TypeUse = None
    AriEncoder = None

logger = logging.getLogger(__name__)

# : Extension module name to hook onto
MODULE_NAME = 'ietf-amm'
MODULE_PREFIX = 'amm'

AMP_OBJ_NAMES = (
    (MODULE_NAME, 'typedef'),
    (MODULE_NAME, 'ident'),
    (MODULE_NAME, 'const'),
    (MODULE_NAME, 'edd'),
    (MODULE_NAME, 'var'),
    (MODULE_NAME, 'ctrl'),
    (MODULE_NAME, 'oper'),
)

TYPED_OBJS = (
    (MODULE_NAME, 'typedef'),
    (MODULE_NAME, 'const'),
    (MODULE_NAME, 'edd'),
    (MODULE_NAME, 'var'),
)


class AdmTree(pyang.plugin.PyangPlugin):
    ''' An output formatter for visualizing an ADM module as an ARI tree.
    '''

    def add_output_format(self, fmts):
        ''' Register this plugin's output formatters. '''
        fmts['admtree'] = self

    def add_opts(self, optparser):
        optlist = [
            optparse.make_option("--full-ari",
                                 dest="full_ari",
                                 action="store_true",
                                 help="Show fully qualified ARI for each object"),
            optparse.make_option("--type-params",
                                 dest="type_params",
                                 action="store_true",
                                 help="Show semantic type parameters, which could be very long"),
        ]
        g = optparser.add_option_group("ADM tree specific options")
        g.add_options(optlist)

    def setup_fmt(self, ctx:Context):
        return pyang.plugin.PyangPlugin.setup_fmt(self, ctx)

    def post_validate(self, ctx:Context, modules):
        return pyang.plugin.PyangPlugin.post_validate(self, ctx, modules)

    def emit(self, ctx:Context, modules:List[Statement], outfile):
        self._prefix = ''

        for module in modules:
            base_ari = f'ari://{module.arg}/'
            self._emit_line(outfile, base_ari, status=self._get_status_str(module))
            self._indent()

            for obj_kwd in AMP_OBJ_NAMES:
                objlist = module.search(obj_kwd)
                if not objlist:
                    continue

                outfile.write('\n')
                if ctx.opts.full_ari:
                    objtype_ari = f'{base_ari}{obj_kwd[1].upper()}/'
                else:
                    objtype_ari = f'./{obj_kwd[1].upper()}/'
                self._emit_line(outfile, objtype_ari)
                self._indent()

                for obj in objlist:
                    if ctx.opts.full_ari:
                        obj_ari = f'{objtype_ari}{obj.arg}'
                    else:
                        obj_ari = f'./{obj.arg}'

                    if obj.keyword in TYPED_OBJS:
                        valtype = self._get_type(ctx, obj)
                    else:
                        valtype = ''

                    self._emit_line(
                        outfile, obj_ari,
                        typestr=valtype,
                        status=self._get_status_str(obj),
                        feature=obj.search_one('if-feature')
                    )
                    self._indent()

                    paramlist = obj.search((MODULE_NAME, 'parameter'), children=obj.i_children)
                    for param in paramlist:
                        typename = self._get_type(ctx, param)
                        self._emit_line(outfile, f'Param {param.arg}', typestr=typename)

                    operandlist = obj.search((MODULE_NAME, 'operand'), children=obj.i_children)
                    for operand in operandlist:
                        typename = self._get_type(ctx, operand)
                        self._emit_line(outfile, f'Operand {operand.arg}', typestr=typename)

                    resultlist = obj.search((MODULE_NAME, 'result'), children=obj.i_children)
                    for result in resultlist:
                        typename = self._get_type(ctx, result)
                        self._emit_line(outfile, f'Result {result.arg}', typestr=typename)

                    self._outdent()

                self._outdent()
            self._outdent()

    def _indent(self):
        self._prefix += '    '

    def _outdent(self):
        self._prefix = self._prefix[:-4]

    def _emit_line(self, outfile, label, typestr=None, status=None, feature=None):
        start = f'{self._prefix} {status or " "} {label}'
        featurestr = f'{{{feature.arg}}}?' if feature else ''
        outfile.write(f'{start:<59} {typestr or "":<19} {featurestr}\n')

    def _get_status_str(self, obj:Statement):
        status = obj.search_one('status')
        if status is None or status.arg == 'current':
            return '+'
        elif status.arg == 'deprecated':
            return 'x'
        elif status.arg == 'obsolete':
            return 'o'

    def _get_type(self, ctx:Context, parent:Statement) -> str:
        if TypingDecoder is None:
            return "(need ACE)";

        ari_dec = AriTextDecoder()
        type_dec = TypingDecoder(ari_dec)
        ari_enc = AriEncoder()

        def get_text(ari) -> str:
            buf = io.StringIO()
            ari_enc.encode(ari, buf)
            return buf.getvalue()

        typeobj = type_dec.decode(parent)
        if ctx.opts.type_params:
            # full parameters
            show = get_text(typeobj.ari_name())
        else:
            # summary text only
            if isinstance(typeobj, TypeUse):
                show = 'use of ' + get_text(typeobj.type_ari)
            else:
                show = typeobj.ari_name().ident.obj_id

        return show


def pyang_plugin_init():
    ''' Called by plugin framework to initialize this plugin.
    '''
    pyang.plugin.register_plugin(AdmTree())
