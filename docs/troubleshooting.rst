Troubleshooting
===============

Testing 
-------

For running individual unit tests, these commands are useful:

.. code-block:: bash

    pytest -v -o log_cli=true tests/test_ari_text.py
    pytest -v --log-cli-level=INFO tests/test_ari_text.py -k 'test_literal_text_options'

Database errors
---------------
If you run into unusual DB complaints from ACE, try removing the cache DB 
at ~/.cache/ace/adms.sqlite. This DB is versioned between releases but dev 
changes can cause mismatches.
