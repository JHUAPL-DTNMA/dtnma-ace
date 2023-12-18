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
''' Perform conversion to and from nickname content in ARIs.
'''
import enum
import logging
import cbor2
from ace import models
from ace.ari import ReferenceARI, StructType
from ace.adm_set import AdmSet

LOGGER = logging.getLogger(__name__)

# : ORM relationship attribute for each ARI reference type
ORM_TYPE = {
    StructType.TYPEDEF: models.Typedef,
    StructType.CONST: models.Const,
    StructType.CTRL: models.Ctrl,
    StructType.EDD: models.Edd,
    StructType.OPER: models.Oper,
    StructType.VAR: models.Var,
}


@enum.unique
class Mode(enum.Enum):
    ''' The :class:`Converter` conversion direction '''
    # : Obtain nickname enums
    TO_NN = enum.auto()
    # : Interpret nickname enums
    FROM_NN = enum.auto()


class Converter:
    ''' This class traverses an ARI and converts all contents to or from
    nickname data based on an :class:`AdmSet` database.

    :param mode: The conversion mode.
    :param adms: The :class:`AdmSet` to look up nicknames.
    :param must_nickname: If true, the conversion will fail if no nickname
    is available.
    '''

    def __init__(self, mode: Mode, adms: AdmSet, must_nickname: bool=False):
        self._mode = mode
        self._adms = adms
        self._must = must_nickname

    def __call__(self, obj):
        LOGGER.debug('Converting object %s', obj)
        if isinstance(obj, ReferenceARI):
            self._convert_ari(obj)
            if obj.params:
                for item in obj.params:
                    self(item)

        elif obj.type_id is StructType.AC:
            for item in obj.value:
                self(item)

        elif obj.type_id is StructType.AM:
            for key, val in obj.value.items():
                self(key)  # FIXME: replace item if key is modified
                self(val)

    def _convert_ari(self, ari):
        if self._mode == Mode.TO_NN and isinstance(ari.ident.ns_id, str):
            # Prefer nicknames
            adm_name = ari.ident.ns_id
            obj_type = ari.ident.type_id
            obj_name = ari.ident.obj_id

            adm = self._adms.get_by_norm_name(adm_name)
            LOGGER.debug('Got ADM %s', adm)
            obj = self._adms.get_child(adm, ORM_TYPE[obj_type], norm_name=obj_name)
            LOGGER.debug('ARI type %s name %s resolved to enums for ADM %s, obj %s',
                         obj_type, obj_name,
                         adm.enum if adm else None,
                         obj.enum if obj else None)

            if adm is None or adm.enum is None:
                if self._must:
                    if adm is None:
                        err = 'does not exist'
                    else:
                        err = 'does not have an enumeration'
                    msg = f'The ADM named {adm_name} {err}'
                    raise RuntimeError(msg)
                return
            if obj is None or obj.enum is None:
                if self._must:
                    if obj is None:
                        err = 'does not exist'
                    else:
                        err = 'does not have an enumeration'
                    msg = f'The ADM object named {obj_name} {err}'
                    raise RuntimeError(msg)
                return

            # ARI IDs from enums
            ari.ident.ns_id = adm.enum
            ari.ident.obj_id = obj.enum

            # Convert parameter types from text ARI as needed
            if isinstance(obj, models.ParamMixin) and obj.parameters is not None:
                for ix, spec in enumerate(obj.parameters.items):
                    if spec.type == 'TNVC':
                        ari.params[ix] = TNVC(items=ari.params[ix].items)

        if self._mode == Mode.FROM_NN and isinstance(ari.ident.ns_id, int):
            adm_enum = ari.ident.ns_id
            obj_enum = ari.ident.obj_id

            adm = self._adms.get_by_enum(adm_enum)
            LOGGER.debug('Got ADM %s', adm)
            obj = self._adms.get_child(adm, ORM_TYPE[ari.ident.type_id], enum=obj_enum)
            LOGGER.debug('ARI nickname %s name %s resolved to type %s name %s obj %s', ari.ident.ns_id, ari.ident.obj_id, ari.ident.type_id, obj_enum, obj)

            # ARI IDs from names
            ari.ident.ns_id = adm.norm_name
            ari.ident.obj_id = obj.norm_name
