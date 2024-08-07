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
''' Manage a set of ADMs read in from some filesystem paths and kept in
a cache database.
'''
import logging
import os
from typing import BinaryIO, Set
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import xdg
from ace import models, adm_json
import json

LOGGER = logging.getLogger(__name__)


class AdmSet:
    ''' An isolated set of managed ADM data.
    Each object of this class keeps a DB session open, so is not thread safe.
    But multiple instances of the same class can be created with the same
    underlying shared database.

    :param cache_dir: A specific directory to keep the cache database in.
        If None, a user default cache path is used.
        If False, the cache is kept in-memory.
    '''

    def __init__(self, cache_dir: str = None):
        if cache_dir is False:
            self.cache_path = None
        else:
            if cache_dir is None:
                cache_dir = os.path.join(xdg.xdg_cache_home(), 'ace')
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
            self.cache_path = os.path.join(cache_dir, 'adms.sqlite')

        self._db_open()

        cur_vers = models.CURRENT_SCHEMA_VERSION
        row = self._db_sess.query(models.SchemaVersion.version_num).one_or_none()
        if row:
            db_vers = row[0]
        else:
            self._db_sess.add(models.SchemaVersion(version_num=cur_vers))
            self._db_sess.commit()
            db_vers = cur_vers

        if db_vers != cur_vers:
            LOGGER.info(
                'Recreating cache DB version %s because of old version %s',
                cur_vers, db_vers
            )
            self._db_close()
            os.unlink(self.cache_path)
            self._db_open()
        
        LOGGER.debug('Cache version contains %d ADMs', len(self))

        # track dependencies    
        self.pending_adms = {} 
        
    def _db_open(self):
        if self.cache_path:
            db_uri = f'sqlite:///{self.cache_path}'
        else:
            db_uri = 'sqlite:///:memory:'

        LOGGER.debug('Opening cache at %s', db_uri)
        self._db_eng = create_engine(db_uri)
        models.Base.metadata.create_all(self._db_eng)
        self._sessmake = sessionmaker(self._db_eng)

        self._db_sess = self._sessmake()

    def _db_close(self):
        if self._db_sess:
            self._db_sess.rollback()
            self._db_sess = None

        self._sessmake = None
        self._db_eng = None

    def db_session(self) -> Session:
        ''' Get the database session.

        :return: The session object, which should not be used in a ``with`` context.
        '''
        return self._db_sess

    def __len__(self):
        ''' Get the total number of known ADMs.
        '''
        query = self._db_sess.query(models.AdmFile.id)
        return query.count()

    def __iter__(self):
        ''' Retreive the set of all known ADMs.
        :return: List of ADMs.
        :rtype: list of :class:`models.AdmFile`
        '''
        query = self._db_sess.query(models.AdmFile)
        return iter(query.all())

    def names(self) -> Set[str]:
        ''' Get all loaded ADM normalized names.

        :return: A set of names.
        '''
        query = self._db_sess.query(models.AdmFile.norm_name).filter(
            models.AdmFile.norm_name.is_not(None)
        )
        return frozenset(row[0] for row in query.all())

    def __contains__(self, name: str) -> bool:
        ''' Determine if a specific ADM normalized name is known.
        :return: True if the name s present.
        '''
        query = self._db_sess.query(models.AdmFile.norm_name).filter(
            models.AdmFile.norm_name == name
        )
        return query.count()

    def __getitem__(self, name) -> models.AdmFile:
        ''' Retreive a specific ADM by its normalized name.

        :param str name: The name to filter on exactly.
        :return: The ADM
        '''
        return self.get_by_norm_name(name)

    def contains_namespace(self, namespace: str) -> bool:
        ''' Determine if a specific ADM normalized name is known.
        :return: True if the name s present.
        '''
        query = self._db_sess.query(models.AdmFile.norm_namespace).filter(
            models.AdmFile.norm_namespace == namespace
        )
        return query.count()

    def get_by_norm_name(self, name: str) -> models.AdmFile:
        ''' Retreive a specific ADM by its normalized name.

        :param name: The value to filter on exactly.
        :return: The ADM
        :raise KeyError: If the name is not present.
        '''
        name = name.casefold()

        query = self._db_sess.query(models.AdmFile).filter(
            models.AdmFile.norm_name == name
        )
        adm = query.one_or_none()
        if not adm:
            raise KeyError(f'No ADM found with name {name}')
        return adm

    def get_by_enum(self, enum: int) -> models.AdmFile:
        ''' Retreive a specific ADM by its integer enum.

        :param enum: The value to filter on exactly.
        :return: The ADM
        :raise KeyError: If the enum is not present.
        '''
        enum = int(enum)

        query = self._db_sess.query(models.AdmFile).filter(
            models.AdmFile.enum == enum
        )
        adm = query.one_or_none()
        if not adm:
            raise KeyError(f'No ADM found with enum {enum}')
        return adm

    def load_default_dirs(self) -> int:
        ''' Scan all default ADM store directories for new ADMs.
        This is based on the :envvar:`XDG_DATA_HOME` and :envvar:`XDG_DATA_DIRS`
        environment with the path segments ``/ace/adms`` appended.

        :return: The total number of ADMs read.
        '''
        dir_list = reversed([xdg.xdg_data_home()] + xdg.xdg_data_dirs())
        adm_cnt = 0
        for root_dir in dir_list:
            adm_dir = os.path.join(root_dir, 'ace', 'adms')
            adm_cnt += self.load_from_dir(adm_dir)
        return adm_cnt

    @staticmethod
    def _is_usable(item) -> bool:
        return (
            item.is_file()
            and item.name != 'index.json'  # FIXME: specific magic name
            and item.name.endswith('.json')
        )

    def load_from_dir(self, dir_path: str) -> int:
        ''' Scan a directory for JSON files and attempt to read them as
        ADM definitions.

        :param dir: The directory path to scan.
        :return: The number of ADMs read from that directory.
        '''
        LOGGER.debug('Scanning directory %s', dir_path)
        dir_path = os.path.realpath(dir_path)
        if not os.path.isdir(dir_path):
            return 0

        adm_cnt = 0
        try:
            dec = adm_json.Decoder()
            with os.scandir(dir_path) as items:
                items = [item for item in items if AdmSet._is_usable(item)]
                LOGGER.debug('Attempting to read %d items', len(items))
                for item in items:
                    self._read_file(dec, item.path, True)
                    adm_cnt += 1

            self._db_sess.commit()
        except Exception:
            self._db_sess.rollback()
            raise

        return adm_cnt

    def load_from_file(self, file_path: str, del_dupe: bool = True) -> models.AdmFile:
        ''' Load an ADM definition from a specific file.
        The ADM may be cached if an earlier load occurred on the same path.

        :param file_path: The file path to read from.
            This path is normalized for cache use.
        :param del_dupe: Remove any pre-existing ADMs with the same `norm_name`.
        :return: The associated :class:`AdmFile` object if successful.
        :raise Exception: if the load fails or if the file does
            not have a "name" metadata object.
        '''
        file_path = os.path.realpath(file_path)
        try:
            dec = adm_json.Decoder()
            self._db_sess.expire_on_commit = False
            adm_new = self._read_file(dec, file_path, del_dupe)
            self._db_sess.commit()
            return adm_new
        except Exception:
            self._db_sess.rollback()
            raise

    def load_from_data(self, buf: BinaryIO, del_dupe: bool = True) -> models.AdmFile:
        ''' Load an ADM definition from file content.

        :param buf: The file-like object to read from.
        :param del_dupe: Remove any pre-existing ADMs with the same `norm_name`.
        :return: The associated :class:`AdmFile` object if successful.
        :raise Exception: if the load fails or if the file does
            not have a "name" metadata object.
        '''
        try:
            dec = adm_json.Decoder()
            self._db_sess.expire_on_commit = False
            adm_new = dec.decode(buf)
            self._post_load(adm_new, del_dupe)
            self._db_sess.commit()
            return adm_new
        except Exception:
            self._db_sess.rollback()
            raise

    def _read_file(self, dec: adm_json.Decoder, file_path: str,
                   del_dupe: bool) -> models.AdmFile:
        ''' Read an ADM from file into the DB.
        if has uses skip till later? 
        :param dec: The ADM decoder object.
        :param file_path: The file to open and read from.
        :return: The associated :cls:`AdmFile` object if successful.
        '''
        adm_existing = self._db_sess.query(models.AdmFile).filter(
            models.AdmFile.abs_file_path == file_path
        ).one_or_none()
        if adm_existing and adm_existing.last_modified >= dec.get_file_time(file_path):
            LOGGER.debug('Skipping file %s already loaded from time %s',
                         file_path, adm_existing.last_modified)
            return adm_existing

        try:
            LOGGER.debug('Loading ADM from %s', file_path)
            with open(file_path, 'rb') as adm_file:
                adm_new = dec.decode(adm_file)
        except Exception as err:
            LOGGER.error(
                'Failed to open or read the file %s: %s',
                file_path, err
            )
            raise

        self._post_load(adm_new, del_dupe)
        return adm_new

    def _post_load(self, adm_new: models.AdmFile, del_dupe: bool):
        ''' Check a loaded ADM file.

        :param adm_new: The loaded ADM.
        :param del_dupe: Remove any pre-existing ADMs with the same `norm_name`.
        '''
        if not adm_new.norm_name:
            raise RuntimeError('ADM has no "name" mdat object')
        LOGGER.debug('Loaded AdmFile name "%s"', adm_new.norm_name)
        
        # if dependant adm not added yet 
        uses = [obj.norm_namespace for obj in adm_new.uses]
        pending = False
        for adm in uses:
            if not self.contains_namespace(adm):
                pending = True
                break

        if pending:
            self.pending_adms[adm_new] = uses
        else:    
            if del_dupe:
                query = self._db_sess.query(models.AdmFile).filter(
                    models.AdmFile.norm_name == adm_new.norm_name
                )
                LOGGER.debug('Removing %d old AdmFile objects', query.count())
                # delete the ORM object so that it cascades
                for adm_old in query.all():
                    self._db_sess.delete(adm_old)

            self._db_sess.add(adm_new)
            # check all pending_adms
            for adm,uses in self.pending_adms.items():
                if adm_new.adm_ns in uses:
                    uses.remove(adm_new.adm_ns)
                    if uses:
                        self.pending_adms[adm] = uses
                    else:
                        self._db_sess.add(adm)
                        


    def get_child(self, adm: models.AdmFile, cls: type, norm_name: str = None, enum: int = None):
        ''' Get one of the :class:`AdmObjMixin` -derived child objects.
        '''
        query = self._db_sess.query(cls).filter(cls.admfile == adm)
        if norm_name is not None:
            query = query.filter(cls.norm_name == norm_name.casefold())
        if enum is not None:
            query = query.filter(cls.enum == enum)
        return query.one_or_none()
