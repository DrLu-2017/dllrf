import unittest
from unittest.mock import Mock, patch
import struct
import socket # Though not directly used by tests, the tested code uses it.

# Assuming LLRF_Soleil_Linux_NAT_LogicX_v4.3.py and reg_dict.py are in python path
# If not, sys.path manipulations might be needed, but for now, assume they are accessible.
from LLRF_Soleil_Linux_NAT_LogicX_v4_3 import llrf_graph_window
from reg_dict import reg_dict

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
        # Simulate timeout if no specific response is set up for recv
        # This matches the behavior of the actual socket more closely
        # when no data is available, rather than blocking indefinitely.
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
        # Mock QApplication to prevent Qt errors if llrf_graph_window constructor needs it
        # This is a common pattern, but might need adjustment based on __init__
        self.qapplication_patch = patch('PyQt5.QtWidgets.QApplication')
        self.mock_qapplication = self.qapplication_patch.start()

        self.window = llrf_graph_window()
        self.mock_socket = MockSocket()
        self.window.mysocket = self.mock_socket
        self.window.map_start = 0x80000000  # Example map_start value

        # Mock the UI update method to avoid Qt errors
        self.window.update_msg = Mock()

    def tearDown(self):
        self.qapplication_patch.stop()

    def _get_offset_addr(self, reg_name):
        address = reg_dict[reg_name]["address"]
        if self.window.map_start is not None and address >= self.window.map_start:
            return address - self.window.map_start
        return address

    # --- Tests for write_val_to_reg ---

    def test_write_positive_float(self):
        reg_name = "REG_float_ph_shift1" # Example float register
        value = 90.0

        # Simulate server "waiting" ack
        self.mock_socket.responses.append(b"waiting")

        self.window.write_val_to_reg(reg_name, value)

        self.assertIn(b"5", self.mock_socket.sent_data) # Command for write

        packed_val = struct.pack('>f', value)
        int_representation = int.from_bytes(packed_val, byteorder='big')
        offset_addr = self._get_offset_addr(reg_name)
        expected_msg = f"{int_representation},{hex(offset_addr)}".encode()

        self.assertIn(expected_msg, self.mock_socket.sent_data)
        self.window.update_msg.assert_called() # Check if update_msg was called

    def test_write_negative_float(self):
        reg_name = "REG_float_ph_shift0" # Another float register
        value = -90.0

        self.mock_socket.responses.append(b"waiting")
        self.window.write_val_to_reg(reg_name, value)

        self.assertIn(b"5", self.mock_socket.sent_data)

        packed_val = struct.pack('>f', value)
        int_representation = int.from_bytes(packed_val, byteorder='big') # Should be 0xc2b40000
        # self.assertEqual(int_representation, 0xc2b40000)
        offset_addr = self._get_offset_addr(reg_name)
        expected_msg = f"{int_representation},{hex(offset_addr)}".encode()

        self.assertIn(expected_msg, self.mock_socket.sent_data)

    def test_write_integer(self):
        reg_name = "REG_RF_Sequence" # Example int register
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

        # No "waiting" response needed as it should fail before socket send for payload
        self.window.write_val_to_reg(reg_name, value)

        # Check that update_msg was called with an error
        self.window.update_msg.assert_called_with(f"Error: Register '{reg_name}' not found in reg_dict.")
        # Assert that only the command "5" might have been sent, but not the payload
        # Depending on implementation, it might not even send "5"
        # For the current write_val_to_reg, it returns before sending anything if reg_name is not found.
        self.assertEqual(len(self.mock_socket.sent_data), 0)


    # --- Tests for read_val_from_reg ---

    def test_read_positive_float(self):
        reg_name = "REG_float_ph_shift1"
        float_val = 90.0
        int_representation = int.from_bytes(struct.pack('>f', float_val), byteorder='big')

        self.mock_socket.responses.append(str(int_representation).encode()) # Server sends int string

        result = self.window.read_val_from_reg(reg_name)

        self.assertEqual(self.mock_socket.sent_data[0], b"4") # Read command
        offset_addr = self._get_offset_addr(reg_name)
        self.assertEqual(self.mock_socket.sent_data[1], str(offset_addr).encode())
        self.assertAlmostEqual(result, float_val, places=5)

    def test_read_negative_float(self):
        reg_name = "REG_float_ph_shift0"
        float_val = -90.0
        # For -90.0, int representation is 0xc2b40000 (big-endian for >f)
        # which is 3266580480 as an unsigned integer.
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
        # Ensure socket was not used for sending address, etc.
        self.assertEqual(len(self.mock_socket.sent_data), 0)
        # (The new read_val_from_reg returns before sending if reg not found)

    def test_read_float_hex_from_server(self):
        reg_name = "REG_float_ph_shift1"
        float_val = 90.0
        # Simulate server sending hex string for the integer representation
        # 90.0 -> 0x42b40000
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
        # Assuming a register with address lower than map_start
        # Add a temporary register to reg_dict for this test case
        original_reg_dict_entry = reg_dict.get("REG_ADC0Pol") # Save if exists
        reg_dict["TEMP_LOW_ADDR_FLOAT_REG"] = {"address": 0x1000, "type": "float"}
        self.window.map_start = 0x80000000 # Ensure map_start is high

        reg_name = "TEMP_LOW_ADDR_FLOAT_REG"
        value = 12.5

        self.mock_socket.responses.append(b"waiting")
        self.window.write_val_to_reg(reg_name, value)

        self.assertIn(b"5", self.mock_socket.sent_data)
        packed_val = struct.pack('>f', value)
        int_representation = int.from_bytes(packed_val, byteorder='big')
        # Offset should be the address itself as it's less than map_start
        offset_addr = reg_dict[reg_name]["address"]
        expected_msg = f"{int_representation},{hex(offset_addr)}".encode()

        self.assertIn(expected_msg, self.mock_socket.sent_data)

        # Clean up: remove temporary register and restore original if any
        del reg_dict["TEMP_LOW_ADDR_FLOAT_REG"]
        if original_reg_dict_entry:
            reg_dict["REG_ADC0Pol"] = original_reg_dict_entry


if __name__ == '__main__':
    unittest.main()
