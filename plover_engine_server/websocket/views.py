"""The views / handlers for the server."""

from aiohttp import web, WSMsgType
import asyncio


async def index(request: web.Request) -> web.Response:
    """Index endpoint for the server. Not really needed.

    Args:
        request: The request from the client.
    """

    return web.Response(text='index')


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """The main WebSocket handler.

    Args:
        request: The request from the client.
    """

    print('WebSocket connection starting', flush=True)
    socket = web.WebSocketResponse()
    await socket.prepare(request)
    sockets = request.app['websockets']
    sockets.append(socket)
    print('WebSocket connection ready', flush=True)

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
                    print('Receive unknown data: ', message.data)
                    continue

                if isinstance(data, dict):
                    callback = request.app['on_message_callback']
                    callback(data)
            elif message.type == WSMsgType.ERROR:
                print('WebSocket connection closed with exception '
                      f'{socket.exception()}', flush=True)
    except asyncio.CancelledError:  # https://github.com/aio-libs/aiohttp/issues/1768
        pass
    finally:
        await socket.close()


    sockets.remove(socket)
    print('WebSocket connection closed', flush=True)
    return socket
