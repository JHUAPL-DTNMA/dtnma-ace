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
''' Algorithms that rely on the ACE data models.
'''
import logging
import string


LOGGER = logging.getLogger(__name__)


def is_printable(name: bytes) -> bool:
    return (
        name and name[:1].isalpha() 
        and all([chr(char) in string.printable for char in name])
    )


def normalize_ident(text: str) -> str:
    ''' Normalize an identity component (namespace or name) to make
    lookup in the database consistent and output in tools like CAmp
    consistent.

    :param text: The text to normalize.
    :return: Normalized text.
    '''
    
    return text.casefold().replace("/", "_")


def get_ident(obj: 'ace.models.ARI') -> 'ace.ari.Ident':
    ''' Extract an Ident object from an ADM's ARI.
    
    :param obj: The ORM object from an ADM.
    :return: The object identity.
    '''
    from ace import ari

    type_name, remain = obj.nm.split('.', maxsplit=1)
    ident = ari.Identity(
        namespace=normalize_ident(obj.ns),
        type_enum=ari.StructType[type_name.upper()],
        name=normalize_ident(remain),
    )
    return ident


def find_ident(db_sess: 'sqlalchemy.orm.Session', ident: 'ace.ari.Ident'):
    ''' Search for a specific referenced object.

    :param ident: The object identity to search for.
    :return: The found object or None.
    '''
    from ace import ari, models, nickname

    adm_ns = normalize_ident(ident.namespace)
    obj_name = normalize_ident(ident.name)
    
    try:
        cls = nickname.ORM_TYPE[ident.type_enum]
    except KeyError:
        return None
    
    LOGGER.debug('Searching for NS %s type %s name %s', ident.namespace, cls.name, obj_name)
    query = db_sess.query(cls).join(models.AdmFile).filter(
        models.AdmFile.norm_namespace == adm_ns,
        cls.norm_name == obj_name
    )
    return query.one_or_none()
