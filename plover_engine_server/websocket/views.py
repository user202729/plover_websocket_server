"""The views / handlers for the server."""

from aiohttp import web, WSMsgType
import asyncio
from plover import log
from http import HTTPStatus, HTTPMethod
from plover_engine_server.websocket.server import APIContext

async def index(request: web.Request) -> web.Response:
    """Index endpoint for the server. Not really needed.

    Args:
        request: The request from the client.
    """

    return web.Response(text='index')

async def protocol(request: web.Request, context: APIContext) -> web.Response:
    """Route to get the protocol of the web server.

    Args:
        request: The request from the client.
    """
    if request.method != HTTPMethod.GET:
        return web.Response(status=HTTPStatus.METHOD_NOT_ALLOWED, text=HTTPStatus.METHOD_NOT_ALLOWED[1])

    if context.ssl:
        protocol = "wss://"
    else:
        protocol = "ws://"

    data = {
        "protocol": protocol
    }

    return web.json_response(data)


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """The main WebSocket handler.

    Args:
        request: The request from the client.
    """

    log.info('WebSocket connection starting')
    socket = web.WebSocketResponse()
    await socket.prepare(request)
    sockets = request.app['websockets']
    sockets.append(socket)
    log.info('WebSocket connection ready')

    try:
        async for message in socket:
            if message.type == WSMsgType.TEXT:
                if message.data == 'close':
                    await socket.close()
                    continue

                import json
                try:  # NOTE is this good API? What if message is not JSON/dict?
                    data = json.loads(message.data)
                except json.decoder.JSONDecodeError:
                    log.info(f'Receive unknown data: {message.data}')
                    continue

                if isinstance(data, dict):
                    callback = request.app['on_message_callback']
                    try:
                        callback(data)
                    except:
                        import traceback
                        traceback.print_exc()

            elif message.type == WSMsgType.ERROR:
                log.info('WebSocket connection closed with exception '
                      f'{socket.exception()}')
    except asyncio.CancelledError:  # https://github.com/aio-libs/aiohttp/issues/1768
        pass
    finally:
        await socket.close()


    sockets.remove(socket)
    log.info('WebSocket connection closed')
    return socket
