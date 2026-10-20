import aiohttp_jinja2
from aiohttp import web


@web.middleware
async def error_middleware(request, handler):
    """Middleware to render error message using the template renderer.

    Only client and server errors are rendered. Redirects and other
    non-error responses raised as exceptions pass through untouched.
    The rendered page keeps the original status code, so monitoring,
    health probes and Sentry see the real error instead of a 200.
    """
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        if ex.status < 400:
            raise
        if ex.text:
            message = ex.text
        else:
            message = ex.reason
        context = {"error_message": message, "status": ex.status}
        response = aiohttp_jinja2.render_template(
            "error.html", request, context=context, status=ex.status
        )
    return response
