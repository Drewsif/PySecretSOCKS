from __future__ import division, absolute_import, print_function, unicode_literals
import asyncore
import socket
import struct
import threading
from collections import deque
try:
    import Queue
except:
    import queue as Queue
try:
    range = xrange
except:
    pass
DEBUG = False


class Client():
    CONNECT = 1
    BIND = 2
    UDP_ASSOCIATE = 3

    def __init__(self):
        self.recvbuf = Queue.Queue()
        self.writebuf = Queue.Queue()
        self._conns = [deque(range(1,255))]
        self._conns.extend([None]*254)

    def recv(self):
        raise NotImplementedError

    def write(self):
        raise NotImplementedError

    def start(self):
        t = threading.Thread(target=self.write)
        t.daemon = True
        t.start()
        t = threading.Thread(target=self._dataparse)
        t.daemon = True
        t.start()
        t = threading.Thread(target=self.recv)
        t.daemon = True
        t.start()
        return t

    def new_conn(self, cmd, addr, port, s):
        id = self._conns[0].pop()
        if DEBUG:
            print('New conn:', id)
        s.settimeout(10)
        self._conns[id] = s
        msg = struct.pack('<HBH'+str(len(addr))+'sB', id, cmd, port, str(addr), 0x00)
        self.writebuf.put(msg)
        t = threading.Thread(target=self._recv_loop, args=(id,))
        t.daemon = True
        t.start()

    def _recv_loop(self, id):
        while self._conns[id] is not None:
            try:
                data = self._conns[id].recv(4092)
                if data == b'':
                    raise socket.error
                else:
                    self.writebuf.put(struct.pack('<H', id) + data)
            except socket.timeout:
                pass
            except socket.error:
                self._close_id(id)

    def _close_id(self, id):
        if self._conns[id] is not None:
            self._conns[id].close()
            self._conns[id] = None
        resp = struct.pack('<HH', 0x00, id)
        self.writebuf.put(resp)
        self._conns[0].appendleft(id)

    def _dataparse(self):
        while True:
            data = self.recvbuf.get()
            id, = struct.unpack('<H', data[:2])
            # ID 0 is to close a con
            if id == 0:
                id, = struct.unpack('<H', data[2:4])
                if self._id_check(id):
                    self._close_id(id)
            # If we dont have that conn ID, tell the server its closed
            elif not self._id_check(id):
                resp = struct.pack('<HH', 0x00, id)
                self.writebuf.put(resp)
            # Else write the data
            else:
                try:
                    self._conns[id].sendall(data[2:])
                except:
                    self._close_id(id)

    def _id_check(self, id):
        # TODO: Make this better
        try:
            return self._conns[id] is not None
        except:
            print('Invalid ID:', id)
            return False

# TODO: This does not need to be an asyncore class
class SocksHandler():
    def __init__(self, sock, addr, client):
        self.conn = sock
        self.conn.setblocking(True)
        self.addr = addr
        self.client = client
        self.socks_init()

    def socks_init(self):
        # Client sends version and methods
        self.ver, = struct.unpack('!B', self.conn.recv(1))
        if DEBUG:
            print('Version:', self.ver)
        if self.ver == 4:
            ret = self._socks4_init()
        elif self.ver == 5:
            ret = self._socks5_init()
        else:
            print('ERROR: Invalid socks version')
            self.conn.close()
        if not ret:
            return None

    def _socks4_init(self):
        cd, dstport, a, b, c ,d = struct.unpack('!BHBBBB', self.conn.recv(7))
        userid = ''
        data = struct.unpack('!B', self.conn.recv(1))
        while data[0] != 0:
            userid += chr(data[0])
            data = struct.unpack('!B', self.conn.recv(1))

        dstaddr = ''
        # sock4a
        if a + b + c == 0 and d > 0:
            data = struct.unpack('!B', self.conn.recv(1))
            while data[0] != 0:
                dstaddr += chr(data[0])
                data = struct.unpack('!B', self.conn.recv(1))
        # normal socks4
        else:
            dstaddr = "{}.{}.{}.{}".format(a, b, c, d)


        ret = self.client.new_conn(cd, dstaddr, dstport, self.conn)
        self.conn.sendall(struct.pack('!BBHI', 0x00, 0x5A, 0x0000, 0x00000000))
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
        pass


class SocksServer(asyncore.dispatcher):
    host = '127.0.0.1'
    port = 1080
    handler = SocksHandler

    def __init__(self, client, host=None, port=None, handler=None):
        asyncore.dispatcher.__init__(self)
        if host is not None:
            self.host = host
        if port is not None:
            self.port = port
        if handler is not None:
            self.handler = handler
        self.client = client
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((self.host, self.port))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            handle = self.handler(sock, addr, self.client)

    def wait(self):
        asyncore.loop()