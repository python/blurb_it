blurb_it
--------

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black

.. image:: https://github.com/python/blurb_it/actions/workflows/ci.yml/badge.svg?event=push
    :target: https://github.com/python/blurb_it/actions

.. image:: https://codecov.io/gh/python/blurb_it/branch/main/graph/badge.svg
    :target: https://codecov.io/gh/python/blurb_it

``blurb add`` over the internet.

About
=====

📜🤖 blurb-it allows you to add a misc/news file to your own
`CPython <https://github.com/python/cpython>`_ pull request.

A Misc/News file `is needed
<https://devguide.python.org/core-developers/committing/index.html#updating-news-and-what-s-new-in-python>`_
for almost all non-trivial changes to CPython.

To use blurb-it, you must be logged in to GitHub.

Install blurb-it GitHub App to your account, and then grant the ``write`` access to your
fork of the CPython repository.

Since blurb-it will have write access to the granted repo, you should only install
it on your own CPython repository.

`Install blurb-it <https://github.com/apps/blurb-it/installations/new>`_ .

Uninstall blurb-it
==================

1. Go to https://github.com/settings/installations.

2. Click blurb-it's "Configure" button.

3. Scroll down and click the "Uninstall" button.

Deploy
======

|Deploy|

.. |Deploy| image:: https://www.herokucdn.com/deploy/button.svg
   :target: https://heroku.com/deploy?template=https://github.com/python/blurb_it


Requirements and dependencies
=============================

- Python 3.7+
- aiohttp
- aiohttp-jinja2
- gidgethub >= 5.0.0
- pyjwt >= 2.0.0
- cryptography


Running tests
=============

1. Create a Python virtual environment with ``$ python3 -m venv venv``
2. Activate the virtual environment with ``$ . venv/bin/activate``
3. Install dev requirements with ``(venv)$ pip install -r dev-requirements.txt``
4. Run all tests with ``(venv)$ pytest tests``
