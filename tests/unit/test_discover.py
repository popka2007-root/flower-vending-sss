from typing import Any
from unittest.mock import MagicMock, patch

from flower_vending.runtime.discover import format_discovery


def test_format_discovery_found() -> None:
    """Test format_discovery when a port is successfully found."""
    results: dict[str, Any] = {
        "port": "COM3",
        "description": "ESP32 Device",
        "response": "STATUS OK",
    }

    expected_lines = [
        "--- COM Port Discovery ---",
        "ESP32 found on: COM3",
        "Description: ESP32 Device",
        "Status response: STATUS OK",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results) == expected_output


@patch("flower_vending.runtime.discover.list_com_ports")
def test_format_discovery_not_found(mock_list_com_ports: MagicMock) -> None:
    """Test format_discovery when no port is found, falling back to listing ports."""
    mock_list_com_ports.return_value = [
        {"device": "COM1", "description": "Standard Serial", "hwid": "HWID1"},
        {"device": "COM2", "description": "Virtual Serial", "hwid": "HWID2"},
    ]

    results: dict[str, Any] = {}

    expected_lines = [
        "--- COM Port Discovery ---",
        "ESP32 not found. Available ports:",
        "  COM1: Standard Serial (HWID1)",
        "  COM2: Virtual Serial (HWID2)",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results) == expected_output


def test_format_discovery_legacy_scalar() -> None:
    """Test format_discovery with legacy format flag for scalar values."""
    results: dict[str, Any] = {"Status": "OK"}

    expected_lines = ["Device Discovery Report", "=======================", "\nStatus:", "  OK"]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output


def test_format_discovery_legacy_list() -> None:
    """Test format_discovery with legacy format flag for list values."""
    results: dict[str, Any] = {"Devices": ["Device A", "Device B"]}

    expected_lines = ["Device Discovery Report", "=======================", "\nDevices:", "  - Device A", "  - Device B"]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output


def test_format_discovery_legacy_dict() -> None:
    """Test format_discovery with legacy format flag for dict values."""
    results: dict[str, Any] = {"Config": {"Port": "COM1", "Baudrate": 115200}}

    expected_lines = ["Device Discovery Report", "=======================", "\nConfig:", "  Port: COM1", "  Baudrate: 115200"]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output
