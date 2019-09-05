#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : database.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 03.09.2019

import dataset

import datetime
import sys

from .utils import now


class SensorDB:

    active_dbs = {}
    
    def __init__(self, dbpath='sqlite:///data/sensors.db'):
        self.db = dataset.connect(dbpath)

        self.devices_table = self.db.create_table('devices', primary_id='device_id')
        self.sessions_table = self.db.create_table('sessions', primary_id='session_id')

        self.known_devices = {}
        for device in self.devices_table.all():
            self.known_devices[device['device_name']] = device['device_id']
        self.print_devices()
        
        self.session = None
        self.start_session()

    def print_devices(self):
        print('Registered Devices:', file=sys.stderr)
        for device in self.devices_table.all():
            print('\t- {device_name} id={device_id} type={device_type}'.format(**device))
    
    def __del__(self):
        self.end_session()
        
    def _check_session(self):
        if self.session is None:
            raise RuntimeError('No active session.')
    
    def start_session(self):
        if self.session is not None:
            self.end_session()
        
        self.session = self.sessions_table.insert({'start': now(), 'end': None})
        return self.session
    
    def end_session(self):
        if self.session is None:
            return
        self.sessions_table.update({'session_id': self.session, 'end': now()}, ['session_id'])
        self.session = None

    def add_device(self, device_name, device_type):
        if device_name in self.known_devices:
            return

        did = self.devices_table.insert_ignore(dict(device_name=device_name,
                                                    device_type=device_type),
                                               ['device_name'])
        self.known_devices[device_name] = did
        print('Registered {0}, id={1}'.format(device_name, did), file=sys.stderr)
    
    def insert_readings(self, device_name, readings):
        self._check_session()
        
        if 'time' not in readings[0]:
            raise ValueError('Sensor readings must have `time` field.')
        
        if device_name not in self.known_devices:
            raise ValueError('Device {0} not registered.'.format(device_name))
        table = self.db.create_table(device_name, primary_id=False)
        
        for item in readings:
            item['session_id'] = self.session
        table.insert_many(readings, ensure=True)
    
    def query_session_readings(self, device_name):
        self._check_session()
        
        table = self.db.load_table(device_name)
        return table.find(session_id = self.session, order_by='time')

    @staticmethod
    def request_instance(dbpath='sqlite:///data/sensors.db'):
        if dbpath in SensorDB.active_dbs:
            return SensorDB.active_dbs[dbpath]
        else:
            db = SensorDB(dbpath)
            SensorDB.active_dbs[dbpath] = db
            return db
