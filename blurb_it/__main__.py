from __future__ import annotations

import base64
import json
import logging
import os

import aiohttp
import aiohttp_jinja2
import gidgethub
import jinja2
import sentry_sdk
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp_session import get_session, session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet
from gidgethub.aiohttp import GitHubAPI
from gidgethub.apps import get_installation_access_token, get_jwt

from blurb_it import error, middleware, util

routes = web.RouteTableDef()


sentry_sdk.init(os.environ.get("SENTRY_DSN"))

GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
# Rendered as a 503; the error template adds the link to GitHub's status page.
GITHUB_UNAVAILABLE_MESSAGE = "GitHub is not responding right now."
# Fail fast when GitHub accepts the connection but never answers, instead of
# holding the user's browser for aiohttp's default five minutes.
GITHUB_TIMEOUT = aiohttp.ClientTimeout(total=30)
# What a GitHub outage looks like from here. The exceptions in
# exchange_code_for_token are wrapped in GitHubUnavailable; the rest come from
# gidgethub calls made directly by the handler.
GITHUB_UNAVAILABLE_ERRORS = (
    error.GitHubUnavailable,
    gidgethub.GitHubBroken,
    gidgethub.RateLimitExceeded,
    aiohttp.ClientError,
    TimeoutError,
)


@routes.get("/", name="home")
async def handle_get(request: Request) -> Response:
    """Render a page with a textbox and submit button."""
    # data = request.query_string
    # data2 = await request.rel_url.query['']
    request_session = await get_session(request)
    context = util.get_app_context()
    if request_session.get("username") and request_session.get("token"):
        raise web.HTTPFound(location=request.app.router["add_blurb"].url_for())
    return aiohttp_jinja2.render_template("index.html", request, context=context)


@routes.get("/howto", name="howto")
async def handle_howto_get(request: Request) -> Response:
    """Render a page explaining how to use blurb_it"""
    context = util.get_app_context()
    response = aiohttp_jinja2.render_template("howto.html", request, context=context)
    return response


@routes.get("/install", name="install")
async def handle_install(request: Request) -> Response:
    """Render a page, ask user to install blurb_it"""
    # data = request.query_string
    # data2 = await request.rel_url.query['']
    context = util.get_app_context()
    if await util.has_session(request):
        context.update(await util.get_session_context(request, context))

    response = aiohttp_jinja2.render_template("install.html", request, context=context)
    return response


@routes.get("/health", name="health")
async def health_check(request: Request) -> Response:
    """Health check endpoint for container orchestration."""
    return web.Response(status=200, text="OK")


@routes.get("/add_blurb", name="add_blurb")
async def handle_add_blurb_get(request: Request) -> Response:
    """Render a page with a textbox and submit button."""
    token = request.rel_url.query.get("code")
    request_session = await get_session(request)
    context = {"csrf": util.get_csrf_token(session=request_session)}

    if await util.has_session(request):
        context.update(await util.get_session_context(request, context))
        async with aiohttp.ClientSession(timeout=GITHUB_TIMEOUT) as session:
            try:
                await require_app_installed(request, session, context["username"])
            except GITHUB_UNAVAILABLE_ERRORS as exc:
                raise web.HTTPServiceUnavailable(
                    text=GITHUB_UNAVAILABLE_MESSAGE
                ) from exc

    elif token is not None:

        async with aiohttp.ClientSession(timeout=GITHUB_TIMEOUT) as session:
            try:
                access_token = await exchange_code_for_token(session, token)
                gh = GitHubAPI(session, "blurb-it", oauth_token=access_token)
                try:
                    user = await gh.getitem("/user")
                except gidgethub.RateLimitExceeded:
                    # Throttling is an outage, not a bad token: let the outer
                    # handler turn it into the 503 page.
                    raise
                except gidgethub.BadRequest as exc:
                    raise error.SignInFailed(
                        f"GitHub rejected the new token ({exc})"
                    ) from exc
                login_name = user["login"]
                request_session["username"] = login_name
                request_session["token"] = access_token
                context["username"] = login_name
                await require_app_installed(request, session, login_name)
            except GITHUB_UNAVAILABLE_ERRORS as exc:
                raise web.HTTPServiceUnavailable(
                    text=GITHUB_UNAVAILABLE_MESSAGE
                ) from exc
            except error.SignInFailed as exc:
                reason = str(exc).rstrip(".")
                raise web.HTTPBadRequest(
                    text=f"GitHub sign-in failed: {reason}. "
                    "Please go back to the home page and sign in again."
                ) from exc

    else:
        raise web.HTTPFound(location=request.app.router["home"].url_for())

    response = aiohttp_jinja2.render_template(
        "add_blurb.html", request, context=context
    )
    return response


async def require_app_installed(
    request: Request, session: aiohttp.ClientSession, username: str
) -> None:
    """Redirect to the install page unless ``username`` has installed the App.

    GitHub errors other than "not installed" propagate so the caller can
    decide what an outage looks like for its page.
    """
    gh = GitHubAPI(session, username)
    jwt = get_jwt(
        app_id=os.getenv("GH_APP_ID"), private_key=os.getenv("GH_PRIVATE_KEY")
    )
    try:
        await util.get_installation(gh, jwt, username)
    except error.InstallationNotFound:
        raise web.HTTPFound(location=request.app.router["install"].url_for())


async def exchange_code_for_token(
    session: aiohttp.ClientSession, code: str, *, url: str = GITHUB_OAUTH_TOKEN_URL
) -> str:
    """Trade the ``code`` from GitHub's OAuth redirect for a user access token.

    ``url`` is GitHub's token endpoint; tests point it at a local server.

    Raises ``GitHubUnavailable`` when GitHub cannot be reached or times out,
    answers with a server error, or sends back something other than the token
    endpoint's JSON. The last case is what an outage or rate-limit interstitial looks
    like: an HTML page whose Content-Security-Policy header is larger than
    aiohttp's 8 KB header limit, so aiohttp rejects the response before the
    body is even read.

    Raises ``SignInFailed`` when GitHub rejects the code because it expired or
    was already used, which the user fixes by signing in again. Any other
    ``error`` code from GitHub means our client id, secret or callback URL is
    wrong and raises ``OAuthMisconfigured`` so the deploy problem reaches Sentry.
    """
    payload = {
        "client_id": os.environ.get("GH_CLIENT_ID"),
        "client_secret": os.environ.get("GH_CLIENT_SECRET"),
        "code": code,
    }
    headers = {"Accept": "application/json"}
    try:
        async with session.post(url, data=payload, headers=headers) as response:
            status = response.status
            try:
                data = await response.json()
            except json.JSONDecodeError:
                data = None
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise error.GitHubUnavailable(str(exc)) from exc

    if status == 429 or status >= 500 or not isinstance(data, dict):
        raise error.GitHubUnavailable(
            f"GitHub answered HTTP {status} instead of a token"
        )
    if "error" in data:
        code_error = data["error"]
        description = data.get("error_description", "")
        if code_error == "bad_verification_code":
            raise error.SignInFailed(description or code_error)
        raise error.OAuthMisconfigured(f"{code_error} {description}".strip())
    access_token = data.get("access_token")
    if not access_token:
        raise error.SignInFailed("GitHub did not return an access token")
    return access_token


@routes.post("/add_blurb")
async def handle_add_blurb_post(request: Request) -> Response:
    if await util.has_session(request):
        session_context = await util.get_session_context(request)
        request_session = await get_session(request)
        data = await request.post()

        csrf_form = data.get("csrf", "").strip()
        if not util.compare_csrf_tokens(
            csrf_form, util.get_csrf_token(session=request_session)
        ):
            raise web.HTTPForbidden(reason="Invalid CSRF token. Please retry.")

        issue_number = data.get("issue_number", "").strip()
        section = data.get("section", "").strip()
        news_entry = data.get("news_entry", "").strip() + "\n"
        cve = data.get("cve", "").strip()
        if cve:
            if section != util.CVE_SECTION:
                raise web.HTTPBadRequest(
                    reason=f"A CVE may only be given for the {util.CVE_SECTION} section."
                )
            cve = util.normalize_cve(cve)
            if cve is None:
                raise web.HTTPBadRequest(
                    reason="Invalid CVE identifier (expected CVE-YYYY-NNNN)."
                )
        path = await util.get_misc_news_filename(issue_number, section, news_entry)
        news_content = util.get_misc_news_content(news_entry, cve=cve)
        pr_number = data.get("pr_number", "").strip()

        context = {}
        context.update(session_context)

        async with aiohttp.ClientSession() as session:
            gh = GitHubAPI(session, session_context["username"])

            jwt = get_jwt(
                app_id=os.getenv("GH_APP_ID"), private_key=os.getenv("GH_PRIVATE_KEY")
            )
            try:
                installation = await util.get_installation(
                    gh, jwt, session_context["username"]
                )
            except error.InstallationNotFound:
                raise web.HTTPFound(location=request.app.router["install"].url_for())
            else:
                access_token = await get_installation_access_token(
                    gh,
                    installation_id=installation["id"],
                    app_id=os.getenv("GH_APP_ID"),
                    private_key=os.getenv("GH_PRIVATE_KEY"),
                )

                gh = GitHubAPI(
                    session,
                    session_context["username"],
                    oauth_token=access_token["token"],
                )
                pr = await gh.getitem(f"/repos/python/cpython/pulls/{pr_number}")
                pr_repo_full_name = pr["head"]["repo"]["full_name"]
                encoded = base64.b64encode(str.encode(news_content))
                decoded = encoded.decode("utf-8")
                put_data = {
                    "branch": pr["head"]["ref"],
                    "content": decoded,
                    "path": path,
                    "message": "📜🤖 Added by blurb_it.",
                }
                try:
                    response = await gh.put(
                        f"/repos/{pr_repo_full_name}/contents/{path}", data=put_data
                    )
                except gidgethub.BadRequest as bac:
                    print("BadRequest")
                    print(int(bac.status_code))
                    print(bac)
                    context[
                        "pr_url"
                    ] = f"https://github.com/python/cpython/pull/{pr_number}"
                    context["pr_number"] = pr_number
                    context["status"] = "failure"
                else:
                    commit_url = response["commit"]["html_url"]
                    context["commit_url"] = commit_url
                    context["path"] = response["content"]["path"]
                    context[
                        "pr_url"
                    ] = f"https://github.com/python/cpython/pull/{pr_number}"
                    context["pr_number"] = pr_number
                    context["status"] = "success"

        template = "add_blurb.html"
        response = aiohttp_jinja2.render_template(template, request, context=context)
        return response
    else:
        raise web.HTTPFound(location=request.app.router["add_blurb"].url_for())


def get_session_key() -> str:
    """Return the Fernet key that encrypts the session cookie.

    The key comes from the ``SESSION_KEY`` environment variable so that it
    stays the same across restarts and deploys. Without it a random key is
    generated, which is fine for local development, but then every restart
    invalidates all existing sessions and signs everyone out.
    """
    session_key = os.environ.get("SESSION_KEY")
    if session_key:
        try:
            fernet.Fernet(session_key)
        except ValueError as exc:
            raise ValueError(
                "SESSION_KEY is not a valid session key. "
                "See the Deploy section of the readme."
            ) from exc
        return session_key
    logging.warning(
        "SESSION_KEY is not set; using a random session key, so sessions "
        "will not survive a restart. See the Deploy section of the readme."
    )
    return fernet.Fernet.generate_key().decode()


if __name__ == "__main__":  # pragma: no cover
    app = web.Application(
        middlewares=[
            middleware.error_middleware,
            session_middleware(EncryptedCookieStorage(get_session_key())),
        ]
    )

    aiohttp_jinja2.setup(
        app, loader=jinja2.FileSystemLoader(os.path.join(os.getcwd(), "templates"))
    )
    app["static_root_url"] = os.path.join(os.getcwd(), "static")
    app.router.add_routes(routes)
    app.add_routes([web.static("/static", os.path.join(os.getcwd(), "static"))])

    if os.path.isdir("/var/run/cabotage"):
        # On cabotage the TLS sidecar proxies to this unix socket.
        os.umask(0)
        web.run_app(app, path="/var/run/cabotage/cabotage.sock")
    else:
        port = os.environ.get("PORT")
        web.run_app(app, port=int(port) if port else None)
