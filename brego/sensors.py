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
from typing import Optional, Iterable, List, Dict, Union, Any, Sequence

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
    
    def read(self) -> List[Dict[str, Union[str, float, int, bytes]]]:
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
            item = (futures[reading], {'time': now(), 'value': reading.result()})
            results.append(item)

        return results

