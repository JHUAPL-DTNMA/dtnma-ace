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
''' This tool converts ARIs between different encoding forms.

It uses environment variables to control where ADMs are searched for and
command options to control the ARI conversion.
For ``text`` or ``cborhex`` forms of input or output, each line is handled
as a separate ARI and converted independently until the input stream is ended.
For ``cbor`` form of input or output, the stream is treated as a CBOR sequence
and each item is handled as a separate ARI.
'''
import argparse
import io
import logging
import os
import sys
from ace import ari_text, ari_cbor, cborutil, nickname, AdmSet, Checker

LOGGER = logging.getLogger(__name__)


def get_parser() -> argparse.ArgumentParser:
    ''' Construct the argument parser. '''
    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument('--log-level', choices=('debug', 'info', 'warning', 'error'),
                        default='info',
                        help='The minimum log severity.')
    parser.add_argument('--inform', choices=('text', 'cbor', 'cborhex'),
                        default='text',
                        help='The input encoding.')
    parser.add_argument('--input', default='-',
                        help='The input file or "-" for stdin stream.')
    parser.add_argument('--outform', choices=('text', 'cbor', 'cborhex'),
                        default='cbor',
                        help='The desired output encoding.')
    parser.add_argument('--output', default='-',
                        help='The output file or "-" for stdout stream.')
    parser.add_argument('--must-nickname', action='store_true', default=False,
                        help='Require that a nickname exist when converting from text.')
    return parser


def decode(args: argparse.Namespace):
    ''' Decode the ARI from the specified form.

    :param args: The command arguments.
    :return: An iterable for the ARI items.
    '''
    # pylint: disable=consider-using-with
    if args.inform == 'text':
        infile = sys.stdin if args.input == '-' else open(args.input, 'r', encoding="utf-8")
        # Assume that each line is a new ARI, but handle cases where line breaks are present in text literals
        buffer = io.StringIO()
        last_err = None
        for line in infile:
            buffer.seek(0, io.SEEK_END)
            buffer.write(line)
            buffer.seek(0)

            try:
                ari = ari_text.Decoder().decode(buffer)
                buffer = io.StringIO()
                last_err = None
                yield ari
            except ari_text.ParseError as err:
                # leave the buffer lines and just add the next one
                last_err = err

        if last_err:
            # Propagate the error from the last failure
            raise last_err

        infile.close()

    elif args.inform == 'cbor':
        infile = sys.stdin.buffer if args.input == '-' else open(args.input, 'rb')
        while infile.peek(1):
            yield ari_cbor.Decoder().decode(infile)
        infile.close()

    elif args.inform == 'cborhex':
        infile = sys.stdin if args.input == '-' else open(args.input, 'r', encoding="utf-8")
        for line in infile:
            indata = line.strip()
            buf = io.BytesIO(cborutil.from_hexstr(indata))
            yield ari_cbor.Decoder().decode(buf)
        infile.close()
    # pylint: enable=consider-using-with


def encode(args: argparse.Namespace, ari):
    ''' Encode the ARI in the desired form.

    :param args: The command arguments.
    :param ari: The single ARI to encode.
    '''
    # pylint: disable=consider-using-with
    if args.outform == 'text':
        outfile = sys.stdout if args.output == '-' else open(args.output, 'w', encoding="utf-8")
        ari_text.Encoder().encode(ari, outfile)
        outfile.write('\n')
    elif args.outform == 'cbor':
        outfile = sys.stdout.buffer if args.output == '-' else open(args.output, 'wb')
        ari_cbor.Encoder().encode(ari, outfile)
    elif args.outform == 'cborhex':
        buf = io.BytesIO()
        ari_cbor.Encoder().encode(ari, buf)

        outfile = sys.stdout if args.output == '-' else open(args.output, 'w', encoding="utf-8")
        outfile.write(cborutil.to_hexstr(buf.getvalue()))
        outfile.write('\n')
    # pylint: enable=consider-using-with


def run(args: argparse.Namespace):
    ''' Run this tool with externally-supplied arguments.

    :param args: The command arguments namespace.
    '''
    adms = AdmSet()
    adms.load_default_dirs()
    LOGGER.info('Loaded %d ADMs', len(adms))

    eng = Checker(adms.db_session())
    issuelist = eng.check()
    for issue in issuelist:
        LOGGER.warning('ADM issue: %s', issue)

    # Text mode prefers non-nickname
    nn_mode = nickname.Mode.FROM_NN if args.outform == 'text' else nickname.Mode.TO_NN
    nn_func = nickname.Converter(nn_mode, adms.db_session(), args.must_nickname)

    # Handle ARIs iteratively
    for ari in decode(args):
        LOGGER.info('Decoded ARI as %s', ari)
        ari = nn_func(ari)
        LOGGER.info('Encoding ARI as %s', ari)
        encode(args, ari)


def main():
    ''' Script entrypoint. '''
    parser = get_parser()
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper())
    if LOGGER.isEnabledFor(logging.DEBUG):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

    run(args)


if __name__ == '__main__':
    sys.exit(main())
