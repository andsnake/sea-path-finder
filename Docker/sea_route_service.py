from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import searoute as sr
from typing import Optional, List, Tuple
from shapely.geometry import LineString, Point
from geopy.distance import geodesic
import math

app = FastAPI()

def _bearing(p1, p2):
    """Calculate bearing from p1 to p2 in degrees."""
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])

    d_lon = lon2 - lon1
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(d_lon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360

def _ang_diff(a, b):
    """Smallest difference between two angles (degrees)."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d

def calculate_distance(p1, p2, units="naut"):
    """Calculate distance between two points."""
    dist_km = geodesic((p1[1], p1[0]), (p2[1], p2[0])).kilometers
    
    if units == "naut":
        return dist_km * 0.539957  # km to nautical miles
    elif units == "km":
        return dist_km
    else:  # miles
        return dist_km * 0.621371

def project_point_onto_route(point, route_coords):
    """
    Project a point (lng, lat) onto the route line.
    Returns:
        - index of segment where projection occurs
        - fraction along segment (0-1)
        - projected point coordinates (lng, lat)
        - distance from point to projected point (km)
    """
    line = LineString(route_coords)
    p = Point(point)
    proj_dist = line.project(p)
    proj_point = line.interpolate(proj_dist)

    accumulated = 0
    for i in range(len(route_coords) - 1):
        seg = LineString([route_coords[i], route_coords[i+1]])
        seg_length = seg.length
        if accumulated + seg_length >= proj_dist:
            frac = (proj_dist - accumulated) / seg_length if seg_length > 0 else 0
            proj_coords = (proj_point.x, proj_point.y)
            distance_km = geodesic((point[1], point[0]), (proj_coords[1], proj_coords[0])).kilometers
            return i, frac, proj_coords, distance_km
        accumulated += seg_length

    proj_coords = (proj_point.x, proj_point.y)
    distance_km = geodesic((point[1], point[0]), (proj_coords[1], proj_coords[0])).kilometers
    return len(route_coords) - 2, 1.0, proj_coords, distance_km

def find_optimal_merge_point(ship_position, reference_route, max_deviation_km=200):
    """
    Find the optimal point on the reference route to merge with,
    considering both distance and route efficiency.
    """
    best_merge_idx = None
    best_score = float('inf')
    best_merge_point = None
    
    # First, find the point on the route that's closest to our ship
    min_dist = float('inf')
    closest_idx = 0
    
    for i, route_point in enumerate(reference_route):
        dist_km = geodesic((ship_position[1], ship_position[0]), (route_point[1], route_point[0])).kilometers
        if dist_km < min_dist:
            min_dist = dist_km
            closest_idx = i
    
    # Now look for merge points starting from the closest point and going forward
    # This ensures we don't go backwards on the route
    for i in range(closest_idx, len(reference_route)):
        route_point = reference_route[i]
        
        # Distance from ship to this route point
        dist_km = geodesic((ship_position[1], ship_position[0]), (route_point[1], route_point[0])).kilometers
        
        # Be more lenient with distance, but prefer closer points
        if dist_km > max_deviation_km:
            continue
        
        # Calculate bearing from ship to this point vs bearing to destination
        bearing_to_point = _bearing(ship_position, route_point)
        bearing_to_dest = _bearing(ship_position, reference_route[-1])
        bearing_diff = _ang_diff(bearing_to_point, bearing_to_dest)
        
        # Score: prioritize points that are in the right direction
        # Lower score is better
        score = dist_km + (bearing_diff * 2)  # Penalty for wrong direction
        
        if score < best_score:
            best_score = score
            best_merge_idx = i
            best_merge_point = route_point
    
    # If no good merge point found, try to find ANY reasonable point
    if best_merge_idx is None:
        # Just use a point that's reasonably forward on the route
        forward_idx = min(closest_idx + len(reference_route) // 4, len(reference_route) - 1)
        best_merge_idx = forward_idx
        best_merge_point = reference_route[forward_idx]
    
    return best_merge_idx, best_merge_point

def create_optimized_route_from_position(ship_position, destination, reference_route=None, units="naut"):
    """
    Create an optimized route from the ship's current position to destination,
    using a reference route as a guideline but creating a new optimal path.
    """
    if reference_route is None:
        # Get reference route from approximate positions
        try:
            ref_feature = sr.searoute(ship_position, destination, units=units)
            reference_route = ref_feature["geometry"]["coordinates"]
        except Exception as e:
            raise Exception(f"Could not generate reference route: {str(e)}")
    
    # Find optimal merge point on the reference route
    merge_idx, merge_point = find_optimal_merge_point(ship_position, reference_route)
    
    if merge_idx is None:
        # If no good merge point found, create direct route
        route_coords = [ship_position, destination]
    else:
        # Create route: ship -> merge point -> rest of reference route
        route_coords = [ship_position]
        
        # Add the merge point if it's different from ship position
        merge_dist = geodesic((ship_position[1], ship_position[0]), (merge_point[1], merge_point[0])).meters
        if merge_dist > 100:  # More than 100 meters difference
            route_coords.append(merge_point)
        
        # Add the rest of the reference route from merge point onwards
        route_coords.extend(reference_route[merge_idx + 1:])
        
        # Ensure destination is the final point
        if route_coords[-1] != destination:
            route_coords.append(destination)
    
    # Calculate total distance
    total_distance = 0
    for i in range(len(route_coords) - 1):
        total_distance += calculate_distance(route_coords[i], route_coords[i+1], units)
    
    # Build the result
    result = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": route_coords
        },
        "properties": {
            "length": total_distance,
            "units": units,
            "duration_hours": total_distance / 24.0 if units == "naut" else total_distance / 44.448,
            "route_type": "optimized_from_position",
            "merge_point_index": merge_idx if merge_idx is not None else None
        }
    }
    
    return result

def create_guided_route(ship_position, destination, units="naut", waypoint_spacing=3):
    """
    Create a route that follows the general path of the reference route
    but starts from the exact ship position and optimizes the path.
    """
    # Get the reference route between similar points to get the network path
    try:
        ref_feature = sr.searoute(ship_position, destination, units=units)
        reference_coords = ref_feature["geometry"]["coordinates"]
    except Exception as e:
        raise Exception(f"Could not generate reference route: {str(e)}")
    
    # If reference route is too simple (just 2 points), it means searoute 
    # couldn't find a proper sea route, so we need to be more creative
    if len(reference_coords) <= 2:
        # Try to get a route between nearby major ports/points
        try:
            # Create offset points to try to get a better reference route
            offset_origin = [ship_position[0] + 0.1, ship_position[1] + 0.1]
            offset_dest = [destination[0] - 0.1, destination[1] - 0.1]
            alt_feature = sr.searoute(offset_origin, offset_dest, units=units)
            if len(alt_feature["geometry"]["coordinates"]) > 2:
                reference_coords = alt_feature["geometry"]["coordinates"]
        except:
            pass
    
    # Start building the guided route
    new_coords = [ship_position]
    
    if len(reference_coords) > 2:
        # We have a proper reference route to follow
        
        # Find a good starting point on the reference route (not the first point)
        # Look for a point that's in a reasonable direction from the ship
        best_start_idx = 1
        best_bearing_diff = 180
        
        ship_to_dest_bearing = _bearing(ship_position, destination)
        
        for i in range(1, min(len(reference_coords), 5)):  # Check first few points
            bearing_to_ref_point = _bearing(ship_position, reference_coords[i])
            bearing_diff = _ang_diff(bearing_to_ref_point, ship_to_dest_bearing)
            
            if bearing_diff < best_bearing_diff:
                best_bearing_diff = bearing_diff
                best_start_idx = i
        
        # Add strategic waypoints from the reference route
        for i in range(best_start_idx, len(reference_coords), waypoint_spacing):
            new_coords.append(reference_coords[i])
        
        # Make sure we don't miss any important waypoints near the end
        if len(reference_coords) > waypoint_spacing:
            # Add the last few points if we missed them
            last_added_idx = best_start_idx + ((len(reference_coords) - best_start_idx - 1) // waypoint_spacing) * waypoint_spacing
            if last_added_idx < len(reference_coords) - 2:
                new_coords.append(reference_coords[-2])  # Second to last point
    
    # Always ensure we end at the exact destination
    if new_coords[-1] != destination:
        new_coords.append(destination)
    
    # Remove any duplicate consecutive points
    filtered_coords = [new_coords[0]]
    for i in range(1, len(new_coords)):
        if new_coords[i] != filtered_coords[-1]:
            filtered_coords.append(new_coords[i])
    
    # Calculate total distance
    total_distance = 0
    for i in range(len(filtered_coords) - 1):
        total_distance += calculate_distance(filtered_coords[i], filtered_coords[i+1], units)
    
    result = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": filtered_coords
        },
        "properties": {
            "length": total_distance,
            "units": units,
            "duration_hours": total_distance / 24.0 if units == "naut" else total_distance / 44.448,
            "route_type": "guided",
            "reference_points_used": len(reference_coords),
            "waypoints_created": len(filtered_coords)
        }
    }
    
    return result

@app.get("/route")
async def get_route(
    start_lat: float = Query(..., description="Start latitude"),
    start_lng: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lng: float = Query(..., description="End longitude"),
    units: Optional[str] = Query("naut", description="Distance units (default nautical miles)"),
    course: Optional[float] = Query(None, description="Current course in degrees (0-359)"),
    heading_tol: Optional[float] = Query(45.0, description="Heading tolerance in degrees"),
    route_type: Optional[str] = Query("guided", description="Route type: 'guided', 'optimized', or 'original'")
):
    ship_position = [start_lng, start_lat]
    destination = [end_lng, end_lat]

    try:
        if route_type == "optimized":
            feature = create_optimized_route_from_position(ship_position, destination, units=units)
        elif route_type == "guided":
            feature = create_guided_route(ship_position, destination, units=units)
        else:  # original
            feature = sr.searoute(ship_position, destination, units=units)
        
        coords = feature["geometry"]["coordinates"]
        
        # Apply course filtering if specified
        if course is not None and len(coords) > 1:
            i_keep = 1
            while i_keep < len(coords):
                brg = _bearing(coords[0], coords[i_keep])
                if _ang_diff(brg, course) <= heading_tol:
                    break
                i_keep += 1
            
            # Rebuild route with course filtering
            filtered_coords = [coords[0]] + coords[i_keep:]
            if filtered_coords[-1] != destination:
                filtered_coords.append(destination)
            
            # Recalculate distance for filtered route
            total_distance = 0
            for i in range(len(filtered_coords) - 1):
                total_distance += calculate_distance(filtered_coords[i], filtered_coords[i+1], units)
            
            feature["geometry"]["coordinates"] = filtered_coords
            feature["properties"]["length"] = total_distance
            feature["properties"]["duration_hours"] = total_distance / 24.0 if units == "naut" else total_distance / 44.448

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing route: {str(e)}")

    return JSONResponse(content=feature)

@app.get("/route/compare")
async def compare_routes(
    start_lat: float = Query(..., description="Start latitude"),
    start_lng: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lng: float = Query(..., description="End longitude"),
    units: Optional[str] = Query("naut", description="Distance units (default nautical miles)")
):
    """
    Compare different routing strategies: original, optimized, and guided.
    """
    ship_position = [start_lng, start_lat]
    destination = [end_lng, end_lat]
    
    results = {}
    
    try:
        # Original searoute
        original = sr.searoute(ship_position, destination, units=units)
        results["original"] = original
        
        # Optimized route
        optimized = create_optimized_route_from_position(ship_position, destination, units=units)
        results["optimized"] = optimized
        
        # Guided route
        guided = create_guided_route(ship_position, destination, units=units)
        results["guided"] = guided
        
        # Direct route for comparison
        direct_distance = calculate_distance(ship_position, destination, units)
        results["direct"] = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [ship_position, destination]
            },
            "properties": {
                "length": direct_distance,
                "units": units,
                "duration_hours": direct_distance / 24.0 if units == "naut" else direct_distance / 44.448,
                "route_type": "direct"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing routes: {str(e)}")
    
    return JSONResponse(content=results)
