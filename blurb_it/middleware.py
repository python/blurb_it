import aiohttp_jinja2
from aiohttp import web


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
