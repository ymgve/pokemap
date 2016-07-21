Pokemap - shows Pokemon near you

This is my version of the Pokemon GO map, based on the [Pokemon API demo](https://github.com/leegao/pokemongo-api-demo/tree/simulation) and [waishda's Pokemon Map](https://github.com/AHAAAAAAA/PokemonGo-Map).

Features:
- Allows you to simply click on the map to see the Pokemon at that location
- Keeps track of previously seen Pokemon spawn locations
- Shows Pokestops and Gyms, with highlighted Lured Pokestops
- Uses my own hackish Protobuf implementation because why not make things harder
- Uses proper S2 [get_edge_neighbors()](http://s2sphere.readthedocs.io/en/latest/api.html#s2sphere.CellId.get_edge_neighbors) to calculate surrounding cells instead of the flawed 10 prev/next used in lots of other pokemaps

In contrast with other maps, this map only does a single API request, which means it will only show Pokemon in a 100m radius around your location (Indicated by the red circle) which is the maximum the API lets you see. Other maps use multiple requests to cover a larger area, which means higher latency, more server load on the Pokemon GO servers and either overlapping areas in requests or small holes between circular areas. I decided to let the users themselves do the covering, and as previous Pokemon locations are shown the users can better decide which points are of interest.

API calls have been stripped of all seemingly unneccesary and undocumented "mystery" fields. This makes the calls blatantly different from the ones sent by the legitimate Pokemon GO client app, which might result in this map stopping worker sooner than later.

Requires python modules `requests`, `s2sphere`, `flask`, `flask_googlemaps`.