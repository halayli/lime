import traceback
from tcpmanager import TcpConnectionManager
from http import *
import traceback
from logger import DaemonLogger

#
# +--------------------+
# |TcpConnectionManager|
# +--------------------+
#          ^
#          |
#          |
#          |
# +--------------------+                 +-----------+
# |   HttpPool         | o-------------N |   Http    |
# |                    | <-------------- |           |
# +--------------------+       use       +-----------+
#
#    ->   listen()


#body='x' * 9000

class HttpPool(TcpConnectionManager):
    def __init__(self, app):
        self._logger = DaemonLogger('trace')
        TcpConnectionManager.__init__(self)
        self._requests = {}
        self._app = app

    def init(self):
        """Called from parent instance to help us initialize on time."""
        self._logger.info('Starting Lime Server %s' % version_)

    def new_conn(self, fd, sock):
        """Called from parent instance whenever a new connection comes in."""
        self._requests[fd] = Http(fd, sock)

    def destroy(self, fd):
        """Virtual function implementation called when connection is closing.  
        """
        pass
 
    def send(self, fd, length):
        """Called when the socket is ready for write"""
        return self._requests[fd].send(length)

    def recv(self, fd, length):
        """Called when data received on a socket. We'll handle it accordingly.
        """
        h = self._requests[fd]
        try:
            res = h.recv(length)
            if res == 0:
                #h.respond('hi')
                resp = self._app.delegate(h.request(), h.method(), h)
                ret = h.respond(resp)
                # if ret == 2, then we haven't finished sending all the data
                # schedule more to write.
                if ret == 2: return ret
                # based on the connection type keep-alive/close, it will either
                # reset the state or close the socket
                h.close()
        except (Exception), e:
            if isinstance(e, HttpError):
                h.respond(status=e.args[1])
            else:
                self._logger.error('%s:%s\n%s\n' %
                    (fd, h.recvd_data(),traceback.format_exc()))
            h.close()

    def shutdown(self):
        """Called when lime is shutting down"""
        pass
