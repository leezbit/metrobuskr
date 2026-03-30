"""Constants for the regional bus integration."""

from __future__ import annotations

DOMAIN = "ggbus"
PLATFORMS = ["sensor"]

REGION_GYEONGGI = "gyeonggi"
REGION_SEOUL = "seoul"
REGION_OPTIONS: tuple[str, str] = (REGION_GYEONGGI, REGION_SEOUL)
REGION_LABELS: dict[str, str] = {
    REGION_GYEONGGI: "경기도",
    REGION_SEOUL: "서울특별시",
}
REGION_MANUFACTURERS: dict[str, str] = {
    REGION_GYEONGGI: "Gyeonggi-do",
    REGION_SEOUL: "Seoul Metropolitan Government",
}

CONF_REGION = "region"
CONF_API_KEY = "api_key"
CONF_STATION_CODE = "station_code"
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_SELECTED_ROUTES = "selected_routes"
CONF_SCAN_INTERVAL_SECONDS = "scan_interval_seconds"

DEFAULT_REGION = REGION_GYEONGGI
DEFAULT_SCAN_INTERVAL_SECONDS = 90
