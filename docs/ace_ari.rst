
The ARI Transcoder Tool
=======================

.. argparse::
    :module: ace.tools.ace_ari
    :func: get_parser
    :prog: ace_ari

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
