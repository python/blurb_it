import base64
import hashlib
import time

import jwt
from aiohttp_session import get_session

from blurb_it import error


async def get_misc_news_filename(bpo, section, body):
    date = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    nonce = await nonceify(body)
    path = f"Misc/NEWS.d/next/{section}/{date}.bpo-{bpo}.{nonce}.rst"
    return path


async def nonceify(body):
    digest = hashlib.md5(body.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)[0:6].decode("ascii")


async def get_session_context(request, context=None):
    context = context or {}
    request_session = await get_session(request)
    if await has_session(request):
        context["username"] = request_session["username"]
        context["token"] = request_session["token"]

    return context


async def has_session(request):
    request_session = await get_session(request)
    return request_session.get("username") and request_session.get("token")


def get_jwt(app_id, private_key):

    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + (10 * 60),
        "iss": app_id,
    }
    encoded = jwt.encode(payload, private_key, algorithm="RS256")
    bearer_token = encoded.decode("utf-8")

    return bearer_token


async def get_installation(gh, jwt, username):

    async for installation in gh.getiter(
        "/app/installations",
        jwt=jwt,
        accept="application/vnd.github.machine-man-preview+json",
    ):
        if installation["account"]["login"] == username:
            return installation

    raise error.InstallationNotFound(
        f"Can't find installation by that user: {username}"
    )


async def get_installation_access_token(gh, jwt, installation_id):
    # doc: https: // developer.github.com/v3/apps/#create-a-new-installation-token

    access_token_url = f"app/installations/{installation_id}/access_tokens"
    response = await gh.post(
        access_token_url,
        data=b"",
        jwt=jwt,
        accept="application/vnd.github.machine-man-preview+json",
    )
    # example response
    # {
    #   "token": "v1.1f699f1069f60xxx",
    #   "expires_at": "2016-07-11T22:14:10Z"
    # }

    return response
