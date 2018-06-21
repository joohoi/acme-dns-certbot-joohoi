import json as JSON
import socket

# python 2/3 compatibility
try:
    import urlparse
    from urllib import urlencode
    import urllib2
    import httplib
except ImportError:
    import urllib.parse as urlparse
    from urllib.parse import urlencode
    import urllib.request as urllib2
    import http.client as httplib

# configurations
socket_scheme = "+unix"


# UNIX socket code
# referenced from https://github.com/docker/docker-py/blob/master/docker/transport/unixconn.py
class UnixHTTPResponse(httplib.HTTPResponse, object):
    def __init__(self, sock, *args, **kwargs):
        disable_buffering = kwargs.pop('disable_buffering', False)
        kwargs['buffering'] = not disable_buffering
        super(UnixHTTPResponse, self).__init__(sock, *args, **kwargs)


class UnixHTTPConnection(httplib.HTTPConnection, object):

    def __init__(self, unix_socket, timeout=60):
        super(UnixHTTPConnection, self).__init__(
            'localhost', timeout=timeout
        )
        self.unix_socket = unix_socket
        self.timeout = timeout
        self.disable_buffering = False

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.unix_socket)
        self.sock = sock

    def putheader(self, header, *values):
        super(UnixHTTPConnection, self).putheader(header, *values)
        if header == 'Connection' and 'Upgrade' in values:
            self.disable_buffering = True

    def response_class(self, sock, *args, **kwargs):
        if self.disable_buffering:
            kwargs['disable_buffering'] = True

        return UnixHTTPResponse(sock, *args, **kwargs)


class CustomHTTPHandler(urllib2.HTTPHandler):
    """
    Custom HTTPHandler for urllib2 to communicate via unix sockets
    """

    def http_open(self, req):
        def customHTTPConnection(host, port=None, strict=None, timeout=0):
            return UnixHTTPConnection(req._socket_path)
        return self.do_open(customHTTPConnection, req)


# Requests code


class RequestResponse(object):
    """
    Request response object that wraps urllib2 response object to mimic requests library.
    """

    def __init__(self, request, response):
        self.request = request
        self.status_code = response.getcode()
        self.url = response.geturl()
        self.headers = dict(response.info())
        self.text = response.read()

        self._json = None

        response.close()

    def __getitem__(self, key):
        if not self._json:
            return self.json()[key]

    def json(self):
        if not self._json:
            self._json = JSON.loads(self.text)
        return self._json

    def keys(self):
        if not self._json:
            return self.json().keys()


def base_request(method, url, params=None, headers=None, data=None, json=None):
    # process url
    if params:
        query = urlencode(params)
        url += "?" + query

    # process if socket
    url_parts = urlparse.urlsplit(url)
    is_sock = socket_scheme in url_parts.scheme
    socket_path = None
    if is_sock:
        # get the socket path
        socket_path = urlparse.unquote(url_parts.netloc)
        # fix the scheme to play well with urllib2
        original_scheme = url_parts.scheme.replace(socket_scheme, "")
        url = url_parts._replace(scheme=original_scheme, netloc="localhost").geturl()

    # default headers
    _headers = {
        "Accept": "*/*"
    }

    # process data
    if data:
        data = urlencode(data)

    if json:
        _headers["Content-Type"] = "application/json"
        data = JSON.dumps(json)

    # process headers
    if headers:
        _headers.update(headers)
    
    # get request obj
    if data:
        request_obj = urllib2.Request(url, data=data, headers=_headers)
    else:
        request_obj = urllib2.Request(url, headers=_headers)

    # process method
    request_obj.get_method = lambda: method

    # piggyback socket_path on request object
    request_obj._socket_path = socket_path

    # make http(s) connection
    try:
        if socket_path:
            response = urllib2.build_opener(CustomHTTPHandler).open(request_obj)
        else:
            response = urllib2.urlopen(request_obj)
    except urllib2.HTTPError as e:
        return RequestResponse(request_obj, e)

    return RequestResponse(request_obj, response)


def get(url, params=None, headers=None, data=None, json=None):
    return base_request("GET", url, params=params, headers=headers, data=data, json=json)


def post(url, params=None, headers=None, data=None, json=None):
    return base_request("POST", url, params=params, headers=headers, data=data, json=json)


def delete(url, params=None, headers=None, data=None, json=None):
    return base_request("DELETE", url, params=params, headers=headers, data=data, json=json)


def put(url, params=None, headers=None, data=None, json=None):
    return base_request("PUT", url, params=params, headers=headers, data=data, json=json)

