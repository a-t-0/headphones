from . import Adapter
from ..makefile import StreamReader, StreamWriter
from OpenSSL import SSL
from typing import Any

ssl_conn_type: SSL.Connection

class SSLFileobjectMixin:
    ssl_timeout: int
    ssl_retry: float
    def recv(self, size): ...
    def readline(self, size: int = ...): ...
    def sendall(self, *args, **kwargs): ...
    def send(self, *args, **kwargs): ...

class SSLFileobjectStreamReader(
    SSLFileobjectMixin, StreamReader
): ...  # type:ignore
class SSLFileobjectStreamWriter(
    SSLFileobjectMixin, StreamWriter
): ...  # type:ignore

class SSLConnectionProxyMeta:
    def __new__(mcl, name, bases, nmspc): ...

class SSLConnection:
    def __init__(self, *args) -> None: ...

class pyOpenSSLAdapter(Adapter):
    def __init__(
        self,
        certificate,
        private_key,
        certificate_chain: Any | None = ...,
        ciphers: Any | None = ...,
    ) -> None: ...
    def bind(self, sock): ...
    def wrap(self, sock): ...
    def get_environ(self): ...
    def makefile(self, sock, mode: str = ..., bufsize: int = ...): ...
