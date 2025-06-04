# sea_route_service.py
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import searoute as sr  # pip install searoute
import logging

app = FastAPI(
    title="SeaRoute API",
    version="1.0.0",
    description="Return the shortest sea-only route between two points in GeoJSON."
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _validate_lat(lat: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("Latitude must be between -90 and 90 degrees.")

def _validate_lng(lng: float) -> None:
    if not (-180.0 <= lng <= 180.0):
        raise ValueError("Longitude must be between -180 and 180 degrees.")


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/route", response_class=JSONResponse, summary="Shortest sea route")
async def get_route(
    start_lat: float = Query(..., description="Start latitude, decimal degrees"),
    start_lng: float = Query(..., description="Start longitude, decimal degrees"),
    end_lat:   float = Query(..., description="End latitude, decimal degrees"),
    end_lng:   float = Query(..., description="End longitude, decimal degrees"),
    units: str = Query("km",
                       description="Unit for length property (km, mi, naut, etc.)")
):
    """
    Compute and return the shortest sea-only path as a **GeoJSON Feature**.

    The algorithm and global maritime graph come from the open-source
    *searoute* package. :contentReference[oaicite:0]{index=0}
    """
    try:
        _validate_lat(start_lat)
        _validate_lat(end_lat)
        _validate_lng(start_lng)
        _validate_lng(end_lng)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    origin      = [start_lng, start_lat]  # searoute expects [lon, lat]
    destination = [end_lng,   end_lat]

    try:
        feature = sr.searoute(origin, destination, units=units)
    except Exception as exc:  # network disconnected, points on land, etc.
        logging.exception("SeaRoute failed:")
        raise HTTPException(
            status_code=500,
            detail=f"Sea routing failed: {exc}"
        )

    # FastAPI will serialise dictionaries automatically, but we set the
    # content-type explicitly for GeoJSON aware clients.
    return JSONResponse(
        content=feature,
        media_type="application/geo+json"
    )


@app.get("/health", summary="Liveness probe")
async def health():
    """Simple health-check endpoint."""
    return {"status": "ok"}

