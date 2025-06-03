import asyncio
import struct
import json
import math # For dec_to_hex_to_float if it handles NaN/Inf, and for general math.
import time # Though time.sleep is replaced by asyncio.sleep, good to keep for other potential uses.
import concurrent.futures
import logging
import sys # For sys.exit in initialize_mmio

# Assuming rw_mio and registers_map are available.
# These will be created as dummies if not present, by the __main__ block.
import rw_mio
from registers_map import registers

# 1. Boilerplate & Helpers
# Constants
DATA_MAP_START = 0x80000000
MAP_LEN = 0xF0000000  # As noted, this is unusually large for a map length.
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 50005
POLL_INTERVAL = 0.5  # Seconds
BROADCAST_INTERVAL = 0.5 # Seconds for broadcasting snapshots
MAX_EXECUTOR_WORKERS = 5
REG_DATA_SNAPSHOT_HEADER = b"REG_SNAP" # 8-byte header for snapshot data

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Globals
current_register_snapshot = {}
snapshot_lock = asyncio.Lock()
mmio_instance = None
connected_clients = set() # Stores active client writer objects
clients_lock = asyncio.Lock() # Lock for accessing connected_clients

# dec_to_hex_to_float function (no type hints, robust)
def dec_to_hex_to_float(value):
    """
    Interpret an integer (presumably from a 32-bit register) as a float.
    Directly interprets the integer bits as a float.
    """
    try:
        # '!I' packs as unsigned int. If value is negative or too large,
        # struct.pack will raise struct.error.
        packed_value = struct.pack('!I', value)
        float_value = struct.unpack('!f', packed_value)[0]
    except struct.error as e:
        logger.warning(f"Could not convert integer {value} (hex: {hex(value)}) to float (struct error: {e}). Returning 0.0.")
        return 0.0 # Fallback value for conversion errors
    return float_value

# 2. MMIO Initialization Function
def initialize_mmio():
    global mmio_instance
    try:
        logger.info(f"Initializing MMIO with base: {hex(DATA_MAP_START)}, length: {hex(MAP_LEN)}")
        mmio_instance = rw_mio.MMIO(DATA_MAP_START, MAP_LEN)
        logger.info("MMIO initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize MMIO: {e}")
        sys.exit(1) # Exit if MMIO fails, as polling would be impossible

# 3. Synchronous Hardware Read Function
def _perform_hardware_reads():
    """
    Performs synchronous hardware reads for all registered devices.
    This function is intended to be run in a thread pool executor.
    """
    global mmio_instance # Access the globally initialized MMIO instance
    if mmio_instance is None:
        logger.error("_perform_hardware_reads: MMIO not initialized.")
        return {"error": "MMIO not initialized"}

    snapshot = {}
    logger.debug(f"Reading {len(registers)} registers from hardware...")
    for reg_name, abs_address in registers.items():
        try:
            if not isinstance(abs_address, int):
                logger.warning(f"Skipping register {reg_name}: Invalid address format '{abs_address}' in register_map.")
                snapshot[reg_name] = f"Error: Invalid address format '{abs_address}'"
                continue

            offset = abs_address - DATA_MAP_START
            if offset < 0 or offset >= MAP_LEN: # Also check if offset is within map length
                logger.warning(f"Skipping register {reg_name}: Calculated offset {hex(offset)} for address {hex(abs_address)} is out of MMIO range (0x0 - {hex(MAP_LEN-1)}).")
                snapshot[reg_name] = f"Error: Calculated offset {hex(offset)} out of MMIO range"
                continue

            raw_value = mmio_instance.read32(offset)
            float_value = dec_to_hex_to_float(raw_value)
            snapshot[reg_name] = float_value
            logger.debug(f"  Read {reg_name} (addr: {hex(abs_address)}, offset: {hex(offset)}): raw={hex(raw_value)}, float={float_value}")

        except Exception as e_reg:
            logger.error(f"Error processing register {reg_name} (addr: {hex(abs_address)}, offset: {hex(offset if 'offset' in locals() else -1)}): {e_reg}")
            snapshot[reg_name] = "ERROR_READING" # Indicate read error for this specific register

    logger.debug(f"Hardware read finished. {len(snapshot)} values/errors captured.")
    return snapshot

# 4. Async Polling Loop
async def poll_hardware_registers():
    """
    Asynchronously polls hardware registers at a defined interval using a thread pool
    for the synchronous hardware read operations.
    """
    global current_register_snapshot, snapshot_lock

    # Using a ThreadPoolExecutor for the blocking mmio_instance.read32 calls
    # MAX_EXECUTOR_WORKERS can be tuned based on performance and number of registers
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_EXECUTOR_WORKERS)

    logger.info("Hardware polling loop started.")
    while True:
        logger.debug("Polling hardware registers...")
        try:
            loop = asyncio.get_running_loop()
            # Run the synchronous _perform_hardware_reads function in an executor thread
            new_data = await loop.run_in_executor(executor, _perform_hardware_reads)

            async with snapshot_lock:
                current_register_snapshot = new_data

            # Log summary of update, avoiding logging the full potentially large snapshot at INFO level
            update_summary = {k: v for k, v in new_data.items() if isinstance(v, str) and "Error" in v}
            if update_summary:
                 logger.info(f"Snapshot updated. {len(new_data)} registers processed. Errors in: {list(update_summary.keys())}")
            else:
                 logger.info(f"Snapshot updated successfully with {len(new_data)} registers.")

        except Exception as e:
            logger.error(f"Error in polling loop: {e}", exc_info=True) # Add exc_info for traceback

        await asyncio.sleep(POLL_INTERVAL)

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handles incoming client connections."""
    addr = writer.get_extra_info('peername')
    logger.info(f"Client {addr} connected.")

    async with clients_lock:
        connected_clients.add(writer)

    try:
        while True:
            # Keep connection alive, read any potential incoming data (e.g. client commands in future)
            # For now, this server primarily broadcasts, so we just check if client is still connected.
            data = await reader.read(100) # Read up to 100 bytes
            if not data:
                logger.info(f"Client {addr} disconnected (received empty data).")
                break
            # If client sends data, log it (for now, no specific client commands are handled)
            logger.debug(f"Received from {addr}: {data.decode(errors='ignore')}")
            # Example: Echo back or process command
            # writer.write(data)
            # await writer.drain()

    except (asyncio.IncompleteReadError, ConnectionResetError) as e:
        logger.info(f"Client {addr} disconnected abruptly: {e}")
    except Exception as e:
        logger.error(f"Error in handle_client for {addr}: {e}", exc_info=True)
    finally:
        logger.info(f"Cleaning up connection for {addr}.")
        async with clients_lock:
            connected_clients.discard(writer)
        if not writer.is_closing():
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"Error closing writer for {addr}: {e_close}", exc_info=True)
        logger.info(f"Connection with {addr} fully closed.")


async def broadcast_snapshots():
    """Periodically broadcasts the current register snapshot to all connected clients."""
    global current_register_snapshot, snapshot_lock, connected_clients, clients_lock

    while True:
        await asyncio.sleep(BROADCAST_INTERVAL)

        async with snapshot_lock:
            # Create a shallow copy to avoid holding the lock during potentially long I/O
            local_snapshot = dict(current_register_snapshot)

        if not local_snapshot:
            logger.debug("Snapshot empty, skipping broadcast.")
            continue

        try:
            # Serialize the snapshot to JSON
            # Handle potential non-serializable items like NaN/Infinity if necessary
            json_payload = json.dumps(local_snapshot)
            payload_bytes = json_payload.encode('utf-8')
        except Exception as e:
            logger.error(f"Failed to serialize snapshot for broadcast: {e}", exc_info=True)
            continue # Skip this broadcast cycle

        # Construct the message: Header + Length + Payload
        message = REG_DATA_SNAPSHOT_HEADER + struct.pack('>I', len(payload_bytes)) + payload_bytes

        disconnected_writers = set()

        async with clients_lock:
            # Iterate over a copy of the set, as we might modify it
            current_client_writers = list(connected_clients)

        if not current_client_writers:
            logger.debug("No clients connected, skipping broadcast.")
            continue

        logger.info(f"Broadcasting snapshot to {len(current_client_writers)} client(s).")

        for writer in current_client_writers:
            if writer.is_closing():
                disconnected_writers.add(writer)
                continue
            try:
                writer.write(message)
                await writer.drain()
                logger.debug(f"Snapshot sent to {writer.get_extra_info('peername')}")
            except (ConnectionResetError, BrokenPipeError) as e:
                logger.info(f"Client {writer.get_extra_info('peername')} disconnected during broadcast: {e}")
                disconnected_writers.add(writer)
            except Exception as e:
                logger.error(f"Error sending snapshot to {writer.get_extra_info('peername')}: {e}", exc_info=True)
                disconnected_writers.add(writer) # Assume problematic, remove

        if disconnected_writers:
            async with clients_lock:
                for writer in disconnected_writers:
                    connected_clients.discard(writer)
                    # Ensure writer is closed if not already (though it should be by handle_client's finally)
                    if not writer.is_closing():
                        try:
                            writer.close()
                            await writer.wait_closed()
                        except Exception: pass # Ignore errors during this cleanup
                logger.info(f"Removed {len(disconnected_writers)} disconnected client(s) after broadcast attempt.")

async def main():
    """Main function to initialize and run the server components."""
    initialize_mmio()

    server = await asyncio.start_server(
        handle_client, SERVER_HOST, SERVER_PORT)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"Server started on {addrs}. Polling every {POLL_INTERVAL}s. Broadcasting every {BROADCAST_INTERVAL}s.")

    # Create and start the background tasks
    polling_task = asyncio.create_task(poll_hardware_registers())
    broadcast_task = asyncio.create_task(broadcast_snapshots())

    try:
        async with server:
            await server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down due to KeyboardInterrupt.")
    finally:
        logger.info("Cancelling background tasks...")
        polling_task.cancel()
        broadcast_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            logger.info("Polling task cancelled.")
        try:
            await broadcast_task
        except asyncio.CancelledError:
            logger.info("Broadcast task cancelled.")

        # Shutdown the executor in poll_hardware_registers (if it were accessible here)
        # For simplicity in this structure, the executor is local to poll_hardware_registers
        # and will be cleaned up when the program exits as its threads are daemonic.
        # For more graceful shutdown in complex apps, pass executor or make it global/class member.

        logger.info("Server fully shut down.")


if __name__ == "__main__":
    # Initialize MMIO first (moved to main())
    # initialize_mmio() # This will exit if MMIO fails


    # The dummy file creation logic is kept for standalone testing if needed.
    # In a deployed scenario, these files (registers_map.py, rw_mio.py) should exist.
    try:
        from registers_map import registers
        if not registers:
             logger.warning("'registers' map from registers_map.py is empty.")
    except ImportError:
        logger.warning("registers_map.py not found. Creating a dummy map for testing.")
        logger.warning("Please ensure a valid registers_map.py exists for actual use.")
        with open("registers_map.py", "w") as f: # Ensure dummy uses correct name
            f.write("registers = {\n")
            f.write("    'DUMMY_REG_1': 0x80000000,\n")
            f.write("    'DUMMY_REG_2': 0x80000004,\n")
            f.write("    'DUMMY_FAULTY_ADDRESS': 'NOT_AN_INT_ADDRESS',\n")
            f.write("    'DUMMY_NEGATIVE_OFFSET': 0x70000000,\n")
            f.write("}\n")
        # Attempt to re-import after dummy creation, not strictly necessary if main() handles it
        from registers_map import registers

    try:
        import rw_mio
        if not hasattr(rw_mio, 'MMIO'):
            raise ImportError("MMIO class not found in rw_mio")
    except ImportError:
        logger.warning("rw_mio.py or MMIO class not found. Creating a dummy MMIO for basic testing.")
        with open("rw_mio.py", "w") as f:
            f.write("class MMIO:\n")
            f.write("    def __init__(self, base_addr, length):\n")
            f.write("        self.base_addr = base_addr\n")
            f.write("        self.length = length\n")
            f.write(f"        print(f'Dummy MMIO Initialized: base={{hex(base_addr)}}, len={{hex(length)}}')\n")
            f.write("    def read32(self, offset):\n")
            f.write("        # Simulate reading a value\n")
            f.write("        if offset == (0x80000000 - 0x80000000): # DUMMY_REG_1\n")
            f.write("            val = 0x41200000 # Represents 10.0\n")
            f.write("        elif offset == (0x80000004 - 0x80000000): # DUMMY_REG_2\n")
            f.write("            val = 0x41A00000 # Represents 20.0\n")
            f.write("        else:\n")
            f.write("            val = 0x0 # Default for other offsets\n")
            f.write(f"        # print(f'Dummy MMIO Read32 from offset {{hex(offset)}}, returning {{hex(val)}}')\n")
            f.write("        return val\n")
            f.write("    def write32(self, offset, value):\n")
            f.write(f"        # print(f'Dummy MMIO Write32 to offset {{hex(offset)}} with value {{hex(value)}}')\n")
            f.write("        pass\n")
            f.write("    def close(self):\n")
            f.write("        print('Dummy MMIO closed')\n")
            f.write("        pass\n")
        # No need to re-initialize mmio_instance here; main() does it.

    asyncio.run(main())
```
