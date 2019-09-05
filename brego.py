#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : brego.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 03.09.2019

import sys

import curio
from gpiozero import MCP3008

from brego.database import SensorDB
from brego.sensors import (find_onewire_devices,
                           AsyncMultiSensor,
                           DS18B20Sensor,
                           SensorServer)

if __name__ == '__main__':
    devices = [DS18B20Sensor(fn) for fn in find_onewire_devices()]
    if not devices:
        print('No devices found, exiting.', file=sys.stderr)
        sys.exit()
    sensors = AsyncMultiSensor(devices)
    database = SensorDB.request_instance()
    for device in devices:
        database.add_device(device.device_name, 'temperature')
    adc = MCP3008()
    database.add_device('MCP3008-0', 'ADC')
    server = SensorServer(sensors, adc, database)
    curio.run(server.run, with_monitor=True)
