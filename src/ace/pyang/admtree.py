''' Plugin to display the contents of an ADM module as an object tree.
'''

from dataclasses import dataclass, field
import optparse
import re
import logging
from typing import List, Tuple
import pyang
from pyang.error import err_add

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

TYPE_RESTRICTS = {
    'length',
    'pattern',
    (MODULE_NAME, 'int-labels'),
    (MODULE_NAME, 'cddl'),
}
TYPE_USES = {'type', 'ulist', 'dlist', 'umap', 'tblt', 'union'}


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
                                 help="Show fullly qualified ARI for each object"),
        ]
        g = optparser.add_option_group("ADM tree specific options")
        g.add_options(optlist)

    def setup_fmt(self, ctx):
        return pyang.plugin.PyangPlugin.setup_fmt(self, ctx)

    def post_validate(self, ctx, modules):
        return pyang.plugin.PyangPlugin.post_validate(self, ctx, modules)

    def emit(self, ctx, modules, outfile):
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

                    paramlist = self._search(ctx, obj, (MODULE_NAME, 'parameter'))
                    for param in paramlist:
                        typename = self._get_type(ctx, param)
                        self._emit_line(outfile, f'Param {param.arg}', typestr=typename)

                    operandlist = self._search(ctx, obj, (MODULE_NAME, 'operand'))
                    for operand in operandlist:
                        typename = self._get_type(ctx, operand)
                        self._emit_line(outfile, f'Operand {operand.arg}', typestr=typename)

                    resultlist = self._search(ctx, obj, (MODULE_NAME, 'result'))
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

    def _get_status_str(self, obj):
        status = obj.search_one('status')
        if status is None or status.arg == 'current':
            return '+'
        elif status.arg == 'deprecated':
            return 'x'
        elif status.arg == 'obsolete':
            return 'o'

    def _search(self, ctx, stmt, name):
        children = getattr(stmt, 'i_children', stmt.substmts)
        return stmt.search(name, children=children)

    def _get_type(self, ctx, typeuse):
        found = {
            keywd: typeuse.search_one((MODULE_NAME, keywd))
            for keywd in TYPE_USES
        }
        found_count = len(tuple(filter(None, found.values())))
        if found_count == 0:
            pass
        elif found_count > 1:
            pass

        if found['type'] is not None:
            typestmt = found['type']
            typename = typestmt.arg
            restrict = []
            for keywd in TYPE_RESTRICTS:
                restrict += typestmt.search(keywd)

            if restrict:
                return f'{typename} ({len(restrict)} restrictions)'
            else:
                return typename
        elif found['ulist'] is not None:
            elemtype = self._get_type(ctx, found['ulist'])
            return f'ulist ({elemtype})'
        elif found['dlist'] is not None:
            types = self._search(ctx, found['dlist'], (MODULE_NAME, 'type'))
            seqs = self._search(ctx, found['dlist'], (MODULE_NAME, 'seq'))
            return f'dlist ({len(types) + len(seqs)} parts)'
        elif found['umap'] is not None:
            return f'map'
        elif found['tblt'] is not None:
            cols = self._search(ctx, found['tblt'], (MODULE_NAME, 'column'))
            return f'tblt ({len(cols)} columns)'
        elif found['union'] is not None:
            subs = []
            for keywd in TYPE_USES:
                subs += self._search(ctx, found['union'], (MODULE_NAME, keywd))
            return f'union ({len(subs)} types)'
        else:
            return 'No type'


def pyang_plugin_init():
    ''' Called by plugin framework to initialize this plugin.
    '''
    pyang.plugin.register_plugin(AdmTree())
