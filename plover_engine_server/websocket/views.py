"""The views / handlers for the server."""

import asyncio
import json
import traceback

from aiohttp import web, WSMsgType
from plover import log


async def index(request: web.Request) -> web.Response:
    return web.Response(text='index')


async def protocol(request: web.Request) -> web.Response:
    proto = "wss://" if request.app['ssl'] else "ws://"
    return web.json_response({"protocol": proto})


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

                try:
                    data = json.loads(message.data)
                except json.decoder.JSONDecodeError:
                    log.info(f'Receive unknown data: {message.data}')
                    continue

                if isinstance(data, dict):
                    callback = request.app['on_message_callback']
                    try:
                        response = callback(data)
                        if response is not None:
                            await socket.send_json(response)
                    except:
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
