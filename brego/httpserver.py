#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : http.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 08.09.2019

import asyncio
import json
import sys

from sanic import Sanic
from sanic import response
from sanic.response import stream
from sanic.websocket import WebSocketProtocol
from sanic_jinja2 import SanicJinja2

from .database import SensorDB


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

    @app.websocket("/sensors/stream/<device>")
    async def sensor_stream(request, socket, device):
        reader, writer = await asyncio.open_unix_connection(socket_path, loop=app.loop)
        try:
            while True:
                data = await reader.readline()
                if device == 'all':
                    await socket.send(data.decode('utf-8'))
                else:
                    parsed = json.loads(data, encoding='utf-8')
                    filtered = [(t, _device, val) for t, _device, val in parsed
                                if _device == device]
                    await socket.send(json.dumps(filtered))

        except asyncio.CancelledError as e:
            print(f'Websocket closed: {request.socket}', file=sys.stderr)
            writer.close()


def dashboard_route(app, jinja):
    @app.route('/')
    @jinja.template('index.html')
    async def dashboard(request):
        return jinja.render('index.html', request)


def devices_route(app, db):
    @app.route('/sensors/devices')
    async def devices(request):
        return response.json(db.devices_table.all())



def run(args):
    app = Sanic('brego')
    app.static('/static/', 'brego/client/')
    jinja = SanicJinja2(app, pkg_name='brego')
    db = SensorDB()
    
    http_sensor_stream_route(app, args.sensors_socket)
    websocket_sensor_stream_route(app, args.sensors_socket)
    dashboard_route(app, jinja)
    devices_route(app, db)

    app.run(host=args.host, port=args.port, debug=True, protocol=WebSocketProtocol)
