from __future__ import annotations

import asyncio
import base64
import logging
import pathlib

import aiohttp
import aiohttp_jinja2
import gidgethub
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


async def fake_github(aiohttp_server, handler) -> str:
    """Stand up ``handler`` as GitHub's OAuth token endpoint and return its URL."""
    app = web.Application()
    app.router.add_post("/login/oauth/access_token", handler)
    server = await aiohttp_server(app)
    return str(server.make_url("/login/oauth/access_token"))


async def test_exchange_code_for_token(aiohttp_server, monkeypatch) -> None:
    # Arrange: GitHub answers the exchange with the token as JSON.
    monkeypatch.setenv("GH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GH_CLIENT_SECRET", "client-secret")
    seen = {}

    async def token_endpoint(request: Request) -> web.Response:
        seen["accept"] = request.headers["Accept"]
        seen["form"] = dict(await request.post())
        return web.json_response(
            {
                "access_token": "gho_token",
                "scope": "repo,gist",
                "token_type": "bearer",
            }
        )

    url = await fake_github(aiohttp_server, token_endpoint)

    # Act
    async with aiohttp.ClientSession() as session:
        token = await __main__.exchange_code_for_token(session, "the-code", url=url)

    # Assert
    assert token == "gho_token"
    assert seen["accept"] == "application/json"
    assert seen["form"] == {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "code": "the-code",
    }


@pytest.mark.parametrize(
    "body, message",
    [
        (
            {
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or expired.",
            },
            "The code passed is incorrect or expired.",
        ),
        (
            {"scope": "repo,gist", "token_type": "bearer"},
            "did not return an access token",
        ),
    ],
)
async def test_exchange_code_for_token_rejected(
    aiohttp_server, body: dict, message: str
) -> None:
    # Arrange: GitHub is up but refuses the code (GitHub sends these as 200).
    async def token_endpoint(request: Request) -> web.Response:
        return web.json_response(body)

    url = await fake_github(aiohttp_server, token_endpoint)

    # Act / Assert
    async with aiohttp.ClientSession() as session:
        with pytest.raises(__main__.error.SignInFailed, match=message):
            await __main__.exchange_code_for_token(session, "the-code", url=url)


@pytest.mark.parametrize(
    "body",
    [
        {
            "error": "incorrect_client_credentials",
            "error_description": "The client_id and/or client_secret are incorrect.",
        },
        {"error": "redirect_uri_mismatch"},
    ],
    ids=["bad-secret", "bad-callback-url"],
)
async def test_exchange_code_for_token_misconfigured(
    aiohttp_server, body: dict
) -> None:
    # Arrange: GitHub rejects our app's credentials. The user cannot fix this
    # by signing in again, so it must not become a SignInFailed.
    async def token_endpoint(request: Request) -> web.Response:
        return web.json_response(body)

    url = await fake_github(aiohttp_server, token_endpoint)

    # Act / Assert
    async with aiohttp.ClientSession() as session:
        with pytest.raises(__main__.error.OAuthMisconfigured, match=body["error"]):
            await __main__.exchange_code_for_token(session, "the-code", url=url)


async def oversized_csp_page(request: Request) -> web.Response:
    """GitHub's outage/interstitial HTML page.

    Its Content-Security-Policy header is bigger than aiohttp's default 8190
    byte header limit, so the client rejects the response before reading the
    body. This is the failure Sentry reported for /add_blurb.
    """
    csp = "default-src 'none'; base-uri 'self'; child-src " + " ".join(
        f"https://host{i}.githubassets.com" for i in range(300)
    )
    assert len(csp) > 8190
    return web.Response(
        text="<html>Unicorn!</html>",
        content_type="text/html",
        headers={"Content-Security-Policy": csp},
    )


async def html_page(request: Request) -> web.Response:
    return web.Response(text="<html>Unicorn!</html>", content_type="text/html")


async def rate_limited(request: Request) -> web.Response:
    return web.json_response({"message": "slow down"}, status=429)


async def server_error(request: Request) -> web.Response:
    return web.Response(
        text="<html>Unicorn!</html>", content_type="text/html", status=503
    )


async def broken_json(request: Request) -> web.Response:
    return web.Response(text="<html>", content_type="application/json")


async def test_exchange_code_for_token_reproduces_sentry_error(aiohttp_server) -> None:
    # Arrange: the interstitial page from the Sentry report.
    url = await fake_github(aiohttp_server, oversized_csp_page)

    # Act / Assert: it is the header-limit error, wrapped as an outage.
    async with aiohttp.ClientSession() as session:
        with pytest.raises(__main__.error.GitHubUnavailable, match="8190 bytes"):
            await __main__.exchange_code_for_token(session, "the-code", url=url)


@pytest.mark.parametrize(
    "handler", [html_page, rate_limited, server_error, broken_json]
)
async def test_exchange_code_for_token_github_unavailable(
    aiohttp_server, handler
) -> None:
    # Arrange: GitHub is down, rate limiting, or serving an HTML page.
    url = await fake_github(aiohttp_server, handler)

    # Act / Assert
    async with aiohttp.ClientSession() as session:
        with pytest.raises(__main__.error.GitHubUnavailable):
            await __main__.exchange_code_for_token(session, "the-code", url=url)


async def test_exchange_code_for_token_timeout(aiohttp_server) -> None:
    # Arrange: GitHub accepts the connection but never answers. aiohttp raises
    # the builtin TimeoutError here, which is not a ClientError.
    async def hangs(request: Request) -> web.Response:
        await asyncio.sleep(1)
        return web.json_response({"access_token": "too-late"})

    url = await fake_github(aiohttp_server, hangs)

    # Act / Assert
    timeout = aiohttp.ClientTimeout(total=0.1)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        with pytest.raises(__main__.error.GitHubUnavailable):
            await __main__.exchange_code_for_token(session, "the-code", url=url)


async def test_exchange_code_for_token_connection_error() -> None:
    # Arrange: nothing answers on GitHub's side at all.
    url = "http://127.0.0.1:1/token"

    # Act / Assert
    async with aiohttp.ClientSession() as session:
        with pytest.raises(__main__.error.GitHubUnavailable):
            await __main__.exchange_code_for_token(session, "the-code", url=url)


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


@pytest.mark.parametrize(
    "exc",
    [
        gidgethub.GitHubBroken(502, "Bad Gateway"),
        aiohttp.ClientConnectionError("connection reset"),
        TimeoutError(),
    ],
    ids=["5xx", "connection-error", "timeout"],
)
async def test_handle_add_blurb_get_signed_in_when_github_is_down(
    aiohttp_client, monkeypatch, exc: Exception
) -> None:
    # Arrange: a signed-in user, and GitHub fails while we check the App install.
    monkeypatch.setattr(__main__, "get_jwt", lambda **kwargs: "jwt")

    async def get_installation(gh, jwt, username):
        raise exc

    monkeypatch.setattr(__main__.util, "get_installation", get_installation)

    app = create_app()
    app.router.add_get("/sign-in", sign_in)
    app.router.add_get("/install", __main__.handle_install, name="install")
    app.router.add_get("/add_blurb", __main__.handle_add_blurb_get, name="add_blurb")
    client = await aiohttp_client(app)
    await client.get("/sign-in")

    # Act
    resp = await client.get("/add_blurb")

    # Assert: the same 503 page as the sign-in leg, with the status link.
    assert resp.status == 503
    text = await resp.text()
    assert "GitHub is not responding right now" in text
    assert '<a href="https://www.githubstatus.com"' in text


class FakeGitHubAPI:
    """Stand-in for gidgethub's GitHubAPI that knows one user."""

    def __init__(self, session, requester, oauth_token=None, **kwargs) -> None:
        self.oauth_token = oauth_token

    async def getitem(self, url):
        assert url == "/user"
        assert self.oauth_token == "gho_token"
        return {"login": "octocat"}


def failing_github_api(exc: Exception) -> type[FakeGitHubAPI]:
    """A FakeGitHubAPI whose ``/user`` lookup raises ``exc``."""

    class FailingGitHubAPI(FakeGitHubAPI):
        async def getitem(self, url):
            raise exc

    return FailingGitHubAPI


def oauth_callback_app(
    monkeypatch, exchange, github_api: type = FakeGitHubAPI
) -> web.Application:
    """App for the ``?code=`` leg of sign-in, with GitHub stubbed by ``exchange``."""
    monkeypatch.setattr(__main__, "exchange_code_for_token", exchange)
    monkeypatch.setattr(__main__, "GitHubAPI", github_api)
    monkeypatch.setattr(__main__, "get_jwt", lambda **kwargs: "jwt")

    async def get_installation(gh, jwt, username):
        return {"id": 1}

    monkeypatch.setattr(__main__.util, "get_installation", get_installation)

    app = create_app()
    app.router.add_get("/", __main__.handle_get, name="home")
    app.router.add_get("/install", __main__.handle_install, name="install")
    app.router.add_get("/add_blurb", __main__.handle_add_blurb_get, name="add_blurb")
    return app


async def test_handle_add_blurb_get_signs_in_with_code(
    aiohttp_client, monkeypatch
) -> None:
    # Arrange: GitHub redirected back with a code and will exchange it.
    seen = {}

    async def exchange(session, code):
        seen["code"] = code
        return "gho_token"

    client = await aiohttp_client(oauth_callback_app(monkeypatch, exchange))

    # Act
    resp = await client.get("/add_blurb", params={"code": "the-code"})

    # Assert: the form renders for the user, and the session now remembers
    # them, so the next visit needs no code at all.
    assert resp.status == 200
    assert seen["code"] == "the-code"
    assert "octocat" in await resp.text()
    resp = await client.get("/add_blurb", allow_redirects=False)
    assert resp.status == 200


async def test_handle_add_blurb_get_when_github_is_down(
    aiohttp_client, monkeypatch
) -> None:
    # Arrange: the exchange fails because GitHub is unavailable.
    async def exchange(session, code):
        raise __main__.error.GitHubUnavailable("Got more than 8190 bytes when reading")

    client = await aiohttp_client(oauth_callback_app(monkeypatch, exchange))

    # Act
    resp = await client.get("/add_blurb", params={"code": "the-code"})

    # Assert: a 503 that names GitHub as the cause, not a 500 or a sign-in
    # error, and the template adds the link to GitHub's status page.
    assert resp.status == 503
    text = await resp.text()
    assert "GitHub is not responding right now" in text
    assert '<a href="https://www.githubstatus.com"' in text
    assert "sign-in failed" not in text


async def test_handle_add_blurb_get_when_code_is_rejected(
    aiohttp_client, monkeypatch
) -> None:
    # Arrange: GitHub is up, but the code was already used or has expired.
    async def exchange(session, code):
        raise __main__.error.SignInFailed("The code passed is incorrect or expired.")

    client = await aiohttp_client(oauth_callback_app(monkeypatch, exchange))

    # Act
    resp = await client.get("/add_blurb", params={"code": "stale-code"})

    # Assert: a 400 that tells the user to sign in again.
    assert resp.status == 400
    text = await resp.text()
    assert (
        "GitHub sign-in failed: The code passed is incorrect or expired. "
        "Please go back to the home page and sign in again." in text
    )
    assert "githubstatus.com" not in text


async def test_handle_add_blurb_get_when_oauth_app_is_misconfigured(
    aiohttp_client, monkeypatch
) -> None:
    # Arrange: GitHub rejects our client secret. The user cannot fix that by
    # signing in again, so it must stay a 500 that Sentry reports.
    async def exchange(session, code):
        raise __main__.error.OAuthMisconfigured("incorrect_client_credentials")

    client = await aiohttp_client(oauth_callback_app(monkeypatch, exchange))

    # Act
    resp = await client.get("/add_blurb", params={"code": "the-code"})

    # Assert
    assert resp.status == 500
    assert "sign in again" not in await resp.text()


async def test_handle_add_blurb_get_with_code_but_app_not_installed(
    aiohttp_client, monkeypatch
) -> None:
    # Arrange: sign-in works, but the user has not installed the GitHub App.
    async def exchange(session, code):
        return "gho_token"

    app = oauth_callback_app(monkeypatch, exchange)

    async def get_installation(gh, jwt, username):
        raise __main__.error.InstallationNotFound()

    monkeypatch.setattr(__main__.util, "get_installation", get_installation)
    client = await aiohttp_client(app)

    # Act
    resp = await client.get(
        "/add_blurb", params={"code": "the-code"}, allow_redirects=False
    )

    # Assert
    assert resp.status == 302
    assert resp.headers["Location"] == "/install"


async def exchange_ok(session, code):
    return "gho_token"


@pytest.mark.parametrize(
    "exc",
    [
        gidgethub.GitHubBroken(502, "Bad Gateway"),
        gidgethub.RateLimitExceeded(
            gidgethub.sansio.RateLimit(limit=5000, remaining=0, reset_epoch=0)
        ),
        aiohttp.ClientConnectionError("connection reset"),
        TimeoutError(),
    ],
    ids=["5xx", "rate-limited", "connection-error", "timeout"],
)
async def test_handle_add_blurb_get_when_user_lookup_hits_outage(
    aiohttp_client, monkeypatch, exc: Exception
) -> None:
    # Arrange: the code exchange worked, but GitHub fails on the /user lookup.
    app = oauth_callback_app(monkeypatch, exchange_ok, failing_github_api(exc))
    client = await aiohttp_client(app)

    # Act
    resp = await client.get("/add_blurb", params={"code": "the-code"})

    # Assert
    assert resp.status == 503
    assert "GitHub is not responding right now" in await resp.text()


async def test_handle_add_blurb_get_when_new_token_is_rejected(
    aiohttp_client, monkeypatch
) -> None:
    # Arrange: GitHub issued a token and then refuses it on /user.
    exc = gidgethub.BadRequest(401, "Bad credentials")
    app = oauth_callback_app(monkeypatch, exchange_ok, failing_github_api(exc))
    client = await aiohttp_client(app)

    # Act
    resp = await client.get("/add_blurb", params={"code": "the-code"})

    # Assert: a sign-in failure, not an outage.
    assert resp.status == 400
    text = await resp.text()
    assert "GitHub sign-in failed: GitHub rejected the new token" in text
    assert "sign in again" in text


async def test_handle_add_blurb_get_when_installation_lookup_hits_outage(
    aiohttp_client, monkeypatch
) -> None:
    # Arrange: sign-in worked, but GitHub fails while we check the App install.
    app = oauth_callback_app(monkeypatch, exchange_ok)

    async def get_installation(gh, jwt, username):
        raise gidgethub.GitHubBroken(502, "Bad Gateway")

    monkeypatch.setattr(__main__.util, "get_installation", get_installation)
    client = await aiohttp_client(app)

    # Act
    resp = await client.get("/add_blurb", params={"code": "the-code"})

    # Assert
    assert resp.status == 503
    assert "GitHub is not responding right now" in await resp.text()


def test_get_session_key_from_env(monkeypatch, caplog) -> None:
    expected = fernet.Fernet.generate_key().decode()
    monkeypatch.setenv("SESSION_KEY", expected)

    session_key = __main__.get_session_key()

    assert session_key == expected
    assert "SESSION_KEY is not set" not in caplog.text
    # The key must be usable as-is by the cookie storage.
    EncryptedCookieStorage(session_key)


def test_get_session_key_random_when_unset(monkeypatch, caplog) -> None:
    monkeypatch.delenv("SESSION_KEY", raising=False)

    with caplog.at_level(logging.WARNING):
        session_key = __main__.get_session_key()

    assert session_key != __main__.get_session_key()
    assert "SESSION_KEY is not set" in caplog.text
    EncryptedCookieStorage(session_key)


def test_get_session_key_rejects_invalid_value(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_KEY", "not-a-fernet-key")

    with pytest.raises(ValueError, match="SESSION_KEY is not a valid Fernet key"):
        __main__.get_session_key()
