from __future__ import annotations

import base64
import pathlib

import aiohttp_jinja2
import jinja2
import pytest
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp_session import new_session
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


async def sign_in(request: Request) -> web.Response:
    """Test route that signs the client in as a placeholder GitHub user."""
    session = await new_session(request)
    session["username"] = "octocat"
    session["token"] = "gho_token"
    return web.Response(text="signed in")


async def test_health_check(aiohttp_client) -> None:
    app = create_app()
    app.router.add_get("/health", __main__.health_check)
    client = await aiohttp_client(app)

    response = await client.get("/health")

    assert response.status == 200
    assert await response.text() == "OK"


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


async def test_handle_howto_get(aiohttp_client, monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("APP_URL", "blurb-it.example.org")
    monkeypatch.delenv("APP_PROTOCOL", raising=False)
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
    assert "https://blurb-it.example.org/" in text
    assert "herokuapp" not in text


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


async def test_handle_get_redirects_signed_in_user(aiohttp_client) -> None:
    # Arrange
    app = create_app()
    app.router.add_get("/sign-in", sign_in)
    app.router.add_get("/", __main__.handle_get, name="home")
    app.router.add_get("/add_blurb", __main__.handle_add_blurb_get, name="add_blurb")
    client = await aiohttp_client(app)
    await client.get("/sign-in")

    # Act
    resp = await client.get("/", allow_redirects=False)

    # Assert
    assert resp.status == 302
    assert resp.headers["Location"] == "/add_blurb"


async def test_handle_add_blurb_get_redirects_without_session(aiohttp_client) -> None:
    # Arrange
    app = create_app()
    app.router.add_get("/", __main__.handle_get, name="home")
    app.router.add_get("/add_blurb", __main__.handle_add_blurb_get, name="add_blurb")
    client = await aiohttp_client(app)

    # Act
    resp = await client.get("/add_blurb", allow_redirects=False)

    # Assert
    assert resp.status == 302
    assert resp.headers["Location"] == "/"


async def test_handle_add_blurb_get_renders_form(aiohttp_client, monkeypatch) -> None:
    # Arrange: a signed-in session, with the GitHub App lookups stubbed out.
    monkeypatch.setattr(__main__, "get_jwt", lambda **kwargs: "jwt")

    async def get_installation(gh, jwt, username):
        return {"id": 1}

    monkeypatch.setattr(__main__.util, "get_installation", get_installation)

    app = create_app()
    app.router.add_get("/sign-in", sign_in)
    app.router.add_get("/install", __main__.handle_install, name="install")
    app.router.add_get("/add_blurb", __main__.handle_add_blurb_get, name="add_blurb")
    client = await aiohttp_client(app)
    await client.get("/sign-in")

    # Act
    resp = await client.get("/add_blurb")

    # Assert: the template renders, and the form still posts every field the
    # handler reads, with the hooks the inline script relies on.
    assert resp.status == 200
    text = await resp.text()
    assert "<title>📜🤖 Blurb It!</title>" in text
    assert "octocat" in text
    for field in ("csrf", "issue_number", "pr_number", "section", "cve", "news_entry"):
        assert f'name="{field}"' in text
    assert f"<option>{__main__.util.CVE_SECTION}</option>" in text
    assert 'id="cve-group"' in text
    assert 'getElementById("cve-group")' in text
