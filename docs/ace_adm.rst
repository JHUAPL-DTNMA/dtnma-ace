ACE ADM Processing
=======================

.. argparse::
    :module: ace.tools.ace_ari
    :func: get_parser
    :prog: ace_adm

ACE Interaction with ADMs
-------------------------

The ACE library is a single Python package composed of 3 areas: ARIs, ADMs, and other
modules. It scans the directory for present ADMs and caches them into a local database 
for fast lookup. AdmSource is the source table, with the sources being the actual cached
file content. Adm_yang is the processing to take a YANG input to decoded with a 3rd party
library called ``pyang`` that produces a yang informational model and converts to ORM
(Object Relational Mapping) model. 


Arguments
---------------------

Transforms:
    ``-t`` to transform module data, e.g. ``-t adm-add-enum`` ensures all objects have a unique ``amm:enum`` value.

Output format:
    ``-f`` to control output file format, _e.g._ ``-f yang`` to output in YANG text form.

    ``--yang-canonical`` to canonicalize the order of statements in the output.

Linting:
    ``--ietf`` and ``--lint-ensure-hyphenated-names`` to check for consistency.

Environment Variables
---------------------

The following environment variables control how the tool searches for and loads ADM files.

ADM_PATH
    This is the highest priority search path.
    All files in the directory named by this variable following the pattern ``*.json`` are loaded as ADMs.

XDG_DATA_HOME, XDG_DATA_DIRS
    These directories are used in accordance with the `XDG Base Directory Specification <https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html>`_ with the suffix path ``/ace/adms``.
    All files in the search subdirectories following the pattern ``*.json`` are loaded as ADMs.

XDG_CACHE_HOME
    This directory is used in accordance with the `XDG Base Directory Specification <https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html>`_ with the suffix path ``/ace`` for storing cached data.
    The two cache names used are ``adms.sqlite`` file and ``ply`` directory.

Examples
````````

The XDG-default local search paths for ADM files would be the priority ordering of

#. ``$ADM_PATH``
#. ``$HOME/.local/share/ace/adms``
#. ``/usr/local/share/ace/adms``
#. ``/usr/share/ace/adms``

And the XDG-default cache directory for ADM lookup and ARI parsing is ``$HOME/.cache/ace``.
