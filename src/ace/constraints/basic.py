#
# Copyright (c) 2020-2026 The Johns Hopkins University Applied Physics
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
''' Basic constraints enforced from the ADM definitions.
'''
import logging
import os
from sqlalchemy import inspect, orm, func
from typing import Iterable, Optional, List
from ace import models, ari, typing
from ace.lookup import dereference, TypeResolver, TypeResolverError
from .core import register, Issue

LOGGER = logging.getLogger(__name__)


@register
def minimal_metadata(issuelist: List[Issue], obj: object, db_sess: orm.Session):  # pylint: disable=invalid-name
    ''' Ensure an ADM contains minimum content. '''
    count = 0
    if obj is None:
        for name in ('name', 'enum', 'revision'):
            val = getattr(obj, name)
            if val is None:
                issuelist.append(Issue(
                    obj=obj,
                    detail=f'ADM is missing required metadata "{name}"'
                ))
            count += 1

    return count


@register
class unique_adm_names:  # pylint: disable=invalid-name
    ''' Ensure an ADM contains unique identification. '''

    is_global = True

    def __call__(self, issuelist: List[Issue], _obj: object, db_sess: orm.Session):
        count = 0
        attr = models.AdmModule.norm_name

        search = (
            db_sess.query(attr, func.count(models.AdmModule.id))
            .group_by(attr)
            .having(func.count(models.AdmModule.id) > 1)
        )
        for row in search.all():
            query = db_sess.query(models.AdmModule).filter(
                attr == row[0]
            )
            for adm in query.all():
                issuelist.append(Issue(
                    obj=adm,
                    detail=f'Multiple ADMs with metadata "norm_name" of "{row[0]}"'
                ))
        count += 1

        return count


@register
def same_file_name(issuelist: List[Issue], obj: object, _db_sess: orm.Session):
    ''' Ensure an ADM name matches its source file name. '''
    if isinstance(obj, models.AdmModule):
        if obj.source.abs_file_path is None:
            return 0
        int_name = obj.norm_name
        ext_name = os.path.splitext(os.path.basename(obj.source.abs_file_path))[0]
        if int_name != ext_name:
            issuelist.append(Issue(
                obj=obj,
                detail=f'ADM name "{int_name}" stored in differently named file {obj.source.abs_file_path}'
            ))
        return 1

    return 0


@register
class unique_object_names:  # pylint: disable=invalid-name
    ''' Ensure all objects within an ADM section have unique names. '''

    def __init__(self):
        self._list_attrs = []
        mapper = inspect(models.AdmModule)
        for column in mapper.attrs:
            if isinstance(column, orm.relationships.RelationshipProperty):
                # Only care about ADM-member objects
                if issubclass(column.entity.class_, models.AdmObjMixin):
                    self._list_attrs.append(column.key)
        LOGGER.debug('UniqueNames checking sets in: %s',
                     ', '.join(self._list_attrs))

    def __call__(self, issuelist: List[Issue], obj: object, _db_sess: orm.Session):
        count = 0
        if isinstance(obj, models.AdmModule):
            for list_name in self._list_attrs:
                seen_names = set()
                dupe_names = set()
                obj_list = getattr(obj, list_name)
                LOGGER.debug('UniqueNames checking list %s', obj_list)
                for top_obj in obj_list:
                    if top_obj.norm_name in seen_names and top_obj.norm_name not in dupe_names:
                        issuelist.append(Issue(
                            obj=top_obj,
                            detail=(
                                f'Within the set of {list_name} objects '
                                f'the name "{top_obj.name}" is duplicated'
                            ),
                        ))
                        dupe_names.add(top_obj.norm_name)
                    seen_names.add(top_obj.norm_name)
                count += 1
        return count


@register
class valid_type_name:  # pylint: disable=invalid-name
    ''' Ensure that all type names are well-fromed, but not necessarily valid in the context. '''

    def __call__(self, issuelist: List[Issue], obj: object, db_sess: orm.Session, adm=None):
        ''' Entrypoint for this functor. '''
        count = 0
        if isinstance(obj, models.AdmModule):
            count += self._iter_call(issuelist, obj.const, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.edd, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.var, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.ctrl, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.oper, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.sbr, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.tbr, db_sess, adm=obj)

        if isinstance(obj, (models.Const, models.Edd, models.Var)):
            count += self._check_typeobj(issuelist, obj, obj, db_sess, adm)
        elif isinstance(obj, models.Ctrl):
            if obj.result:
                count += self._check_typeobj(issuelist, obj, obj.result, db_sess, adm)
        elif isinstance(obj, models.Oper):
            count += self._check_typeobj(issuelist, obj, obj.result, db_sess, adm)
            for operand in obj.operands.items:
                count += self._check_typeobj(issuelist, obj, operand, db_sess, adm)
        return count

    def _iter_call(self, issuelist: List[Issue], container, *args, **kwargs):
        count = 0
        for obj in container:
            count += self(issuelist, obj, *args, **kwargs)
        return count

    def _check_typeobj(self, issuelist: List[Issue], top_obj, ctr: models.TypeUseMixin, db_sess: orm.Session, adm: models.AdmModule):
        ''' Verify a single named type. '''
        typeobj = ctr.typeobj
        if not typeobj:
            return 0
        LOGGER.debug('Checking object %s type %s', top_obj.norm_name, typeobj)

        try:
            TypeResolver().resolve(ctr.typeobj, adm)
        except TypeResolverError as err:
            issuelist.append(Issue(
                obj=top_obj,
                detail=(
                    f'Within the object named "{top_obj.name}" '
                    f'the type names are not known: {err.badtypes}'
                ),
            ))

        return 1


@register
class valid_reference_ari:  # pylint: disable=invalid-name
    ''' Ensure that all ARIs embedded within ADMs point to real objects.
    Type references in TypeUseMixin are handled separately by the constraint
    :py:cls:`valid_type_name` so not handled here.
    '''

    def __call__(self, issuelist: List[Issue], obj: object, db_sess: orm.Session, top_obj: Optional[models.AdmObjMixin] = None, adm: Optional[models.AdmModule] = None):
        ''' Entrypoint for this functor. '''
        count = 0
        if isinstance(obj, models.AdmModule):
            # object types which have parameters or embedded ARIs, but not type use
            count += self._iter_call(issuelist, obj.ident, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.const, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.ctrl, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.edd, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.oper, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.var, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.sbr, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.tbr, db_sess, adm=obj)

        if isinstance(obj, models.ParamMixin) and obj.parameters:
            for param in obj.parameters.items:
                count += self(issuelist, param, db_sess, top_obj=obj, adm=adm)

        if isinstance(obj, (models.Const, models.Var)):
            # actual check on init value
            count += self._do_check(issuelist, obj.init_value, obj.init_ari, obj, adm, db_sess)
        elif isinstance(obj, models.Sbr):
            count += self._do_check(issuelist, obj.action_value, obj.action_ari, obj, adm, db_sess)
            count += self._do_check(issuelist, obj.condition_value, obj.condition_ari, obj, adm, db_sess)
        elif isinstance(obj, models.Tbr):
            count += self._do_check(issuelist, obj.action_value, obj.action_ari, obj, adm, db_sess)

        if isinstance(obj, models.TypeNameItem):
            # actual check on default
            count += self._do_check(issuelist, obj.default_value, obj.default_ari, top_obj, adm, db_sess)

        return count

    def _iter_call(self, issuelist: List[Issue], container, *args, **kwargs) -> int:
        count = 0
        for obj in container:
            count += self(issuelist, obj, *args, **kwargs)
        return count

    def _do_check(self, issuelist: List[Issue], _value: str, val_ari: Optional[ari.ARI], top_obj: models.AdmObjMixin, adm: models.AdmModule, db_sess: orm.Session) -> int:
        ''' Walk the ARI for any internal references '''
        if val_ari is None:
            return 0

        def checker(val):
            if not isinstance(val, ari.ReferenceARI):
                return
            if dereference(val, db_sess) is None:
                issuelist.append(Issue(
                    obj=top_obj,
                    detail=(
                        f'Within the object named "{top_obj.name}" '
                        f'the reference ARI for {val.ident} is not resolvable'
                    ),
                ))

        val_ari.visit(checker)
        return 1


@register
class default_value_type_match:  # pylint: disable=invalid-name
    ''' Ensure that all ARIs as default or initial values actually match their
    associated type.
    Default values are contained in object parameters, initial values are
    for Const and Var objects.
    '''

    def __call__(self, issuelist: List[Issue], obj: object, db_sess: orm.Session, top_obj: Optional[models.AdmObjMixin] = None, adm: Optional[models.AdmModule] = None):
        ''' Entrypoint for this functor. '''
        count = 0
        if isinstance(obj, models.AdmModule):
            # object types which have parameters or init values
            count += self._iter_call(issuelist, obj.ident, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.const, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.ctrl, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.edd, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.oper, db_sess, adm=obj)
            count += self._iter_call(issuelist, obj.var, db_sess, adm=obj)

        if isinstance(obj, models.ParamMixin) and obj.parameters:
            for param in obj.parameters.items:
                count += self(issuelist, param, db_sess, top_obj=obj, adm=adm)

        if isinstance(obj, models.Ctrl):
            count += self(issuelist, obj.result, db_sess, top_obj=obj, adm=adm)
        elif isinstance(obj, (models.Const, models.Var)):
            # actual check on init-value
            count += self._do_check(issuelist, obj.init_value, obj.init_ari, obj.typeobj, obj, adm)

        if isinstance(obj, models.TypeNameItem):
            # actual check on default
            count += self._do_check(issuelist, obj.default_value, obj.default_ari, obj.typeobj, top_obj, adm)

        return count

    def _iter_call(self, issuelist: List[Issue], container: Iterable, db_sess: orm.Session, adm) -> int:
        count = 0
        for obj in container:
            count += self(issuelist, obj, db_sess, top_obj=obj, adm=adm)
        return count

    def _do_check(self, issuelist: List[Issue], value: str, val_ari: Optional[ari.ARI], typeobj: typing.BaseType, top_obj: models.AdmObjMixin, adm: models.AdmModule) -> int:
        ''' Check the root ARI against its needed type '''
        if val_ari is None:
            return 0

        try:
            TypeResolver().resolve(typeobj, adm)
        except TypeResolverError:
            # treat as separate error
            pass

        if typeobj.get(val_ari) is None:
            issuelist.append(Issue(
                obj=top_obj,
                detail=(
                    f'Within the object named "{top_obj.name}" '
                    f'the value "{value}" does not match '
                    f'the associated type'
                ),
            ))
        return 1
