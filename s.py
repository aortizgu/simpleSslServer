#!/usr/local/bin/python
import sys
import os
import re
import shutil
import json
import urllib
import urllib2
import BaseHTTPServer
import ssl
import base64
import urlparse
import math

reload(sys)
sys.setdefaultencoding('utf8')

here = os.path.dirname(os.path.realpath(__file__))

fData = open(os.path.join(here, "data/data.json"))
data = json.load(fData)
fData.close()

fUsers = open(os.path.join(here, "data/users.json"))
users = json.load(fUsers)
fUsers.close()

def haversine(lat1, lon1, lat2, lon2):
    rad=math.pi/180
    dlat=lat2-lat1
    dlon=lon2-lon1
    R=6372.795477598
    a=(math.sin(rad*dlat/2))**2 + math.cos(rad*lat1)*math.cos(rad*lat2)*(math.sin(rad*dlon/2))**2
    distancia=2*R*math.asin(math.sqrt(a))
    return distancia

def save_data():
    data['version'] = data['version'] + 1
    with open("data/data.json", "w") as outfile:
        json.dump(data, outfile, indent=4)

def valid_user(username):
    for user in users:
        if username == user['user']:
            return True
    return False

def valid_password(username, password):
    for user in users:
        if username == user['user']:
            if password == user['password']:
                return True
    return False

def get_data(handler):
    return data

def get_data_version(handler):
    ret = {}
    ret['version'] = data['version']
    return ret

def get_users(handler):
    print "get_user::"
    ret = {}
    ret['found'] = False
    ret['valid'] = False
    parsed = urlparse.urlparse(handler.path)
    if 'id' in urlparse.parse_qs(parsed.query):
        print urlparse.parse_qs(parsed.query)
        user = urlparse.parse_qs(parsed.query)['id'][0]
        user = user.split(':')
        if valid_user(user[0]):
            ret['found'] = True
            if valid_password(user[0], user[1]):
                ret['valid'] = True
    return ret

def set_user(handler):
    print "set_user::"
    print handler.path
    parsed = urlparse.urlparse(handler.path)
    print urlparse.parse_qs(parsed.query)['id']
    return users

def delete_user(handler):
    print handler.get_payload()
    return users

def post_record(handler):
    print "post_record::"
    record = handler.get_payload()
    print record
    data['records'].append(record)
    save_data()
    return data

def post_photo(handler):
    print "post_photo::"
    print handler.path
    ret = None
    parsed = urlparse.urlparse(handler.path)
    if 'id' in urlparse.parse_qs(parsed.query):
        print urlparse.parse_qs(parsed.query)
        photo_name = 'images/'
        photo_name += urlparse.parse_qs(parsed.query)['id'][0]
        f = open(photo_name, 'w')
        f.write(handler.get_payload_raw())
        f.close()
        ret = True
    return ret

def post_search(handler):
    print "post_search::"
    ret = []
    search = handler.get_payload()
    print search
    for record in data['records']:
        dist = haversine(record['lat'], record['lng'], search['lat'], search['lng'])
        print "dist(", dist, ")-> (", record['lat'], ", ", record['lng'], ") (", search['lat'], ", ", search['lng'], ")"
        if dist <= search['radious']:
            ret.append(record)
    return ret

def rest_call_json(url, payload=None, with_payload_method='PUT'):
    'REST call with JSON decoding of the response and JSON payloads'
    if payload:
        if not isinstance(payload, basestring):
            payload = json.dumps(payload)
        # PUT or POST
        response = urllib2.urlopen(MethodRequest(url, payload, {'Content-Type': 'application/json'}, method=with_payload_method))
    else:
        # GET
        response = urllib2.urlopen(url)
    response = response.read().decode()
    return json.loads(response)

class MethodRequest(urllib2.Request):
    'See: https://gist.github.com/logic/2715756'
    def __init__(self, *args, **kwargs):
        if 'method' in kwargs:
            self._method = kwargs['method']
            del kwargs['method']
        else:
            self._method = None
        return urllib2.Request.__init__(self, *args, **kwargs)

    def get_method(self, *args, **kwargs):
        return self._method if self._method is not None else urllib2.Request.get_method(self, *args, **kwargs)

class RESTRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.routes = {
            r'^/$': {'file': 'web/index.html', 'media_type': 'text/html'},
            r'^/images$': {'file': 'images', 'media_type': 'image/jpg'},
            r'^/users$': {'GET': get_users, 'PUT': set_user, 'DELETE': delete_user, 'media_type': 'application/json'},
            r'^/data$': {'GET': get_data, 'media_type': 'application/json'},
            r'^/data_version$': {'GET': get_data_version, 'media_type': 'application/json'},
            r'^/record': {'POST': post_record, 'media_type': 'application/json'},
            r'^/search': {'POST': post_search, 'media_type': 'application/json'},
            r'^/photo': {'POST': post_photo, 'media_type': 'image/jpg'}}

        return BaseHTTPServer.BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def do_HEAD(self):
        self.handle_method('HEAD')

    def do_GET(self):
        self.handle_method('GET')

    def do_POST(self):
        self.handle_method('POST')

    def do_PUT(self):
        self.handle_method('PUT')

    def do_DELETE(self):
        self.handle_method('DELETE')

    def get_payload(self):
        payload_len = int(self.headers.getheader('content-length', 0))
        payload = self.rfile.read(payload_len)
        payload = json.loads(payload)
        return payload

    def get_payload_raw(self):
        payload_len = int(self.headers.getheader('content-length', 0))
        payload = self.rfile.read(payload_len)
        return payload

    def handle_method(self, method):
        route = self.get_route()
        if route is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write('Route not found\n')
        else:
            if method == 'HEAD':
                self.send_response(200)
                if 'media_type' in route:
                    self.send_header('Content-type', route['media_type'])
                self.end_headers()
            else:
                if 'file' in route:
                    if method == 'GET':
                        try:
                            filename = os.path.join(here, route['file'])
                            parsed = urlparse.urlparse(self.path)
                            if 'id' in urlparse.parse_qs(parsed.query):
                                filename += '/'
                                filename += urlparse.parse_qs(parsed.query)['id'][0]
                            f = open(filename)
                            try:
                                self.send_response(200)
                                if 'media_type' in route:
                                    self.send_header('Content-type', route['media_type'])
                                self.end_headers()
                                shutil.copyfileobj(f, self.wfile)
                            finally:
                                f.close()
                        except:
                            self.send_response(404)
                            self.end_headers()
                            self.wfile.write('File not found\n')
                    else:
                        self.send_response(405)
                        self.end_headers()
                        self.wfile.write('Only GET is supported\n')
                else:
                    if method in route:
                        content = route[method](self)
                        if content is not None:
                            self.send_response(200)
                            if 'media_type' in route:
                                self.send_header('Content-type', route['media_type'])
                            self.end_headers()
                            if method != 'DELETE':
                                self.wfile.write(json.dumps(content))
                        else:
                            self.send_response(404)
                            self.end_headers()
                            self.wfile.write('Not found\n')
                    else:
                        self.send_response(405)
                        self.end_headers()
                        self.wfile.write(method + ' is not supported\n')


    def get_route(self):
        for path, route in self.routes.iteritems():
            if re.match(path, self.path.split("?")[0]):
                return route
        return None

def rest_server(port):
    'Starts the REST server'
    http_server = BaseHTTPServer.HTTPServer(('', port), RESTRequestHandler)
    http_server.socket = ssl.wrap_socket(http_server.socket, keyfile="certs/server/privkey.pem",
        certfile='certs/server/cert.pem', server_side=True)

    print 'Starting HTTP server at port %d' % port
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    print 'Stopping HTTP server'
    http_server.server_close()

def main(argv):
    rest_server(8081)

if __name__ == '__main__':
    main(sys.argv[1:])
