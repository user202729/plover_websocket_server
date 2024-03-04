#!/bin/python
"""An example client for the server."""

import argparse
import asyncio

import aiohttp

from plover_engine_server.config import DEFAULT_HOST, DEFAULT_PORT


async def client_loop(host: str, port: str):
    """The functionality of the client.

    Args:
        host: The host address for the server to run on.
        port: The port for the server to run on.
    """

    url = f'http://{host}:{port}/websocket'
    session = aiohttp.ClientSession()

    # Create custom headers
    headers = {"X-Secret-Token": "mysecretkey"}

    async with session.ws_connect(url, headers=headers) as socket:
        async def send_function():
            while True:
                await asyncio.sleep(1)
                print("do toggle")
                await socket.send_str(r'{"zero_last_stroke_length": true, "translation": "{PLOVER:toggle}"}')

        async def listen_function():
            async for message in socket:
                if message.type in (aiohttp.WSMsgType.CLOSE,
                                    aiohttp.WSMsgType.CLOSING,
                                    aiohttp.WSMsgType.CLOSED,
                                    aiohttp.WSMsgType.ERROR):
                    break

                print(f'data: {message.data}')

        await asyncio.gather(
                send_function(),
                listen_function(),
                )



def main():
    """The main entry point."""

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default=DEFAULT_HOST,
                        help='the host address for the server to run on')
    parser.add_argument('--port', default=DEFAULT_PORT,
                        help='the port for the server to run on')

    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(client_loop(args.host, args.port))


if __name__ == '__main__':
    main()
