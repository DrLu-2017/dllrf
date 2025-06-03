import unittest
from unittest.mock import Mock, patch, AsyncMock # Added AsyncMock
import struct
import socket # Though not directly used by tests, the tested code uses it.
import asyncio # Added for AsyncClientApp tests

# Assuming LLRF_Soleil_Linux_NAT_LogicX_v4.3.py and reg_dict.py are in python path
from LLRF_Soleil_Linux_NAT_LogicX_v4_3 import llrf_graph_window
from async_register_client import AsyncClientApp # Added import
from reg_dict import reg_dict

# Qt classes for mocking UI elements if needed by AsyncClientApp's methods
from PyQt5.QtWidgets import QLineEdit, QComboBox, QStatusBar


class MockSocket:
    def __init__(self):
        self.sent_data = []
        self.responses = []
        self.timeout_val = None

    def send(self, data):
        self.sent_data.append(data)
        return len(data)

    def recv(self, size):
        if self.responses:
            return self.responses.pop(0)
        raise socket.timeout("Mock socket timeout")

    def gettimeout(self):
        return self.timeout_val

    def settimeout(self, val):
        self.timeout_val = val

    def reset(self):
        self.sent_data = []
        self.responses = []
        self.timeout_val = None

class TestRegisterConversion(unittest.TestCase):

    def setUp(self):
        self.qapplication_patch = patch('PyQt5.QtWidgets.QApplication')
        self.mock_qapplication = self.qapplication_patch.start()

        self.window = llrf_graph_window()
        self.mock_socket = MockSocket()
        self.window.mysocket = self.mock_socket
        self.window.map_start = 0x80000000
        self.window.update_msg = Mock()

    def tearDown(self):
        self.qapplication_patch.stop()

    def _get_offset_addr(self, reg_name): # Specific to llrf_graph_window's map_start logic
        address = reg_dict[reg_name]["address"]
        if self.window.map_start is not None and address >= self.window.map_start:
            return address - self.window.map_start
        return address

    def test_write_positive_float(self):
        reg_name = "REG_float_ph_shift1"
        value = 90.0
        self.mock_socket.responses.append(b"waiting")
        self.window.write_val_to_reg(reg_name, value)
        self.assertIn(b"5", self.mock_socket.sent_data)
        packed_val = struct.pack('>f', value)
        int_representation = int.from_bytes(packed_val, byteorder='big')
        offset_addr = self._get_offset_addr(reg_name)
        expected_msg = f"{int_representation},{hex(offset_addr)}".encode()
        self.assertIn(expected_msg, self.mock_socket.sent_data)
        self.window.update_msg.assert_called()

    def test_write_negative_float(self):
        reg_name = "REG_float_ph_shift0"
        value = -90.0
        self.mock_socket.responses.append(b"waiting")
        self.window.write_val_to_reg(reg_name, value)
        self.assertIn(b"5", self.mock_socket.sent_data)
        packed_val = struct.pack('>f', value)
        int_representation = int.from_bytes(packed_val, byteorder='big')
        offset_addr = self._get_offset_addr(reg_name)
        expected_msg = f"{int_representation},{hex(offset_addr)}".encode()
        self.assertIn(expected_msg, self.mock_socket.sent_data)

    def test_write_integer(self):
        reg_name = "REG_RF_Sequence"
        value = 123
        self.mock_socket.responses.append(b"waiting")
        self.window.write_val_to_reg(reg_name, value)
        self.assertIn(b"5", self.mock_socket.sent_data)
        offset_addr = self._get_offset_addr(reg_name)
        expected_msg = f"{value},{hex(offset_addr)}".encode()
        self.assertIn(expected_msg, self.mock_socket.sent_data)

    def test_write_unknown_register(self):
        reg_name = "FAKE_REGISTER"
        value = 100
        self.window.write_val_to_reg(reg_name, value)
        self.window.update_msg.assert_called_with(f"Error: Register '{reg_name}' not found in reg_dict.")
        self.assertEqual(len(self.mock_socket.sent_data), 0)

    def test_read_positive_float(self):
        reg_name = "REG_float_ph_shift1"
        float_val = 90.0
        int_representation = int.from_bytes(struct.pack('>f', float_val), byteorder='big')
        self.mock_socket.responses.append(str(int_representation).encode())
        result = self.window.read_val_from_reg(reg_name)
        self.assertEqual(self.mock_socket.sent_data[0], b"4")
        offset_addr = self._get_offset_addr(reg_name)
        self.assertEqual(self.mock_socket.sent_data[1], str(offset_addr).encode())
        self.assertAlmostEqual(result, float_val, places=5)

    def test_read_negative_float(self):
        reg_name = "REG_float_ph_shift0"
        float_val = -90.0
        int_representation_unsigned = 0xc2b40000
        self.mock_socket.responses.append(str(int_representation_unsigned).encode())
        result = self.window.read_val_from_reg(reg_name)
        self.assertEqual(self.mock_socket.sent_data[0], b"4")
        offset_addr = self._get_offset_addr(reg_name)
        self.assertEqual(self.mock_socket.sent_data[1], str(offset_addr).encode())
        self.assertAlmostEqual(result, float_val, places=5)

    def test_read_integer(self):
        reg_name = "REG_RF_Sequence"
        int_val = 123
        self.mock_socket.responses.append(str(int_val).encode())
        result = self.window.read_val_from_reg(reg_name)
        self.assertEqual(self.mock_socket.sent_data[0], b"4")
        offset_addr = self._get_offset_addr(reg_name)
        self.assertEqual(self.mock_socket.sent_data[1], str(offset_addr).encode())
        self.assertEqual(result, int_val)

    def test_read_unknown_register(self):
        reg_name = "FAKE_REGISTER_READ"
        result = self.window.read_val_from_reg(reg_name)
        self.assertIsNone(result)
        self.window.update_msg.assert_called_with(f"Error: Register '{reg_name}' not found in reg_dict.")
        self.assertEqual(len(self.mock_socket.sent_data), 0)

    def test_read_float_hex_from_server(self):
        reg_name = "REG_float_ph_shift1"
        float_val = 90.0
        hex_int_representation = "0x42b40000"
        self.mock_socket.responses.append(hex_int_representation.encode())
        result = self.window.read_val_from_reg(reg_name)
        self.assertAlmostEqual(result, float_val, places=5)

    def test_read_integer_hex_from_server(self):
        reg_name = "REG_RF_Sequence"
        int_val = 255
        hex_int_representation = "0xFF"
        self.mock_socket.responses.append(hex_int_representation.encode())
        result = self.window.read_val_from_reg(reg_name)
        self.assertEqual(result, int_val)

    def test_write_float_register_not_in_map_start_range(self):
        original_reg_dict_entry = reg_dict.get("REG_ADC0Pol")
        reg_dict["TEMP_LOW_ADDR_FLOAT_REG"] = {"address": 0x1000, "type": "float"}
        self.window.map_start = 0x80000000
        reg_name = "TEMP_LOW_ADDR_FLOAT_REG"
        value = 12.5
        self.mock_socket.responses.append(b"waiting")
        self.window.write_val_to_reg(reg_name, value)
        self.assertIn(b"5", self.mock_socket.sent_data)
        packed_val = struct.pack('>f', value)
        int_representation = int.from_bytes(packed_val, byteorder='big')
        offset_addr = reg_dict[reg_name]["address"]
        expected_msg = f"{int_representation},{hex(offset_addr)}".encode()
        self.assertIn(expected_msg, self.mock_socket.sent_data)
        del reg_dict["TEMP_LOW_ADDR_FLOAT_REG"]
        if original_reg_dict_entry:
            reg_dict["REG_ADC0Pol"] = original_reg_dict_entry

# --- New Test Class for AsyncClientApp ---
CMD_WRITE_REG = b"WR_RG" # Define command globally or within class

class TestAsyncClientWriteRegister(unittest.TestCase):
    def setUp(self):
        self.qapplication_patch = patch('PyQt5.QtWidgets.QApplication')
        self.mock_qapplication = self.qapplication_patch.start()

        self.mock_loop = Mock(spec=asyncio.AbstractEventLoop)
        self.app = AsyncClientApp(loop=self.mock_loop)

        # Mock UI elements and writer
        self.app.writer = AsyncMock(spec=asyncio.StreamWriter)
        self.app.addr_edit = Mock(spec=QLineEdit)
        self.app.val_edit = Mock(spec=QLineEdit)
        self.app.reg_combo = Mock(spec=QComboBox)
        self.app.statusBar = Mock(spec=QStatusBar)
        self.app.statusBar.showMessage = Mock() # Ensure showMessage is also a mock

    def tearDown(self):
        self.qapplication_patch.stop()

    def test_write_float_positive(self):
        reg_name = "REG_float_ph_shift1"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        self.app.addr_edit.text.return_value = hex(addr) # Not directly used by write_register but good for consistency
        self.app.val_edit.text.return_value = "10.0"

        asyncio.run(self.app.write_register())

        expected_value_to_write = int.from_bytes(struct.pack('>f', 10.0), 'big') # 0x41200000
        expected_data = CMD_WRITE_REG + struct.pack('>I', addr) + struct.pack('>I', expected_value_to_write)
        self.app.writer.write.assert_called_once_with(expected_data)
        self.app.writer.drain.assert_awaited_once()

    def test_write_float_negative(self):
        reg_name = "REG_float_ph_shift0"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        self.app.val_edit.text.return_value = "-90.0"

        asyncio.run(self.app.write_register())

        expected_value_to_write = int.from_bytes(struct.pack('>f', -90.0), 'big') # 0xc2b40000
        expected_data = CMD_WRITE_REG + struct.pack('>I', addr) + struct.pack('>I', expected_value_to_write)
        self.app.writer.write.assert_called_once_with(expected_data)
        self.app.writer.drain.assert_awaited_once()

    def test_write_int_decimal(self):
        reg_name = "REG_RF_Sequence"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        self.app.val_edit.text.return_value = "123"

        asyncio.run(self.app.write_register())

        expected_value_to_write = 123
        expected_data = CMD_WRITE_REG + struct.pack('>I', addr) + struct.pack('>I', expected_value_to_write)
        self.app.writer.write.assert_called_once_with(expected_data)
        self.app.writer.drain.assert_awaited_once()

    def test_write_int_hex(self):
        reg_name = "REG_interlock"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        self.app.val_edit.text.return_value = "0x7b" # 123 in hex

        asyncio.run(self.app.write_register())

        expected_value_to_write = 123
        expected_data = CMD_WRITE_REG + struct.pack('>I', addr) + struct.pack('>I', expected_value_to_write)
        self.app.writer.write.assert_called_once_with(expected_data)
        self.app.writer.drain.assert_awaited_once()

    def test_write_float_hex_input_behavior(self):
        # This test verifies current behavior: float input is always parsed by float()
        reg_name = "REG_float_ph_shift1"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        hex_string_input = "0x42b40000" # Hex for 90.0f

        # float("0x...") is not valid in Python. The client's _parse_input_value handles this for ints,
        # but for floats, it directly uses float(). This direct use of float() will raise ValueError for "0x..."
        self.app.val_edit.text.return_value = hex_string_input

        asyncio.run(self.app.write_register())

        # Expect float conversion to fail and show error, no write call
        self.app.writer.write.assert_not_called()
        self.app.statusBar.showMessage.assert_called_with(f"Error: Invalid float value '{hex_string_input}'.")


    def test_write_invalid_float_input(self):
        reg_name = "REG_float_ph_shift1"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        self.app.val_edit.text.return_value = "not_a_float"

        asyncio.run(self.app.write_register())

        self.app.writer.write.assert_not_called()
        self.app.statusBar.showMessage.assert_called_with("Error: Invalid float value 'not_a_float'.")

    def test_write_int_value_out_of_range_positive(self):
        reg_name = "REG_RF_Sequence"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        self.app.val_edit.text.return_value = str(0xFFFFFFFF + 1)

        asyncio.run(self.app.write_register())

        self.app.writer.write.assert_not_called()
        self.app.statusBar.showMessage.assert_called_with("Error: Integer value out of range for 32-bit register (0 to 0xFFFFFFFF).")

    def test_write_int_value_out_of_range_negative(self):
        # Current _parse_input_value only checks positive range for the final value_to_write.
        # Negative numbers for int registers are not explicitly prevented by 0 <= value_to_write <= 0xFFFFFFFF if they are small negative.
        # However, struct.pack('>I') would raise error for negative numbers.
        # Let's test _parse_input_value's behavior.
        reg_name = "REG_RF_Sequence"
        addr = reg_dict[reg_name]["address"]
        reg_type = reg_dict[reg_name]["type"]
        self.app.reg_combo.currentData.return_value = {"address": addr, "type": reg_type, "name": reg_name}
        self.app.val_edit.text.return_value = "-1"

        asyncio.run(self.app.write_register())
        # The check `0 <= value_to_write <= 0xFFFFFFFF` will catch -1.
        self.app.writer.write.assert_not_called()
        self.app.statusBar.showMessage.assert_called_with("Error: Integer value out of range for 32-bit register (0 to 0xFFFFFFFF).")

    def test_no_register_selected(self):
        self.app.reg_combo.currentData.return_value = None # "Select Register..." case

        asyncio.run(self.app.write_register())

        self.app.writer.write.assert_not_called()
        self.app.statusBar.showMessage.assert_called_with("Please select a valid register.")


if __name__ == '__main__':
    unittest.main()
