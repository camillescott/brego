#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : server.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 05.09.2019

'''The core sensor server. This handles sensor reporting
and timing and makes the collected data available over
TCP and WebSocket protocols.
'''

import json
import os
import signal
import sys
from typing import Awaitable, Optional, Callable, Tuple

import curio
from curio.socket import *

from .database import SensorDB
from .utils import notifies, now
from .ws_server import serve_ws

# Type definition for sensor-reporter coroutines
ReporterType = Callable[[curio.Queue, float], Awaitable[None]]

class SensorServer:

    def __init__(self, sensor_db: SensorDB,
                       polling_interval: float = 0.05,
                       database_write_interval: float = 0.5,
                       bcast_host: Optional[str] = None,
                       bcast_port: int = 5454,
                       websocket_host: Optional[str] = '',
                       websocket_port: int = 6565):
        """

        Args:
            sensor_db (SensorDB): Database to write to.
            polling_interval (float): Global sensor min polling interval.
            database_write_interval (float): Data write op min interval.
            bcast_host (str): Host address for TCP broadcast; if None, don't broadcast.
            bcast_port (int): Host port for TCP broadcast.
            websocket_host (str): Host address for websocket broadcast; if None, don't broadcast.
            websocket_port (int): Host port for websocket broadcast.

        Returns:
        """

        self.readings = curio.Queue()
        self.sensor_db = sensor_db

        self.polling_interval = polling_interval
        self.database_write_interval = database_write_interval

        self.bcast_host = bcast_host
        self.bcast_port = bcast_port

        self.websocket_host = websocket_host
        self.websocket_port = websocket_port

        self.subscribers = set()
        self.reporters= set()

    def register_reporter(self, reporter: ReporterType) -> None:
        """Register a new reporter coroutine. These act as the
        producers and push their results on to the readings queue.

        Args:
            reporter (ReporterType): Reporter coroutine.

        Returns:
            None: 
        """
        self.reporters.add(reporter)

    async def dispatcher(self) -> None:
        try:
            async for reading in self.readings:
                for q in list(self.subscribers):
                    await q.put(reading)
        except curio.CancelledError:
            raise

    async def database_writer(self) -> None:
        try:
            write_q = curio.Queue()
            self.subscribers.add(write_q)

            while True:
                device, data = await write_q.get()

                self.sensor_db.insert_readings(device, [data])
                await write_q.task_done()

        except curio.CancelledError:
            raise

    async def broadcast_client(self, client: curio.io.Socket, addr: Tuple[str, int]) -> None:
        print('Broadcast connection from', addr, file=sys.stderr)

        stream = client.as_stream()
        bcast_q = curio.Queue()
        self.subscribers.add(bcast_q)

        try:
            while True:
                device, data = await bcast_q.get()
                string = json.dumps({'device': device,
                                      'data': data}) + '\n'
                await stream.write(string.encode('ascii'))
        except curio.CancelledError:
            await stream.write({'msg': 'END_STREAM'})
            raise
        except BrokenPipeError:
            print('{0} closed connection.'.format(addr))

    async def broadcaster(self, host: str, port: int) -> None:
        async with curio.SignalQueue(signal.SIGHUP) as restart:
            while True:
                print('Starting broadcast server.', file=sys.stderr)
                broadcast_task = await curio.spawn(curio.tcp_server, host, port, self.broadcast_client)
                await restart.get()
                await broadcast_task.cancel()

    async def websocket_client(self, in_q: curio.Queue, out_q: curio.Queue) -> None:
        bcast_q = curio.Queue()
        self.subscribers.add(bcast_q)

        try:
            while True:
                if not in_q.empty():
                    msg = await in_q.get()
                    if msg is None:
                        break

                device, data = await bcast_q.get()
                strdata = json.dumps({'device': device,
                                      'data': data}) + '\n'
                await out_q.put(strdata)
        except curio.CancelledError:
            raise

    async def run(self) -> None:
        async with curio.TaskGroup() as g:
            cancel = curio.SignalEvent(signal.SIGINT, signal.SIGTERM)

            await g.spawn(self.dispatcher)
            await g.spawn(self.database_writer)
            if self.bcast_host is not None:
                await g.spawn(self.broadcaster,
                              self.bcast_host,
                              self.bcast_port)
            if self.websocket_host is not None:
                await g.spawn(curio.tcp_server,
                              self.websocket_host,
                              self.websocket_port,
                              serve_ws(self.websocket_client))
            for reporter in self.reporters:
                await g.spawn(reporter,
                              self.readings,
                              self.polling_interval)

            await cancel.wait()
            del cancel

            print('Shutting down server...', file=sys.stderr)
            await g.cancel_remaining()

        self.sensor_db.end_session()

