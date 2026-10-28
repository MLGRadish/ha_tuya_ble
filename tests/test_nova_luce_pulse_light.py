"""Tests for the Nova Luce CCT ceiling light (pilbpgf9wisbac1o)."""

from unittest.mock import AsyncMock, Mock, call

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_ble.cloud import HASSTuyaBLEDeviceManager
from custom_components.tuya_ble.const import DOMAIN
from custom_components.tuya_ble.devices import (
    TuyaBLECoordinator,
    TuyaBLEData,
    TuyaBLEDevice,
)
from custom_components.tuya_ble.light import TuyaBLEPulseLight, async_setup_entry
from custom_components.tuya_ble.tuya_ble.manager import TuyaBLEDeviceCredentials
from custom_components.tuya_ble.tuya_ble.tuya_ble import TuyaBLEDataPointType

SWITCH_DP = 20
BRIGHTNESS_DP = 22


@pytest.fixture(autouse=True)
def no_pulse_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TuyaBLEPulseLight, "PULSE_SECONDS", 0)


async def _setup_light(hass: HomeAssistant) -> tuple[TuyaBLEDevice, TuyaBLEPulseLight]:
    entry = MockConfigEntry(domain=DOMAIN, data={"address": "C0:F8:53:05:FA:52"})
    entry.add_to_hass(hass)

    manager = HASSTuyaBLEDeviceManager(hass, entry.options.copy())
    device = TuyaBLEDevice(manager, BLEDevice("C0:F8:53:05:FA:52", "TY", {}))
    device._device_info = TuyaBLEDeviceCredentials(
        uuid="uuid123",
        local_key="0123456789abcdef",
        device_id="bf0908d0b7f90b2b4aw8lm",
        category="xdd",
        product_id="pilbpgf9wisbac1o",
        device_name="Nova Luce",
        product_model="WIFI-BLE-CCT-CBU-IPEX",
        product_name="WIFI-BLE-CCT-CBU-IPEX",
        functions=[],
        status_range=[],
    )
    device._send_datapoints = AsyncMock()

    coordinator = TuyaBLECoordinator(hass, device)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = TuyaBLEData(
        title="Nova Luce",
        device=device,
        manager=manager,
        product=None,
        coordinator=coordinator,
    )

    add_entities = Mock()
    await async_setup_entry(hass, entry, add_entities)
    entities = add_entities.call_args.args[0]
    # One light: the category's night light DP doesn't exist on this product.
    assert len(entities) == 1
    entity = entities[0]
    entity.async_write_ha_state = Mock()
    coordinator._async_handle_connect()
    return device, entity


async def test_pulse_light_setup(hass: HomeAssistant) -> None:
    """The light is a pulse light with brightness and colour temperature."""
    _, entity = await _setup_light(hass)

    assert isinstance(entity, TuyaBLEPulseLight)
    assert entity.assumed_state is True
    assert entity.supported_color_modes == {ColorMode.COLOR_TEMP}
    assert entity.is_on is False


async def test_pulse_light_turn_on_and_off_pulse_the_switch(
    hass: HomeAssistant,
) -> None:
    """On and off each send the switch on then off, and only on a change."""
    device, entity = await _setup_light(hass)

    await entity.async_turn_on()
    await hass.async_block_till_done()
    assert device._send_datapoints.call_args_list == [
        call([SWITCH_DP]),
        call([SWITCH_DP]),
    ]
    assert device.datapoints[SWITCH_DP].value is False
    assert entity.is_on is True

    device._send_datapoints.reset_mock()
    await entity.async_turn_on()
    await hass.async_block_till_done()
    device._send_datapoints.assert_not_called()

    await entity.async_turn_off()
    await hass.async_block_till_done()
    assert device._send_datapoints.call_args_list == [
        call([SWITCH_DP]),
        call([SWITCH_DP]),
    ]
    assert entity.is_on is False

    device._send_datapoints.reset_mock()
    await entity.async_turn_off()
    await hass.async_block_till_done()
    device._send_datapoints.assert_not_called()


async def test_pulse_light_brightness_skips_the_switch(hass: HomeAssistant) -> None:
    """Brightness while on is sent without any switch write."""
    device, entity = await _setup_light(hass)
    await entity.async_turn_on()
    await hass.async_block_till_done()
    device._send_datapoints.reset_mock()

    await entity.async_turn_on(**{ATTR_BRIGHTNESS: 255})
    await hass.async_block_till_done()
    device._send_datapoints.assert_called_once_with([BRIGHTNESS_DP])
    assert device.datapoints[BRIGHTNESS_DP].value == 1000


async def test_pulse_light_on_reports_color_temp_mode(hass: HomeAssistant) -> None:
    """With the work mode never reported, the light is in colour temp mode.

    It doesn't support HS, and Home Assistant rejects an on light reporting
    an unsupported colour mode.
    """
    _, entity = await _setup_light(hass)
    await entity.async_turn_on()
    await hass.async_block_till_done()

    assert entity.color_mode == ColorMode.COLOR_TEMP


async def test_pulse_light_ignores_switch_reports(hass: HomeAssistant) -> None:
    """The device reporting the switch doesn't change the tracked state."""
    device, entity = await _setup_light(hass)
    await entity.async_turn_on()
    await hass.async_block_till_done()

    device.datapoints._update_from_device(
        SWITCH_DP, 0, 0, TuyaBLEDataPointType.DT_BOOL, False
    )
    assert entity.is_on is True
