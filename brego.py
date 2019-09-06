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
from brego.reporters import (adc_reporter, multionewire_reporter)
from brego.sensors import (find_onewire_devices,
                           MultiOneWireSensor,
                           DS18B20Sensor)
from brego.server import SensorServer

if __name__ == '__main__':
    database = SensorDB.request_instance()
    server = SensorServer(database)

    # one-wire temperature senseoers
    onewire_devices = [DS18B20Sensor(fn) for fn in find_onewire_devices()]
    onewire_sensors = MultiOneWireSensor(onewire_devices)
    for device in onewire_devices:
        database.add_device(device.device_name, 'temperature')
    server.register_reporter(multionewire_reporter(onewire_sensors))

    # ADCs
    adc = MCP3008()
    database.add_device('MCP3008-0', 'ADC')
    server.register_reporter(adc_reporter(adc, 'MCP3008-0'))

    curio.run(server.run, with_monitor=True)
