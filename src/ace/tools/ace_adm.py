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
''' This tool wraps the pyang package CLI with local plugins.
'''
import subprocess
import os
import sys

SELFDIR = os.path.dirname(__file__)
''' Directory containing this file '''


def main():
    env = os.environ
    env['PYANG_PLUGINPATH'] = os.path.abspath(os.path.join(SELFDIR, '..', 'pyang'))
    env['YANG_MODPATH'] = os.environ.get('ADM_PATH', '')
    return subprocess.call(['pyang'] + sys.argv[1:], env=env)


if __name__ == '__main__':
    sys.exit(main())
