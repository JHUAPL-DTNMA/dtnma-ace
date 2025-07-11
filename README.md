<!--
Copyright (c) 2020-2025 The Johns Hopkins University Applied Physics
Laboratory LLC.

This file is part of the AMM CODEC Engine (ACE) under the
DTN Management Architecture (DTNMA) reference implementaton set from APL.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Portions of this work were performed for the Jet Propulsion Laboratory,
California Institute of Technology, sponsored by the United States Government
under the prime contract 80NM0018D0004 between the Caltech and NASA under
subcontract 1658085.
-->
# ACE Tools
This is the AMM CODEC Engine (ACE) for the DTN Management Architecture (DTNMA).
It is part of the larger Asynchronous Network Managment System (ANMS) managed for [NASA AMMOS](https://ammos.nasa.gov/).

It is a library to manage the information in DTNMA Application Data Models (ADMs) and use that information to encode and decode DTNMA Application Resource Identifiers (ARIs) in:
 * Text form based on [URI encoding](https://www.rfc-editor.org/rfc/rfc3986.html)
 * Binary form based on [CBOR encoding](https://www.rfc-editor.org/rfc/rfc9052.html)

It also includes an `ace_ari` command line interface (CLI) for translating between the two ARI forms.

## Development

It is advised to operate within a Python virtual environment, ideally Python 3.11, to help prevent dependency errors later on. You can run the following commands to create and activate your venv: 
```
python3.11 -m venv .venv
source .venv/bin/activate
```
If you wish to deactivate your venv, simply run `deactivate`.

To install development and test dependencies for this project, run from the root directory (possibly under `sudo` if installing to the system path):
```sh
pip3 install -r <(python3 -m piptools compile --extra test pyproject.toml 2>&1)
```

If this command fails, you may have to install the `pip-tools` package first and then run two separate commands like so:
```
pip3 install pip-tools
python3 -m piptools compile --extra test pyproject.toml
pip3 install -r requirements.txt
```

To install the project itself from source run:
```
pip3 install .
```

If you are a developer seeking to do unit testing, you can run the following two commands to install the dependencies for unit tests and then run said unit tests to see if any are failing:
```
pip3 install -e '.[test]'
python3 -m pytest -v --cov=ace tests
```
Likewise, if you wish to update our Sphinx documentation and then see your changes, you can run the following two commands to install and build the docs, and then open the generated html files in a web browser:
```
pip3 install .[docs]
./build_docs.sh
```

If you are still encountering installation errors, you may need to update the submodules:
```
git submodule update --init --recursive
```

An example of using the ARI transcoder, from the source tree, to convert from text to binary form is:
```
echo 'ari:/EXECSET/n=123;(//ietf/dtnma-agent/CTRL/inspect(//ietf/dtnma-agent/EDD/sw-version))' | PYTHONPATH=./src ADM_PATH=./tests/adms python3 -m ace.tools.ace_ari --inform=text --outform=cborhex
```
which will produce a hexadecimal output:
```
0x821482187B8501012205818401012301
```

An example of using the ADM parser, from the source tree, to normalize and compare ADMs (with meld tool) is:
```
ADMFILE=../adms/ietf-inet.yang; meld ${ADMFILE} <(PYTHONPATH=./src ADM_PATH=./tests/adms python3 -m ace.tools.ace_adm -f yang ${ADMFILE})
```

An example of using the ADM parser, from the soruce tree, to normalize and compare ADMs (with meld tool) is:
```
ADMFILE=../adms/ietf-inet.yang; meld ${ADMFILE} <(PYTHONPATH=./src ADM_PATH=./tests/adms python3 -m ace.tools.ace_adm -f yang ${ADMFILE})
```

## Contributing

To contribute to this project, through issue reporting or change requests, see the [CONTRIBUTING](CONTRIBUTING.md) document.
