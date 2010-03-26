import time
import wsgiref.handlers

format_date_time = wsgiref.handlers.format_date_time

version_ = 'v1.0'

def unixtm():
    return int(str(time.time()).split('.')[0])

def profile_method(fn):
    return fn
    def mod_fn(*args, **kwargs):
        t1 = time.time()
        print 'entering %s' % fn.func_name
        ret = fn(*args, **kwargs)
        print '%s returned in %5.15f' % (fn.func_name, time.time() - t1)
        if time.time() - t1 > 0.5:
            print '*'*10+'TOO LONG'+'*'*10
        return ret
    return mod_fn
