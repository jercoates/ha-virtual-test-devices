from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN

class VirtualTestDevicesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Virtual Test Devices."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(step_id="user")

        return self.async_create_entry(title="Virtual Test Devices", data={})