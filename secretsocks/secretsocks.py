#!/usr/bin/env python
from __future__ import division, absolute_import, print_function, unicode_literals
import asyncore
import socket
import struct
import Queue
import threading

global DEBUG
DEBUG = False


class RemoteConnection():
    CONNECT = 1
    BIND = 2
    UDP_ASSOCIATE = 3

    def __init__(self):
        pass

    def new_conn(self, cmd, addr, port, io):
        t = threading.Thread(target=self.handle_con, args=(cmd, addr, port, io))
        t.daemon = True
        t.start()
        return True

    def handle_con(self, cmd, addr, port, io):
        if cmd != self.CONNECT:
            io.close()
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((addr, port))
        except:
            io.close()
        if DEBUG:
            print('Connection open', addr, port)
        s.settimeout(10)
        t1 = threading.Thread(target=self.read, args=(s, io))
        t1.daemon = True
        t1.start()
        t2 = threading.Thread(target=self.write, args=(s, io))
        t2.daemon = True
        t2.start()
        io.ready()
        t1.join()
        t2.join()
        self.cleanup(s, io)

    def read(self, s, io):
        while not io.closed:
            try:
                data = s.recv(4096)
                if data != b'':
                    io.write(data)
                else:
                    io.close()
            except socket.timeout:
                pass
            except socket.error:
                io.close()

    def write(self, s, io):
        while not io.closed:
            try:
                data = io.read()
                if data is not None:
                    s.sendall(data)
            except Queue.Empty:
                pass
            except socket.error:
                io.close()

    def cleanup(self, s, io):
        s.close()
        io.close()


class IO():
    def __init__(self):
        self.readq = Queue.Queue()
        self.writeq = Queue.Queue()
        self.closed = False
        self.remoteopen = threading.Event()

    def ready(self):
        self.remoteopen.set()

    def ready_wait(self):
        self.remoteopen.wait()

    def write(self, data):
        return self.readq.put(data)

    def read(self):
        return self.writeq.get(True, 1)

    def srvread(self):
        return self.readq.get(True, 1)

    def srvwrite(self, data):
        if self.closed:
            return None
        return self.writeq.put(data)

    def close(self):
        self.closed = True
        self.remoteopen.set()
        self.readq.put(None)
        self.writeq.put(None)


class SocksHandler(asyncore.dispatcher_with_send):
    def __init__(self, sock=None, addr=None, remote=None, map=None):
        asyncore.dispatcher_with_send.__init__(self, sock=sock, map=map)
        self.addr = addr
        self.remote = remote
        self.socks_init()
        t = threading.Thread(target=self.io_loop)
        t.daemon = True
        t.start()

    def io_loop(self):
        while not self.io.closed:
            try:
                data = self.io.srvread()
                if data != '':
                    self.send(data)
                else:
                    print('close')
                    self.io.close()
                    self.close()
            except Queue.Empty:
                pass
            except socket.error:
                self.io.close()
                self.close()


    def socks_init(self):
        self.socket.setblocking(True)
        # Client sends version and methods
        self.ver, = struct.unpack('!B', self.recv(1))
        if DEBUG:
            print('Version:', self.ver)
        if self.ver == 4:
            ret = self._socks4_init()
        elif self.ver == 5:
            ret = self._socks5_init()
        else:
            print('ERROR: Invalid socks version')
            self.close()
        if not ret:
            return None
        self.socket.setblocking(False)

    def _socks4_init(self):
        cd, dstport, a, b, c ,d = struct.unpack('!BHBBBB', self.recv(7))
        userid = ''
        data = struct.unpack('!B', self.recv(1))
        while data[0] != 0:
            userid += chr(data[0])
            data = struct.unpack('!B', self.recv(1))

        dstaddr = ''
        # sock4a
        if a + b + c == 0 and d > 0:
            data = struct.unpack('!B', self.recv(1))
            while data[0] != 0:
                dstaddr += chr(data[0])
                data = struct.unpack('!B', self.recv(1))
        # normal socks4
        else:
            dstaddr = "{}.{}.{}.{}".format(a, b, c, d)

        self.io = IO()
        ret = self.remote.new_conn(cd, dstaddr, dstport, self.io)
        self.io.ready_wait()
        if self.io.closed:
            self.send(struct.pack('!BBHI', 0x00, 0x5B, 0x0000, 0x00000000))
            return False
        self.send(struct.pack('!BBHI', 0x00, 0x5A, 0x0000, 0x00000000))
        return True

    def _socks5_init(self):
        # Get list of auth methods
        methods, = struct.unpack('!B', self.recv(1))
        mlist = []
        for i in range(0, methods):
            test = self.recv(1)
            if test == 0x00:
                print('wat')
            val, = struct.unpack('!B', test)
            mlist.append(val)
        # Always use no auth
        if 0 in mlist:
            if DEBUG:
                print('Using no auth', mlist)
            self.send(struct.pack('!BB', self.ver, 0x00))
        else:
            print('No valid auth method', mlist)
            self.send(struct.pack('!BB', self.ver, 0xFF))
            self.close()

        # Get the request
        ver, cmd, rsv, atyp = struct.unpack('!BBBB', self.recv(4))
        print(ver, cmd, rsv, atyp)
        dstaddr = None
        if atyp == 1:
            a, b, c, d = struct.unpack('!BBBB', self.recv(4))
            dstaddr = "{}.{}.{}.{}".format(a, b, c, d)
            print(dstaddr)
        # , dstport = 0

    def handle_read(self):
        self.io.srvwrite(self.recv(4098))


class SocksServer(asyncore.dispatcher):
    host = '127.0.0.1'
    port = 1080
    handler = SocksHandler
    remote = RemoteConnection()

    def __init__(self, host=None, port=None, remote=None, handler=None):
        asyncore.dispatcher.__init__(self)
        if host is not None:
            self.host = host
        if port is not None:
            self.port = port
        if remote is not None:
            self.remote = remote
        if handler is not None:
            self.handler = handler
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((self.host, self.port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            handle = self.handler(sock, addr, self.remote)

if __name__ == '__main__':
    DEBUG = True
    print('Starting server...')
    server = SocksServer()
    asyncore.loop()
