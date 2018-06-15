"""
WSGI Server 和 Web Framework
异步就是我发出请求时候不管完成没完成都要返回，所以不在乎结果。
阻塞就是调用结果没返回之前我会挂起当前线程，一直在等。
非阻塞就不会挂起，因为Tornado会想办法让自己避免被挂起
"""

import sys
import time
import socket
import collections
import selectors
import logging
from datetime import datetime
from io import StringIO


class IOLoop:
    _EPOLLIN = 0x001
    _EPOLLOUT = 0x004
    _EPOLLERR = 0x008
    _EPOLLHUP = 0x010

    READ = _EPOLLIN
    WRITE = _EPOLLOUT
    ERROR = _EPOLLERR | _EPOLLHUP

    PULL_TIMEOUT = 1

    def __init__(self):
        self.handlers = {}
        self.events = {}
        # self.epoll = select.epoll()
        self._selector = selectors.DefaultSelector()

        self._future_callbacks = collections.deque()

    @staticmethod
    def instance():  # 只允许创建一个实例
        if not hasattr(IOLoop, '_instance'):
            IOLoop._instance = IOLoop()
        return IOLoop._instance

    def add_handler(self, fd_obj, handler, event):
        fd = fd_obj.fileno()
        self.handlers[fd] = (fd_obj, handler)
        self._selector.register(fd, event)

    def update_handler(self, fd, event):
        self._selector.modify(fd, event)

    def remove_handler(self, fd):
        self.handlers.pop(fd, None)
        try:
            self._selector.unregister(fd)
        except Exception as error:
            print('epoll unregister failed %r' % error)

    def replace_handler(self, fd, handler):
        self.handlers[fd] = (self.handlers[fd][0], handler)

    def start(self):
        try:
            while True:
                for i in range(len(self._future_callbacks)):
                    callback = self._future_callbacks.popleft()
                    callback()

                events = self._selector.select(self.PULL_TIMEOUT)
                self.events.update(events)
                while self.events:
                    fd, event = self.events.popitem()
                    try:
                        fd_obj, handler = self.handlers[fd]
                        handler(fd_obj, event)
                    except Exception as error:
                        print('ioloop callback error: %r' % error)
                        time.sleep(0.5)
        finally:
            for fd, _ in self.handlers.items():
                self.remove_handler(fd)
            self._selector.close()


EOL1 = b'\n\n'
EOL2 = b'\n\r\n'


class Connection:
    def __init__(self, fd):
        self.fd = fd
        self.request_buffer = []
        self.handled = False
        self.response = b''

        self.headers = None
        self.status = None
        self.address = None


class WSGIServer:
    ADDRESS_FAMILY = socket.AF_INET
    SOCKET_TYPE = socket.SOCK_STREAM
    BACKLOG = 5

    HEADER_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'
    SERVER_NAME = 'test/WSGIServer 0.3'

    def __init__(self, server_address):
        self.ssocket = self.setup_server_socket(server_address)
        host, self.server_port = self.ssocket.getsockname()[:2]
        self.server_name = socket.getfqdn(host)

        self.ioloop = IOLoop.instance()
        self.conn_pool = {}

    @classmethod
    def setup_server_socket(cls, server_address):
        ssocket = socket.socket(cls.ADDRESS_FAMILY, cls.SOCKET_TYPE)
        ssocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # SO_REUSEPORT
        ssocket.bind(server_address)
        ssocket.listen(cls.BACKLOG)
        ssocket.setblocking(0)
        return ssocket

    def set_app(self, application):
        self.application = application

    def _accept(self, ssocket, event):
        if event & IOLoop.ERROR:
            self._close(ssocket)

        connect, addr = ssocket.accept()
        connect.setblocking(0)
        ioloop = IOLoop.instance()
        ioloop.add_handler(connect, self._receive, IOLoop.READ)

        fd = connect.fileno()
        connection = Connection(fd)
        connection.address = addr
        self.conn_pool[fd] = connection

    def _receive(self, connect, event):
        if event & IOLoop.ERROR:
            self._close(connect)

        fd = connect.fileno()
        connection = self.conn_pool[fd]
        fragment = connect.recv(1024)
        connection.request_buffer.append(fragment)

        last_fragment = ''.join(connection.request_buffer[:2])
        if EOL2 in last_fragment:
            ioloop = IOLoop.instance()
            ioloop.update_handler(fd, IOLoop.WRITE)
            ioloop.replace_handler(fd, self._send)

    def _send(self, connect, event):
        if event & IOLoop.ERROR:
            self._close(connect)

        fd = connect.fileno()
        connection = self.conn_pool[fd]
        if not connection.handled:
            self.handle(connection)

        byteswritten = connect.send(connection.response)
        if byteswritten:
            connection.response = connection.response[byteswritten:]

        if not len(connection.response):
            self._close(connect)

    def _close(self, connect, event=None):
        fd = connect.fileno()
        connect.shutdown(socket.SHUT_RDWR)
        connect.close()

        ioloop = IOLoop.instance()
        ioloop.remove_handler(fd)

        del self.conn_pool[fd]

    def serve_forever(self):
        self.ioloop.add_handler(self.ssocket, self._accept,
                                IOLoop.READ | IOLoop.ERROR)
        try:
            self.ioloop.start()
        finally:
            self.ssocket.close()

    def handle(self, connection):
        def start_response(status, response_headers, exc_info=False):
            utc_now = datetime.utcnow().strftime(self.HEADER_DATE_FORMAT)
            connection.headers = response_headers + [
                ('Date', utc_now),
                ('Server', self.SERVER_NAME),
            ]
            connection.status = status

        request_text = ''.join(connection.request_buffer)
        environ = self.get_environ(request_text)
        body = self.application(environ, start_response)
        connection.response = self.package_response(body, connection)

        request_line = request_text.splitlines()[0]
        logging.info(
            '%s "%s" %s %s', connection.address[0], request_line,
            connection.status.split(' ', 1)[0], len(body[0]),
        )
        logging.debug('\n' + ''.join(
            '< {line}\n'.format(line=line)
            for line in request_text.splitlines()
        ))

    @classmethod
    def parse_request_buffer(cls, text):
        content_lines = text.splitlines()

        request_line = content_lines[0].rstrip('\r\n')
        request_method, path, request_version = request_line.split()
        if '?' in path:
            path, query_string = path.split('?', 1)
        else:
            path, query_string = path, ''

        return {
            'PATH_INFO': path,
            'REQUEST_METHOD': request_method,
            'SERVER_PROTOCOL': request_version,
            'QUERY_STRING': query_string,
        }

    def get_environ(self, request_text):
        request_data = self.parse_request_buffer(request_text)
        scheme = request_data['SERVER_PROTOCOL'].split('/')[1].lower(),
        environ = {
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': scheme,
            'wsgi.input': StringIO(request_text),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'SERVER_NAME': self.server_name,
            'SERVER_PORT': self.server_port,
        }
        environ.update(request_data)
        return environ

    def package_response(self, body, connection):
        response = 'HTTP/1.1 {status}\r\n'.format(status=connection.status)
        for header in connection.headers:
            response += '{0}: {1}\r\n'.format(*header)
        response += '\r\n'
        for data in body:
            response += data
        logging.debug('\n' + ''.join(
            '> {line}\n'.format(line=line)
            for line in response.splitlines()
        ))
        return response
