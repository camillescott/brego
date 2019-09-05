#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : utils.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 02.09.2019

import datetime
import time


def notifies(notifier):
    def notify_wrapper(func):
        def _wrapped(*args, **kwargs):
            if notifier is not None:
                notifier.on()
            result = func(*args, **kwargs)
            if notifier is not None:
                notifier.off()
            return result
        return _wrapped
    return notify_wrapper


def now():
    return time.time()
    #return datetime.datetime.now().isoformat()
