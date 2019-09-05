"""
Curio - Concurrent I/O

Copyright (C) 2015-2017
David Beazley (Dabeaz LLC)
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

* Redistributions of source code must retain the above copyright notice,
  this list of conditions and the following disclaimer.  
* Redistributions in binary form must reproduce the above copyright notice, 
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.  
* Neither the name of the David Beazley or Dabeaz LLC may be used to
  endorse or promote products derived from this software without
  specific prior written permission. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

"""A Curio websocket server.

pip install wsproto before running this.

"""

import sys

from curio import Queue, run, spawn, TaskGroup
from curio.socket import IPPROTO_TCP, TCP_NODELAY
from wsproto import WSConnection, ConnectionType
from wsproto.events import (AcceptConnection, CloseConnection,
                            Request, Message, TextMessage, BytesMessage)

DATA_TYPES = (TextMessage, BytesMessage)


async def process_incoming(wsconn, in_q, client):
    rsp = b''
    for event in wsconn.events():
        if isinstance(event, (TextMessage, BytesMessage)):
            await in_q.put(event.data)
        elif isinstance(event, Request):
            # Auto accept. Maybe consult the handler?
            rsp += wsconn.send(AcceptConnection())
            print('Accepted WebSocket connection from {0}.'.format(client.getpeername()),
                  file=sys.stderr)
        elif isinstance(event, CloseConnection):
            # The client has closed the connection.
            print('{0} closed WebSocket connection.'.format(client.getpeername()),
                  file=sys.stderr)
            await in_q.put(None)
            closed = True
        elif isinstance(event, Ping):
            rsp += wsconn.send(event.response())
        else:
            print('Unhandled event: {!r}'.format(event), file=sys.stderr)
    return rsp


async def ws_adapter(in_q, out_q, client, _):
    """A simple, queue-based Curio-Sans-IO websocket bridge."""
    client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    wsconn = WSConnection(ConnectionType.SERVER)
    closed = False


    # need to accept the request first
    auth = await client.recv(65535)
    wsconn.receive_data(auth)
    rsp = await process_incoming(wsconn, in_q, client)
    await client.sendall(rsp)

    while not closed:
        wstask = await spawn(client.recv, 65535)
        outqtask = await spawn(out_q.get)

        async with TaskGroup([wstask, outqtask]) as g:
            task = await g.next_done()
            result = await task.join()
            await g.cancel_remaining()

        if task is wstask:
            wsconn.receive_data(result)
            rsp = await process_incoming(wsconn, in_q, client)

            await client.sendall(rsp)
        else:
            # We got something from the out queue.
            if result is None:
                # Terminate the connection.
                print('Closing WebSocket connection from server:', client.getpeername(),
                      file=sys.stderr)
                wsconn.close()
                closed = True
            else:
                payload = wsconn.send(Message(data=result))
                await client.sendall(payload)
                await out_q.task_done()
    print("Bridge done.")


async def ws_echo_server(in_queue, out_queue):
    """Just echo websocket messages, reversed. Echo 3 times, then close."""
    for _ in range(3):
        msg = await in_queue.get()
        if msg is None:
            # The ws connection was closed.
            break
        await out_queue.put(msg[::-1])
    print("Handler done.")


def serve_ws(handler):
    """Start processing web socket messages using the given handler."""
    async def run_ws(client, addr):
        in_q, out_q = Queue(), Queue()
        ws_task = await spawn(ws_adapter, in_q, out_q, client, addr)
        await handler(in_q, out_q)
        await out_q.put(None)
        await ws_task.join()  # Wait until it's done.
        # Curio will close the socket for us after we drop off here.
        print("Master task done.")

    return run_ws


if __name__ == '__main__':
    from curio import tcp_server
    port = 5000
    print(f'Listening on port {port}.')
    run(tcp_server, '', port, serve_ws(ws_echo_server))
