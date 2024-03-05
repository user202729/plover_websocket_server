"""WebSocket server definition."""

import asyncio

from aiohttp import web, WSCloseCode
import ssl

from plover_engine_server.errors import (
    ERROR_SERVER_RUNNING,
    ERROR_NO_SERVER
)
from plover_engine_server.server import (
    EngineServer,
    ServerStatus
)
from plover_engine_server.websocket.routes import setup_routes

from typing import TypedDict

class APIContext(TypedDict):
    ssl: bool

class SSLConfig(TypedDict):
    cert_path: str
    key_path: str

class WebSocketServer(EngineServer):
    """A server based on WebSockets."""

    _ssl: SSLConfig
    _app: web.Application
    _secretkey: str
    def __init__(self, host: str, port: str, secretkey: str, ssl: dict):
        """Initialize the server.

        Args:
            host: The host address for the server to run on.
            port: The port for the server to run on.
        """

        super().__init__(host, port)
        self._app = None
        self._ssl = ssl
        self._secretkey = secretkey

    async def secret_auth_middleware(self, handler: function):
        async def middleware(request: web.Request):
            # Get the secret token from the request (you can use headers, query params, etc.)
            provided_secret = request.headers.get('X-Secret-Token')

            if provided_secret == self._secretkey:
                # Secret matches, proceed with the request
                return await handler(request)
            else:
                # Secret doesn't match, return a 403 Forbidden response
                return web.Response(status=403, text='Forbidden')

        return middleware

    async def context_middleware(self, handler: function):
        async def middleware(request: web.Request):
            # Inject ssl bool into the request context
            context: APIContext = {'ssl': True if (self._ssl) else False}

            # Proceed with the request
            return await handler(request, context)

        return middleware

    def _start(self):
        """Starts the server.

        Will create a blocking event loop.
        """
        if self.status == ServerStatus.Running:
            raise AssertionError(ERROR_SERVER_RUNNING)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        self._app = web.Application(middlewares=[self.secret_auth_middleware, self.context_middleware])

        async def on_shutdown(app):
            for ws in set(app['websockets']):
                await ws.close()
        self._app.on_shutdown.append(on_shutdown)

        self._app['websockets'] = []
        self._app['on_message_callback'] = self._on_message

        setup_routes(self._app)
        self._app.on_shutdown.append(self._on_server_shutdown)

        self._stop_event = asyncio.Event()

        async def run_async():
            self._runner = runner = web.AppRunner(self._app)
            await runner.setup()

            if self._ssl:
                # Load your SSL certificate and private key
                ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                ssl_context.load_cert_chain(self._ssl.get('cert_path'), self._ssl.get('key_path'))
            else:
                ssl_context = None

            self._site = site = web.TCPSite(runner, host=self._host, port=self._port, ssl_context=ssl_context)
            await site.start()
            self.status = ServerStatus.Running
            await self._stop_event.wait()
            await runner.cleanup()
            self._app = None
            self._loop = None
            self.status = ServerStatus.Stopped

        loop.run_until_complete(run_async())

    async def _stop(self):
        """Stops the server.

        Performs any clean up operations as needed.
        """

        if self.status != ServerStatus.Running:
            raise AssertionError(ERROR_NO_SERVER)

        self._stop_event.set()

    async def _on_server_shutdown(self, app: web.Application):
        """Handles pre-shutdown behavior for the server.

        Args:
            app: The web application shutting down.
        """

        for socket in app.get('websockets', []):
            await socket.close(code=WSCloseCode.GOING_AWAY,
                               message='Server shutdown')

    async def _broadcast_message(self, data: dict):
        """Broadcasts a message to connected clients.

        Args:
            data: The data to broadcast. Internally it's sent with WebSocketResponse.send_json.
        """

        if not self._app:
            return

        sockets=self._app.get('websockets', [])
        for socket in sockets:
            try:
                await socket.send_json(data)
            except:
                print(f'Failed to update websocket {socket} {id(socket)} {socket.closed} (this should not happen)', flush=True)
        sockets[:]=[socket for socket in sockets if not socket.closed] #this should not change sockets normally
