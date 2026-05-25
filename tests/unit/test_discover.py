from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from flower_vending.runtime.discover import format_discovery


from flower_vending.runtime.discover import (
    discover_arduino,
    find_esp32_port,
    find_jcm_port,
    list_com_ports,
)


class MockPort:
    def __init__(self, device: str, description: str, hwid: str, manufacturer: str = "") -> None:
        self.device = device
        self.description = description
        self.hwid = hwid
        self.manufacturer = manufacturer


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


@patch("flower_vending.runtime.discover.list_com_ports")
def test_format_discovery_empty_dict(mock_list_com_ports: MagicMock) -> None:
    """Test format_discovery with an empty dictionary for standard format."""
    mock_list_com_ports.return_value = []
    results: dict[str, Any] = {}

    expected_lines = [
        "--- COM Port Discovery ---",
        "ESP32 not found. Available ports:",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results) == expected_output


def test_format_discovery_empty_dict_legacy() -> None:
    """Test format_discovery with an empty dictionary for legacy format."""
    results: dict[str, Any] = {}

    expected_lines = [
        "Device Discovery Report",
        "=======================",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output


def test_format_discovery_legacy_nested_dict() -> None:
    """Test format_discovery with deeply nested dicts (though the function flattens 1 level)."""
    results: dict[str, Any] = {"Config": {"Settings": {"Depth": "Deep"}}}

    expected_lines = [
        "Device Discovery Report",
        "=======================",
        "\nConfig:",
        "  Settings: {'Depth': 'Deep'}",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output


def test_format_discovery_legacy_malformed_data() -> None:
    """Test format_discovery handles malformed/None data properly in legacy format."""
    results: dict[str, Any] = {"NullCategory": None, "IntCategory": 123}

    expected_lines = [
        "Device Discovery Report",
        "=======================",
        "\nNullCategory:",
        "  None",
        "\nIntCategory:",
        "  123",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output


@patch("serial.tools.list_ports.comports")
def test_find_esp32_port_found_cp210(mock_comports: MagicMock) -> None:
    """Test finding an ESP32 port with cp210 description."""
    mock_comports.return_value = [
        MockPort("COM1", "Standard Serial", "HWID1"),
        MockPort("COM2", "CP210x USB to UART Bridge", "USB VID:PID=10C4:EA60"),
    ]
    assert find_esp32_port() == "COM2"


@patch("serial.tools.list_ports.comports")
def test_find_esp32_port_found_ch34(mock_comports: MagicMock) -> None:
    """Test finding an ESP32 port with ch34 description."""
    mock_comports.return_value = [
        MockPort("COM3", "USB-SERIAL CH340", "USB VID:PID=1A86:7523"),
    ]
    assert find_esp32_port() == "COM3"


@patch("serial.tools.list_ports.comports")
def test_find_esp32_port_found_silab(mock_comports: MagicMock) -> None:
    """Test finding an ESP32 port with silab description."""
    mock_comports.return_value = [
        MockPort("COM4", "Silicon Labs CP210x", "USB VID:PID=10C4:EA60"),
    ]
    assert find_esp32_port() == "COM4"


@patch("serial.tools.list_ports.comports")
def test_find_esp32_port_not_found(mock_comports: MagicMock) -> None:
    """Test finding an ESP32 port when no matching port exists."""
    mock_comports.return_value = [
        MockPort("COM1", "Standard Serial", "HWID1"),
        MockPort("COM5", "Bluetooth Link", "BTHENUM"),
    ]
    assert find_esp32_port() is None


@patch("serial.tools.list_ports.comports")
def test_find_esp32_port_exception(mock_comports: MagicMock) -> None:
    """Test find_esp32_port handles exceptions gracefully."""
    mock_comports.side_effect = Exception("Mock exception")
    assert find_esp32_port() is None


@patch("serial.tools.list_ports.comports")
def test_find_jcm_port_found_jcm(mock_comports: MagicMock) -> None:
    """Test finding a JCM port with jcm description."""
    mock_comports.return_value = [
        MockPort("COM1", "Standard Serial", "HWID1"),
        MockPort("COM2", "JCM DBV-300", "USB VID:PID=0000:0000"),
    ]
    assert find_jcm_port() == "COM2"


@patch("serial.tools.list_ports.comports")
def test_find_jcm_port_found_dbv(mock_comports: MagicMock) -> None:
    """Test finding a JCM port with dbv description."""
    mock_comports.return_value = [
        MockPort("COM3", "DBV Validator", "USB VID:PID=0000:0001"),
    ]
    assert find_jcm_port() == "COM3"


@patch("serial.tools.list_ports.comports")
def test_find_jcm_port_not_found(mock_comports: MagicMock) -> None:
    """Test finding a JCM port when no matching port exists."""
    mock_comports.return_value = [
        MockPort("COM1", "Standard Serial", "HWID1"),
        MockPort("COM5", "Bluetooth Link", "BTHENUM"),
    ]
    assert find_jcm_port() is None


@patch("serial.tools.list_ports.comports")
def test_find_jcm_port_exception(mock_comports: MagicMock) -> None:
    """Test find_jcm_port handles exceptions gracefully."""
    mock_comports.side_effect = Exception("Mock exception")
    assert find_jcm_port() is None


@patch("serial.tools.list_ports.comports")
def test_list_com_ports(mock_comports: MagicMock) -> None:
    """Test list_com_ports successfully converts port objects to dictionaries."""
    mock_comports.return_value = [
        MockPort("COM1", "Standard Serial", "HWID1", "Manufacturer A"),
        MockPort("COM2", "Virtual Serial", "HWID2", None),  # Test None manufacturer
    ]

    result = list_com_ports()

    assert len(result) == 2
    assert result[0] == {
        "device": "COM1",
        "description": "Standard Serial",
        "hwid": "HWID1",
        "manufacturer": "Manufacturer A",
    }
    assert result[1] == {
        "device": "COM2",
        "description": "Virtual Serial",
        "hwid": "HWID2",
        "manufacturer": "",
    }


@patch("serial.tools.list_ports.comports")
def test_list_com_ports_exception(mock_comports: MagicMock) -> None:
    """Test list_com_ports handles exceptions gracefully and returns empty list."""
    mock_comports.side_effect = Exception("Mock exception")

    result = list_com_ports()

    assert result == []


@pytest.mark.asyncio
@patch("flower_vending.runtime.discover.list_com_ports")
@patch("serial.Serial")
async def test_discover_arduino_found(
    mock_serial: MagicMock, mock_list_com_ports: MagicMock
) -> None:
    """Test successful discovery of an Arduino/ESP32 device."""
    mock_list_com_ports.return_value = [
        {
            "device": "COM3",
            "description": "ESP32 Device",
            "hwid": "HWID",
            "manufacturer": "Espressif",
        }
    ]

    mock_instance = MagicMock()
    # Mock readline to return the correct byte sequence
    mock_instance.readline.return_value = b"BUTTON_PRESSED"
    mock_serial.return_value = mock_instance

    result = await discover_arduino()

    assert result == {
        "port": "COM3",
        "description": "ESP32 Device",
        "response": "BUTTON_PRESSED",
        "type": "arduino_esp32",
    }

    # Verify serial was initialized correctly
    mock_serial.assert_called_once_with(
        port="COM3",
        baudrate=115200,
        timeout=1.0,
        write_timeout=0.5,
    )
    mock_instance.write.assert_called_once_with(b"STATUS\n")
    mock_instance.close.assert_called_once()


@pytest.mark.asyncio
@patch("flower_vending.runtime.discover.list_com_ports")
@patch("serial.Serial")
async def test_discover_arduino_not_found(
    mock_serial: MagicMock, mock_list_com_ports: MagicMock
) -> None:
    """Test when no Arduino/ESP32 is discovered."""
    mock_list_com_ports.return_value = [
        {
            "device": "COM1",
            "description": "Standard Serial",
            "hwid": "HWID",
            "manufacturer": "Unknown",
        }
    ]

    mock_instance = MagicMock()
    # Mock readline to return an invalid response
    mock_instance.readline.return_value = b"UNKNOWN"
    mock_serial.return_value = mock_instance

    result = await discover_arduino()

    assert result == {
        "port": "",
        "description": "not found",
        "response": "",
        "type": "unknown",
    }


@pytest.mark.asyncio
@patch("flower_vending.runtime.discover.list_com_ports")
@patch("serial.Serial")
async def test_discover_arduino_readline_exception(
    mock_serial: MagicMock, mock_list_com_ports: MagicMock
) -> None:
    """Test when readline throws an exception."""
    mock_list_com_ports.return_value = [
        {
            "device": "COM1",
            "description": "Standard Serial",
            "hwid": "HWID",
            "manufacturer": "Unknown",
        }
    ]

    mock_instance = MagicMock()
    # Mock readline to throw exception
    mock_instance.readline.side_effect = Exception("Read timeout")
    mock_serial.return_value = mock_instance

    result = await discover_arduino()

    assert result == {
        "port": "",
        "description": "not found",
        "response": "",
        "type": "unknown",
    }
    # verify close was still called
    mock_instance.close.assert_called_once()


@pytest.mark.asyncio
@patch("flower_vending.runtime.discover.list_com_ports")
@patch("serial.Serial")
async def test_discover_arduino_serial_init_exception(
    mock_serial: MagicMock, mock_list_com_ports: MagicMock
) -> None:
    """Test when serial.Serial throws an exception during initialization."""
    mock_list_com_ports.return_value = [
        {
            "device": "COM1",
            "description": "Standard Serial",
            "hwid": "HWID",
            "manufacturer": "Unknown",
        }
    ]

    # Mock Serial init to throw exception
    mock_serial.side_effect = Exception("Access denied")

    result = await discover_arduino()

    assert result == {
        "port": "",
        "description": "not found",
        "response": "",
        "type": "unknown",
    }


def test_format_discovery_legacy_list() -> None:
    """Test format_discovery with legacy format flag for list values."""
    results: dict[str, Any] = {"Devices": ["Device A", "Device B"]}

    expected_lines = [
        "Device Discovery Report",
        "=======================",
        "\nDevices:",
        "  - Device A",
        "  - Device B",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output


def test_format_discovery_legacy_dict() -> None:
    """Test format_discovery with legacy format flag for dict values."""
    results: dict[str, Any] = {"Config": {"Port": "COM1", "Baudrate": 115200}}

    expected_lines = [
        "Device Discovery Report",
        "=======================",
        "\nConfig:",
        "  Port: COM1",
        "  Baudrate: 115200",
    ]
    expected_output = "\n".join(expected_lines)

    assert format_discovery(results, legacy_format=True) == expected_output
