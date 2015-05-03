# PySecretSocks #
A python SOCKS server for tunneling connections over another channel. Making implementing covert channels a breeze!

## Terminology ##
- **Listener** - The listener is the class that listens on a local port and sends incoming connections to the handler.
- **Handler** - The handler processes the proxy requests, normally via socks 4a/5, and extracts the connection request to pass to the Client.
- **Client** - The client sends and receives data to the server via your custom communication channel.
- **Server** - The server communicates with the client via your created channel and initiates the outbound connections.

## Using the library ##
For a real simple implementation see [example.py](example.py)

### Client/Server ###
At a minimum you will need to create a Client and Server class for your communication channel. Both classes have a recv and write function you will need to override from the base class. Note that at runtime these will be run in separate threads.
- **recv()** - This function reads data from the communication channel and should put the raw data in the *self.revbuf* queue.
- **write()** - This function writes data from the *self.writebuf* queue to the communication channel.

You also are required to write an \__init__() function to initialize your communication channel in both classes. At the end you need to call self.start() to start the threads. The return of start() is the handle to the recv() thread.

#### Considerations ####
When defining your custom communication channel there are some things you should be aware of. 
- It is assumed that your communication channel will send messages in a first in first out fashion and that they will arrive in order as well.
- You can combine multiple messages from the write queue before you send them over the communication channel.
- Data from the write queue can be split into parts if the size becomes to large to send in one transmission.
- The max size of something popped of the write queue will be 65539 bytes. 65535 bytes is the max size we will read off the local socket and there is a 4 byte overhead for each chunk of data received.

### Listener ###
The listener class has 4 arguments that it can take with only the client being required.
- **client** - This is an initialized client object.
- **host=None** - This is the IP to listen on. When host is None it will use 127.0.0.1
- **port=None** - This is the port to listen on. When port is None it will use 1080
- **handler=None** - This is an initialized handler object. When handler is None it will use SocksHandler which supports SOCKS 4a/5.

## Handler ##
Custom handlers can be created if the SocksHandler or OneToOneHandler do not work for you. Handler classes need only have one function, new_request.

new_request(self, sock, addr, client)
- **sock** - This is a python socket object for the connection for you to process.
- **addr** - This is the address bound to the socket on the other end of the connection.
- **client** - This is the initialized client object.

In new_request you will pull out whatever information you need in order to call client.new_conn which is described below.

client.new_conn(cmd, addr, port, s)
- **cmd** - This is the command for the connection. Accepted values are 1 to establish a TCP/IP stream connection (Connect), 2 to establish a TCP/IP port binding (Bind), and 3 to associate a UDP port (UDP Associate).
  - *NOTE:* Currently only connect requests are supported by client/servers.
- **addr** - The IP or hostname to connect to.
- **port** - The port to connect to.
- **s** - The socket object which is ready to being sending/receiving data.

## Current State ##
Works! Just needs more polishing and a few features

### Features ###
- [x] Socks4a
- [ ] Socks5 - In progress
- [x] Remote Class Communication
 - 95% happy with it, just needs some bug fixes
- [x] 1-1 mode
- [ ] Linux transparent proxy support

### Bugs ###
- There is a slight delay in the client's connection being close from when the servers is closed.
