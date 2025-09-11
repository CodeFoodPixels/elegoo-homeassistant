"""Frontend for elegoo printer integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig

from custom_components.elegoo_printer.const import DOMAIN
from custom_components.elegoo_printer.public import locate_dir

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_register_frontend(hass: HomeAssistant, url: str) -> None:
    """Register the frontend."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig("/elegoo-ui", locate_dir(), cache_headers=False)]
    )
    if DOMAIN not in hass.data.get("frontend_panels", {}):
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Elegoo Web UI",
            sidebar_icon="mdi:printer-3d",
            frontend_url_path=DOMAIN,
            config={
                "_panel_custom": {
                    "name": "elegoo-frontend",
                    "embed_iframe": True,
                    "trust_external": False,
                    "module_url": "/elegoo-ui/entrypoint.js",
                },
                "elegoo": {"url": url},
            },
            require_admin=True,
        )


async def async_unregister_frontend(hass: HomeAssistant) -> None:
    """Unregister the frontend."""
    async_remove_panel(hass, DOMAIN)
