"""Config flow for regional bus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import BusApi, BusApiError, BusAuthError, BusQuotaError, BusStationNotFoundError
from .const import (
    CONF_API_KEY,
    CONF_REGION,
    CONF_SCAN_INTERVAL_SECONDS,
    CONF_SELECTED_ROUTES,
    CONF_STATION_CODE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    REGION_LABELS,
    REGION_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=30,
        max=600,
        step=10,
        mode=NumberSelectorMode.BOX,
    )
)


class GGBusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for regional bus arrivals."""

    VERSION = 1

    _region: str
    _api_key: str
    _station_code: str
    _station_id: str
    _station_name: str
    _route_options: dict[str, str]

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return GGBusOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._region = user_input[CONF_REGION]
            return await self.async_step_station()

        region_selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"label": REGION_LABELS[region], "value": region}
                    for region in REGION_OPTIONS
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_REGION, default=DEFAULT_REGION): region_selector,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            input_key = user_input[CONF_API_KEY].strip()
            self._api_key = input_key or self._default_api_key(self._region)
            self._station_code = user_input[CONF_STATION_CODE].strip()
            if not self._api_key:
                errors["base"] = "invalid_auth"
                api = None
            else:
                api = BusApi(async_get_clientsession(self.hass), self._api_key, region=self._region)

            try:
                if api is None:
                    raise BusAuthError
                station = await api.resolve_station_by_code(self._station_code)
                arrivals = await api.get_station_arrivals(station.station_id)
            except BusAuthError:
                errors["base"] = "invalid_auth"
            except BusStationNotFoundError:
                errors["base"] = "station_not_found"
            except BusQuotaError:
                errors["base"] = "quota_exceeded"
            except BusApiError as err:
                _LOGGER.warning("Bus setup failed region=%s station_code=%s: %s", self._region, self._station_code, err)
                errors["base"] = "cannot_connect"
            else:
                self._station_id = station.station_id
                self._station_name = station.station_name
                self._route_options = {
                    route_id: arrival.route_name
                    for route_id, arrival in sorted(
                        arrivals.items(), key=lambda item: item[1].route_name
                    )
                }
                if not self._route_options:
                    errors["base"] = "no_routes_found"
                else:
                    unique_id = f"{self._region}:{self._station_id}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return await self.async_step_routes()

        default_api = self._default_api_key(self._region)
        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=default_api): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_STATION_CODE): vol.All(str, vol.Length(min=4, max=6)),
            }
        )
        return self.async_show_form(step_id="station", data_schema=schema, errors=errors)

    async def async_step_routes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_routes: list[str] = user_input[CONF_SELECTED_ROUTES]
            scan_interval_seconds = int(user_input[CONF_SCAN_INTERVAL_SECONDS])
            if not selected_routes:
                errors["base"] = "no_route_selected"
            else:
                return self.async_create_entry(
                    title=f"{self._station_name} ({self._station_code})",
                    data={
                        CONF_REGION: self._region,
                        CONF_API_KEY: self._api_key,
                        CONF_STATION_CODE: self._station_code,
                        CONF_STATION_ID: self._station_id,
                        CONF_STATION_NAME: self._station_name,
                    },
                    options={
                        CONF_SELECTED_ROUTES: selected_routes,
                        CONF_SCAN_INTERVAL_SECONDS: scan_interval_seconds,
                    },
                )

        selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"label": _route_label(name), "value": route_id}
                    for route_id, name in self._route_options.items()
                ],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SELECTED_ROUTES): selector,
                vol.Required(
                    CONF_SCAN_INTERVAL_SECONDS,
                    default=DEFAULT_SCAN_INTERVAL_SECONDS,
                ): SCAN_INTERVAL_SELECTOR,
            }
        )

        return self.async_show_form(
            step_id="routes",
            data_schema=schema,
            errors=errors,
            description_placeholders={"station_name": self._station_name},
        )

    def _default_api_key(self, region: str) -> str:
        entries = self._async_current_entries()
        if not entries:
            return ""

        for entry in entries:
            if entry.data.get(CONF_REGION, DEFAULT_REGION) == region and entry.data.get(CONF_API_KEY):
                return str(entry.data[CONF_API_KEY])

        return entries[0].data.get(CONF_API_KEY, "")


def _route_label(route_name: str) -> str:
    cleaned = str(route_name).strip()
    if not cleaned:
        return "노선"
    if cleaned.endswith("번"):
        return cleaned
    return f"{cleaned}번"


class GGBusOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing config entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        api_key = self._entry.data[CONF_API_KEY]
        station_id = self._entry.data[CONF_STATION_ID]
        region = self._entry.data.get(CONF_REGION, DEFAULT_REGION)

        api = BusApi(async_get_clientsession(self.hass), api_key, region=region)
        try:
            arrivals = await api.get_station_arrivals(station_id)
        except BusAuthError:
            errors["base"] = "invalid_auth"
            arrivals = {}
        except BusQuotaError:
            errors["base"] = "quota_exceeded"
            arrivals = {}
        except BusApiError:
            errors["base"] = "cannot_connect"
            arrivals = {}

        route_options = {
            route_id: arrival.route_name
            for route_id, arrival in sorted(arrivals.items(), key=lambda item: item[1].route_name)
        }
        current_selected_raw = self._entry.options.get(CONF_SELECTED_ROUTES, [])
        current_selected = current_selected_raw if isinstance(current_selected_raw, list) else []

        if not route_options:
            route_options = {route_id: route_id for route_id in current_selected}

        if user_input is not None:
            selected_routes: list[str] = user_input[CONF_SELECTED_ROUTES]
            if not selected_routes:
                errors["base"] = "no_route_selected"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SELECTED_ROUTES: selected_routes,
                        CONF_SCAN_INTERVAL_SECONDS: int(user_input[CONF_SCAN_INTERVAL_SECONDS]),
                    },
                )

        if not route_options and not errors:
            errors["base"] = "no_routes_found"

        selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"label": _route_label(name), "value": route_id}
                    for route_id, name in route_options.items()
                ],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SELECTED_ROUTES,
                    default=[rid for rid in current_selected if rid in route_options] or current_selected,
                ): selector,
                vol.Required(
                    CONF_SCAN_INTERVAL_SECONDS,
                    default=int(self._entry.options.get(CONF_SCAN_INTERVAL_SECONDS, DEFAULT_SCAN_INTERVAL_SECONDS)),
                ): SCAN_INTERVAL_SELECTOR,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
