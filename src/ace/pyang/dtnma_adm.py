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
''' DTNMA-ADM Plugin
Copyright (c) 2023-2025 The Johns Hopkins University Applied Physics
Laboratory LLC.

DTNMA Application Data Model (ADM) of [I-D.ietf-dtn-adm-yang] uses
YANG syntax and extension statements, but not YANG data modeling statements,
to define static data models known as "ADM Modules".

The transforms provided for ADM Modules are used to apply auto-generated
object enumerations where needed.
'''
import io
import optparse
import os
from typing import List
from pyang import plugin, context, statements, grammar, error
from ace.pyang.dtnma_amm import MODULE_NAME, AMM_OBJ_NAMES
# Use ARI processing library when possible
try:
    import ace
except ImportError:
    ace = None


def pyang_plugin_init():
    ''' Called by plugin framework to initialize this plugin.
    '''
    plugin.register_plugin(DtnmaAdmPlugin())
    plugin.register_plugin(DtnmaRefsPlugin())


class DtnmaAdmPlugin(plugin.PyangPlugin):
    ''' A transformer to clean up ADM Module contents. '''

    def add_opts(self, _optparser:optparse.OptionParser):
        pass

    def setup_ctx(self, _ctx:context.Context):
        pass

    def add_transform(self, xforms):
        xforms['adm-add-enum'] = self

    def transform(self, _ctx:context.Context, modules:List[statements.ModSubmodStatement]):
        for mod_stmt in modules:
            ns_stmt = mod_stmt.search_one('namespace')
            if not ns_stmt or not ns_stmt.arg.startswith('ari:'):
                continue

            # Each object type gets its own enumeration domain
            for obj_kywd in AMM_OBJ_NAMES:
                enums = {}
                missing = []
                for obj_stmt in mod_stmt.search(obj_kywd):
                    enum_stmt = obj_stmt.search_one((MODULE_NAME, 'enum'))
                    if enum_stmt:
                        enums[int(enum_stmt.arg)] = obj_stmt
                    else:
                        missing.append(obj_stmt)
                if not missing:
                    continue

                amm_prefix = [
                    key
                    for key, (name, _rev) in mod_stmt.i_prefixes.items()
                    if name == MODULE_NAME
                ]
                enum_kywd = (amm_prefix[0], 'enum')

                # Start just beyond the existing values
                next_val = max(enums.keys()) + 1 if enums else 0
                for obj_stmt in missing:
                    enum_stmt = statements.new_statement(mod_stmt, obj_stmt, obj_stmt.pos, enum_kywd, str(next_val))
                    obj_stmt.substmts.insert(0, enum_stmt)
                    next_val += 1


class DtnmaRefsPlugin(plugin.PyangPlugin):
    ''' A transformer to validate ARI values as object references. '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not ace:
            return
        self._adms = None
        self._mod_resolver = {}
        self._ari_dec = ace.ari_text.Decoder()

    def add_opts(self, optparser:optparse.OptionParser):
        if ace:
            optparser.add_option(optparse.make_option(
                '--adm-check-refs',
                action="store_true",
                help='Validate all object reference ARI values are dereferenceable'
            ))

    def setup_ctx(self, ctx:context.Context):
        if not ctx.opts.adm_check_refs or not ace:
            return

        self._adms = ace.AdmSet()
        if 'ADM_PATH' not in os.environ:
            os.environ['ADM_PATH'] = os.pathsep.join(ctx.opts.path)
        self._adms.load_default_dirs()

        # keywords using the ARI pyang type
        ari_keywords = [
            keyword
            for keyword, (arg_type, _subspec) in grammar.stmt_map.items()
            if arg_type == 'ARI'
        ]

        # reference checking after all module-level resolution
        statements.add_validation_fun(
            'reference_4',
            ari_keywords,
            self._chk_ari
        )

        # register our error codes
        error.add_error_code(
            'ADM_DEREFERENCE_FAILED', 3,  # minor error
            'the object referenced by "%s" cannot be found in the module path')

    def pre_validate_ctx(self, ctx, modules):
        # cache module namespaces
        self._mod_resolver = {}

        for mod_stmt in modules:
            ns_stmt = mod_stmt.search_one('namespace')
            with io.StringIO(ns_stmt.arg) as buf:
                ns_val = self._ari_dec.decode(buf)

            res = ace.lookup.RelativeResolver(ns_val.ident.org_id, ns_val.ident.model_id)
            self._mod_resolver[mod_stmt] = res

    def _chk_ari(self, ctx:context.Context, stmt:statements.Statement):
        if not ctx.opts.adm_check_refs:
            return

        with io.StringIO(stmt.arg) as buf:
            ari_val = self._ari_dec.decode(buf)
        if not isinstance(ari_val, ace.ari.ReferenceARI):
            return

        # only care about targeted modules from pre-validate
        resolver = self._mod_resolver.get(stmt.top)
        if resolver is None:
            return
        # resolve any module-relative parts
        ari_abs = ari_val.map(resolver)
        # ignore namespace references
        if not ace.typing.BUILTINS_BY_ENUM[ace.StructType.OBJECT].get(ari_abs):
            return

        obj = ace.lookup.dereference(ari_abs, self._adms.db_session())

        if obj is None:
            error.err_add(ctx.errors, stmt.pos,
                          'ADM_DEREFERENCE_FAILED', (stmt.arg,))
