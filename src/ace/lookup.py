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
''' Dereference objects and types from a model.
'''

import copy
from dataclasses import dataclass
import datetime
import logging
from typing import Dict, List, Optional, Union
from sqlalchemy.orm.session import Session, object_session
from .util import normalize_ident
from .ari import (
    ARI, LiteralARI, ReferenceARI, Identity, StructType,
    UNDEFINED, is_undefined
)
from .typing import (
    BUILTINS_BY_ENUM, BaseType, SemType, TypeUse, Sequence, type_walk
)
from . import models
from .models import AdmModule, AdmObjMixin

LOGGER = logging.getLogger(__name__)

ORM_TYPE = {
    StructType.TYPEDEF: models.Typedef,
    StructType.IDENT: models.Ident,
    StructType.CONST: models.Const,
    StructType.EDD: models.Edd,
    StructType.VAR: models.Var,
    StructType.CTRL: models.Ctrl,
    StructType.OPER: models.Oper,
    StructType.SBR: models.Sbr,
    StructType.TBR: models.Tbr,
}
''' Map from reference type-ID to ADM model type. '''


class RelativeResolver:
    ''' Resolve module-relative ARIs '''

    def __init__(self, org_id: Union[str, int], model_id: Union[str, int]):
        self._org_id = org_id
        self._model_id = model_id

    def __call__(self, ari:ARI) -> ARI:
        if isinstance(ari, ReferenceARI):
            if ari.ident.org_id is None or ari.ident.model_id is None:
                out_org_id = ari.ident.org_id if ari.ident.org_id is not None else self._org_id
                out_mod_id = ari.ident.model_id if ari.ident.model_id is not None else self._model_id
                ari.ident = Identity(
                    org_id=out_org_id,
                    model_id=out_mod_id,
                    type_id=ari.ident.type_id,
                    obj_id=ari.ident.obj_id,
                )
        return ari


def find_adm(org_id: Union[str, int], model_id: Union[str, int],
             model_rev: Optional[datetime.date], db_sess:Session) -> Optional[AdmModule]:
    ''' Dereference an ADM module.
    '''
    query_adm = db_sess.query(AdmModule)

    if isinstance(org_id, int):
        query_adm = query_adm.filter(AdmModule.ns_org_enum == org_id)
    elif isinstance(org_id, str):
        query_adm = query_adm.filter(AdmModule.ns_org_name == normalize_ident(org_id))
    else:
        raise TypeError(f'ReferenceARI org_id is not int or str: {org_id}')

    if isinstance(model_id, int):
        query_adm = query_adm.filter(AdmModule.ns_model_enum == model_id)
    elif isinstance(model_id, str):
        query_adm = query_adm.filter(AdmModule.ns_model_name == normalize_ident(model_id))
    else:
        raise TypeError(f'ReferenceARI model_id is not int or str: {model_id}')

    if model_rev is not None:
        query_adm = query_adm.filter(AdmModule.latest_revision_date == model_rev)

    found_adm = query_adm.one_or_none()
    return found_adm


def dereference(ref:ReferenceARI, db_sess:Session) -> Optional[AdmObjMixin]:
    ''' Dereference a single object reference.
    '''
    orm_type = ORM_TYPE[ref.ident.type_id]

    found_adm = find_adm(ref.ident.org_id, ref.ident.model_id, ref.ident.model_rev, db_sess)
    if found_adm is None:
        return None

    obj_id = ref.ident.obj_id
    query_obj = (
        db_sess.query(orm_type)
        .filter(orm_type.module == found_adm)
    )
    if isinstance(obj_id, int):
        query_obj = query_obj.filter(orm_type.enum == obj_id)
    elif isinstance(obj_id, str):
        query_obj = query_obj.filter(orm_type.norm_name == normalize_ident(obj_id))
    else:
        raise TypeError('ReferenceARI obj_id is not int or str')
    found_obj = query_obj.one_or_none()
    return found_obj


class TypeResolverError(RuntimeError):

    def __init__(self, msg:str, badtypes:List):
        super().__init__(msg)
        self.badtypes = badtypes


class TypeResolver:
    ''' A caching recursive type resolver.
    '''

    def __init__(self):
        self._cache = dict()
        self._badtypes = None
        self._db_sess = None

    def resolve(self, typeobj:SemType, adm:'AdmModule') -> SemType:
        ''' Bind references to external BaseType objects from type names.
        This function is not reentrant.

        :param typeobj: The original unbound type object (and any children).
        :return: The :ivar:`typeobj` with all type references bound.
        :raise TypeResolverError: If any required types are missing.
        '''
        if typeobj is None:
            return None

        self._badtypes = set()
        self._db_sess = object_session(adm)
        LOGGER.debug('Resolver started')
        for sub_obj in type_walk(typeobj):
            self._typeuse_bind(sub_obj)
        LOGGER.debug('Resolver finished with %d bad', len(self._badtypes))
        if self._badtypes:
            raise TypeResolverError(f'Missing types to bind to: {self._badtypes}', self._badtypes)

        for sub_obj in type_walk(typeobj):
            self._constraint_bind(sub_obj)

        # Verify type use constraint applicability
        for sub_obj in type_walk(typeobj):
            if isinstance(sub_obj, TypeUse):

                have_types = set()
                for subsub_obj in type_walk(sub_obj):
                    have_types |= subsub_obj.all_type_ids()

                for constr in sub_obj.constraints:
                    need_one_type = constr.applicable()
                    met_types = need_one_type & have_types
                    if not met_types:
                        raise TypeResolverError(f'Constraint needs {need_one_type} but have only {have_types}', [])

        self._badtypes = None
        self._db_sess = None
        return typeobj

    def _typeuse_bind(self, obj:'BaseType'):
        ''' A type visitor suitable for binding :cls:`TypeUse` objects
        from type references.
        '''
        if not isinstance(obj, TypeUse):
            return

        if obj.base is not None:
            # already bound, nothing to do
            return

        basetypeobj = None
        typedef = None
        LOGGER.debug('type search for %s', obj.type_ari)
        if isinstance(obj.type_ari, LiteralARI):
            basetypeobj = BUILTINS_BY_ENUM[obj.type_ari.value]
        elif isinstance(obj.type_ari, ReferenceARI):
            try:
                typedef = dereference(obj.type_ari, self._db_sess)
                if not isinstance(typedef, models.Typedef):
                    typedef = None
            except TypeError:
                typedef = None

            if typedef is None:
                self._badtypes.add(obj.type_ari.ident)
        else:
            self._badtypes.add(obj.type_ari)

        if basetypeobj:
            obj.base = basetypeobj
        elif typedef:
            key = (typedef.module.norm_name, typedef.norm_name)
            cached = self._cache.get(key)
            if cached:
                obj.base = cached
            else:
                # recursive binding
                typeobj = copy.copy(typedef.typeobj)
                # cache object before recursion
                self._cache[key] = typeobj

                LOGGER.debug('recurse binding %s for %s', typedef.norm_name, typeobj)
                for sub_obj in type_walk(typeobj):
                    self._typeuse_bind(sub_obj)

                obj.base = typeobj

        LOGGER.debug('result for %s bound %s', obj.type_ari, obj.base)

    def _constraint_bind(self, obj:'BaseType') -> None:
        ''' Bindi :cls:`Constraint` objects to local DB session.
        '''
        from .type_constraint import IdentRefBase

        if not isinstance(obj, TypeUse):
            return

        for cnst in obj.constraints:
            if isinstance(cnst, IdentRefBase):
                try:
                    ident = dereference(cnst.base_ari, self._db_sess)
                    if not isinstance(ident, models.Ident):
                        ident = None
                except TypeError:
                    ident = None

                if ident is None:
                    self._badtypes.add(cnst.base_ari.ident)
                else:
                    cnst.base_ident = ident


@dataclass
class FormalParameter:
    ''' A single formal parameter obtained from a :cls:`models.ParamMixin`
    object within an ADM context. '''

    name:str
    ''' The unique name of the parameter. '''
    index:int
    ''' The list index (ordinal) of the parameter. '''
    typeobj:SemType
    ''' The fully recursively resolved type of the parameter. '''
    default:Optional[ARI] = None
    ''' Default value. '''


class ParameterError(RuntimeError):
    ''' Exception when parameter handling fails. '''


class ActualParameterSet:
    ''' An actual parameter set normalized from given parameters
    based on formal parameters.

    :param gparams: The given parameters from a :cls:`ReferenceARI` value.
    :param fparams: The formal parameters from an ADM.
    '''

    def __init__(self, gparams:Union[List[ARI], Dict[ARI, ARI]],
                 fparams:List['FormalParameter']):
        self._ordinal = [None for _ix in range(len(fparams))]
        self._name = {}

        # manipulate the list/dict in place
        gparams = copy.copy(gparams)

        for fparam in fparams:
            if gparams is None:
                # no parameters at all
                gparam = UNDEFINED
            elif isinstance(gparams, list):
                if isinstance(fparam.typeobj, Sequence):
                    # special handling of greedy formal parameter
                    glist = gparams[fparam.index:]
                    got = fparam.typeobj.take(glist)
                    if glist:
                        LOGGER.warning('seq parameter type left %d unused given parameters', len(glist))

                    # indicate all are used
                    for g_ix in range(fparam.index, fparam.index + len(got)):
                        gparams[g_ix] = None

                    gparam = LiteralARI(got, StructType.AC)
                else:
                    try:
                        gparam = gparams[fparam.index]
                        gparams[fparam.index] = None  # mark as used
                    except IndexError:
                        gparam = UNDEFINED
            elif isinstance(gparams, dict):
                # Try both numeric and text keys
                keys = (
                    LiteralARI(fparam.index),
                    LiteralARI(fparam.name),
                )
                gparam = tuple(filter(None, [gparams.pop(key, None) for key in keys]))
                if len(gparam) > 1:
                    keys = [str(key.value) for key in keys]
                    raise ParameterError(f'Duplicate given parameters for: {",".join(keys)}')
                elif len(gparam) == 1:
                    gparam = gparam[0]
                else:
                    gparam = UNDEFINED
            else:
                raise ParameterError(f'Unhandled given parameters as {type(gparams)}')

            self._add_val(gparam, fparam)

        if isinstance(gparams, list):
            unused = [val for val in gparams if val is not None]
            if unused:
                raise ParameterError(f'Too many given parameters, unused: {unused}')
        if isinstance(gparams, dict) and gparams:
            keys = [str(key.value) for key in gparams.keys()]
            raise ParameterError(f'Too many given parameters, unused keys: {",".join(keys)}')

    def _add_val(self, gparam:ARI, fparam:'FormalParameter'):
        if is_undefined(gparam):
            if fparam.default is not None:
                gparam = fparam.default
            else:
                LOGGER.warning('Parameter %s/%s has no default value, leaving undefined',
                               fparam.name, fparam.index)

        try:
            aparam = fparam.typeobj.convert(gparam)
        except (TypeError, ValueError):
            raise ParameterError(f'Parameter "{fparam.name}" cannot be coerced from value {gparam}')
        LOGGER.debug('Normalizing parameter %s from %s to %s', fparam.name, gparam, aparam)
        self._ordinal[fparam.index] = aparam
        self._name[fparam.name] = aparam

    def __iter__(self):
        return iter(self._ordinal)

    def __len__(self):
        return len(self._ordinal)

    def __getitem__(self, idx:Union[int, str]) -> ARI:
        if isinstance(idx, int):
            return self._ordinal[idx]
        elif isinstance(idx, str):
            return self._name[idx]
        else:
            raise KeyError(f'Invalid index type {type(idx).__name__}')
