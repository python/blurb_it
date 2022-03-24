import base64
import hashlib
import time
import secrets

from aiohttp_session import get_session

from blurb_it import error


async def get_misc_news_filename(issue_number, section, body):
    date = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    nonce = await nonceify(body)
    path = f"Misc/NEWS.d/next/{section}/{date}.gh-issue-{issue_number}.{nonce}.rst"
    return path


async def nonceify(body):
    digest = hashlib.md5(body.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)[0:6].decode("ascii")


async def get_session_context(request, context=None):
    context = context or {}
    if await has_session(request):
        request_session = await get_session(request)
        context["username"] = request_session["username"]
        context["token"] = request_session["token"]

    return context


async def has_session(request):
    request_session = await get_session(request)
    return request_session.get("username") and request_session.get("token")


def get_csrf_token(session):
    try:
        return session["csrf"]
    except KeyError:
        session["csrf"] = csrf = create_csrf_token()
        return csrf


def create_csrf_token():
    return secrets.token_urlsafe(32)


def compare_csrf_tokens(token_a, token_b):
    return secrets.compare_digest(token_a, token_b)


async def get_installation(gh, jwt, username):

    async for installation in gh.getiter(
        "/app/installations",
        jwt=jwt,
        accept="application/vnd.github.machine-man-preview+json",
    ):  # pragma: no cover
        if installation["account"]["login"] == username:
            return installation

    raise error.InstallationNotFound(
        f"Can't find installation by that user: {username}"
    )
