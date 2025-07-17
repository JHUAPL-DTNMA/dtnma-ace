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
''' An interface and runner of model consistency constraints.
'''
from dataclasses import dataclass
import logging
from ace import models

LOGGER = logging.getLogger(__name__)
CONSTRAINTS = {}
''' Accumulated list of all constraints to check '''


@dataclass
class Issue:
    ''' An issue resulting from a failed constraint.
    '''
    check_name: str = None
    ''' The name of the constraint noting the issue, which will be set automatically '''
    module_name: str = None
    ''' The name of the ADM module containing the issue, which will be set automatically '''
    obj: object = None
    ''' The object containing the issue '''
    detail: str = None
    ''' Any specific detail about the issue '''


def register(obj):
    ''' A decorator to mark a function as being ADM constraint-checking.

    All constraint functions must take arguments of:
      - issuelist: a list of aggregated :class:`Issue` objects
      - obj: The object being checked, starting at the :class:`AdmModule`
      - db_sess: The database session being run under.
    '''
    if isinstance(obj, type):
        name = f'{obj.__module__}.{obj.__name__}'
        obj = obj()
    elif callable(obj):
        name = f'{obj.__module__}.{obj.__name__}'
    else:
        raise TypeError(f'Object given to register() is not usable: {obj}')
    CONSTRAINTS[name] = obj


class Checker:
    ''' A class which visits objects of the ORM and performs checks
    to create Issue objects.

    :param db_sess: A database session to operate within.
    '''

    def __init__(self, db_sess):
        self._db_sess = db_sess

    def check(self, src: models.AdmModule=None):
        ''' Check a specific ADM for issues.

        :param src: The ADM to check or None.
        :return: A list of found :class:`Issue` objects.
        '''
        if src is not None:
            adm_list = (src,)
        else:
            adm_list = self._db_sess.query(models.AdmModule).all()

        check_count = 0
        allissues = []

        # Run global constraints once
        for cst_name, cst in CONSTRAINTS.items():
            if getattr(cst, 'is_global', False):
                issuelist = []
                self._add_result(issuelist, check_count, cst_name, cst, adm=None)
                allissues += issuelist

        # Run non-global constraints per each adm
        for adm in adm_list:
            module_name = adm.norm_name
            LOGGER.debug('Checking ADM: %s', module_name)
            for cst_name, cst in CONSTRAINTS.items():
                if getattr(cst, 'is_global', False):
                    continue

                issuelist = []
                self._add_result(issuelist, check_count, cst_name, cst, adm)
                allissues += issuelist

        LOGGER.info('Checked %d rules and produced %d issues',
                    check_count, len(allissues))
        return allissues

    def _add_result(self, issuelist, check_count, cst_name, cst, adm):
        LOGGER.debug('Running constraint check: %s', cst_name)
        count = cst(issuelist, adm, self._db_sess) or 0
        check_count += count

        for issue in issuelist:
            if issue.module_name is None:
                if adm is not None:
                    issue.module_name = adm.norm_name
                elif isinstance(issue.obj, models.AdmModule):
                    issue.module_name = issue.obj.norm_name
            if issue.check_name is None:
                issue.check_name = cst_name
        LOGGER.debug(
            'Checked %d rules and produced %d issues:\n%s',
            count, len(issuelist),
            '\n'.join(repr(iss) for iss in issuelist)
        )
