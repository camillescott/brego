#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : http.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 08.09.2019

import asyncio
import sys

from sanic import Sanic
from sanic.response import stream
from sanic.websocket import WebSocketProtocol


def http_sensor_stream_route(app, socket_path):

    @app.route("/sensors/stream/chunked")
    async def sensor_stream(request):
        async def _stream(response):
            reader, writer = await asyncio.open_unix_connection(socket_path, loop=app.loop)
            while True:
                data = await reader.readline()
                await response.write(data)
            writer.close()
        return stream(_stream, content_type='text/json')


def websocket_sensor_stream_route(app, socket_path):

    @app.websocket("/sensors/stream/websocket")
    async def sensor_stream(request, socket):
        reader, writer = await asyncio.open_unix_connection(socket_path, loop=app.loop)
        while True:
            data = await reader.readline()
            await socket.send(data.decode('utf-8'))
        writer.close()


def run(args):
    app = Sanic('brego')
    
    http_sensor_stream_route(app, args.sensors_socket)
    websocket_sensor_stream_route(app, args.sensors_socket)

    app.run(host=args.host, port=args.port, protocol=WebSocketProtocol)
