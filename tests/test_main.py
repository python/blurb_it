from __future__ import annotations

import base64
import pathlib

import aiohttp_jinja2
import jinja2
import pytest
from aiohttp import web
from aiohttp_session import setup as setup_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet

from blurb_it import __main__


def create_app() -> web.Application:
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)

    app = web.Application(
        middlewares=[
            __main__.middleware.error_middleware,
            __main__.session_middleware(EncryptedCookieStorage(secret_key)),
        ]
    )

    aiohttp_jinja2.setup(
        app, loader=jinja2.FileSystemLoader(pathlib.Path.cwd() / "templates")
    )
    return app


async def test_handle_get(aiohttp_client) -> None:
    # Arrange
    app = create_app()

    # Act
    app.router.add_get("/", __main__.handle_get)
    client = await aiohttp_client(app)
    resp = await client.get("/")

    # Assert
    assert resp.status == 200
    text = await resp.text()
    assert "<title>📜🤖 Blurb It!</title>" in text
    assert "Sign in with GitHub" in text


async def test_handle_howto_get(aiohttp_client) -> None:
    # Arrange
    app = create_app()

    # Act
    app.router.add_get("/howto", __main__.handle_howto_get)
    client = await aiohttp_client(app)
    resp = await client.get("/howto")

    # Assert
    assert resp.status == 200
    text = await resp.text()
    assert "<title>📜🤖 Blurb It!</title>" in text
    assert "As part of CPython’s workflow" in text


async def test_handle_install(aiohttp_client) -> None:
    # Arrange
    app = create_app()

    # Act
    app.router.add_get("/install", __main__.handle_install)
    client = await aiohttp_client(app)
    resp = await client.get("/install")

    # Assert
    assert resp.status == 200
    text = await resp.text()
    assert "<title>📜🤖 Blurb It!</title>" in text
    assert "Please install" in text


@pytest.mark.parametrize(
    "token_str, expected",
    [
        (
            "access_token=gho_16C7e42F292c6912E7710c838347Ae178B4a&scope=repo%2Cgist&token_type=bearer",
            "gho_16C7e42F292c6912E7710c838347Ae178B4a",
        ),
        ("scope=repo%2Cgist&token_type=bearer", None),
    ],
)
def test_get_access_token(token_str: str, expected: str | None) -> None:
    assert __main__.get_access_token(token_str) == expected
