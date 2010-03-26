from lime import HttpPool
from app import Application

def some_method(http, id):
    return 'hello this some method %s' % id

def method1(http, id, id2):
    return 'hello, this is method1 with id %s %s' % (id, id2)

#module 1
module1_urls = {
    '/some_method/(\d+)/(\d+)': {'GET': method1}
}

module1 = Application(module1_urls)

main_urls = {
    '/(\d*)': {'GET': some_method},
    '/test2': module1
}

#main module
main_module = Application(main_urls)

pool = HttpPool(main_module)
pool.listen(bind_address='127.0.0.1', port=8080)
