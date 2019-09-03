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
import sys
import time

import curio

from utils import notifies


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

        result = {'time': str(datetime.datetime.now())}
        for reading in concurrent.futures.as_completed(futures):
            result[futures[reading]] = reading.result()

        return result

    
    def read_as_dataframe(self, *args):
        return pd.DataFrame(self.read(), index=pd.DatetimeIndex([datetime.datetime.now()])).sort_index(axis=1)



async def temperature_scraper(multisensor, readings, lock):
    print('Start scraping temperature sensors.')
    try:
        while True:
            _temps = await curio.run_in_thread(multisensor.read)
            temps = {k:[v] for k,v in _temps.items()}
            async with lock:
                readings.append(temps)
    except curio.CancelledError:
        raise


async def csv_interval_writer(readings, fp, lock, interval=0.05):
    try:
        prev = None
        curr = None

        while True:
            await curio.sleep(interval)
            async with lock:
                if prev is None and len(readings) == 0:
                    continue

                curr = dict(readings[-1])
                if prev == curr:
                    curr['time'] = [str(datetime.datetime.now())]
                else:
                    prev = dict(readings[-1])

            print(json.dumps(curr), file=fp)

    except curio.CancelledError:
        raise

            
class TemperatureServer:

    def __init__(self, multisensor, output_filename):
        self.readings = []
        self.multisensor = multisensor
        self.output_filename = output_filename

    async def run(self):
        lock = curio.Lock()
        with open(self.output_filename, 'w', buffering=1) as fp:
            #writer = csv.DictWriter(fp,
            #                        fieldnames=self.multisensor.device_names + ['time'])
            #writer.writeheader()
            async with curio.TaskGroup() as g:
                await g.spawn(temperature_scraper,
                              self.multisensor,
                              self.readings,
                              lock)
                await g.spawn(csv_interval_writer,
                              self.readings,
                              fp,
                              lock)

if __name__ == '__main__':
    devices = [DS18B20Sensor(fn) for fn in find_onewire_devices()]
    if not devices:
        print('No devices found, exiting.', file=sys.stderr)
        sys.exit()
    sensors = AsyncMultiSensor(devices)
    server = TemperatureServer(sensors, 'output.csv')
    curio.run(server.run, with_monitor=True)
