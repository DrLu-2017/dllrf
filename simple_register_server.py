import socket
import struct
import json
import time
import math # Required for dec_to_hex_to_float if it uses math, though the direct pack/unpack won't.

# Assuming rw_mio and register_map are available in the Python path
# For the purpose of this task, if rw_mio is just for memory access,
# and we are simulating it for now if direct hardware access isn't possible
# in the execution environment, we might need to mock it or define a placeholder.
# However, the request asks to initialize it, so I will proceed with the import.
import rw_mio
from registers_map import registers # Corrected import to match filename

# 1. Define constants
DATA_MAP_START = 0x80000000
MAP_LEN = 0xF0000000  # This seems very large, usually it's the size of the mapped region.
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 50004
# REG_DATA_HEADER defined below as it's used with START_CMD
START_CMD = b"STARTCMD"       # 8-byte start command
REG_DATA_HEADER = b"REG_DATA" # 8-byte header for register data payload

# 3. Implement the dec_to_hex_to_float helper function
def dec_to_hex_to_float(value: int) -> float:
    """
    Interpret an integer (presumably from a 32-bit register) as a float.
    The original name is a bit misleading; it's not converting to hex string first.
    It directly interprets the integer bits as a float.
    """
    try:
        # Pack integer into 4 bytes (big-endian, unsigned int)
        packed_value = struct.pack('!I', value)
        # Unpack those 4 bytes as a big-endian float
        float_value = struct.unpack('!f', packed_value)[0]
        return float_value
    except struct.error as e:
        print(f"Error in dec_to_hex_to_float: {e} for value {value}")
        # Depending on how errors should be propagated, either raise or return a special value.
        # For this server, we'll let it propagate to be caught by the per-register error handling.
        raise

def main():
    # 4. Initialize rw_mio.MMIO
    mmio = None
    try:
        print(f"Initializing MMIO with base: {hex(DATA_MAP_START)}, length: {hex(MAP_LEN)}")
        mmio = rw_mio.MMIO(DATA_MAP_START, MAP_LEN)
        print("MMIO initialized successfully.")
    except Exception as e:
        print(f"Fatal Error: Could not initialize MMIO: {e}")
        print("This server cannot function without MMIO. Exiting.")
        return # Exit if MMIO fails

    # 5. Set up a TCP/IP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow address reuse

    try:
        print(f"Binding server to {SERVER_HOST}:{SERVER_PORT}...")
        server_socket.bind((SERVER_HOST, SERVER_PORT))
        server_socket.listen(5)
        print("Server is listening for incoming connections...")
    except socket.error as e:
        print(f"Fatal Error: Could not bind or listen on socket: {e}")
        print("Exiting.")
        if mmio: # Assuming mmio might have resources to clean up if it has a close/del method
            # mmio.close() # Or similar cleanup if available
            pass
        return

    # 6. Loop to accept client connections
    try:
        while True:
            conn = None # Ensure conn is defined for finally block
            try:
                print("\nWaiting for a new client connection...")
                conn, addr = server_socket.accept()
                print(f"Accepted connection from {addr}")

                conn.settimeout(10.0)  # Set timeout for receiving START command
                print(f"Waiting for START command from {addr}...")
                received_cmd = conn.recv(len(START_CMD))

                if received_cmd == START_CMD:
                    print(f"START command received from {addr}.")
                    conn.settimeout(None)  # Disable timeout for data sending

                    # a. Create a dictionary to store register data
                    register_data_to_send = {}

                    # b. Iterate registers.items()
                    print(f"Reading {len(registers)} registers...")
                    if not registers:
                        print("Register map is empty. Nothing to send.")
                    
                    for reg_name, abs_address in registers.items():
                        try:
                            # i. Calculate offset
                            if not isinstance(abs_address, int):
                                print(f"Skipping register {reg_name}: Invalid address format '{abs_address}' in register_map.")
                                register_data_to_send[reg_name] = f"Error: Invalid address format '{abs_address}'"
                                continue

                            offset = abs_address - DATA_MAP_START
                            if offset < 0:
                                print(f"Skipping register {reg_name}: Calculated negative offset ({offset}) for address {hex(abs_address)}. DATA_MAP_START is {hex(DATA_MAP_START)}.")
                                register_data_to_send[reg_name] = f"Error: Negative offset for address {hex(abs_address)}"
                                continue
                            
                            # ii. Try to read raw_value
                            raw_value = mmio.read32(offset)
                            
                            # iii. Try to convert float_value
                            float_value = dec_to_hex_to_float(raw_value)
                            
                            # iv. Store float_value or an error string
                            register_data_to_send[reg_name] = float_value

                        except Exception as e_reg:
                            print(f"Error processing register {reg_name} (addr: {hex(abs_address)}, offset: {hex(offset if 'offset' in locals() else -1)}): {e_reg}")
                            register_data_to_send[reg_name] = f"Error: {str(e_reg)}"
                    
                    if not register_data_to_send:
                        print("No register data was collected (map might be empty or all registers failed).")
                        # Optionally send an empty response or an error message to client here
                        # For now, it will just close the connection if no data.

                    # c. Serialize the dictionary to a JSON string
                    try:
                        json_string = json.dumps(register_data_to_send, indent=4)
                        json_bytes = json_string.encode('utf-8')
                    except TypeError as e_json:
                        print(f"Error serializing register data to JSON: {e_json}")
                        # Fallback for non-serializable data (like NaN/inf floats by default)
                        safe_data = {k: str(v) if isinstance(v, float) and (math.isinf(v) or math.isnan(v)) else v for k, v in register_data_to_send.items()}
                        try:
                            json_string = json.dumps(safe_data, indent=4)
                            json_bytes = json_string.encode('utf-8')
                            print("  Successfully serialized register data with problematic items as strings.")
                        except Exception as e_json_fallback:
                            print(f"  Fallback JSON serialization also failed: {e_json_fallback}")
                            # If fallback fails, we cannot send valid JSON.
                            # Consider sending an error message or specific error structure to the client.
                            # For now, we'll close the connection.
                            if conn: conn.close()
                            continue # Next client connection

                    # d. Send the header
                    conn.sendall(REG_DATA_HEADER)
                    print(f"Sent header: {REG_DATA_HEADER.decode()}")

                    # e. Send the length of the JSON string
                    packed_len = struct.pack('>I', len(json_bytes))
                    conn.sendall(packed_len)
                    print(f"Sent JSON data length: {len(json_bytes)}")

                    # f. Send the UTF-8 encoded JSON string
                    conn.sendall(json_bytes)
                    print("Sent JSON data payload.")
                
                else:
                    print(f"Invalid or missing START command from {addr}. Received: {received_cmd}")
                    # No data sent, connection will be closed in finally.

            except socket.timeout:
                print(f"Timeout waiting for START command from {addr}.")
            except socket.error as e_sock:
                print(f"Socket error during client interaction with {addr}: {e_sock}")
            except Exception as e_client:
                print(f"Error during client interaction with {addr}: {e_client}")
            finally:
                # g. Close the client connection
                if conn:
                    print(f"Closing connection with {addr}")
                    conn.close()
    
    except KeyboardInterrupt:
        print("\nServer shutting down due to KeyboardInterrupt.")
    except Exception as e_server:
        print(f"An unexpected error occurred in the server loop: {e_server}")
    finally:
        print("Closing server socket.")
        server_socket.close()
        if mmio: # Assuming mmio might have resources to clean up
            # mmio.close() # Or similar cleanup if available
            pass
        print("Server shutdown complete.")

if __name__ == "__main__":
    # Create a dummy register_map.py if it doesn't exist for testing purposes
    # In a real environment, this would be provided.
    try:
        from registers_map import registers # Corrected import
        if not registers: # If registers is empty or None
             print("Warning: 'registers' map from registers_map.py is empty. Server will run but send no data.")
    except ImportError:
        print("Warning: registers_map.py not found. This should not happen if ls() is accurate.")
        # The dummy creation logic below would create register_map.py (singular)
        # which is not what we want if registers_map.py (plural) is the true source.
        # For now, if registers_map.py is missing, it's a critical error for the intended operation.
        print("Critical: registers_map.py (plural) not found. The server relies on this file.")
        print("A dummy register_map.py (singular) might be created by fallback, but it's not the intended register definition.")
        # Fallback to creating a dummy register_map.py (singular) if registers_map.py (plural) is truly missing
        # This part of the logic might need review based on actual deployment strategy
        try:
            from register_map import registers as fallback_registers
            if not fallback_registers: print("Fallback dummy 'register_map.py' is also empty or non-existent.")
        except ImportError:
            print("Creating a new dummy 'register_map.py' (singular) as a last resort fallback.")
            with open("register_map.py", "w") as f: # Singular
                f.write("registers = {\n")
                f.write("    'FALLBACK_DUMMY_REG_1': 0x80000000,\n")
                f.write("    'FALLBACK_DUMMY_REG_2': 0x80000004,\n")
                f.write("}\n")
            from register_map import registers # Try importing the singular version
    
    # Create a dummy rw_mio.py if it doesn't exist for basic testing
    try:
        import rw_mio
        if not hasattr(rw_mio, 'MMIO'):
            raise ImportError("MMIO class not found in rw_mio")
    except ImportError:
        print("Warning: rw_mio.py or MMIO class not found. Creating a dummy MMIO for basic testing.")
        print("Please ensure a valid rw_mio.py with an MMIO class is available for actual hardware interaction.")
        with open("rw_mio.py", "w") as f:
            f.write("class MMIO:\n")
            f.write("    def __init__(self, base_addr, length):\n")
            f.write("        self.base_addr = base_addr\n")
            f.write("        self.length = length\n")
            f.write("        print(f'Dummy MMIO Initialized: base={hex(base_addr)}, len={hex(length)}')\n")
            f.write("    def read32(self, offset):\n")
            f.write("        # Simulate reading a value; for testing, return offset + a base\n")
            f.write("        # This will produce predictable float values\n")
            f.write("        sim_val = offset + 0x41200000 # Produces ~10.0 for offset 0\n")
            f.write("        print(f'Dummy MMIO Read32 from offset {hex(offset)}, returning {hex(sim_val)}')\n")
            f.write("        return sim_val\n")
            f.write("    def write32(self, offset, value):\n")
            f.write("        print(f'Dummy MMIO Write32 to offset {hex(offset)} with value {hex(value)}')\n")
            f.write("        pass # Dummy write does nothing\n")
            f.write("    def close(self):\n")
            f.write("        print('Dummy MMIO closed')\n")
            f.write("        pass\n")
        import rw_mio # Try importing again
        # from register_map import registers # This line might be problematic if register_map.py was dummied
                                         # and registers_map.py is the primary.
                                         # The import at the top of the file should be the definitive one.

    main()
