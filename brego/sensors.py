#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : sensors.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 02.09.2019

import concurrent.futures
import csv
import datetime
import json
import os
import glob
import signal
import sys
import time

import curio
from curio.socket import *

from .database import SensorDB
from .utils import notifies, now
from .ws_server import serve_ws


def find_onewire_devices():
    return glob.glob('/sys/bus/w1/devices/28*/w1_slave')


class DS18B20Sensor:
    """Reads the DS18B20 temperature sensor on the one-wire protocol.
    This sensor takes ~750ms to respond, so it's best to offload
    the reading two a new thread (see the AsyncMultiSensor class).
    """

    def __init__(self, device_filename):
        self.device_filename = device_filename
        self.device_name = device_filename.split('/')[5]

    def read(self):
        with open(self.device_filename) as fp:
            data = fp.read()
            if 'YES' in data:
                (_, sep, reading) = data.partition(' t=')
                temperature = float(reading) / 1000.0
                return temperature
            else:
                return None


class AsyncMultiSensor:
    """Asynchronously reads multiple devices on the one-wire bus.
    """
    def __init__(self, devices, executor=None, notifier=None):
        self.devices = devices
        if executor is None:
            self.executor = concurrent.futures.ThreadPoolExecutor(len(devices))
        else:
            self.executor = executor
        
        self.notifier = notifier

    @property
    def device_names(self):
        return [d.device_name for d in self.devices]
    
    def read(self, *args):
        futures = {}
        for device in self.devices:
            future = self.executor.submit(notifies(self.notifier)(device.read))
            futures[future] = device.device_name

        results = []
        for reading in concurrent.futures.as_completed(futures):
            item = (futures[reading], {'time': now(), 'value': reading.result()})
            results.append(item)

        return results


class SensorServer:

    def __init__(self, multisensor, adc, sensor_db, bcast_host='', bcast_port=5454,
                       websocket_host='', websocket_port=6565):
        self.readings = curio.Queue()
        self.multisensor = multisensor
        self.adc = adc
        self.sensor_db = sensor_db
        self.subscribers = set()

        self.bcast_host = bcast_host
        self.bcast_port = bcast_port

        self.websocket_host = websocket_host
        self.websocket_port = websocket_port

        self.scrapers = {}

    async def adc_scraper(self, adc, readings, interval=.1):
        print('Start scraping ADC.', file=sys.stderr)
        try:
            while True:
                await self.readings.put(('MCP3008-0', {'time': now(), 'value': adc.value}))
                await curio.sleep(interval)
        except:
            raise

    async def temperature_scraper(self, multisensor, readings):
        print('Start scraping temperature sensors.', file=sys.stderr)
        try:
            while True:
                temps = await curio.run_in_thread(multisensor.read)
                for temp in temps:
                    await self.readings.put(temp)
        except curio.CancelledError:
            raise

    async def dispatcher(self):
        try:
            async for reading in self.readings:
                for q in list(self.subscribers):
                    await q.put(reading)
        except curio.CancelledError:
            raise

    async def database_writer(self, readings, db, buf_size=10):
        try:
            write_q = curio.Queue()
            self.subscribers.add(write_q)

            while True:
                device, data = await write_q.get()

                db.insert_readings(device, [data])
                await write_q.task_done()

        except curio.CancelledError:
            raise

    async def broadcast_client(self, client, addr):
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

    async def broadcaster(self, host, port):
        async with curio.SignalQueue(signal.SIGHUP) as restart:
            while True:
                print('Starting broadcast server.', file=sys.stderr)
                broadcast_task = await curio.spawn(curio.tcp_server, host, port, self.broadcast_client)
                await restart.get()
                await broadcast_task.cancel()

    async def websocket_client(self, in_q, out_q):
        #print('Broadcast websocket connection from', addr, file=sys.stderr)

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

    async def run(self):
        async with curio.TaskGroup() as g:
            cancel = curio.SignalEvent(signal.SIGINT, signal.SIGTERM)

            dispatcher_task  = await g.spawn(self.dispatcher)
            scraper_task     = await g.spawn(self.temperature_scraper,
                                             self.multisensor,
                                             self.readings)
            adc_task         = await g.spawn(self.adc_scraper,
                                             self.adc,
                                             self.readings)
            database_task    = await g.spawn(self.database_writer,
                                             self.readings,
                                             self.sensor_db)
            #broadcaster_task = await g.spawn(self.broadcaster,
            #                                 self.bcast_host,
            #                                 self.bcast_port)
            websocket_task   = await g.spawn(curio.tcp_server,
                                             self.websocket_host,
                                             self.websocket_port,
                                             serve_ws(self.websocket_client))

            await cancel.wait()
            del cancel

            print('Shutting down server...', file=sys.stderr)
            await scraper_task.cancel()
            await adc_task.cancel()
            await dispatcher_task.cancel()
            await database_task.cancel()
            #await broadcaster_task.cancel()
            await websocket_task.cancel()

        self.sensor_db.end_session()

