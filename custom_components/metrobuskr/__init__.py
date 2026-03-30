"""The regional bus integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_REGION,
    CONF_SELECTED_ROUTES,
    CONF_STATION_CODE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_REGION,
    DOMAIN,
    PLATFORMS,
    REGION_MANUFACTURERS,
)
from .coordinator import GGBusCoordinator

GGBusConfigEntry = ConfigEntry[GGBusCoordinator]


def _station_identifier(region: str, station_id: str) -> str:
    return f"{region}:{station_id}"


async def async_setup_entry(hass: HomeAssistant, entry: GGBusConfigEntry) -> bool:
    """Set up bus arrivals from a config entry."""
    coordinator = GGBusCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    region = entry.data.get(CONF_REGION, DEFAULT_REGION)
    station_id = entry.data[CONF_STATION_ID]
    station_name = entry.data[CONF_STATION_NAME]
    station_code = entry.data[CONF_STATION_CODE]
    station_identifier = _station_identifier(region, station_id)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, station_identifier)},
        manufacturer=REGION_MANUFACTURERS.get(region, "Public Transit"),
        model="Bus Stop",
        name=f"{station_name} ({station_code})",
    )

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GGBusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: GGBusConfigEntry) -> None:
    """Reload integration when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: GGBusConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removing child bus devices by updating selected routes."""
    region = entry.data.get(CONF_REGION, DEFAULT_REGION)
    station_id = entry.data[CONF_STATION_ID]
    station_identifier = _station_identifier(region, station_id)
    target_route_id: str | None = None

    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue

        if identifier == station_identifier:
            await hass.config_entries.async_remove(entry.entry_id)
            return True

        prefix = f"{station_identifier}_"
        if identifier.startswith(prefix):
            target_route_id = identifier[len(prefix) :]
            break

    if not target_route_id:
        return False

    current_selected = entry.options.get(CONF_SELECTED_ROUTES, [])
    if target_route_id not in current_selected:
        return True

    updated = [rid for rid in current_selected if rid != target_route_id]
    if not updated:
        await hass.config_entries.async_remove(entry.entry_id)
        return True

    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_SELECTED_ROUTES: updated,
        },
    )
    await hass.config_entries.async_reload(entry.entry_id)
    return True
