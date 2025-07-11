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
''' Manage a set of ADMs read in from some filesystem paths and kept in
a cache database.
'''
import logging
import os
import traceback
from typing import BinaryIO, List, Set, Union
from pyang.repository import Repository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import xdg_base_dirs
from ace import models, adm_yang

LOGGER = logging.getLogger(__name__)


class DbRepository(Repository):

    def __init__(self, db_sess, file_entries:List[os.DirEntry]=None):
        self._db_sess = db_sess
        self._file_entries = file_entries or []

    def get_modules_and_revisions(self, _ctx):
        found = self._db_sess.query(models.AdmModule)

        result = []
        for adm_mod in found.all():
            rev = adm_mod.revisions[0].name if adm_mod.revisions else None
            result.append((adm_mod.module_name, rev, ('yang', adm_mod.source_id)))

        for file_entry in self._file_entries:
            name, ext = os.path.splitext(file_entry.name)
            if ext != '.yang':
                continue

            if '@' in name:
                name, rev = name.split('@', 2)
            else:
                rev = None
            result.append((name, rev, ('yang', file_entry.path)))

        LOGGER.debug('available modules %s', result)
        return result

    def get_module_from_handle(self, handle):
        if isinstance(handle[1], int):
            found = (
                self._db_sess.query(
                    models.AdmSource.abs_file_path,
                    models.AdmSource.file_text
                )
                    .filter(models.AdmSource.id == handle[1])
                    .one_or_none()
            )
            if found is None:
                raise Repository.ReadError(
                    f'No ADM found with DB ID {handle[1]}'
                )
            file_text = found.file_text
            return (found.abs_file_path, 'yang', file_text)
        elif isinstance(handle[1], str):
            with open(handle[1], 'r') as infile:
                file_text = infile.read()
            return (handle, 'yang', file_text)


class AdmSet:
    ''' An isolated set of managed ADM data.
    Each object of this class keeps a DB session open, so is not thread safe.
    But multiple instances of the same class can be created with the same
    underlying shared database.

    :param cache_dir: A specific directory to keep the cache database in.
        If None, a user default cache path is used.
        If False, the cache is kept in-memory.
    '''

    def __init__(self, cache_dir:str=None):
        if cache_dir is False:
            self.cache_path = None
        else:
            if cache_dir is None:
                cache_dir = os.path.join(xdg_base_dirs.xdg_cache_home(), 'ace')
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
        query = self._db_sess.query(models.AdmModule.id)
        return query.count()

    def __iter__(self):
        ''' Retreive the set of all known ADMs.
        :return: List of ADMs.
        :rtype: list of :class:`models.AdmModule`
        '''
        query = self._db_sess.query(models.AdmModule)
        return iter(query.all())

    def names(self) -> Set[str]:
        ''' Get all loaded ADM normalized names.

        :return: A set of names.
        '''
        query = self._db_sess.query(models.AdmModule.norm_name).filter(
            models.AdmModule.norm_name.is_not(None)
        )
        return frozenset(row[0] for row in query.all())

    def __contains__(self, name:str) -> bool:
        ''' Determine if a specific ADM normalized name is known.
        :return: True if the name s present.
        '''
        query = self._db_sess.query(models.AdmModule.norm_name).filter(
            models.AdmModule.norm_name == name
        )
        return query.count()

    def __getitem__(self, name) -> models.AdmModule:
        ''' Retreive a specific ADM by its normalized name.

        :param str name: The name to filter on exactly.
        :return: The ADM
        '''
        return self.get_by_norm_name(name)

    def get_by_norm_name(self, name:str) -> models.AdmModule:
        ''' Retreive a specific ADM by its normalized name.

        :param name: The value to filter on exactly.
        :return: The ADM
        :raise KeyError: If the name is not present.
        '''
        name = name.casefold()

        query = self._db_sess.query(models.AdmModule).filter(
            models.AdmModule.norm_name == name
        )
        adm = query.one_or_none()
        if not adm:
            raise KeyError(f'No ADM found with name {name}')
        return adm

    def get_by_enum(self, enum:int) -> models.AdmModule:
        ''' Retreive a specific ADM by its integer enum.

        :param enum: The value to filter on exactly.
        :return: The ADM
        :raise KeyError: If the enum is not present.
        '''
        enum = int(enum)

        query = self._db_sess.query(models.AdmModule).filter(
            models.AdmModule.enum == enum
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
        prefix_list = (
            [xdg_base_dirs.xdg_data_home()] +
            xdg_base_dirs.xdg_data_dirs()
        )

        adm_dirs = [
            os.path.join(prefix, 'ace', 'adms')
            for prefix in prefix_list
        ]
        if 'ADM_PATH' in os.environ:
            adm_dirs.insert(0, os.environ['ADM_PATH'])

        return self.load_from_dirs(adm_dirs)

    @staticmethod
    def _is_usable(item:os.DirEntry) -> bool:
        return (
            item.is_file() and item.name.endswith('.yang')
        )

    def load_from_dirs(self, dir_paths:Union[str, List[str]]) -> int:
        ''' Scan directories for YANG files and attempt to read them as
        ADM definitions.

        :param dir_paths: One or more directory paths to scan.
        :return: The number of ADMs read from that directory.
        '''
        LOGGER.debug('Loading from directories %s', dir_paths)
        if isinstance(dir_paths, str):
            dir_paths = [dir]

        file_entries = []
        for dir_path in reversed(dir_paths):
            if not os.path.isdir(dir_path):
                continue
            with os.scandir(dir_path) as items:
                file_entries += [item for item in items if AdmSet._is_usable(item)]

        adm_cnt = 0
        try:
            dec = adm_yang.Decoder(DbRepository(self._db_sess, file_entries))
            LOGGER.debug('Attempting to read %d items', len(file_entries))
            for item in file_entries:
                self._read_file(dec, item.path, True)
                adm_cnt += 1

            self._db_sess.commit()
        except Exception:
            self._db_sess.rollback()
            raise

        return adm_cnt

    def load_from_file(self, file_path:str, del_dupe:bool=True) -> models.AdmModule:
        ''' Load an ADM definition from a specific file.
        The ADM may be cached if an earlier load occurred on the same path.

        :param file_path: The file path to read from.
            This path is normalized for cache use.
        :param del_dupe: Remove any pre-existing ADMs with the same `norm_name`.
        :return: The associated :class:`AdmModule` object if successful.
        :raise Exception: if the load fails or if the file does
            not have a "name" metadata object.
        '''
        file_path = os.path.realpath(file_path)
        LOGGER.debug('Loading from file %s', file_path)
        try:
            dec = adm_yang.Decoder(DbRepository(self._db_sess))
            self._db_sess.expire_on_commit = False
            adm_new = self._read_file(dec, file_path, del_dupe)
            self._db_sess.commit()
            return adm_new
        except Exception:
            self._db_sess.rollback()
            raise

    def load_from_data(self, buf:BinaryIO, del_dupe:bool=True) -> models.AdmModule:
        ''' Load an ADM definition from file content.

        :param buf: The file-like object to read from.
        :param del_dupe: Remove any pre-existing ADMs with the same `norm_name`.
        :return: The associated :class:`AdmModule` object if successful.
        :raise Exception: if the load fails or if the file does
            not have a "name" metadata object.
        '''
        try:
            dec = adm_yang.Decoder(DbRepository(self._db_sess))
            self._db_sess.expire_on_commit = False
            adm_new = dec.decode(buf)
            self._post_load(adm_new, del_dupe)
            self._db_sess.commit()
            return adm_new
        except Exception:
            self._db_sess.rollback()
            raise

    def _read_file(self, dec:adm_yang.Decoder, file_path:str,
                   del_dupe:bool) -> models.AdmModule:
        ''' Read an ADM from file into the DB.
        if has uses skip till later?
        :param dec: The ADM decoder object.
        :param file_path: The file to open and read from.
        :return: The associated :cls:`AdmModule` object if successful.
        '''
        # skip loading the file_text field
        src_existing = (
            self._db_sess.query(
                models.AdmSource.id,
                models.AdmSource.last_modified,
            )
                .filter(models.AdmSource.abs_file_path == file_path)
                .one_or_none()
        )
        if (src_existing is not None
            and src_existing.last_modified >= dec.get_file_time(file_path)):
            LOGGER.debug('Skipping file %s already loaded from time %s',
                         file_path, src_existing.last_modified)
            mod = (
                self._db_sess.query(models.AdmModule)
                    .filter(models.AdmModule.source_id == src_existing.id)
                    .one()
            )
            return mod

        LOGGER.debug('Loading ADM from %s', file_path)
        try:
            with open(file_path, 'r') as adm_file:
                adm_new = dec.decode(adm_file)
        except Exception as err:
            LOGGER.error(
                'Failed to open or read the file %s: %s',
                file_path, err
            )
            LOGGER.debug('%s', traceback.format_exc())
            raise

        self._post_load(adm_new, del_dupe)
        return adm_new

    def _post_load(self, adm_new:models.AdmModule, del_dupe:bool):
        ''' Check a loaded ADM file.

        :param adm_new: The loaded ADM.
        :param del_dupe: Remove any pre-existing ADMs with the same `norm_name`.
        '''
        if not adm_new.norm_name:
            raise RuntimeError('ADM has no "name" mdat object')
        LOGGER.debug('Loaded AdmModule name "%s"', adm_new.norm_name)

        # if dependant adm not added yet
        import_names = [obj.name for obj in adm_new.imports]
        pending = False
        for module_name in import_names:
            if not module_name in self:
                pending = True
                break

        if pending:
            self.pending_adms[adm_new] = import_names

        if del_dupe:
            query = self._db_sess.query(models.AdmModule).filter(
                models.AdmModule.norm_name == adm_new.norm_name
            )
            LOGGER.debug('Removing %d old AdmModule objects', query.count())
            # delete the ORM object so that it cascades
            for adm_old in query.all():
                self._db_sess.delete(adm_old)

        self._db_sess.add(adm_new)
        # check all pending_adms
        for adm, import_names in self.pending_adms.items():
            if adm_new.norm_name in import_names:
                import_names.remove(adm_new.norm_name)
                if import_names:
                    self.pending_adms[adm] = import_names
                else:
                    self._db_sess.add(adm)

    def get_child(self, adm:models.AdmModule, cls:type, norm_name:str=None, enum:int=None):
        ''' Get one of the :class:`AdmObjMixin` -derived child objects.
        '''
        query = self._db_sess.query(cls).filter(cls.module == adm)
        if norm_name is not None:
            query = query.filter(cls.norm_name == norm_name.casefold())
        if enum is not None:
            query = query.filter(cls.enum == enum)
        return query.one_or_none()
