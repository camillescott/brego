#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : server.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 05.09.2019

'''The core sensor server. This handles sensor reporting
and timing and makes the collected data available over
UNIX socket and WebSocket protocols.
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

DEFAULT_SOCKET = '/tmp/brego.gpio.sock'

class SensorServer:

    def __init__(self, sensor_db: SensorDB,
                       broadcast_socket: str = DEFAULT_SOCKET,
                       database_write_interval: float = 0.5,
                       write_results: bool = False,
                       report_status: bool = False):
        """

        Args:
            sensor_db (SensorDB): Database to write to.
            polling_interval (float): Global sensor min polling interval.
            database_write_interval (float): Data write op min interval.
            websocket_host (str): Host address for websocket broadcast; if None, don't broadcast.
            websocket_port (int): Host port for websocket broadcast.

        Returns:
        """

        try:
            os.unlink(broadcast_socket)
        except OSError:
            if os.path.exists(broadcast_socket):
                raise

        self.readings = curio.Queue()
        self.sensor_db = sensor_db

        self.write_results = write_results
        self.database_write_interval = database_write_interval

        self.broadcast_socket = broadcast_socket

        self.subscribers = set()
        self.subscriber_names = {}
        self.reporters= set()

        self.report_status = report_status

    def register_subscriber(self, q: curio.Queue, name: str) -> None:
        if q not in self.subscribers:
            self.subscribers.add(q)
            self.subscriber_names[q] = name

    def unsubscribe(self, q: curio.Queue) -> None:
        try:
            self.subscribers.remove(q)
            del self.subscriber_names[q]
        except:
            pass

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

    async def status_reporter(self) -> None:
        try:
            while True:
                await curio.sleep(5)
                sizes = {name: q.qsize() for q, name in self.subscriber_names.items()}
                print(f'Subscriber queue sizes: {sizes}', file=sys.stderr)
        except curio.CancelledError:
            raise

    async def database_writer(self) -> None:
        try:
            write_q = curio.Queue()
            self.register_subscriber(write_q, 'database_writer')

            while True:
                block = await write_q.get()
                self.sensor_db.insert_readings(block)
                await write_q.task_done()

        except curio.CancelledError:
            raise
        finally:
            self.unsubscribe(write_q)

    async def broadcast_client(self, client: curio.io.Socket, addr: Tuple[str, int]) -> None:
        client_name = hash(client) # i guess getpeername() doesn't work with AF_UNIX
        print(f'Unix socket connection: {client_name}', file=sys.stderr)

        stream = client.as_stream()
        bcast_q = curio.Queue()
        self.register_subscriber(bcast_q, f'broadcast_client:{client_name}')
        n_readings = 0
        last_report = now()
        try:
            while True:
                block = await bcast_q.get()

                n_readings += len(block)
                delta = block[-1][0] - last_report
                if(delta >= 5.0):
                    print(f'Broadcasting {n_readings / delta} readings/second.', file=sys.stderr)
                    last_report = now()
                    n_readings = 0

                string = json.dumps(block) + '\n'
                await curio.timeout_after(60, stream.write, string.encode('ascii'))
        except curio.CancelledError:
            await stream.write(json.dumps([(0, 'END_STREAM', -1)]).encode('ascii'))
            raise
        except (BrokenPipeError, curio.TaskTimeout):
            print(f'Unix socket closed: {client_name}', file=sys.stderr)
        finally:
            self.unsubscribe(bcast_q)

    async def broadcaster(self) -> None:
        async with curio.SignalQueue(signal.SIGHUP) as restart:
            while True:
                print(f'Starting broadcast server on {self.broadcast_socket}.', file=sys.stderr)
                broadcast_task = await curio.spawn(curio.unix_server,
                                                   self.broadcast_socket,
                                                   self.broadcast_client)
                await restart.get()
                await broadcast_task.cancel()


    async def run(self) -> None:
        async with curio.TaskGroup() as g:
            cancel = curio.SignalEvent(signal.SIGINT, signal.SIGTERM)

            await g.spawn(self.dispatcher)

            if self.report_status:
                await g.spawn(self.status_reporter)

            if self.write_results:
                await g.spawn(self.database_writer)

            await g.spawn(self.broadcaster)

            for reporter in self.reporters:
                await g.spawn(reporter,
                              self.readings)

            await cancel.wait()
            del cancel

            print('Shutting down server...', file=sys.stderr)
            await g.cancel_remaining()

        self.sensor_db.end_session()


def run(args):
    from gpiozero import MCP3008

    from brego.database import SensorDB
    from brego.sensors import (find_onewire_devices,
                               MultiOneWireSensor,
                               DS18B20Sensor,
                               ADCManager)

    database = SensorDB.request_instance()
    server = SensorServer(database,
                          broadcast_socket=args.broadcast_socket,
                          report_status=args.report_status)
    
    # one-wire temperature sensors
    onewire_devices = [DS18B20Sensor(fn) for fn in find_onewire_devices()]
    onewire_sensors = MultiOneWireSensor(onewire_devices)
    for device in onewire_devices:
        database.add_device(device.device_name, 'temperature')
    server.register_reporter(onewire_sensors.reporter)

    # ADCs
    adc_devices = [MCP3008(channel=0), MCP3008(channel=7)]
    adc_names   = ['Potentiometer', 'Tachometer']
    for name in adc_names:
        database.add_device(name, 'ADC')
    adc_manager = ADCManager(adc_devices, adc_names)
    adc_manager.start()
    server.register_reporter(adc_manager.reporter)

    curio.run(server.run, with_monitor=True)
