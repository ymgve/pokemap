import binascii
import json
import os
import struct
import time
import traceback

import requests
from s2sphere import *
from flask import Flask, render_template
from flask_googlemaps import GoogleMaps
from flask_googlemaps import Map

import protobuf

config = json.load(open("config.json", "rb"))

def f2i(f):
    return struct.unpack('<Q', struct.pack('<d', f))[0]

def i2f(i):
    return struct.unpack('<d', struct.pack('<Q', i))[0]

def debug(s):
    if config["debug"] == 1:
        print(s)
        
def recursive_walk(cellids, center, depth):
    cellids.add(center.id())
    if depth == 0:
        return
        
    for neigh in center.get_edge_neighbors():
        recursive_walk(cellids, neigh, depth - 1)
        
class PokemonAPI(object):
    def __init__(self):
        self.api_url = 'https://pgorelease.nianticlabs.com/plfe/rpc'
        self.login_url = 'https://sso.pokemon.com/sso/login?service=https%3A%2F%2Fsso.pokemon.com%2Fsso%2Foauth2.0%2FcallbackAuthorize'
        self.login_oauth = 'https://sso.pokemon.com/sso/oauth2.0/accessToken'

        self.session = requests.session()
        self.session.headers.update({'User-Agent': 'Niantic App'})
        self.session.verify = False

        self.loginstatus = 0
        
    def login_ptc(self):
        if not os.path.isfile(self.tokenfile):
            debug("Getting access token")
            head = {'User-Agent': 'niantic'}
            res = self.session.get(self.login_url, headers=head)
            jdata = json.loads(res.content)

            data = {
                'lt': jdata['lt'],
                'execution': jdata['execution'],
                '_eventId': 'submit',
                'username': self.username,
                'password': self.password,
            }
            
            res = self.session.post(self.login_url, data=data, headers=head, timeout=15)
            ticket = res.history[0].headers['Location'].split("?ticket=")[1]
            debug("Got ticket %s" % repr(ticket))
            
            data = {
                'client_id': 'mobile-app_pokemon-go',
                'redirect_uri': 'https://www.nianticlabs.com/pokemongo/error',
                'client_secret': 'w8ScCUXJQc6kXKw8FiOhd8Fixzht18Dq3PEVkUCP5ZPxtgyWsbTvWHFLm2wNY0JR',
                'grant_type': 'refresh_token',
                'code': ticket,
            }
            res = self.session.post(self.login_oauth, data=data, timeout=15)
            self.access_token = res.content.split("access_token=")[1].split("&")[0]
            debug("Got access_token %s" % repr(self.access_token))
            
            open(self.tokenfile, "wb").write(self.access_token)
        
        self.access_token = open(self.tokenfile, "rb").read().strip()
        self.loginstatus = 1
        
    def get_api_endpoint_and_new_auth(self):
        if not os.path.isfile(self.endpointfile):
            debug("Getting endpoint")
            
            jwt_pb = protobuf.ProtoSerializer()
            jwt_pb.insert(1, 2, self.access_token)
            jwt_pb.insert(2, 0, 14)
            
            auth_pb = protobuf.ProtoSerializer()
            auth_pb.insert(1, 2, "ptc")
            auth_pb.insert(2, 2, jwt_pb.message)
            
            pb2 = protobuf.ProtoSerializer()
            pb2.insert(1, 0, 2)
            
            pb = protobuf.ProtoSerializer()
            pb.insert(1, 0, 2)          # different gives "incompatible protocol version"
            pb.insert(4, 2, pb2.message)
            pb.insert(10, 2, auth_pb.message)      # missing gives "client was not authenticated"
            pb.insert(12, 0, 989)       # different gives "incompatible protocol version"
            
            res = self.api_call(self.api_url, pb)
            endpoint_url = "https://" + res[3] + "/rpc"
            debug("Got endpoint " + endpoint_url)
            newauth = res[7]
            
            open(self.endpointfile, "wb").write("%s|%s" % (endpoint_url, binascii.b2a_hex(newauth)))
            
        self.endpoint_url, newauth = open(self.endpointfile, "rb").read().strip().split("|")
        self.newauth = binascii.a2b_hex(newauth)
        self.loginstatus = 2

    def authed_api_call(self, pb):
        if self.loginstatus == 0:
            self.login_ptc()
        
        if self.loginstatus == 1:
            self.get_api_endpoint_and_new_auth()
    
        pb.insert(11, 2, self.newauth)      # missing gives "client was not authenticated"
    
        return self.api_call(self.endpoint_url, pb)
        
    def api_call(self, url, pb):
        debug("APICALL: querying " + url)
        res = self.session.post(url, data=pb.message, verify=False, timeout=15)
        debug("APICALL: raw response " + repr(res.content))
        res = protobuf.ProtoDeserializer(res.content).deserialize()
        debug("APICALL: protobuf response " + repr(res))
        if res[1] == 102:
            self.loginstatus = 0
            os.unlink(self.tokenfile)
            os.unlink(self.endpointfile)
            raise Exception("Session has timed out")
        return res

    def get_map_info(self, pokemarkers, pokestops, curr_lat, curr_long):
        for retries in xrange(3):
            try:
                cellids = set()
                center = CellId.from_lat_lng(LatLng.from_degrees(curr_lat, curr_long)).parent(15)
                recursive_walk(cellids, center, 2)
                
                debug("Number of cellids %d" % len(cellids))
                
                pb3 = protobuf.ProtoSerializer()
                for cellid in cellids:
                    pb3.insert(1, 0, cellid)
                    
                pb2 = protobuf.ProtoSerializer()
                pb2.insert(1, 0, 106)
                pb2.insert(2, 2, pb3.message)

                pb = protobuf.ProtoSerializer()
                pb.insert(1, 0, 2)          # different gives "incompatible protocol version"
                pb.insert(4, 2, pb2.message)
                pb.insert(7, 1, f2i(curr_lat))
                pb.insert(8, 1, f2i(curr_long))
                pb.insert(9, 1, f2i(0.0))   # altitude
                pb.insert(12, 0, 989)       # different gives "incompatible protocol version"
                
                res = self.authed_api_call(pb)
                res = protobuf.ProtoDeserializer(res[100]).deserialize(False, (1,))

                for current_cell in res[1]:
                    current_cell_pb = protobuf.ProtoDeserializer(current_cell).deserialize(False, (3,5))
                    debug("Current Cell protobuf %s" % repr(current_cell_pb))
                    debug("Current Cell center %s\n" % LatLng.from_point(Cell(CellId(current_cell_pb[1])).get_center()))
                    
                    if 5 in current_cell_pb:
                        for spawn in current_cell_pb[5]:
                            pb = protobuf.ProtoDeserializer(spawn).deserialize()
                            debug("Pokemon spawned at %s" % repr(pb))
                            pokespawn = pb[5]
                            pokeid = protobuf.ProtoDeserializer(pb[7]).deserialize()[2]
                            pokelat = i2f(pb[3])
                            pokelong = i2f(pb[4])
                            timeleft = pb[11] / 1000
                            open(self.pokeencountersfile, "ab").write("%s|%f|%f|%d|%d|%f|%f|%d\n" % (pokespawn, pokelat, pokelong, pokeid, timeleft, curr_lat, curr_long, int(time.time())))
                            
                    if 3 in current_cell_pb:
                        for stop in current_cell_pb[3]:
                            pb = protobuf.ProtoDeserializer(stop).deserialize()
                            debug("Pokestop info %s" % repr(pb))
                            
                            stopid = pb[1]
                            stoplat = i2f(pb[3])
                            stoplong = i2f(pb[4])
                            
                            if 9 in pb:
                                stoptype = 1
                            else:
                                stoptype = 2
                                
                            if stopid not in pokestops:
                                open(self.pokestopsfile, "ab").write("%s|%f|%f|%d|%f|%f|%d\n" % (stopid, stoplat, stoplong, stoptype, curr_lat, curr_long, int(time.time())))
                                print "new pokestop!", stopid, stoplat, stoplong
                                
                            pokestops[stopid] = stoplat, stoplong, stoptype, pb
                    
                    debug("\n")
                    
                return
                
            except Exception as e:
                print("EXCEPTION")
                traceback.print_exc()
                print("Retrying...")
                time.sleep(1)
                
        self.loginstatus = 0
        os.unlink(self.tokenfile)
        os.unlink(self.endpointfile)
        
        marker = {}
        marker["lat"] = curr_lat
        marker["lng"] = curr_long
        marker["title"] = "SERVER ERROR"
        marker["icon"] = "/static/icons/error.png"
        marker["zIndex"] = 99
        pokemarkers["ERROR"] = marker
        return

def create_app():
    app = Flask(__name__, template_folder='templates')

    GoogleMaps(app, key=config["google_maps_key"])
    return app


app = create_app()

@app.route('/')
@app.route('/map/<float:curr_lat>,<float:curr_long>,<int:zoomlevel>')
def mapview(curr_lat = None, curr_long = None, zoomlevel=17):
    pokemon_list = json.load(open('pokemon.json'))
    
    api = PokemonAPI()
    api.username = config["username"]
    api.password = config["password"]
    api.pokestopsfile = "data_pokestops.txt"
    api.pokeencountersfile = "data_pokemon_encounters.txt"
    api.tokenfile = "auth_token.txt"
    api.endpointfile = "auth_endpoint.txt"
    
    if curr_lat is None or curr_lat is None:
        curr_lat = config["default_lat"]
        curr_long = config["default_long"]
        
    pokemarkers = {}
    pokestops = {}
    
    if os.path.isfile(api.pokestopsfile):
        for line in open(api.pokestopsfile, "rb"):
            cols = line.strip().split("|")
            stopid = cols[0]
            stoplat = float(cols[1])
            stoplong = float(cols[2])
            stoptype = int(cols[3])
            pokestops[stopid] = (stoplat, stoplong, stoptype, None)
        
    api.get_map_info(pokemarkers, pokestops, curr_lat, curr_long)
    
    if os.path.isfile(api.pokeencountersfile):
        for line in open(api.pokeencountersfile, "rb"):
            cols = line.strip().split("|")
            pokespawn = cols[0]
            pokelat = float(cols[1])
            pokelong = float(cols[2])
            pokeid = int(cols[3])
            timeleft = int(cols[4])
            timedisc = int(cols[7])
            
            marker = {}
            marker["lat"] = pokelat
            marker["lng"] = pokelong
            
            realtimeleft = (timedisc + timeleft) - time.time()
            if realtimeleft > 86400:
                realtimeleft = (timedisc + 15*60) - time.time()
                
            if realtimeleft >= 0:
                pokename = pokemon_list[pokeid - 1]["Name"]
                marker["title"] = "[%d] %s discovered %d seconds ago, staying for %dm%ds" % (pokeid, pokename, time.time()-timedisc, realtimeleft / 60, realtimeleft % 60)
                marker["icon"] = "/static/icons/pokemon_better/%d.png" % pokeid
                marker["zIndex"] = 50
            else:
                marker["title"] = "Spawn point"
                marker["icon"] = "/static/icons/greenmarker.gif"
                marker["zIndex"] = 30
                
            marker["info"] = marker["title"] + '<br/><a href="/details/%s">More info about spawn point %s</a>' % (pokespawn, pokespawn)
            pokemarkers[pokespawn] = marker

    for stopid in pokestops:
        marker = {}
        stoplat, stoplong, stoptype, stopdata = pokestops[stopid]
        marker["lat"] = stoplat
        marker["lng"] = stoplong
        if stoptype == 1:
            if stopdata is not None and 12 in stopdata:
                marker["title"] = "Pokestop with Lure"
                marker["icon"] = "/static/icons/bluemarker.gif"
                marker["info"] = "Pokestop with Lure " + repr(stopdata)
                marker["zIndex"] = 10
            else:
                marker["title"] = "Pokestop"
                marker["icon"] = "/static/icons/bluemarker6px.gif"
                marker["info"] = "Pokestop " + repr(stopdata)
                marker["zIndex"] = 10
        elif stoptype == 2:
            marker["title"] = "Gym"
            marker["icon"] = "/static/icons/orangemarker6px.gif"
            marker["info"] = "Gym " + repr(stopdata)
            marker["zIndex"] = 10
        
        pokemarkers[stopid] = marker
        
    map = {}
    map["center"] = (curr_lat, curr_long)
    map["zoomlevel"] = zoomlevel
    map["pokemarkers"] = pokemarkers.values()
    return render_template('map.html', map=map)
    
@app.route('/details/<string:pokespawn>')
def pokespawn_details(pokespawn):
    pokemon_list = json.load(open('pokemon.json'))

    prev_despawn = 0
    prev_pokeid = -1
    
    res = "<table border=0>"
    for line in open("data_pokemon_encounters.txt", "rb"):
        cols = line.strip().split("|")
        ps = cols[0]
        pokelat = float(cols[1])
        pokelong = float(cols[2])
        pokeid = int(cols[3])
        timeleft = int(cols[4])
        timedisc = int(cols[7])
        if timeleft >= 86400:
            timeleft = 15*60
            
        if pokespawn != ps:
            continue
            
        if prev_pokeid == pokeid and timedisc < prev_despawn:
            continue
                
        prev_pokeid = pokeid
        prev_despawn = timedisc + timeleft
        
        pokename = pokemon_list[pokeid - 1]["Name"]
        icon = "/static/icons/pokemon_better/%d.png" % pokeid
        res += '<tr><td><img src="%s"> %s was here at %s timeleft %d<br/>' % (icon, pokename, time.ctime(timedisc), timeleft)
            
    res += "</table>"
    return res
    

if __name__ == '__main__':
    app.run(debug=True, threaded=True, host=config["server_host"], port=config["server_port"])
