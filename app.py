import re
class Application:
    def __init__(self, urls):
        self._urls = urls

    def delegate(self, url, method, http):
        params = []
        try:
            url_part1, url_rest = ['/'+u for u in url.split('/',2) if u != '']
        except:
            url_part1 = url_rest = url
        for u in self._urls:
            key = u
            if u != '/':
                u = ['/'+u for u in u.split('/',2) if u != ''][0]
            m = re.match('%s$' % u, url_part1)
            if m: break
        if not m:
            return 'method not found'

        user_method = self._urls[key]
        if isinstance(user_method, Application):
            return user_method.delegate(url_rest, method, http)
        else:
            m = None
            for u in self._urls:
                #print 'matching %s with %s' % (u, url)
                m = re.match('%s$' % u, url)
                if m: break
            if not m:
                return 'method not found'
            params = m.groups()
            user_method = self._urls[key].get(method)
            return user_method(http, *params)
