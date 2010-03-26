from utils import *
import urllib
import os, signal, re

#
# This is all what we support from the HTTP. We don't need more for now
#

http_version = 'HTTP/1.1'
http_status_codes = {
    200: 'OK',
    204: 'No Content',
    400: 'Bad Request',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    408: 'Request Timeout',
    413: 'Request Entity Too Large',
    414: 'Request-URI Too Long',
    500: 'Internal Server Error'}

allowed_methods = ['GET', 'POST']
content_types = {
    'multipart': 'multipart/mixed;boundary=%s',
    'html': 'text/html',
    'plain': 'text/plain',
    'javascript': 'text/javascript',
    'js': 'text/javascript',
    'css': 'text/css',
    'xml': 'text/xml',
    'json': 'text/json',
    'png': 'image/png',
    'gif': 'image/gif',
    'ico': 'image/x-icon',
}

http_header_format = '%s: %s\r\n'
http_status_format = '%s %s %s\r\n'
http_response_format = '%s\r\n'
http_mime_format = '--%s\r\nContent-Type: %s\r\n\r\n%s\r\n'
http_server_name = 'Lime Server %s' % version_

class HttpError(Exception):
    def __init__(self, *args):
        # arg0: ip arg1: err_code arg2: request_msg
        self.args = args
    def __str__(self):
        return '%s: %s %s: %s' % (self.args[0], self.args[1], 
            http_status_codes[self.args[1]], self.args[2])

class HttpIncompleteHeader(Exception): pass
class HttpIncompleteBody(Exception): pass


REQUEST_LINE = re.compile('(GET|POST) (.+) (HTTP/1.[01])')
H_MATCH = re.compile('^(.+):\s?(.+)$')

class Http:
    """A Class that understands and communicates Http. """

    max_request_length = 767 # Maximum request length a user can send
    max_post_length = 16384 # Maximum post length a user can send
    max_uri_length = 256 # Maximum post length a user can send

    def __init__(self, fd, sock):
        """Requires an opened TCP socket to communicate Http over it."""
        self._sock = sock
        self._fileno = fd
        self._reset()

    def get_peer(self):
        self._ip_address, self._ephim_port = self._sock.getpeername()
        return '%s:%s:%s' % (self._ip_address, self._ephim_port, self._fileno)

    def get_request_line(self, length):
        """recv length of data without blocking."""
        # it is safe to return if we failed to recv because failing eventually
        # means the socket has closed and we'll receive a kevent to close it
        # properly later on. Same thing for send

        # At this point we want to check if we have received all the data.
        # if not, then block again until we recv more
        # Might raise HttpIncompleteHeader, in this case it will be passed
        # by the caller. Or it might raise HttpError if user sent us crap
       
        while 1:
            try:
                self._data_recvd += self._sock.recv(length)
            except:
                return 
            try:
                # let's try parsing the first line (request)
                # if we fail, then we still haven't received the first line
                # check if we are receiving a huge single line mal request
                i = self._data_recvd.find('\r')
                if i == -1:
                    # if we haven't found it we might be receiving data 
                    # in very small chunks. For this reason  check if we 
                    # have exceeded the maximum header length without a 
                    # newline and take appropriate action
                    ln = len(self._data_recvd) 
                    if ln > Http.max_request_length:
                        raise HttpError(413, ln)
                    return 1

                request = self._data_recvd[:i]
                tmp = REQUEST_LINE.match(request)
                if not tmp:
                    raise Exception (400, request)
                request_parts = tmp.groups()
                self._method, self._request_line =  request_parts[0:2]
                # three conditions makes a request valid:
                # method requested should be supported
                # followed by a uri
                # followed by HTTP version
                if not request_parts[0] in allowed_methods:
                    raise Exception (400, request)
                if len(self._request_line) > Http.max_uri_length:
                    raise Exception (414, request)
                # we can move on to check the rest of the request header
            except ValueError, e:
                    raise HttpError(self.get_peer(), 400, request+str(e))
            except (HttpError, Exception), e:
                    raise HttpError(self.get_peer(), e.args[0], e.args[1])
            break
        self.recv = self.get_header
        return self.recv(0)

    def get_header(self, length):
        # at this point we have verified that the request is valid.
        # let's check the rest of the request header
        # how much data have we received so far? did we exceed the request
        # header maximum size?
        while 1:
            try:
                self._data_recvd += self._sock.recv(length)
            except:
                return # return silently. wait for the socket to close
            if self._header_length == -1:
                self._header_length = self._data_recvd.find('\r\n\r\n')
                if self._header_length == -1:
                    if len(self._data_recvd) > Http.max_request_length: 
                        raise HttpError(self.get_peer(), 413, ln)
                    return
            # restore the 4 crlf we found
            self._header_length += 4
            break
 
        if self._header_length > Http.max_request_length: 
            raise HttpError(self.get_peer(), 413, ln)
 
        # split the client request lines and make them accessible for later
        itr = H_MATCH.finditer(self._data_recvd[:self._header_length])

        for l in itr:
            try:
                n, v = l.groups()
            except Exception, e:
                raise HttpError(self.get_peer(), 400, line)

            self._client_headers[n.lower()] = v.lower()
 
        self._request_header = self._data_recvd[:self._header_length]

        self.recv = self.get_body
        return self.recv(0)

        browser =  self._client_headers.get('user-agent', '').lower()
        if browser:
            if 'webkit' in browser:
                self._client_browser = 'safari'
                self._match_version('version\/(.*?) ', browser);
            elif 'msie' in browser:
                self._client_browser = 'msie'
                self._match_version('msie (.*?);', browser);
            elif 'firefox' in browser:
                self._client_browser = 'mozilla'
                self._match_version('firefox\/(.*)', browser);
            elif 'opera' in browser:
                self._client_browser = 'opera'
            else:
                self._client_browser = 'unknown'
        self._match_platform(browser)

    def get_body(self, length):
        # at this point, we have received a complete header and we are ready
        # to process the body
        while 1:
            try:
                try:
                    self._data_recvd += self._sock.recv(length)
                except:
                    return 3
                ln = len(self._data_recvd)
                if ln > Http.max_post_length: 
                    raise HttpError(self.get_peer(), 413, ln)
                if self._method == 'POST':
                    body = self._data_recvd[self._header_length:]
                    if int(self._client_headers['content-length']) !=len(body):
                        return 1
                    else:
                        body_fields = body.split('&')
                        # fields of more than 50 chars are not allowed 
                        # because we are using dicts. 
                        for field_value in body_fields:
                            field, value = field_value.split('=')
                            field = urllib.unquote_plus(field)[0:50]
                            value = urllib.unquote_plus(value)
                            self._post[field] = value
            except Exception, e:
                raise HttpError(self.get_peer(), 400, str(e))
            break
        return 0
 
    def client_info(self):
        return '%s:%s:%s:%s' % (self.get_peer(), self._client_browser,
            self._client_browser_v, self._client_browser_p)

    def _match_version(self, regex, browser):
        m = re.search(regex , browser)
        if m:
           self._client_browser_v = m.groups()[0]
        else:
           self._client_browser_v = "0.0"

    def _match_platform(self, browser):
        m = re.search('(\(.*?\))', browser)
        if m:
           self._client_browser_p = m.groups()[0]
        else:
           self._client_browser_p = "unknown"

    def browser(self):
        return self._client_browser

    def browser_version(self):
        return 0

    def send(self, length=0, data=None):
        if not self._in_send:
       	    self._in_send = 1
            self._total_sent = 0
            self._total_to_send = len(data)
            self._data = data
            self._buf = 128000
            length = self._buf

        if self._total_sent != self._total_to_send:
            self._total_sent += self._sock.send(
                self._data[self._total_sent:self._total_sent+length])
            #self._total_sent += self._sock.send(self._data)
            if self._total_to_send - self._total_sent != 0:
                return 2
        self._in_send = 0
        if not self._is_multipart and not self._is_chunk:
            self.close()
        return 0

    def append_custom_header(self, name, value):
        self._custom_headers[name] = value

    def set_cookie(self, name, value, max_age=0, path='/', domain=None):
        cookie = '%s=%s' % (name, value)
        cookie += ';Max-Age='+max_age
        cookie += ';Path='+path
        cookie += ';Domain='+self._my_domain
        cookie += ';secure'
        self._cookies.append(cookie)

    def _generate_header(self, status, state='keep-alive'):
        final_header = ''
        rfc1123_dt = format_date_time(time.time())

        self._headers[status] = http_status_codes[status]
        self._headers['Date'] = rfc1123_dt
        self._headers['Server'] = http_server_name
        self._headers['Connection'] = state
        for header in self._headers:
            if type(header) == int:
                final_header = http_status_format % (http_version,
                    header, http_status_codes[header]) + final_header
            else:
                final_header += http_header_format % (header, 
                    self._headers[header])

        for cookie in self._cookies:
            final_header += 'Set-Cookie: %s\r\n' % (cookie)

        for custom_header in self._custom_headers:
            final_header += http_header_format % (custom_header,
                self._custom_headers[custom_header])

        return final_header

    def respond(self, data='', status=200, ctype='html', multipart=0, chunk=0):
        to_send = ''
   
        if (status not in http_status_codes.keys() or
            (multipart and chunk) or
            ctype not in content_types.keys()): # check if improper args
            self._headers['Content-Length'] =  len(data)
            final_header = self._generate_header(500, 'close') # report 5xx 
            to_send =  http_response_format % final_header
        elif status >= 400: # handle 4xx and 5xx generically
            self._headers['Content-Length'] =  len(data)
            final_header = self._generate_header(status, 'close')
            to_send = http_response_format % final_header
        elif not self._header_sent: # first time sending a response
            self._header_sent = 1
            if multipart:
                self._boundary = 'commentie'
                self._is_multipart = 1
                self._headers['Content-Type'] =\
                    content_types['multipart'] % self._boundary
            else:
                self._headers['Content-Type'] = content_types[ctype]

            if chunk:
                self._is_chunk = 1
                self._headers['Transfer-Encoding'] =  'chunked'

            self._headers[status] = http_status_codes[status]
            self._headers['Allow'] = ','.join(allowed_methods)
            if not multipart and not chunk: # only case to send length
                self._headers['Content-Length'] =  len(data)

            final_header = self._generate_header(status)
            final_header =  http_response_format % final_header

            if multipart:
                to_send = final_header + (http_mime_format % (self._boundary,
                   content_types[ctype], data))
            else:
                if chunk:
                    to_send = final_header + ('%s\r\n%s\r\n' % (
                        hex(len(data)).split('x')[1], data))
                else:
                    to_send = final_header + data
            #DEBUG:
            #print  final_header
        else: # we've already sent the header, keep going
            if self._is_multipart: # format multipart response if needed
                to_send = (http_mime_format % (self._boundary,
                   content_types[ctype], data))
            elif self._is_chunk:
                to_send = '%s\r\n%s\r\n' %(hex(len(data)).split('x')[1], data)
            else:
                to_send =  data

        return self.send(data=to_send)

    def _reset(self):
        self._data_recvd = ''
        self._is_multipart = 0
        self._header_sent = 0
        self._headers = {}
        self._custom_headers = {}
        self._cookies = {}
        self._client_headers = {}
        self._post = {}
        self._client_browser = 'unknown'
        self._client_browser_v = "0.0"
        self._client_browser_p = "unknown"
        self._method = ''
        self._request_line = ''
        self._header_length = -1
        self._is_chunk = 0
        self.recv = self.get_request_line
        self.send = self.send
        self._in_send = 0

    def request(self):
        return self._request_line

    def method(self):
        return self._method

    def getpeername(self):
        return self._sock.getpeername()

    def get_post(self, key=None):
       if key:
           return self._post.get(key, '')
       return self._post

    def close(self):
        if self._client_headers.get('connection','') == 'close':
            # if the connection was closed from the client already we don't
            # want the exception to propagate. Silently drop it.
            try:
                self._sock.close()
            except:
                pass
        else:
            self._reset()

    def is_post(self): 
        return self.method() == 'POST'

    def fileno(self):
        return self._fileno

    def recvd_data(self):
        return self._data_recvd

    def set_sock(self, sock):
        self._sock = sock
