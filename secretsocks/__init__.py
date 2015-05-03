from .server import *
from .secretsocks import *
from . import server
from . import secretsocks


def set_debug(bool):
    server.DEBUG = bool
    secretsocks.DEBUG = bool
