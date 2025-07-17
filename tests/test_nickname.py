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
''' Verify behavior of the :mod:`ace.adm_yang` module tree.
'''
import logging
import os
import unittest
from ace import ari, nickname
from .test_adm_yang import BaseYang

LOGGER = logging.getLogger(__name__)
SELFDIR = os.path.dirname(__file__)


class TestNickname(BaseYang):

    maxDiff = None

    def setUp(self):
        BaseYang.setUp(self)

        buf = self._get_mod_buf('''
  amm:ctrl no-enum {
  }
  amm:ctrl with-enum {
    amm:enum 4;
  }
''')
        adm = self._adm_dec.decode(buf)
        self._db_sess.add(adm)
        self._db_sess.commit()

    def test_to_enum_must_valid(self):
        as_text = '//example/mod/CTRL/with-enum'
        as_enum = '//65535/1/-3/4'

        ari_text = self._from_text(as_text)
        ari_enum = self._from_text(as_enum)

        to_enum = nickname.Converter(nickname.Mode.TO_NN, self._db_sess, True)
        got_enum = to_enum(ari_text)
        self.assertEqual(ari_enum, got_enum)

    def test_to_enum_must_nomod(self):
        as_text = '//no/mod/CTRL/no-enum'

        ari_text = self._from_text(as_text)

        to_enum = nickname.Converter(nickname.Mode.TO_NN, self._db_sess, True)
        with self.assertRaises(RuntimeError):
            to_enum(ari_text)

    def test_to_enum_must_noobj(self):
        as_text = '//example/mod/CTRL/missing'

        ari_text = self._from_text(as_text)

        to_enum = nickname.Converter(nickname.Mode.TO_NN, self._db_sess, True)
        with self.assertRaises(RuntimeError):
            to_enum(ari_text)

    def test_to_enum_nomust_valid(self):
        as_text = '//example/mod/CTRL/with-enum'
        as_enum = '//65535/1/-3/4'

        ari_text = self._from_text(as_text)
        ari_enum = self._from_text(as_enum)

        to_enum = nickname.Converter(nickname.Mode.TO_NN, self._db_sess, False)
        got_enum = to_enum(ari_text)
        self.assertEqual(ari_enum, got_enum)

    def test_to_enum_nomust_noobj(self):
        as_text = '//example/mod/CTRL/missing'
        as_enum = '//65535/1/-3/missing'

        ari_text = self._from_text(as_text)
        ari_enum = self._from_text(as_enum)

        to_enum = nickname.Converter(nickname.Mode.TO_NN, self._db_sess, False)
        got_enum = to_enum(ari_text)
        self.assertEqual(ari_enum, got_enum)

    @unittest.expectedFailure
    def test_to_enum_nomust_noobjenum(self):
        as_text = '//example/mod/CTRL/no-enum'
        as_enum = '//65535/1/-3/no-enum'

        ari_text = self._from_text(as_text)
        ari_enum = self._from_text(as_enum)

        to_enum = nickname.Converter(nickname.Mode.TO_NN, self._db_sess, False)
        got_enum = to_enum(ari_text)
        self.assertEqual(ari_enum, got_enum)

    def test_from_enum_must_valid(self):
        as_text = '//example/mod/CTRL/with-enum'
        as_enum = '//65535/1/-3/4'

        ari_text = self._from_text(as_text)
        ari_enum = self._from_text(as_enum)

        from_enum = nickname.Converter(nickname.Mode.FROM_NN, self._db_sess, True)
        got_text = from_enum(ari_enum)
        self.assertEqual(ari_text, got_text)

    def test_from_enum_must_nomod(self):
        as_text = '//100/1/CTRL/4'

        ari_text = self._from_text(as_text)

        from_enum = nickname.Converter(nickname.Mode.FROM_NN, self._db_sess, True)
        with self.assertRaises(RuntimeError):
            from_enum(ari_text)

    def test_from_enum_must_noobj(self):
        as_text = '//65535/1/CTRL/100'

        ari_text = self._from_text(as_text)

        from_enum = nickname.Converter(nickname.Mode.FROM_NN, self._db_sess, True)
        with self.assertRaises(RuntimeError):
            from_enum(ari_text)

    def test_from_enum_nomust_valid(self):
        as_text = '//example/mod/CTRL/with-enum'
        as_enum = '//65535/1/-3/4'

        ari_text = self._from_text(as_text)
        ari_enum = self._from_text(as_enum)

        from_enum = nickname.Converter(nickname.Mode.FROM_NN, self._db_sess, False)
        got_text = from_enum(ari_enum)
        self.assertEqual(ari_text, got_text)

    def test_from_enum_nomust_noobj(self):
        as_text = '//example/mod/CTRL/missing'
        as_enum = '//65535/1/-3/missing'

        ari_text = self._from_text(as_text)
        ari_enum = self._from_text(as_enum)

        from_enum = nickname.Converter(nickname.Mode.FROM_NN, self._db_sess, False)
        got_text = from_enum(ari_enum)
        self.assertEqual(ari_text, got_text)
