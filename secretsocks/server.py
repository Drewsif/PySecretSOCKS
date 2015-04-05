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
        while True:
            data = self.recvbuf.get()
            id, = struct.unpack('<H', data[:2])
            # ID 0 is to close a con
            if id == 0:
                id, = struct.unpack('<H', data[2:4])
                if self._id_check(id):
                    self._close_id(id)
            # If we dont have that conn ID open
            elif not self._id_check(id):
                cmd, = struct.unpack('<B', data[2:3])
                # Connect Request
                if cmd == 1:
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
                        s.connect((addr, port))
                        s.settimeout(10)
                    except:
                        s.close()
                        s = None
                        self._close_id(id)
                    if s is not None:
                        self._conns[id] = s
                        t = threading.Thread(target=self._recv_loop, args=(id,))
                        t.daemon = True
                        t.start()
            # Else we send the data
            else:
                try:
                    self._conns[id].sendall(data[2:])
                except:
                    self._close_id(id)

    def _recv_loop(self, id):
        while self._conns[id] is not None:
            try:
                data = self._conns[id].recv(2048)
                if data == b'':
                    raise socket.error
                else:
                    print(len(data))
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