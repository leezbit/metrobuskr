"""API client for Gyeonggi bus data.go.kr endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from aiohttp import ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)

STATION_ENDPOINTS = (
    "http://apis.data.go.kr/6410000/busstationservice/v2/getBusStationListv2",
    "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationListv2",
)

ARRIVAL_ENDPOINTS = (
    "http://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2",
    "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2",
)


class GGBusApiError(Exception):
    """Base API error."""


class GGBusAuthError(GGBusApiError):
    """Authentication/authorization error."""


class GGBusStationNotFoundError(GGBusApiError):
    """Raised when a station code cannot be resolved."""


class GGBusQuotaError(GGBusApiError):
    """Raised when API daily quota is exceeded."""


@dataclass(slots=True)
class Station:
    """A resolved bus station."""

    station_id: str
    station_name: str
    station_no: str


@dataclass(slots=True)
class Arrival:
    """Arrival data for a route at a station."""

    route_id: str
    route_name: str
    location_no_1: int | None
    predict_time_1: int | None
    location_no_2: int | None
    predict_time_2: int | None
    flag: str | None
    low_plate_1: str | None
    low_plate_2: str | None
    plate_no_1: str | None
    plate_no_2: str | None


class GGBusApi:
    """Thin async API wrapper."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key.strip()

    async def resolve_station_by_code(self, station_code: str) -> Station:
        """Resolve stop 5-digit code to stationId and name."""
        query = station_code.strip()
        if not query:
            raise GGBusApiError("Station code is empty")

        params_candidates = [
            {"serviceKey": key, "keyword": query, "format": "json"}
            for key in self._service_key_candidates()
        ]

        payload = await self._request_with_fallback(
            list(STATION_ENDPOINTS),
            params_candidates,
        )

        items = _extract_items(payload)
        query_digits = _digits_only(query)
        best_match: Station | None = None

        for item in items:
            station_no_raw = str(item.get("stationNo") or item.get("stationno") or "").strip()
            mobile_no_raw = str(item.get("mobileNo") or item.get("mobileno") or "").strip()
            station_id = str(item.get("stationId") or item.get("stationid") or "").strip()
            station_name = str(item.get("stationName") or item.get("stationname") or query).strip()
            if not station_id:
                continue

            station_no_digits = _digits_only(station_no_raw)
            mobile_no_digits = _digits_only(mobile_no_raw)

            matches_exact = query_digits in {station_no_digits, mobile_no_digits}
            matches_suffix = (
                bool(query_digits)
                and (
                    station_no_digits.endswith(query_digits)
                    or mobile_no_digits.endswith(query_digits)
                    or query_digits.endswith(station_no_digits)
                    or query_digits.endswith(mobile_no_digits)
                )
            )

            if matches_exact:
                return Station(station_id=station_id, station_name=station_name, station_no=station_no_raw or mobile_no_raw)

            if matches_suffix and best_match is None:
                best_match = Station(station_id=station_id, station_name=station_name, station_no=station_no_raw or mobile_no_raw)

        if best_match is not None:
            return best_match

        raise GGBusStationNotFoundError(f"Station code {station_code} was not found")

    async def get_station_arrivals(self, station_id: str) -> dict[str, Arrival]:
        """Fetch all arrivals for a station in a single API call."""
        params_candidates = [
            {"serviceKey": key, "stationId": station_id, "format": "json"}
            for key in self._service_key_candidates()
        ]

        payload = await self._request_with_fallback(
            list(ARRIVAL_ENDPOINTS),
            params_candidates,
        )

        items = _extract_items(payload)
        arrivals: dict[str, Arrival] = {}
        for item in items:
            route_id = str(item.get("routeId") or item.get("routeid") or "").strip()
            route_name = str(item.get("routeName") or item.get("routename") or "").strip()
            if not route_id or not route_name:
                continue

            arrivals[route_id] = Arrival(
                route_id=route_id,
                route_name=route_name,
                location_no_1=_to_int(item.get("locationNo1")),
                predict_time_1=_to_int(item.get("predictTime1")),
                location_no_2=_to_int(item.get("locationNo2")),
                predict_time_2=_to_int(item.get("predictTime2")),
                flag=_to_optional_str(item.get("flag")),
                low_plate_1=_to_low_plate_code(_first_present(item, "lowPlate1", "lowplate1", "low_plate_1")),
                low_plate_2=_to_low_plate_code(_first_present(item, "lowPlate2", "lowplate2", "low_plate_2")),
                plate_no_1=_to_optional_str(item.get("plateNo1")),
                plate_no_2=_to_optional_str(item.get("plateNo2")),
            )

        return arrivals

    def _service_key_candidates(self) -> list[str]:
        """Try raw and decoded values to avoid key-format mismatch."""
        candidates = [self._api_key]
        if "%" in self._api_key:
            decoded = unquote(self._api_key)
            if decoded != self._api_key:
                candidates.append(decoded)
        return candidates

    async def _request_with_fallback(
        self,
        endpoints: list[str],
        params_candidates: list[dict[str, str]],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for endpoint in endpoints:
            for params in params_candidates:
                try:
                    return await self._request(endpoint, params)
                except GGBusAuthError:
                    raise
                except GGBusApiError as err:
                    last_error = err
                    _LOGGER.debug("GGBus endpoint failed %s params=%s err=%s", endpoint, params, err)

        raise GGBusApiError(str(last_error) if last_error else "Unknown API failure")

    async def _request(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._session.get(endpoint, params=params, timeout=15)
            text = await response.text()
        except ClientError as err:
            raise GGBusApiError(f"Connection error: {err}") from err

        if response.status in (401, 403):
            raise GGBusAuthError("API key is not authorized")
        if response.status == 429:
            raise GGBusQuotaError("API quota exceeded (HTTP 429)")
        if response.status >= 400:
            raise GGBusApiError(f"API HTTP error {response.status}")

        payload = _parse_payload(text)
        result_code = _extract_result_code(payload)
        if result_code and result_code not in {"0", "00", "INFO-000", "SUCCESS"}:
            normalized = result_code.upper()
            if "SERVICE_KEY" in normalized or "AUTH" in normalized:
                raise GGBusAuthError(result_code)
            if "LIMIT" in normalized or "EXCEED" in normalized or "QUOTA" in normalized:
                raise GGBusQuotaError(result_code)
            raise GGBusApiError(result_code)

        return payload


def _parse_payload(text: str) -> dict[str, Any]:
    body = text.strip()
    if not body:
        raise GGBusApiError("Empty response")

    if body.startswith("{"):
        return json.loads(body)

    try:
        root = ET.fromstring(body)
    except ET.ParseError as err:
        raise GGBusApiError("Unsupported payload") from err

    parsed = _xml_to_dict(root)
    if isinstance(parsed, str):
        raise GGBusApiError("Unexpected scalar payload")
    return parsed


def _xml_to_dict(element: ET.Element) -> dict[str, Any] | str:
    if len(element) == 0:
        return (element.text or "").strip()

    values: dict[str, Any] = {}
    for child in element:
        value = _xml_to_dict(child)
        if child.tag in values:
            existing = values[child.tag]
            if not isinstance(existing, list):
                values[child.tag] = [existing, value]
            else:
                existing.append(value)
        else:
            values[child.tag] = value
    return values


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response_obj = payload.get("response") or payload.get("ServiceResult") or payload
    msg_body = response_obj.get("msgBody") if isinstance(response_obj, dict) else {}

    if not isinstance(msg_body, dict):
        return []

    for key in ("busArrivalList", "busStationList", "itemList", "item"):
        value = msg_body.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]

    return []


def _extract_result_code(payload: dict[str, Any]) -> str | None:
    paths = [
        ((payload.get("response") or {}).get("msgHeader") or {}).get("resultCode"),
        ((payload.get("ServiceResult") or {}).get("msgHeader") or {}).get("resultCode"),
        ((payload.get("msgHeader") or {}).get("resultCode")),
        (payload.get("cmmMsgHeader") or {}).get("returnReasonCode"),
    ]
    for value in paths:
        if value is not None:
            return str(value)
    return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _to_low_plate_code(value: Any) -> str | None:
    if value in (None, ""):
        return None

    normalized = str(value).strip().upper()
    if normalized in {"0", "1", "2", "5", "6", "7"}:
        return normalized

    # 일부 환경에서 bool 계열 문자열이 섞여 들어오는 경우 보정
    if normalized in {"TRUE", "Y", "YES", "ON"}:
        return "1"
    if normalized in {"FALSE", "N", "NO", "OFF"}:
        return "0"
    return None


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized if normalized else None


def _digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None

