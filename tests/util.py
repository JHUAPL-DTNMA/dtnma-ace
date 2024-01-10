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
''' Shared test fixture utilities.
'''
import os
import tempfile


class TmpDir:
    ''' A temporary test directory with associated XDG environment.

    :param kwargs: Arguments to pass down to :class:`tempfile.TemporaryDirectory`.
    '''

    def __init__(self, **kwargs):
        self._dir = tempfile.TemporaryDirectory(**kwargs)  # pylint: disable=consider-using-with
        os.environ['XDG_CACHE_HOME'] = os.path.join(self._dir.name, 'home', 'cache')
        os.environ['XDG_DATA_HOME'] = os.path.join(self._dir.name, 'home', 'data')
        os.environ['XDG_DATA_DIRS'] = os.path.join(self._dir.name, 'usr', 'data')

    def __del__(self):
        self._dir.cleanup()


from dataclasses import dataclass
from ace import typing


@dataclass
class TypeSummary:

    type:type
    detail:object = None

    @staticmethod
    def from_type(obj:typing.BaseType):
        summary = TypeSummary(type=type(obj))
        if isinstance(obj, typing.BuiltInType):
            summary.detail = obj.type_id
        elif isinstance(obj, typing.TypeUse):
            summary.detail = obj.type_text

        return summary
