from __future__ import division, absolute_import, print_function, unicode_literals
import threading
import struct
import socket
import sys
DEBUG = False
PY3 = False
if sys.version_info[0] == 3:
    import queue as Queue
    PY3 = True
else:
    import Queue
    range = xrange


class Server():
    def __init__(self):
        self.recvbuf = Queue.Queue()
        self.writebuf = Queue.Queue()
        self._conns = [254]
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

    def _dataparse(self):
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
            if len(data) < 2:
                needmore = True
                continue
            id, = struct.unpack('<H', data[:2])
            # ID 0 is to close a con
            # TODO: extend this to be a command channel for opening and closing cons
            if id == 0:
                id, = struct.unpack('<H', data[2:4])
                if DEBUG:
                    print('Server requested to close', id)
                if self._id_check(id):
                    self._close_id(id)
                data = data[4:]
            # If we dont have that conn ID open
            elif not self._id_check(id):
                cmd, = struct.unpack('<B', data[2:3])
                # Connect Request
                if cmd == 1:
                    if DEBUG:
                        print('Server requested to open', id)
                    port, = struct.unpack('<H', data[3:5])
                    addr = ""
                    i = 5
                    c, = struct.unpack('<c', data[i:i+1])
                    while c != b'\x00':
                        c = c.decode('utf8')
                        addr += c
                        i += 1
                        c, = struct.unpack('<c', data[i:i+1])
                    # Open Socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        print(addr, port)
                        s.connect((addr, port))
                        s.settimeout(10)
                    except Exception as e:
                        if DEBUG:
                            print(e)
                        s.close()
                        s = None
                        self._close_id(id)
                    if s is not None:
                        self._conns[id] = s
                        t = threading.Thread(target=self._recv_loop, args=(id,))
                        t.daemon = True
                        t.start()
                    data = data[i+1:]
                # Invalid commands are most likely a size for a close connection
                else:
                    if DEBUG:
                        print('Garbage data received', id)
                    if len(data) >= cmd+4:
                        data = data[cmd+4:]
                    else:
                        needmore = True
            # Else we send the data
            else:
                tosend = False
                size, = struct.unpack('<H', data[2:4])
                datasize = len(data[4:])
                if DEBUG:
                    print('Server c->s:', id, size, datasize)
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
                        self._conns[id].sendall(tosend)
                        if DEBUG:
                            print('Server s->out:', id, len(tosend))
                    except:
                        self._close_id(id)

    def _recv_loop(self, id):
        while self._conns[id] is not None:
            try:
                data = self._conns[id].recv(65535)
                size = len(data)
                if data == b'':
                    raise socket.error
                else:
                    if self._conns[id] is not None:
                        self.writebuf.put(struct.pack('<HH', id, size) + data)
                        if DEBUG:
                            print('Server s->c:', id, len(data))
            except socket.timeout:
                pass
            except socket.error:
                self._close_id(id)

    def _close_id(self, id):
        if DEBUG:
            print('Server close id', id)
        if self._conns[id] is not None:
            self._conns[id].close()
            self._conns[id] = None
        resp = struct.pack('<HH', 0x00, id)
        self.writebuf.put(resp)

    def _id_check(self, id):
        if id - self._conns[0] > 0:
            self._conns.extend([None] * (id - self._conns[0]))
            self._conns[0] = id
            return False
        else:
            if self._conns[id] is None:
                return False
            else:
                return True

# This allows this file to be executed by a remote python interpreter to initialise the class before the custom server
# class is sent.
if __name__ == '__main__':
    class secretsocks(object):
        Server = Server
