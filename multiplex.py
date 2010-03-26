from select import *

LM_TIMER = 1
LM_READ = 2
LM_WRITE = 3
LM_RESET = 4

class _Multiplexer:
    def schedule_read(self):
        raise NotImplementedError
    def deschedule_read(self):
        raise NotImplementedError
    def schedule_write(self):
        raise NotImplementedError
    def deschedule_write(self):
        raise NotImplementedError
    def schedule_timer(self):
        raise NotImplementedError
    def deschedule_timer(self):
        raise NotImplementedError
    def get_events(self):
        raise NotImplementedError

class Event:
    def __init__(self, filter, fd, data):
        self.fd, self.filter, self.data = (fd, filter, data)
    def __str__(self):
        return 'fd: %s filter: %s data: %s' % (self.fd, self.filter, self.data)

class _KQueue(_Multiplexer):
    def __init__(self):
        self._events = []
        self._fd_handle = kqueue()

    def _generate_events(self):
        """Generates an array of kevent filters to pass it to kqueue control."""
        new_list = []
        # ident, flags, filter
        for fd, flags, filter,data, udata in self._events:
            new_list.append(kevent(fd, flags=KQ_EV_ENABLE|flags,
                 filter=filter, data=data, udata=udata))
        self._events = []
        return new_list

    def get_events(self):
        elist = self._generate_events()
        events = self._fd_handle.control(elist, 50, 3)
        results = []
        for e in events:
            if e.flags & KQ_EV_EOF == KQ_EV_EOF:
                results.append(Event(LM_RESET, e.ident, 0))
            elif e.filter == KQ_FILTER_TIMER:
                results.append(Event(LM_TIMER, e.udata, 0))
            elif e.filter == KQ_FILTER_WRITE:
                results.append(Event(LM_WRITE, e.ident, e.data))
            elif e.filter == KQ_FILTER_READ:
                results.append(Event(LM_READ, e.ident, e.data))

        return results

    def schedule_read(self, fd, data=0):
        self._events.append((fd, KQ_EV_ADD, KQ_FILTER_READ, data, 0))

    def deschedule_read(self):
        pass

    def schedule_write(self, fd):
        self._events.append((fd, KQ_EV_ADD, KQ_FILTER_WRITE, 0, 0))

    def deschedule_write(self, fd):
        self._events.append((fd, KQ_EV_DELETE, KQ_FILTER_WRITE, 0, 0))

    def schedule_timer(self, fd, timeout): 
        self._events.append((1, KQ_EV_ENABLE | KQ_EV_ADD | KQ_EV_ONESHOT,
            KQ_FILTER_TIMER, timeout, fd))

    def deschedule_timer(self, fd, timeout): 
        pass


#class _EPoll(_Multiplexer):
#    pass

#factory method to select the appropriate multiplexer based on the system.
def Multiplex():
    for m in ('_KQueue', '_EPoll'):
        try:
            return globals().get(m)()
        except Exception, e:
            print e
    return None
