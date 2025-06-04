this project makes use of sea routes python library to get the predefined routes as defined in the marnet network file.
it then tries to adjust the route to start from the given coordinates

this project creates a dockenarized python web service where you can call a url like : 
http://0.0.0.0:8000/route?start_lat=51.286833&start_lng=-135.219667&end_lat=35.62004694102301&end_lng=139.79918003082278&units=naut&route_type=guided 


start_lat,star_lng are the start cordinates
end_lat, end_lng are the end coordinates

units is the unit the is sued to measure distance
route_type :
- guided: will try to start the route from the given position
- empty will return the best route between guided and the closer sea route in the manet network
