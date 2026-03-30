"""Constants for the Gyeonggi Bus integration."""

from __future__ import annotations

DOMAIN = "ggbus"
PLATFORMS = ["sensor"]

CONF_API_KEY = "api_key"
CONF_STATION_CODE = "station_code"
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_SELECTED_ROUTES = "selected_routes"
CONF_SCAN_INTERVAL_SECONDS = "scan_interval_seconds"

DEFAULT_SCAN_INTERVAL_SECONDS = 90
