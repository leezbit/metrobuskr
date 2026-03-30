"""API clients for Gyeonggi/Seoul bus endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from aiohttp import ClientError, ClientSession

from .const import REGION_GYEONGGI, REGION_SEOUL

_LOGGER = logging.getLogger(__name__)

GYEONGGI_STATION_ENDPOINTS = (
    "http://apis.data.go.kr/6410000/busstationservice/v2/getBusStationListv2",
    "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationListv2",
)

GYEONGGI_ARRIVAL_ENDPOINTS = (
    "http://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2",
    "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2",
)

SEOUL_STATION_ENDPOINTS = (
    "http://ws.bus.go.kr/api/rest/stationinfo/getStationByUid",
    "https://ws.bus.go.kr/api/rest/stationinfo/getStationByUid",
)

SEOUL_ARRIVAL_ENDPOINTS = (
    "http://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId",
    "https://ws.bus.go.kr/api/rest/arrive/getLowArrInfoByStId",
)


class BusApiError(Exception):
    """Base API error."""


class BusAuthError(BusApiError):
    """Authentication/authorization error."""


class BusStationNotFoundError(BusApiError):
    """Raised when a station code cannot be resolved."""


class BusQuotaError(BusApiError):
    """Raised when API daily quota is exceeded."""


# Backward-compatible aliases for existing imports.
GGBusApiError = BusApiError
GGBusAuthError = BusAuthError
GGBusStationNotFoundError = BusStationNotFoundError
GGBusQuotaError = BusQuotaError


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


class BusApi:
    """Thin async API wrapper with region-aware endpoint mapping."""

    def __init__(self, session: ClientSession, api_key: str, region: str = REGION_GYEONGGI) -> None:
        self._session = session
        self._api_key = api_key.strip()
        self._region = region

    async def resolve_station_by_code(self, station_code: str) -> Station:
        if self._region == REGION_SEOUL:
            return await self._resolve_station_by_code_seoul(station_code)
        return await self._resolve_station_by_code_gyeonggi(station_code)

    async def get_station_arrivals(self, station_id: str) -> dict[str, Arrival]:
        if self._region == REGION_SEOUL:
            return await self._get_station_arrivals_seoul(station_id)
        return await self._get_station_arrivals_gyeonggi(station_id)

    async def _resolve_station_by_code_gyeonggi(self, station_code: str) -> Station:
        query = station_code.strip()
        if not query:
            raise BusApiError("Station code is empty")

        params_candidates = [
            {"serviceKey": key, "keyword": query, "format": "json"}
            for key in self._service_key_candidates()
        ]

        payload = await self._request_with_fallback(list(GYEONGGI_STATION_ENDPOINTS), params_candidates)
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
            matches_suffix = bool(query_digits) and (
                station_no_digits.endswith(query_digits)
                or mobile_no_digits.endswith(query_digits)
                or query_digits.endswith(station_no_digits)
                or query_digits.endswith(mobile_no_digits)
            )

            if matches_exact:
                return Station(station_id=station_id, station_name=station_name, station_no=station_no_raw or mobile_no_raw)

            if matches_suffix and best_match is None:
                best_match = Station(station_id=station_id, station_name=station_name, station_no=station_no_raw or mobile_no_raw)

        if best_match is not None:
            return best_match
        raise BusStationNotFoundError(f"Station code {station_code} was not found")

    async def _resolve_station_by_code_seoul(self, station_code: str) -> Station:
        query_digits = _digits_only(station_code)
        if not query_digits:
            raise BusApiError("Station code is empty")

        params_candidates = []
        for key in self._service_key_candidates():
            params_candidates.append({"ServiceKey": key, "arsId": query_digits})
            params_candidates.append({"serviceKey": key, "arsId": query_digits})

        payload = await self._request_with_fallback(list(SEOUL_STATION_ENDPOINTS), params_candidates)
        items = _extract_items(payload)

        for item in items:
            ars_id = str(item.get("arsId") or item.get("arsid") or "").strip()
            station_id = str(item.get("stId") or item.get("stationId") or item.get("stationid") or "").strip()
            station_name = str(item.get("stNm") or item.get("stationNm") or item.get("stationName") or "").strip()
            if not station_id:
                continue

            if _digits_only(ars_id) == query_digits or not ars_id:
                return Station(
                    station_id=station_id,
                    station_name=station_name or station_code,
                    station_no=ars_id or station_code,
                )

        raise BusStationNotFoundError(f"Station code {station_code} was not found")

    async def _get_station_arrivals_gyeonggi(self, station_id: str) -> dict[str, Arrival]:
        params_candidates = [
            {"serviceKey": key, "stationId": station_id, "format": "json"}
            for key in self._service_key_candidates()
        ]
        payload = await self._request_with_fallback(list(GYEONGGI_ARRIVAL_ENDPOINTS), params_candidates)
        items = _extract_items(payload)
        return _arrivals_from_gyeonggi_items(items)

    async def _get_station_arrivals_seoul(self, station_id: str) -> dict[str, Arrival]:
        params_candidates = []
        for key in self._service_key_candidates():
            params_candidates.append({"ServiceKey": key, "stId": station_id})
            params_candidates.append({"serviceKey": key, "stId": station_id})

        payload = await self._request_with_fallback(list(SEOUL_ARRIVAL_ENDPOINTS), params_candidates)
        items = _extract_items(payload)
        return _arrivals_from_seoul_items(items)

    def _service_key_candidates(self) -> list[str]:
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
                except BusAuthError:
                    raise
                except BusApiError as err:
                    last_error = err
                    _LOGGER.debug("Bus endpoint failed %s params=%s err=%s", endpoint, params, err)

        raise BusApiError(str(last_error) if last_error else "Unknown API failure")

    async def _request(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._session.get(endpoint, params=params, timeout=15)
            text = await response.text()
        except ClientError as err:
            raise BusApiError(f"Connection error: {err}") from err

        if response.status in (401, 403):
            raise BusAuthError("API key is not authorized")
        if response.status == 429:
            raise BusQuotaError("API quota exceeded (HTTP 429)")
        if response.status >= 400:
            raise BusApiError(f"API HTTP error {response.status}")

        payload = _parse_payload(text)
        result_code = _extract_result_code(payload)
        if result_code and result_code not in {"0", "00", "INFO-000", "SUCCESS"}:
            normalized = result_code.upper()
            if "SERVICE_KEY" in normalized or "AUTH" in normalized:
                raise BusAuthError(result_code)
            if "LIMIT" in normalized or "EXCEED" in normalized or "QUOTA" in normalized:
                raise BusQuotaError(result_code)
            raise BusApiError(result_code)

        return payload


# Backward-compatible alias
GGBusApi = BusApi


def _arrivals_from_gyeonggi_items(items: list[dict[str, Any]]) -> dict[str, Arrival]:
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


def _arrivals_from_seoul_items(items: list[dict[str, Any]]) -> dict[str, Arrival]:
    arrivals: dict[str, Arrival] = {}
    for item in items:
        route_id = str(item.get("busRouteId") or item.get("busrouteid") or "").strip()
        route_name = str(item.get("rtNm") or item.get("rtnm") or "").strip()
        if not route_id or not route_name:
            continue

        arrivals[route_id] = Arrival(
            route_id=route_id,
            route_name=route_name,
            location_no_1=_to_int(_extract_station_distance(item.get("arrmsg1") or item.get("arrMsg1"))),
            predict_time_1=_to_int(_first_present(item, "traTime1") or _extract_minutes(item.get("arrmsg1") or item.get("arrMsg1"))),
            location_no_2=_to_int(_extract_station_distance(item.get("arrmsg2") or item.get("arrMsg2"))),
            predict_time_2=_to_int(_first_present(item, "traTime2") or _extract_minutes(item.get("arrmsg2") or item.get("arrMsg2"))),
            flag=_to_optional_str(item.get("arrmsgSec1") or item.get("arrmsg1") or item.get("arrMsg1")),
            low_plate_1=_to_low_plate_code_from_bus_type(_first_present(item, "busType1", "busTypeNm1")),
            low_plate_2=_to_low_plate_code_from_bus_type(_first_present(item, "busType2", "busTypeNm2")),
            plate_no_1=_to_optional_str(item.get("plainNo1")),
            plate_no_2=_to_optional_str(item.get("plainNo2")),
        )

    return arrivals


def _extract_minutes(value: Any) -> int | None:
    text = _to_optional_str(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _extract_station_distance(value: Any) -> int | None:
    text = _to_optional_str(value)
    if text is None:
        return None
    markers = ("전", "번째", "정류장")
    if not any(marker in text for marker in markers):
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _to_low_plate_code_from_bus_type(value: Any) -> str | None:
    text = _to_optional_str(value)
    if text is None:
        return None
    if "저상" in text:
        return "1"
    if text in {"0", "1", "2", "5", "6", "7"}:
        return text
    return None


def _parse_payload(text: str) -> dict[str, Any]:
    body = text.strip()
    if not body:
        raise BusApiError("Empty response")

    if body.startswith("{"):
        return json.loads(body)

    try:
        root = ET.fromstring(body)
    except ET.ParseError as err:
        raise BusApiError("Unsupported payload") from err

    parsed = _xml_to_dict(root)
    if isinstance(parsed, str):
        raise BusApiError("Unexpected scalar payload")
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

    for key in ("busArrivalList", "busStationList", "itemList", "item", "ServiceResult"):
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
