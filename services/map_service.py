"""Folium map construction boundary."""

import folium

from config.settings import get_settings


def create_trip_map(locations: list[dict], *, zoom_start: int = 6) -> folium.Map:
    """Create a Folium map from normalized location dictionaries."""
    if locations:
        center = [locations[0]["latitude"], locations[0]["longitude"]]
    else:
        center = [0.0, 0.0]
    settings = get_settings()
    if not settings.non_commercial_mode:
        map_view = folium.Map(location=center, zoom_start=zoom_start, tiles=None, control_scale=True)
    else:
        map_view = folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles=settings.osm_tile_url,
            attr=settings.osm_tile_attribution,
            control_scale=True,
        )
    for location in locations:
        folium.Marker(
            [location["latitude"], location["longitude"]],
            tooltip=location.get("name", "Trip location"),
        ).add_to(map_view)
    return map_view
