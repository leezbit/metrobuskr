"""Sensor platform for Gyeonggi Bus arrivals."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import Arrival
from .const import (
    CONF_SELECTED_ROUTES,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
)
from .coordinator import GGBusCoordinator


@dataclass(frozen=True, slots=True)
class GGBusMetricDescription:
    """Description for per-route metric entity."""

    key: str
    name_suffix: str
    icon: str
    value_fn: Callable[[Arrival], Any]
    code_fn: Callable[[Arrival], Any] | None = None
    unit: str | None = None


METRICS: tuple[GGBusMetricDescription, ...] = (
    GGBusMetricDescription(
        key="arrival_1",
        name_suffix="1번째 도착예정",
        icon="mdi:clock-outline",
        unit="분",
        value_fn=lambda arrival: arrival.predict_time_1,
    ),
    GGBusMetricDescription(
        key="location_1",
        name_suffix="1번째 전 정류장",
        icon="mdi:map-marker-distance",
        unit="번째 전",
        value_fn=lambda arrival: arrival.location_no_1,
    ),
    GGBusMetricDescription(
        key="low_plate_1",
        name_suffix="1번째 저상버스",
        icon="mdi:wheelchair-accessibility",
        value_fn=lambda arrival: _low_floor_text(arrival.low_plate_1),
        code_fn=lambda arrival: arrival.low_plate_1,
    ),
    GGBusMetricDescription(
        key="arrival_2",
        name_suffix="2번째 도착예정",
        icon="mdi:clock-fast",
        unit="분",
        value_fn=lambda arrival: arrival.predict_time_2,
    ),
    GGBusMetricDescription(
        key="location_2",
        name_suffix="2번째 전 정류장",
        icon="mdi:map-marker-distance",
        unit="번째 전",
        value_fn=lambda arrival: arrival.location_no_2,
    ),
    GGBusMetricDescription(
        key="low_plate_2",
        name_suffix="2번째 저상버스",
        icon="mdi:wheelchair-accessibility",
        value_fn=lambda arrival: _low_floor_text(arrival.low_plate_2),
        code_fn=lambda arrival: arrival.low_plate_2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up bus arrival sensors based on a config entry."""
    coordinator: GGBusCoordinator = entry.runtime_data
    selected_route_ids = entry.options.get(CONF_SELECTED_ROUTES, [])

    registry = er.async_get(hass)
    valid_unique_ids = {f"{entry.entry_id}_api_status"}
    for route_id in selected_route_ids:
        for metric in METRICS:
            valid_unique_ids.add(f"{entry.entry_id}_{route_id}_{metric.key}")

    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id and reg_entry.unique_id.startswith(f"{entry.entry_id}_"):
            if reg_entry.unique_id not in valid_unique_ids:
                registry.async_remove(reg_entry.entity_id)

    device_registry = dr.async_get(hass)
    station_id = entry.data[CONF_STATION_ID]
    selected_set = set(selected_route_ids)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain != DOMAIN:
                continue
            prefix = f"{station_id}_"
            if identifier.startswith(prefix):
                route_id = identifier[len(prefix) :]
                if route_id not in selected_set:
                    device_registry.async_remove_device(device.id)
                break

    entities: list[SensorEntity] = [GGBusApiStatusSensor(coordinator, entry)]
    entities.extend(
        GGBusRouteMetricSensor(coordinator, entry, route_id, metric)
        for route_id in selected_route_ids
        for metric in METRICS
    )
    async_add_entities(entities)


class GGBusApiStatusSensor(CoordinatorEntity[GGBusCoordinator], SensorEntity):
    """Expose API status and last error for easier troubleshooting."""

    _attr_icon = "mdi:api"

    def __init__(self, coordinator: GGBusCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_api_status"
        self._attr_name = "API 상태"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to parent station device."""
        station_id = self._entry.data[CONF_STATION_ID]
        station_name = self._entry.data[CONF_STATION_NAME]
        return DeviceInfo(
            identifiers={(DOMAIN, station_id)},
            name=station_name,
            manufacturer="Gyeonggi-do",
            model="Bus Stop",
        )

    @property
    def native_value(self) -> str:
        return _api_status_text(_effective_api_status(self.coordinator))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status_code = _effective_api_status(self.coordinator)
        success_at = self.coordinator.last_success_at
        attempt_at = self.coordinator.last_attempt_at
        error_at = self.coordinator.last_error_at
        now_utc = dt_util.utcnow()
        seconds_since_last_success: int | None = None
        seconds_since_last_attempt: int | None = None
        if success_at is not None:
            seconds_since_last_success = int((now_utc - success_at).total_seconds())
        if attempt_at is not None:
            seconds_since_last_attempt = int((now_utc - attempt_at).total_seconds())
        return {
            "status_code": status_code,
            "raw_api_status": self.coordinator.last_api_status,
            "last_api_error": self.coordinator.last_api_error,
            "last_success_at": success_at.isoformat() if success_at else None,
            "last_attempt_at": attempt_at.isoformat() if attempt_at else None,
            "last_error_at": error_at.isoformat() if error_at else None,
            "seconds_since_last_success": seconds_since_last_success,
            "seconds_since_last_attempt": seconds_since_last_attempt,
            "consecutive_error_count": self.coordinator.consecutive_error_count,
            "total_success_count": self.coordinator.total_success_count,
            "total_error_count": self.coordinator.total_error_count,
            "last_error_type": self.coordinator.last_error_type,
            "is_stale": status_code == "stale",
            "current_poll_seconds": int(self.coordinator.update_interval.total_seconds()),
            "recommended_action": _recommended_action(status_code),
        }

    @property
    def available(self) -> bool:
        """Always show status sensor even during API errors."""
        return True


class GGBusRouteMetricSensor(CoordinatorEntity[GGBusCoordinator], SensorEntity):
    """Represent one metric for a specific route at a station."""

    def __init__(
        self,
        coordinator: GGBusCoordinator,
        entry: ConfigEntry,
        route_id: str,
        metric: GGBusMetricDescription,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._route_id = route_id
        self._metric = metric
        self._attr_unique_id = f"{entry.entry_id}_{route_id}_{metric.key}"
        self._attr_name = metric.name_suffix
        self._attr_has_entity_name = True
        self._attr_icon = metric.icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return bus device metadata (child of station device)."""
        arrival = self._arrival
        route_name = _route_label(arrival.route_name if arrival else self._route_id)
        station_id = self._entry.data[CONF_STATION_ID]
        station_name = self._entry.data[CONF_STATION_NAME]

        return DeviceInfo(
            identifiers={(DOMAIN, f"{station_id}_{self._route_id}")},
            name=route_name,
            manufacturer="Gyeonggi-do",
            model="Bus Route",
            via_device=(DOMAIN, station_id),
            suggested_area=station_name,
        )

    @property
    def native_value(self) -> Any:
        """Return metric value for the route."""
        arrival = self._arrival
        if arrival is None:
            return None

        value = self._metric.value_fn(arrival)
        if self._metric.key in {"arrival_1", "arrival_2"} and value is None:
            return "대기 중"
        if self._metric.key in {"location_1", "location_2"} and value is None:
            return "정보없음"
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        arrival = self._arrival
        if arrival is None:
            return None
        if self._metric.code_fn is None:
            return None
        return {"raw_low_plate_code": self._metric.code_fn(arrival)}

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit only when state is numeric."""
        if self._metric.unit is None:
            return None
        value = self.native_value
        return self._metric.unit if isinstance(value, (int, float)) else None

    @property
    def available(self) -> bool:
        """Entity availability follows route presence in station payload."""
        return super().available and self._arrival is not None

    @property
    def _arrival(self) -> Arrival | None:
        return self.coordinator.data.get(self._route_id) if self.coordinator.data else None


def _route_label(route_name: str) -> str:
    cleaned = str(route_name).strip()
    if not cleaned:
        return "노선"
    return cleaned


def _low_floor_text(code: str | None) -> str:
    mapping = {
        "0": "일반",
        "1": "저상",
        "2": "2층",
        "5": "전세",
        "6": "예약",
        "7": "트롤리",
    }
    return mapping.get(code, "정보없음")


def _api_status_text(status: str | None) -> str:
    mapping = {
        "ok": "정상",
        "unknown": "알 수 없음",
        "stale": "데이터 지연",
        "auth_error": "인증 실패",
        "quota_exceeded": "할당량 초과",
        "api_error": "API 응답 오류",
        "unknown_error": "알 수 없는 오류",
    }
    if not status:
        return "알 수 없음"
    return mapping.get(status, status)


def _effective_api_status(coordinator: GGBusCoordinator) -> str:
    status = coordinator.last_api_status
    if status != "ok":
        return status

    success_at = coordinator.last_success_at
    if success_at is None:
        return "unknown"

    stale_after_seconds = max(
        int(coordinator.update_interval.total_seconds()) * 3,
        600,
    )
    age_seconds = (dt_util.utcnow() - success_at).total_seconds()
    if age_seconds >= stale_after_seconds:
        return "stale"
    return "ok"


def _recommended_action(status_code: str) -> str:
    recommendations = {
        "ok": "정상 수집 중입니다.",
        "stale": "최근 데이터가 지연되었습니다. 잠시 후 다시 확인하세요.",
        "auth_error": "API 서비스키 유효기간/권한을 확인하세요.",
        "quota_exceeded": "일일 호출량 초과 상태입니다. 익일에 재시도하세요.",
        "api_error": "공공 API 응답 상태를 확인하고 잠시 후 재시도하세요.",
        "unknown_error": "통합을 재시작하고 로그를 확인하세요.",
        "unknown": "첫 수집 대기 중입니다.",
    }
    return recommendations.get(status_code, "로그를 확인하세요.")
