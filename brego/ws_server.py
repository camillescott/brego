"""A simple curio websocket server. Based on the old example by
David Beazley, but updated for the modern wsproto API. This
also (more or less) properly handles incoming connection
requests; the original would crash if the handler managed
to get an outgoing message on the queue before processing
the connection Request and accepting it.

Adapted by Camille Scott (@camillescott), 2019.

Requires wsproto:
    pip install wsproto

"""

import sys
from typing import Tuple, Callable, Awaitable

import curio
import wsproto

from curio import Queue, run, spawn, TaskGroup
from curio.socket import IPPROTO_TCP, TCP_NODELAY
from wsproto import WSConnection, ConnectionType
from wsproto.events import (AcceptConnection, CloseConnection,
                            Request, Message, TextMessage, BytesMessage)


async def process_incoming(wsconn: wsproto.WSConnection,
                           in_q:   curio.Queue, 
                           client: curio.io.Socket) -> Tuple[bool, bytes]:

    """Process incoming messages: pass text messages on to the handler's
    incoming queue, and handle acceptance and closing.

    Args:
        wsconn (wsproto.WSConnection): Active WebSocket connection
        in_q (curio.Queue): Queue of incoming messages hooked up to the handler
        client (curio.Socket): The client socket

    Returns:
        Tuple[bool, bytes]: Connection closed status and server response.
    """

    rsp = b''
    closed = False
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
    return closed, rsp


async def ws_adapter(in_q: curio.Queue,
                     out_q: curio.Queue,
                     client: curio.io.Socket, _):

    """A queue-based WebSocket bridge. Sits between a
    a `curio.tcp_server` and a user-defined handler; the handler
    should accept an ingoing and outgoing queue which will be loaded
    by the adapter.

    Args:
        in_q (curio.Queue): Queue for incoming messages.
        out_q (curio.Queue): Queue for outgoing messages.
        client (curio.Socket): The client socket.
        _: dummy

    Returns:
    """
    client.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
    wsconn = WSConnection(ConnectionType.SERVER)
    closed = False


    # need to accept the request first
    auth = await client.recv(65535)
    wsconn.receive_data(auth)
    closed, rsp = await process_incoming(wsconn, in_q, client)
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
            closed, rsp = await process_incoming(wsconn, in_q, client)

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


async def ws_echo_server(in_queue: curio.Queue,
                         out_queue: curio.Queue) -> None:
    """Example handler: echoes messages, reversed.

    Args:
        in_queue (curio.Queue):
        out_queue (curio.Queue):

    Returns:
    """
    for _ in range(3):
        # note: if you want your handler to push a continuous
        # outgoing stream, you should check that the in_queue
        # has messages before awaiting it, otherwise it will
        # hang and never push out your data.
        msg = await in_queue.get()
        if msg is None:
            # The ws connection was closed.
            break
        await out_queue.put(msg[::-1])


# Some "typedefs." Starting to wonder if this is a good idea for python...
HandlerType = Callable[[curio.Queue, curio.Queue], Awaitable[None]]
RunnerType  = Callable[[curio.io.Socket, Tuple[str, int]], Awaitable[None]]

def serve_ws(handler: HandlerType) -> RunnerType:
    """Build the WebSocket runner with the user-supplied handler.

    Args:
        handler (HandlerType): The handler coroutine that juggles the incoming
                               that juggles the incoming and outgoing data queues.

    Returns:
        RunnerType: The runner coroutine.
    """
    async def run_ws(client: curio.io.Socket, addr: Tuple[str, int]) -> None:
        in_q, out_q = Queue(), Queue()
        ws_task = await spawn(ws_adapter, in_q, out_q, client, addr)
        await handler(in_q, out_q)
        await out_q.put(None)
        await ws_task.join()  # Wait until it's done.
        # Curio will close the socket for us after we drop off here.

    return run_ws


if __name__ == '__main__':
    from curio import tcp_server
    port = 5000
    print(f'Listening on port {port}.', file=sys.stderr)
    run(tcp_server, '', port, serve_ws(ws_echo_server))
