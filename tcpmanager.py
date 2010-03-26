import socket
import signal
import os
from utils import *
from logger import DaemonLogger
import traceback
import time
from multiplex import *


# These should be saved in a config file.
TCP_LOG = 'trace'
PORT = 8080
REQ_TIMEOUT = 900000
MAX_ACCEPT = 5000 # silent limit

def shutdown(frame, signal):
    return

class TcpManagerError(Exception):
    def __init__(self, value=None):
        self.value = value

class ConnectionLimitError(TcpManagerError):
    def __str__(self):
        return 'Cannot accept new connections. Maximum limit reached'

class TcpConnectionManager:
    """An abstract network class to listen and manage Tcp connections.

    Methods that MUST to be implemented when extending the class:
    -new_conn(sock) -- Called everytime a new connection is established.
    -recv(fd, size_to_read) -- Called when there is data to be read on socket.
    -send(fd, size_to_write) -- Called when the socket is ready for write

    Methods that can be redefined when extending the class:
    -init() -- Called when listener is up.
    -shutdown() -- called when process is exiting.
    -destroy(fd, reason) -- Called when connection has closed.
    """
    def __init__(self):
        # {fd: (sock_obj, last_active, type, birth)}
        self._conn_pool = {}
        # we use it to push kevents, and free it once control() is called
        self._logger = DaemonLogger(TCP_LOG)
        self._multiplex = Multiplex()
        self._gens = {}

    def _run(self):
        self._init_listener()
        self._loop()

    def _loop(self):
        """Wait for events and handle them accordingly. Do nothing otherwise."""
        while 1:
            # Block until an activity takes place in the pool
            try:
                events = self._multiplex.get_events()
            except Exception, e:
                self._shutdown()
                return
            #
            # !!WARNING!! !!WARNING!! !!WARNING!!
            # NOT ONE METHOD CALL BELOW IS ALLOWED TO BLOCK.
            # !!WARNING!! !!WARNING!! !!WARNING!!
            #
            self._process_events(events)

    def _process_events(self, events):
        """Called everytime we have kqueue events to process."""
        deleted = []
        # first we close the bad sockets so that they don't get processed
        # in the second loop and throw an error
        #print len(events)
        for event in events[:]:
            # connection reset by peer
            if event.filter == LM_RESET:
                if event.fd in deleted:
                    events.remove(event)
                    continue
                self._close_conn(event.fd, reason='Connection rst by peer')
                deleted.append(event.fd)
                events.remove(event)

        for event in events:
            if event.fd in deleted: continue
            if event.filter == LM_TIMER:
                if event.fd not in self._conn_pool: continue
                if type == TcpConnectionManager.REQ:
                    self._multiplex.schedule_timer(event.fd, REQ_TIMEOUT - elap)
                continue
            try:
                # 1. New connection?
                if event.fd == self._listener_fn:
                    self._accept_conn(int(event.data))
                    continue
                # 2. Existing connection, more data to send?
                if event.filter == LM_WRITE:
                    send_more = self.send(int(event.fd), event.data)
                    # meaning we didn't finish writing all the data, yet
                    if send_more == 2:
                        self._multiplex.schedule_write(event.fd)
                    else:
                        self._multiplex.deschedule_write(event.fd)
                    continue
                # if it is not a new connection, and not a write, then it has to
                # to be a read since we already filtered out the bad events
                # 3. Existing connection, more data to receive?
                should_send = self.recv(int(event.fd), event.data)
                # 4. we finished reading, and now it is time to respond
                if should_send == 2:
                    self._multiplex.schedule_write(event.fd)
                continue
            # out of fds?
            except ConnectionLimitError:
                self._logger.error('Cannot accept more connections')
            except Exception, e:
                self._logger.error('%s: %s' % (event.fd,e))
                if e.args[0] in (os.errno.EMFILE,os.errno.EINVAL,
                    os.errno.ENFILE): # os errors
                    continue
                if event.fd in deleted:
                    continue
                self._close_conn(event.fd, reason='oops'+repr(e))
                deleted.append(event.fd)

    def _accept_conn(self, conns):
        """Handles new incoming connections."""
        for i in range(conns):
            try:
                s, addr = self._listener.accept()
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 128000)
            except Exception, e:
                raise
            
            now = unixtm()
            fd = s.fileno()
            self._conn_pool[fd] = [s, now]
            # ident, flags, filter
            self._multiplex.schedule_read(fd)
            self.new_conn(fd, s)

    def _init_listener(self):
        """Prepares process to start listening to new connections."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self._bind_address, self._port))
        self._listener_fn = s.fileno()
        # use a tuple so that we don't accidentally change the listener config
        now = unixtm()
        self._conn_pool[s.fileno()] = (s, now)
        self._listener = s
        # ident, flags, filter
        self._multiplex.schedule_read(s.fileno(), 128)
        s.listen(MAX_ACCEPT)
        self._logger.info('Listening on %s:%s' % (
            self._bind_address, self._port))
        self._accept_tm = now

    def _close_conn(self, fd, reason=None):
        """Closes a connection and calls any destroy() if implemented."""
        try:
            ip = 0
            # If we failed here it means we have closed the connection
            # else it means the user has closed the connection
            # we only log when the user closes the connection.
            try:
                pass
                #ip, port = self._conn_pool[fd][0].getpeername()
            except:
                pass
            finally:
                self.destroy(fd)
            if ip:
                msg = 'Closing connection %s:%s:%s(%s)' % (ip, port, fd, reason)
                #self._logger.trace(msg)
        except Exception, e:
            pass
            #self._logger.error(e)
        finally:
            self._conn_pool[fd][0].close()
            del self._conn_pool[fd]

    def new_conn(self, sock):
        """Pure virtual method to be implemented by the subclass.

        Handle new connections in the subclass.
        """
        raise NotImplementedError

    def send(self, fd):
        """Pure virtual method to be implemented by the subclass.

        recv is called whenever the socket can read length bytes without
        blocking.
        """
        raise NotImplementedError

    def recv(self, sock, length):
        """Pure virtual method to be implemented by the subclass.

        recv is called whenever the socket can read length bytes without
        blocking.
        """
        raise NotImplementedError

    def listen(self, bind_address, port):
        self._bind_address= bind_address
        self._port = port
        self.init()
        self._run()

    def _shutdown(self):
        # shutdown listener first
        self._logger.info('Received shutdown signal')
        self._close_conn(self._listener.fileno(), reason='Shutting down')
        self._logger.info('Listener shutdown')
        open_fds = self._conn_pool.keys()
        for fd in open_fds:
            self._close_conn(fd, reason='Shutting down')
        self.shutdown()

    def init(self):
        """To be redifined by the sublcass."""
        pass

    def print_stats(self):
        """To be redifined by the sublcass."""
        pass

    def shutdown(self):
        """To be redifined by the sublcass."""
        pass

    def destroy(self, fd):
        """To be redifined by the sublcass."""
        pass

for sig in (1, 2, 3, 4, 5, 6, 10, 11):
    signal.signal(sig, shutdown)
