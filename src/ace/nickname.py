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
''' Perform conversion to and from nickname content in ARIs.
'''
import enum
import logging
from sqlalchemy.orm.session import Session
from ace import models
from ace.ari import ARI, ReferenceARI, Identity
from ace.lookup import find_adm, dereference

LOGGER = logging.getLogger(__name__)


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
    :param db_sess: The :class:`AdmSet` to look up nicknames.
    :param must_nickname: If true, the conversion will fail if no nickname
    is available.
    '''

    def __init__(self, mode:Mode, db_sess:Session, must_nickname:bool=False):
        self._mode = mode
        self._db_sess = db_sess
        self._must = must_nickname

    def __call__(self, ari:ARI) -> ARI:
        LOGGER.debug('Converting object %s', ari)
        return ari.map(self._convert_ari)

    def _convert_ari(self, ari:ARI) -> ARI:
        if isinstance(ari, ReferenceARI):
            ari = self._convert_ref(ari)

        return ari

    def _convert_ref(self, ari:ReferenceARI) -> ReferenceARI:
        if ari.ident.type_id is not None:
            obj = dereference(ari, self._db_sess)
        else:
            obj = None
        if obj is not None:
            adm = obj.module
        else:
            adm = find_adm(ari.ident.org_id, ari.ident.model_id, ari.ident.model_rev, self._db_sess)
        LOGGER.debug('ARI for %s resolved to ADM %s, obj %s',
                     ari.ident, adm, obj)

        if self._mode == Mode.TO_NN:
            # Prefer nicknames
            org_id = ari.ident.org_id
            if adm is None or adm.ns_org_enum is None:
                if self._must:
                    if adm is None:
                        err = 'does not exist'
                    else:
                        err = 'does not have an enumeration'
                    msg = f'The ADM named {org_id} {err}'
                    raise RuntimeError(msg)
            else:
                org_id = adm.ns_org_enum

            model_id = ari.ident.model_id
            if adm is None or adm.ns_model_enum is None:
                if self._must:
                    if adm is None:
                        err = 'does not exist'
                    else:
                        err = 'does not have an enumeration'
                    msg = f'The ADM named {model_id} {err}'
                    raise RuntimeError(msg)
            else:
                model_id = adm.ns_model_enum

            obj_id = ari.ident.obj_id
            if obj is None or obj.enum is None:
                if self._must:
                    if obj is None:
                        err = 'does not exist'
                    else:
                        err = 'does not have an enumeration'
                    msg = f'The ADM object named {obj_id} {err}'
                    raise RuntimeError(msg)
            else:
                obj_id = obj.enum

            # ARI IDs from enums
            new_ident = Identity(
                org_id=org_id,
                model_id=model_id,
                type_id=ari.ident.type_id,
                obj_id=obj_id
            )

        elif self._mode == Mode.FROM_NN:
            org_id = ari.ident.org_id
            if adm is None:
                if self._must:
                    msg = f'The ADM organization named {org_id} does not exist'
                    raise RuntimeError(msg)
            else:
                org_id = adm.ns_org_name

            model_id = ari.ident.model_id
            if adm is None:
                if self._must:
                    msg = f'The ADM model named {model_id} does not exist'
                    raise RuntimeError(msg)
            else:
                model_id = adm.ns_model_name

            obj_id = ari.ident.obj_id
            if obj is None:
                if self._must:
                    msg = f'The ADM object named {obj_id} does not exist'
                    raise RuntimeError(msg)
            else:
                obj_id = obj.norm_name

            # ARI IDs from names
            new_ident = Identity(
                org_id=org_id,
                model_id=model_id,
                type_id=ari.ident.type_id,
                obj_id=obj_id
            )

        LOGGER.debug('got ident %s', new_ident)
        return ReferenceARI(
            ident=new_ident,
            params=ari.params
        )
