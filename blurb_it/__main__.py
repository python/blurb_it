
import base64
import os

import aiohttp
import aiohttp_jinja2
import jinja2
from aiohttp import web
from aiohttp_session import get_session, session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet
from gidgethub.aiohttp import GitHubAPI

import gidgethub


from blurb_it import util


@web.middleware
async def error_middleware(request, handler):
    """Middleware to render error message using the template renderer."""
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        if ex.text:
            message = ex.text
        else:
            message = ex.reason
        context = {"error_message": message, "status": ex.status}
        response = aiohttp_jinja2.render_template(
            "error.html", request, context=context
        )
    return response


async def handle_get(request):
    """Render a page with a textbox and submit button."""
    # data = request.query_string
    # data2 = await request.rel_url.query['']
    request_session = await get_session(request)
    context = {}
    context["client_id"] = os.environ.get("GH_CLIENT_ID")
    if request_session.get("username") and request_session.get("token"):
        context["username"] = request_session["username"]
        location = request.app.router["add_blurb"].url_for()
        raise web.HTTPFound(location=location)
    else:

        response = aiohttp_jinja2.render_template("index.html", request, context={})
    return response


async def handle_add_blurb_get(request):
    """Render a page with a textbox and submit button."""
    token = request.rel_url.query.get("code")

    context = {}

    if await util.has_session(request):
        context.update(await util.get_session_context(request, context))
    elif token is not None:

        async with aiohttp.ClientSession() as session:
            payload = {
                "client_id": os.environ.get("GH_CLIENT_ID"),
                "client_secret": os.environ.get("GH_CLIENT_SECRET"),
                "code": token,
            }
            async with session.post(
                "https://github.com/login/oauth/access_token", data=payload
            ) as response:
                response_text = await response.text()
                access_token = get_access_token(response_text)
                gh = GitHubAPI(session, "python/cpython", oauth_token=access_token)
                response = await gh.getitem("/user")
                print(response)
                login_name = response["login"]
                request_session = await get_session(request)
                request_session["username"] = login_name
                request_session["token"] = access_token
                context["username"] = request_session["username"]
    else:
        raise web.HTTPFound(location="home")

    response = aiohttp_jinja2.render_template(
        "add_blurb.html", request, context=context
    )
    return response


def get_access_token(token_str):
    for token in token_str.split("&"):
        token_split = token.split("=")
        if token_split[0] == "access_token":
            return token_split[1]
    return None


async def handle_add_blurb_post(request):
    if await util.has_session(request):
        session_context = await util.get_session_context(request)
        data = await request.post()
        print(data)
        bpo_number = data.get("bpo_number", "").strip()
        section = data.get("section", "").strip()
        news_entry = data.get("news_entry", "").strip()
        path = await util.get_misc_news_filename(bpo_number, section, news_entry)
        pr_number = data.get("pr_number", "").strip()

        context = {}
        context.update(session_context)
        async with aiohttp.ClientSession() as session:
            print("session context")
            print(session_context)
            gh = GitHubAPI(
                session, "python/cpython", oauth_token=session_context["token"]
            )
            pr = await gh.getitem(f"/repos/python/cpython/pulls/{pr_number}")
            encoded = base64.b64encode(str.encode(news_entry))
            decoded = encoded.decode("utf-8")
            put_data = {
                "branch": pr["head"]["ref"],
                "content": decoded,
                "path": path,
                "message": "Added by blurb_it",
            }
            print(put_data)
            try:
                response = await gh.put(
                    f"/repos/{pr['user']['login']}/cpython/contents/{path}",
                    data=put_data,
                )
            except gidgethub.BadRequest as bac:
                print("error")
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


if __name__ == "__main__":  # pragma: no cover
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)

    app = web.Application(
        middlewares=[
            error_middleware,
            session_middleware(EncryptedCookieStorage(secret_key)),
        ]
    )

    aiohttp_jinja2.setup(
        app, loader=jinja2.FileSystemLoader(os.path.join(os.getcwd(), "templates"))
    )
    app["static_root_url"] = os.path.join(os.getcwd(), "static")
    port = os.environ.get("PORT")
    if port is not None:
        port = int(port)
    app.add_routes(
        [
            web.get("/", handle_get, name="home"),
            web.get("/add_blurb", handle_add_blurb_get, name="add_blurb"),
            web.post("/add_blurb", handle_add_blurb_post),
            web.static("/static", os.path.join(os.getcwd(), "static")),
        ]
    )
    web.run_app(app, port=port)
