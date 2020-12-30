"""WebSocket server definition."""

import asyncio

from aiohttp import web, WSCloseCode

from plover_engine_server.errors import (
    ERROR_SERVER_RUNNING,
    ERROR_NO_SERVER
)
from plover_engine_server.server import (
    EngineServer,
    ServerStatus
)
from plover_engine_server.websocket.routes import setup_routes


class WebSocketServer(EngineServer):
    """A server based on WebSockets."""

    def __init__(self, host: str, port: str):
        """Initialize the server.

        Args:
            host: The host address for the server to run on.
            port: The port for the server to run on.
        """

        super().__init__(host, port)
        self._app = None

    def _start(self):
        """Starts the server.

        Will create a blocking event loop.
        """
        if self.status == ServerStatus.Running:
            raise AssertionError(ERROR_SERVER_RUNNING)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        self._app = web.Application()
        self._app['websockets'] = []
        self._app['on_message_callback'] = self._on_message

        setup_routes(self._app)
        self._app.on_shutdown.append(self._on_server_shutdown)

        self._stop_event = asyncio.Event()

        async def run_async():
            self._runner = runner = web.AppRunner(self._app)
            await runner.setup()
            self._site = site = web.TCPSite(runner, host=self._host, port=self._port)
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
