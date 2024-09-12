"""The routes for the server."""

from aiohttp import web


def setup_routes(app: web.Application):
    """Sets up the routes for the web server.

    Args:
        app: The web server.
    """
    from plover_engine_server.websocket.views import index, protocol, websocket_handler
    app.router.add_get('/', index)
    app.router.add_get('/protocol', protocol)
    app.router.add_get('/websocket', websocket_handler)
