import asyncio
import time
import hashlib
import base64

from aiohttp_session import get_session


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
    if has_session(request):
        print("has session")
        print(request_session["username"])
        print(request_session["token"])
        context["username"] = request_session["username"]
        context["token"] = request_session["token"]

    return context


async def has_session(request):
    request_session = await get_session(request)
    return request_session.get("username") and request_session.get("token")
