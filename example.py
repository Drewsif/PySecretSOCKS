#!/usr/bin/env python
from __future__ import division, absolute_import, print_function, unicode_literals
import secretsocks
import socket
import threading
import sys
PY3	= False
if sys.version_info[0] == 3:
    import queue as Queue
    PY3 = True
else:
    import Queue
    range = xrange

class Client(secretsocks.Client):
    def __init__(self, ip, port):
        secretsocks.Client.__init__(self)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
        s.settimeout(2)
        self.conn = s
        self.alive = True
        self.start()

    def recv(self):
        while self.alive:
            try:
                data = self.conn.recv(4092)
                self.recvbuf.put(data)
            except socket.timeout:
                continue
            except:
                self.alive = False
                self.conn.close()

    def write(self):
        while self.alive:
            try:
                data = self.writebuf.get(timeout=10)
            except Queue.Empty:
                continue
            self.conn.sendall(data)


class Server(secretsocks.Server):
    def __init__(self, ip, port):
        secretsocks.Server.__init__(self)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((ip, port))
        s.listen(1)
        self.conn, nill = s.accept()
        self.conn.settimeout(2)
        self.alive = True
        self.start()

    def recv(self):
        while self.alive:
            try:
                data = self.conn.recv(4092)
                self.recvbuf.put(data)
            except socket.timeout:
                continue
            except:
                self.alive = False
                self.conn.close()

    def write(self):
        while self.alive:
            try:
                data = self.writebuf.get(timeout=10)
            except Queue.Empty:
                continue
            self.conn.sendall(data)


def start_fake_remote():
    Server('127.0.0.1', 8080)

if __name__ == '__main__':
    secretsocks.DEBUG = True
    print('Starting the fake remote server...')
    t = threading.Thread(target=start_fake_remote)
    t.daemon = True
    t.start()
    print('Creating a the client...')
    client = Client('127.0.0.1', 8080)
    print('Starting socks server...')
    server = secretsocks.SocksServer(client, host='127.0.0.1', port=1080)
    server.wait()
