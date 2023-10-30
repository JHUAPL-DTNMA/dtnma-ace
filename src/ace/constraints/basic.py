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
''' Basic constraints enforced from the ADM definitions.
'''
import json
import logging
import os
from sqlalchemy import inspect, orm, func
from ace import models, ari, nickname, util
from .core import register, Issue

LOGGER = logging.getLogger(__name__)


@register
def minimal_metadata(issuelist, obj, db_sess):  # pylint: disable=invalid-name
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

    def __call__(self, issuelist, obj, db_sess):
        count = 0
        for name in ('norm_name', 'enum'):
            attr = getattr(models.AdmFile, name)
            search = (
                db_sess.query(attr, func.count(models.AdmFile.id))
                .group_by(attr)
                .having(func.count(models.AdmFile.id) > 1)
            )
            for row in search.all():
                query = db_sess.query(models.AdmFile).filter(
                    attr == row[0]
                )
                for adm in query.all():
                    issuelist.append(Issue(
                        obj=adm,
                        detail=f'Multiple ADMs with metadata "{name}" of "{row[0]}"'
                    ))
            count += 1

        return count


@register
def same_file_name(issuelist, obj, _db_sess):
    ''' Ensure an ADM name matches its source file name. '''
    if isinstance(obj, models.AdmFile):
        if obj.abs_file_path is None:
            return 0
        int_name = obj.norm_name
        ext_name = os.path.splitext(os.path.basename(obj.abs_file_path))[0]
        if int_name != ext_name:
            issuelist.append(Issue(
                obj=obj,
                detail=f'ADM name "{int_name}" stored in differently named file {obj.abs_file_path}'
            ))
        return 1

    return 0


@register
class unique_object_names:  # pylint: disable=invalid-name
    ''' Ensure all objects within an ADM section have unique names. '''

    def __init__(self):
        self._list_attrs = []
        mapper = inspect(models.AdmFile)
        for column in mapper.attrs:
            if isinstance(column, orm.relationships.RelationshipProperty):
                # Only care about ADM-member objects
                if issubclass(column.entity.class_, models.AdmObjMixin):
                    self._list_attrs.append(column.key)
        LOGGER.debug('UniqueNames checking sets in: %s',
                     ', '.join(self._list_attrs))

    def __call__(self, issuelist, obj, _db_sess):
        count = 0
        if isinstance(obj, models.AdmFile):
            for list_name in self._list_attrs:
                seen_names = set()
                dupe_names = set()
                obj_list = getattr(obj, list_name)
                LOGGER.debug('UniqueNames checking list %s', obj_list)
                for top_obj in obj_list:
                    if top_obj.name in seen_names and top_obj.name not in dupe_names:
                        issuelist.append(Issue(
                            obj=top_obj,
                            detail=(
                                f'Within the set of {list_name} objects '
                                f'the name "{top_obj.name}" is duplicated'
                            ),
                        ))
                        dupe_names.add(top_obj.name)
                    seen_names.add(top_obj.name)
                count += 1
        return count


@register
class valid_type_name:  # pylint: disable=invalid-name
    ''' Ensure that all type names are well-fromed, but not necessarily valid in the context. '''

    def __call__(self, issuelist, obj, db_sess):
        ''' Entrypoint for this functor. '''
        count = 0
        if isinstance(obj, models.AdmFile):
            count += self._iter_call(issuelist, obj.const, db_sess)
            count += self._iter_call(issuelist, obj.edd, db_sess)
            count += self._iter_call(issuelist, obj.oper, db_sess)
            count += self._iter_call(issuelist, obj.var, db_sess)
        elif isinstance(obj, models.Const):
            count += self._check_type(issuelist, obj, obj.semtype)
        elif isinstance(obj, models.Edd):
            count += self._check_type(issuelist, obj, obj.semtype)
        elif isinstance(obj, models.Oper):
            count += self._check_type(issuelist, obj, obj.result_type)
            for parm in obj.in_type:
                count += self._check_type(issuelist, obj, parm.semtype)
        elif isinstance(obj, models.Var):
            count += self._check_type(issuelist, obj, obj.semtype)
            if obj.initializer:
                count += self._check_type(issuelist, obj, obj.initializer.type)
        return count

    def _iter_call(self, issuelist, container, *args, **kwargs):
        count = 0
        for obj in container:
            count += self(issuelist, obj, *args, **kwargs)
        return count

    def _check_type(self, issuelist, top_obj, type_name):
        ''' Verify a single named type. '''
        try:
            ari.StructType[type_name]
        except KeyError:
            issuelist.append(Issue(
                obj=top_obj,
                detail=(
                    f'Within the object named "{top_obj.name}" '
                    f'the type name "{type_name}" is not known'
                ),
            ))
        return 1


@register
class valid_reference_ari:  # pylint: disable=invalid-name
    ''' Ensure that all ARIs embedded within ADMs point to real objects. '''

    def __call__(self, issuelist, obj, db_sess, top_obj=None):
        ''' Entrypoint for this functor. '''
        count = 0
        if isinstance(obj, models.AdmFile):
            count += self._iter_call(issuelist, obj.var, db_sess)
        elif isinstance(obj, models.Var):
            if obj.initializer is not None:
                items = obj.initializer.postfix.items
                count += self._iter_call(issuelist, items, db_sess, top_obj=obj)
        elif isinstance(obj, models.ARI):
            ident = util.get_ident(obj)
            ident.strip_name()
            if not util.find_ident(db_sess, ident):
                issuelist.append(Issue(
                    obj=top_obj,
                    detail=(
                        f'Within the object named "{top_obj.name}" '
                        f'the reference ARI for {ident} is not resolvable'
                    ),
                ))
            count += 1
        return count

    def _iter_call(self, issuelist, container, *args, **kwargs):
        count = 0
        for obj in container:
            count += self(issuelist, obj, *args, **kwargs)
        return count
