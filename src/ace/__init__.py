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
''' A package for converting ADMs from JSON and checking them, and
converting ARIs between text URI and CBOR.
'''

from ace.adm_set import AdmSet
from ace.constraints import Checker
from ace.ari import ARI, LiteralARI, ReferenceARI, StructType
import ace.ari_text as ari_text
import ace.ari_cbor as ari_cbor
import ace.nickname as nickname

# make linters happy
__all__ = [
    'AdmSet',
    'ARI',
    'Checker',
    'LiteralARI',
    'ReferenceARI',
    'StructType',
    'ari_text',
    'ari_cbor',
    'nickname',
]
