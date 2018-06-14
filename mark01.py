import cgi
import re
import json
import importlib
from io import StringIO
from wsgiref.simple_server import make_server, demo_app


responses = {200: "OK"}


def import_string(dotted_path):
    module_path, class_name = dotted_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class RegexPattern:
    def __init__(self, regex):
        self.regex = re.compile(regex)

    def match(self, path):
        match = self.regex.search(path)
        if match:
            return True
        return False


class BaseHandler:
    _request_middleware = None
    _view_middleware = None
    _template_response_middleware = None
    _response_middleware = None
    _exception_middleware = None
    _middleware_chain = None

    _router = None  # 路由系统

    def load_middleware(self, middleware_list):
        """load settings.middleware list"""
        self._request_middleware = []
        # self._view_middleware = []
        # self._template_response_middleware = []
        self._response_middleware = []
        # self._exception_middleware = []

        for middleware_path in middleware_list:
            mw_instance = import_string(middleware_path)

            if hasattr(mw_instance, 'process_request'):
                self._request_middleware.append(mw_instance.process_request)
            if hasattr(mw_instance, 'process_response'):
                self._response_middleware.append(mw_instance.process_response)

    def load_urls(self, urlpatterns):
        self._router = {RegexPattern(i[0]): i[1] for i in urlpatterns}

    def get_response(self, request):
        response = None
        # 1.首先处理中间件 middleware
        for req in self._request_middleware:
            request = req(req, request)

        # 2.然后处理view请求
        for regex, view in self._router.items():
            if regex.match(request.path):
                response = view(request)

        # 3.最后处理response
        for resp in self._response_middleware:
            response = resp(resp, request, response)
        return response


class HttpResponse:
    streaming = False
    status_code = 200

    def __init__(self, content=b'', content_type=None, status=None, reason=None, charset=None):
        self.content = content
        if status is not None:
            try:
                self.status_code = int(status)
            except (ValueError, TypeError):
                raise TypeError('HTTP status code must be an integer.')

            if not 100 <= self.status_code <= 599:
                raise ValueError('HTTP status code must be an integer from 100 to 599.')
        self._reason_phrase = reason
        self._charset = charset
        if content_type is None:
            content_type = 'text/plain; charset=utf-8'
        self.content_type = content_type

    def reason_phrase(self):
        if self._reason_phrase is not None:
            return self._reason_phrase
        return responses.get(self.status_code, 'Unknown Status Code')

    def render(self):
        stdout = StringIO()
        print(self.content, file=stdout)
        return [stdout.getvalue().encode("utf-8")]


class WSGIRequest:
    """environ to request object"""
    def __init__(self, environ):
        script_name = ''
        path_info = environ.get('PATH_INFO', '/')
        self.environ = environ
        self.path_info = path_info
        self.path = '%s/%s' % (script_name.rstrip('/'),
                               path_info.replace('/', '', 1))
        self.META = environ
        self.META['PATH_INFO'] = path_info
        self.META['SCRIPT_NAME'] = script_name
        self.method = environ['REQUEST_METHOD'].upper()
        self.content_type, self.content_params = cgi.parse_header(environ.get('CONTENT_TYPE', ''))

        try:
            content_length = int(environ.get('CONTENT_LENGTH'))
        except (ValueError, TypeError):
            content_length = 0
        self.content_length = content_length


class WSGIHandler(BaseHandler):
    request_class = WSGIRequest

    def __init__(self, **kwargs):  # urlpatterns middleware
        super().__init__()
        self.load_middleware(kwargs['middleware'])
        self.load_urls(kwargs["urlpatterns"])

    def __call__(self, environ, start_response):
        request = self.request_class(environ)  # 将请求内容变成一个 request 对象
        response = self.get_response(request)

        status = '%d %s' % (response.status_code, response.reason_phrase)
        response_headers = [('Content-type', 'text/plain; charset=utf-8')]
        start_response(status, response_headers)

        return response.render()


def demo_views(request):
    r = HttpResponse(json.dumps({"status": 0}))
    return r


def runserver(ip='127.0.0.1', port=8000):
    middleware = ['middleware.test.TestMiddleware']
    urlpatterns = [(r'^/test$', demo_views)]
    app = make_server(ip, port, WSGIHandler(urlpatterns=urlpatterns, middleware=middleware))
    app.serve_forever()


if __name__ == '__main__':
    runserver()
