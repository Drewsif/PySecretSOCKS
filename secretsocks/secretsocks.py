from __future__ import division, absolute_import, print_function, unicode_literals
import asyncore
import socket
import struct
import threading
import sys
from collections import deque
DEBUG = False
PY3 = False
if sys.version_info[0] == 3:
    import queue as Queue
    PY3 = True
else:
    import Queue
    range = xrange


class Client():
    CONNECT = 1
    BIND = 2
    UDP_ASSOCIATE = 3

    def __init__(self):
        self.recvbuf = Queue.Queue()
        self.writebuf = Queue.Queue()
        # Hard coding this is bad and I feel bad
        self._conns = [deque(range(1, 2048))]
        self._conns.extend([None]*2048)

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
            print('Client new conn:', id, cmd, addr, port)
        s.settimeout(10)
        self._conns[id] = s
        if PY3:
            addr = bytes(addr, 'utf8')
        else:
            addr = str(addr)
        msg = struct.pack('<HBH'+str(len(addr))+'sB', id, cmd, port, addr, 0x00)
        self.writebuf.put(msg)
        t = threading.Thread(target=self._recv_loop, args=(id,))
        t.daemon = True
        t.start()

    def _recv_loop(self, id):
        while self._conns[id] is not None:
            try:
                data = self._conns[id].recv(65535)
                size = len(data)
                if data == b'':
                    raise socket.error
                else:
                    if self._conns[id] is not None:
                        if DEBUG:
                            print('Client c->s:', id, size)
                        self.writebuf.put(struct.pack('<HH', id, size) + data)
            except socket.timeout:
                pass
            except socket.error:
                self._close_id(id)

    def _close_id(self, id):
        if DEBUG:
            print('Client closing id', id)
        if self._conns[id] is not None:
            self._conns[id].close()
            self._conns[id] = None
        resp = struct.pack('<HH', 0x00, id)
        self.writebuf.put(resp)
        self._conns[0].appendleft(id)

    def _dataparse(self, get=True):
        data = b''
        needmore = False
        while True:
            if not data or needmore:
                data += self.recvbuf.get()
                needmore = False
            else:
                try:
                    data += self.recvbuf.get_nowait()
                except:
                    pass

            # Make sure we at least have the header
            if len(data) < 4:
                needmore = True
                continue

            id, = struct.unpack('<H', data[:2])
            # ID 0 is to close a con
            if id == 0:
                id, = struct.unpack('<H', data[2:4])
                if self._id_check(id):
                    self._close_id(id)
                data = data[4:]
            # If we dont have that conn ID, tell the server its closed
            elif not self._id_check(id):
                resp = struct.pack('<HH', 0x00, id)
                size, = struct.unpack('<H', data[2:4])
                if DEBUG:
                    print('Client invalid id request', id)
                self.writebuf.put(resp)
                # TODO: Need to add support for if size>msg
                data = data[4+size:]
            # Else write the data
            else:
                tosend = False
                size, = struct.unpack('<H', data[2:4])
                datasize = len(data[4:])
                if DEBUG:
                    print('Client s->c:', id, size, datasize)
                if datasize == size:
                    tosend = data[4:]
                    data = b''
                elif datasize > size:
                    tosend = data[4:size+4]
                    data = data[size+4:]
                elif datasize < size:
                    needmore = True

                if tosend:
                    try:
                        if DEBUG:
                            print('Client c->out:', id, len(tosend))
                        self._conns[id].sendall(tosend)
                    except:
                        self._close_id(id)

    def _id_check(self, id):
        # TODO: Make this better
        try:
            return self._conns[id] is not None
        except:
            return False


class SocksHandler():
    def __init__(self):
        pass

    def new_request(self, sock, addr, client):
        # Client sends version and methods
        sock.setblocking(True)
        data = sock.recv(1)
        if not data:
            return None
        ver, = struct.unpack('!B', data)
        if DEBUG:
            print('Version:', ver)
        if ver == 4:
            ret = self._socks4_init(sock, client)
        elif ver == 5:
            ret = self._socks5_init(sock, client)
        else:
            if DEBUG:
                print('ERROR: Invalid socks version')
            sock.close()
        if not ret:
            return None

    def _socks4_init(self, sock, client):
        cmd, dstport, a, b, c ,d = struct.unpack('!BHBBBB', sock.recv(7))
        userid = ''
        data = struct.unpack('!B', sock.recv(1))
        while data[0] != 0:
            userid += chr(data[0])
            data = struct.unpack('!B', sock.recv(1))

        dstaddr = ''
        # sock4a
        if a + b + c == 0 and d > 0:
            data = struct.unpack('!B', sock.recv(1))
            while data[0] != 0:
                dstaddr += chr(data[0])
                data = struct.unpack('!B', sock.recv(1))
        # normal socks4
        else:
            dstaddr = "{}.{}.{}.{}".format(a, b, c, d)

        ret = client.new_conn(cmd, dstaddr, dstport, sock)
        sock.sendall(struct.pack('!BBHI', 0x00, 0x5A, 0x0000, 0x00000000))
        return ret

    def _socks5_init(self, sock, client):
        # Get list of auth methods
        methods, = struct.unpack('!B', sock.recv(1))
        mlist = []
        for i in range(0, methods):
            test = sock.recv(1)
            val, = struct.unpack('!B', test)
            mlist.append(val)
        # Always use no auth
        if 0 in mlist:
            sock.send(struct.pack('!BB', 0x05, 0x00))
        else:
            print('No valid auth method', mlist)
            sock.send(struct.pack('!BB', 0x05, 0xFF))
            sock.close()

        # Get the request
        ver, cmd, rsv, atyp = struct.unpack('!BBBB', sock.recv(4))
        dstaddr = None
        dstport = None
        if atyp == 1:
            a, b, c, d, dstport = struct.unpack('!BBBBH', sock.recv(6))
            dstaddr = "{}.{}.{}.{}".format(a, b, c, d)
        elif atyp == 3:
            size, = struct.unpack('!B', sock.recv(1))
            dstaddr = sock.recv(size)
            if type(dstaddr) == bytes:
                dstaddr = dstaddr.decode('utf8')
            dstport, = struct.unpack('!H', sock.recv(2))
        #TODO: ipv6 addr support
        #elif atyp = 4:
        else:
            print('Unknown address type', atyp)
            sock.send(struct.pack('!BB', 0x05, 0xFF))
            sock.close()
        ret = client.new_conn(cmd, dstaddr, dstport, sock)
        sock.sendall(struct.pack('!BBBBHI', 0x05, 0x00, 0x00, 0x01, 0x00000000, 0x0000))
        return ret


class OneToOneHandler():
    def __init__(self, addr, port):
        self.addr = addr
        self.port = port

    def new_request(self, sock, addr, client):
        ret = client.new_conn(1, self.addr, self.port, sock)
        return ret


class Listener(asyncore.dispatcher):
    host = '127.0.0.1'
    port = 1080
    handler = SocksHandler()

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
            handle = self.handler.new_request(sock, addr, self.client)

    def wait(self):
        asyncore.loop()
