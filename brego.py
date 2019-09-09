#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) Camille Scott, 2019
# File   : brego.py
# License: MIT
# Author : Camille Scott <camille.scott.w@gmail.com>
# Date   : 03.09.2019

import argparse

from brego import http
from brego import server


DEFAULT_SOCKET = '/tmp/brego.sock'


def main():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=lambda args: parser.print_help())
    subparsers = parser.add_subparsers(title='commands')

    sensors_subparser = subparsers.add_parser('sensors')
    sensors_subparser.set_defaults(func=server.run)
    sensors_subparser.add_argument('--broadcast-socket', default=DEFAULT_SOCKET)
    sensors_subparser.add_argument('--websocket-host', default='')
    sensors_subparser.add_argument('--websocket-port', default=6565)

    http_subparser = subparsers.add_parser('http')
    http_subparser.set_defaults(func=http.run)
    http_subparser.add_argument('--sensors-socket', default=DEFAULT_SOCKET)
    http_subparser.add_argument('--host', default='127.0.0.1')
    http_subparser.add_argument('-port', default=8080)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
