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

A ``Misc/NEWS.d`` file `is needed
<https://devguide.python.org/getting-started/pull-request-lifecycle/#news-entry>`_
for almost all non-trivial changes to CPython.

For an entry in the ``Security`` section, blurb-it also offers an optional
CVE field. Give the identifier in the ``CVE-YYYY-NNNN`` form and blurb-it
records it as ``.. cve:`` metadata at the top of the news file.

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

blurb-it is deployed to `cabotage <https://github.com/cabotage/cabotage-app>`_,
the container platform managed by the PSF. cabotage builds the image from the
``Dockerfile`` and runs the ``web`` process from the ``Procfile``. The ``web``
process listens on the unix socket ``/var/run/cabotage/cabotage.sock`` when
that directory exists, and on ``PORT`` otherwise. ``GET /health`` is the
health check path.

Configuration variables, set in the cabotage UI:

- ``GH_CLIENT_ID``, ``GH_CLIENT_SECRET``: the GitHub OAuth App credentials.
- ``GH_APP_ID``, ``GH_PRIVATE_KEY``: the GitHub App ID and private key.
- ``APP_URL``: the public hostname, without scheme. Must match the OAuth App
  callback URL.
- ``SESSION_KEY``: the Fernet key that encrypts the session cookie. Generate
  it once with ``python -c "from cryptography.fernet import Fernet;
  print(Fernet.generate_key().decode())"`` and keep it the same across
  deploys; changing it signs everyone out. Without it the app generates a
  random key at startup, with the same effect on every restart.
- ``SENTRY_DSN``: where errors are reported.


Requirements and dependencies
=============================

- Python 3.14+
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
