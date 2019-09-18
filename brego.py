#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : brego.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 03.09.2019

import argparse

from brego import httpserver
from brego import gpioserver


def main():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=lambda args: parser.print_help())
    subparsers = parser.add_subparsers(title='commands')

    sensors_subparser = subparsers.add_parser('sensors')
    sensors_subparser.set_defaults(func=gpioserver.run)
    sensors_subparser.add_argument('--broadcast-socket', default=gpioserver.DEFAULT_SOCKET)
    sensors_subparser.add_argument('--report-status', action='store_true', default=False)
    sensors_subparser.add_argument('--write-results', action='store_true', default=False)

    http_subparser = subparsers.add_parser('http')
    http_subparser.set_defaults(func=httpserver.run)
    http_subparser.add_argument('--sensors-socket', default=gpioserver.DEFAULT_SOCKET)
    http_subparser.add_argument('--host', default='127.0.0.1')
    http_subparser.add_argument('-port', default=8080)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
