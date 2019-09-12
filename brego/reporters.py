#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : reporters.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 05.09.2019

import sys

import curio
import gpiozero

from .sensors import MultiOneWireSensor
from .server import ReporterType
from .utils import now


def adc_reporter(adc: gpiozero.AnalogInputDevice,
                 device_name: str,
                 polling_interval: float) -> ReporterType:

    async def _reporter(readings: curio.Queue):
        print('Start polling ADC {0}'.format(adc), file=sys.stderr)
        try:
            while True:
                await readings.put((device_name,
                                    {'time': now(),
                                     'value': adc.value}))
                await curio.sleep(polling_interval)
        except:
            # TODO: some actual error handling
            raise

    return _reporter


def multionewire_reporter(multisensor: MultiOneWireSensor,
                          polling_interval: float) -> ReporterType:

    async def _reporter(readings: curio.Queue):
        print('Start scraping one-wire sensors.', file=sys.stderr)
        try:
            while True:
                temps = await curio.run_in_thread(multisensor.read)
                for temp in temps:
                    await readings.put(temp)
                await curio.sleep(polling_interval)
        except curio.CancelledError:
            raise

    return _reporter

