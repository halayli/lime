import logging
import traceback
import sys
import datetime

lvl = {'info': 1, 'warn': 2, 'trace': 3, 'debug': 4}

class DaemonLogger(object):
    """A class to help daemons log their activities."""
    def __init__(self, log_level=None, sticky=''):
        object.__setattr__(self, '__log_level', lvl.get(log_level, lvl['info']))
        if sticky:
            fmt = '%s: '+sticky+': %s (%s)\n'
        else:
            fmt = '%s: %s (%s)\n'
        object.__setattr__(self, '__fmt', fmt)

    def __getattribute__(self, attr):
        if attr in lvl.keys():
            def print_method(msg):
                if object.__getattribute__(self, '__log_level') >= lvl[attr]:
                    fmt = object.__getattribute__(self, '__fmt')
                    tm = datetime.datetime.now().strftime('%c')
                    sys.stdout.write(fmt % (tm, msg, attr))
            return print_method
        return object.__getattribute__(self, attr)

    def set_level(self, log_level=None):
        object.__setattr__(self, '__log_level', lvl.get(log_level, lvl['info']))

    def error(self, msg):
        fmt = object.__getattribute__(self, '__fmt')
        tm = datetime.datetime.now().strftime('%c')
        sys.stderr.write(fmt % (tm, msg, 'error'))
