#!/usr/bin/env python
from __future__ import division, absolute_import, print_function, unicode_literals
import secretsocks
import socket
import threading
import sys
PY3 = False
if sys.version_info[0] == 3:
    import queue as Queue
    PY3 = True
else:
    import Queue
    range = xrange


# The client class which connects out to a server over TCP/IP
class Client(secretsocks.Client):
    # Initialize our data channel
    def __init__(self, ip, port):
        secretsocks.Client.__init__(self)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.settimeout(2)
        self.data_channel = s
        self.alive = True
        self.start()

    # Receive data from our data channel and push it to the receive queue
    def recv(self):
        while self.alive:
            try:
                data = self.data_channel.recv(4092)
                self.recvbuf.put(data)
            except socket.timeout:
                continue
            except:
                self.alive = False
                self.data_channel.close()

    # Take data from the write queue and send it over our data channel
    def write(self):
        while self.alive:
            try:
                data = self.writebuf.get(timeout=10)
            except Queue.Empty:
                continue
            self.data_channel.sendall(data)


class Server(secretsocks.Server):
    # Initialize our data channel
    def __init__(self, ip, port):
        secretsocks.Server.__init__(self)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((ip, port))
        s.listen(1)
        self.data_channel, nill = s.accept()
        self.data_channel.settimeout(2)
        self.alive = True
        self.start()

    # Receive data from our data channel and push it to the receive queue
    def recv(self):
        while self.alive:
            try:
                data = self.data_channel.recv(4092)
                self.recvbuf.put(data)
            except socket.timeout:
                continue
            except:
                self.alive = False
                self.data_channel.close()

    # Take data from the write queue and send it over our data channel
    def write(self):
        while self.alive:
            try:
                data = self.writebuf.get(timeout=10)
            except Queue.Empty:
                continue
            self.data_channel.sendall(data)


def start_fake_remote():
    Server('127.0.0.1', 8080)

if __name__ == '__main__':
    # Set secretsocks into debug mode
    secretsocks.set_debug(True)

    # Create a server object in its own thread
    print('Starting the fake remote server...')
    t = threading.Thread(target=start_fake_remote)
    t.daemon = True
    t.start()

    # Create the client object
    print('Creating a the client...')
    client = Client('127.0.0.1', 8080)

    # Start the standard listener with our client
    print('Starting socks server...')
    listener = secretsocks.Listener(client, host='127.0.0.1', port=1080)
    listener.wait()
