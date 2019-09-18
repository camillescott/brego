#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : sensors.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 02.09.2019

"""
Sensor-polling utilities.
"""

from abc import ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import sys
import threading
from typing import Optional, Iterable, List, Dict, Union, Any, Sequence, Tuple

import curio
import gpiozero

from .utils import notifies, now


def find_onewire_devices() -> Iterable[str]:
    """Get the list of files corresponding to devices
    on the one-wire bus.

    Args:

    Returns:
        Iterable[str]: The file paths.
    """
    return glob.glob('/sys/bus/w1/devices/28*/w1_slave')


class OneWire(metaclass=ABCMeta):
    """Generic one-wire device. Subclasses must define `read`.
    Will have attributes device_filename and device_name, where
    the latter is derived from the filename.
    """

    def __init__(self, device_filename: str) -> None:
        """
        Args:
            device_filename (str): Path to the device file.

        Returns:
            None: 
        """
        self.device_filename = device_filename
        self.device_name = device_filename.split('/')[5]
    
    @abstractmethod
    def read(self) -> Any: pass


class DS18B20Sensor(OneWire):
    """Reads the DS18B20 temperature sensor on the one-wire protocol.
    This sensor takes ~750ms to respond, so it's best to offload
    the reading to a new thread (see the AsyncMultiSensor class).
    """
    def __init__(self, *args, **kwargs) -> None:
        super(DS18B20Sensor, self).__init__(*args, **kwargs)

    def read(self) -> Optional[float]:
        """Read the temperature in celsius.

        Returns:
            Optional[float]: Temperature in celsius.
        """
        # the response time of this sensor is slow enough
        # that it doesn't really matter if we reopen the file
        # every time we poll it
        with open(self.device_filename) as fp:
            data = fp.read()
            if 'YES' in data:
                (_, sep, reading) = data.partition(' t=')
                temperature = float(reading) / 1000.0
                return temperature
            else:
                return None


class MultiOneWireSensor:
    """Manages multiple (high-latency) one-wire sensors.
    Uses a thread pool to read each sensor simultaenously, which
    is necessary for devices like the DS18B20.

    Notifier should define `on()` and `off()` methods.
    """
    def __init__(self, devices:  Sequence[OneWire],
                       executor: Optional[ThreadPoolExecutor] = None,
                       notifier: Optional[gpiozero.DigitalOutputDevice] = None):
        self.devices = devices
        if executor is None:
            self.executor = ThreadPoolExecutor(len(devices))
        else:
            self.executor = executor
        
        self.notifier = notifier

    @property
    def device_names(self) -> List[str]:
        return [d.device_name for d in self.devices]
    
    def read(self) -> List[Tuple[float, str, float]]:
        """Poll all devices by spawning futures for each one.

        Returns:
            List[Dict[str, Union[str,float,int,bytes]]]: The results.
        """
        futures = {}
        for device in self.devices:
            future = self.executor.submit(notifies(self.notifier)(device.read))
            futures[future] = device.device_name

        results = []
        for reading in as_completed(futures):
            item = (now(), futures[reading],  reading.result())
            results.append(item)

        return results

    async def reporter(self, readings: curio.Queue) -> None:
        print(f'Start polling one-wire sensors: {self.device_names}', file=sys.stderr)
        try:
            while True:
                results = await curio.run_in_thread(self.read)
                await readings.put(results)
        except:
            raise


class ADCManager:

    def __init__(self, devices:      Sequence[gpiozero.AnalogInputDevice],
                       device_names: Sequence[str],
                       block_length: float = 0.1,
                       max_qsize:    int = 10000):
        self.devices = devices
        self.device_names = device_names
        self.block_length = block_length
        self.output = curio.UniversalQueue(maxsize=max_qsize)
        self.running = False

    def worker(self) -> None:
        print(f'Start polling ADC\'s: {list(self.device_names)}', file=sys.stderr)
        block = []
        block_start = now()
        while self.running:
            for device, name in zip(self.devices, self.device_names):
                t = now()
                if t - block_start >= self.block_length:
                    self.output.put(list(block))
                    block = []
                    block_start = t
                block.append((t, name, device.value))
        if block:
            self.output.put(list(block))

    def start(self) -> None:
        self.task = threading.Thread(target=self.worker, daemon=True)
        self.running = True
        self.task.start()

    def stop(self) -> None:
        """Stop the polling thread. Will fail is the queue is full.
        """
        self.running = False
        try:
            self.task.join()
        except AttributeError:
            pass

    async def reporter(self, readings: curio.Queue) -> None:
        try:
            while True:
                block = await self.output.get()
                await readings.put(block)
        except:
            # TODO: handle errors or some such
            raise
