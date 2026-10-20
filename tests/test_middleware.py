from __future__ import annotations

import pathlib

import aiohttp_jinja2
import jinja2
from aiohttp import web

from blurb_it import middleware


def create_app() -> web.Application:
    app = web.Application(middlewares=[middleware.error_middleware])
    aiohttp_jinja2.setup(
        app, loader=jinja2.FileSystemLoader(pathlib.Path.cwd() / "templates")
    )
    return app


async def test_not_found_keeps_status_code(aiohttp_client) -> None:
    app = create_app()
    client = await aiohttp_client(app)

    response = await client.get("/does-not-exist")

    assert response.status == 404
    text = await response.text()
    assert "<h1>404</h1>" in text
    assert "Not Found" in text


async def test_handler_error_renders_text_with_status(aiohttp_client) -> None:
    async def forbidden(request):
        raise web.HTTPForbidden(reason="Invalid CSRF token. Please retry.")

    app = create_app()
    app.router.add_get("/forbidden", forbidden)
    client = await aiohttp_client(app)

    response = await client.get("/forbidden")

    assert response.status == 403
    text = await response.text()
    assert "<h1>403</h1>" in text
    assert "Invalid CSRF token. Please retry." in text


async def test_redirect_passes_through(aiohttp_client) -> None:
    async def redirect(request):
        raise web.HTTPFound(location="/elsewhere")

    app = create_app()
    app.router.add_get("/redirect", redirect)
    client = await aiohttp_client(app)

    response = await client.get("/redirect", allow_redirects=False)

    assert response.status == 302
    assert response.headers["Location"] == "/elsewhere"
