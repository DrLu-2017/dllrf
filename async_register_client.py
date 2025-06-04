import sys
import asyncio
import json
import struct
import logging
import math

from qasync import QEventLoop, asyncSlot, asyncClose

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QStatusBar, QHeaderView, QComboBox, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer # Added QTimer

# Assuming reg_dict.py is in the same directory or Python path.
try:
    from reg_dict import reg_dict
except ImportError:
    # Fallback if reg_dict.py is not found, to allow UI to load
    reg_dict = {"ERROR_LOADING_REG_DICT": 0x0}


# Constants
SERVER_HOST_DEFAULT = '192.168.87.90'
SERVER_PORT_DEFAULT = 50005
REG_DATA_SNAPSHOT_HEADER = b"REG_SNAP" # 8 bytes

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__) # Moved to class as self.logger

def int_bits_to_float(value: int) -> float:
    """
    Interprets the bits of a 32-bit integer as a single-precision float.
    Assumes network byte order (big-endian) for packing/unpacking.
    """
    try:
        # The value from server is result of struct.unpack('>I', packed_val)[0] in read_register (server)
        # or struct.pack('>I', value) was used for server's read response.
        # Server read response: RESP_READ_SUCCESS + struct.pack('>I', value)
        # So client receives an integer already. It needs to pack it again to then unpack as float.
        packed_value = struct.pack('!I', value) # Pack as network byte order (big-endian) unsigned 32-bit integer
        float_value = struct.unpack('!f', packed_value)[0] # Unpack as network byte order single-precision float
        return float_value
    except struct.error as e:
        # Accessing self.logger might be an issue if this is a global function.
        # For now, print, or pass logger in, or make it a method.
        print(f"Error converting int {hex(value)} to float: {e}")
        return math.nan # Return NaN for conversion errors

class AsyncClientApp(QMainWindow):
    def __init__(self, loop=None):
        super().__init__()
        self.loop = loop or asyncio.get_event_loop()
        self.logger = logging.getLogger(__name__) # Logger as instance member

        # Filter reg_dict for display registers
        self.display_registers = []
        if reg_dict and "ERROR_LOADING_REG_DICT" not in reg_dict:
            for name, info in reg_dict.items():
                if info.get("display") is True:
                    self.display_registers.append({
                        "name": name,
                        "address": info["address"],
                        "type": info.get("type", "int") # Default to int if type not specified
                    })
        self.logger.info(f"Found {len(self.display_registers)} registers to display.")

        self.initUI()

        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None
        self.receive_task: asyncio.Task = None
        self.is_receiving_updates = False
        self.ui_update_queue = asyncio.Queue()
        self.ui_update_timer = QTimer(self) # Initialize QTimer
        self.ui_update_timer.timeout.connect(self.process_ui_queue) # Connect its timeout signal

        self.is_updating_display_registers = False
        self.pending_display_register_updates = []

        # Server response opcodes
        self.REG_DATA_SNAPSHOT_HEADER = REG_DATA_SNAPSHOT_HEADER
        self.RESP_READ_SUCCESS = b"RD_OK"
        self.RESP_READ_ERROR = b"RD_ER"
        self.RESP_WRITE_SUCCESS = b"WR_OK"
        self.RESP_WRITE_ERROR = b"WR_ER"

    def initUI(self):
        self.setWindowTitle("Async Register Viewer")
        self.setGeometry(100, 100, 1100, 700) # Increased window size

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        top_level_layout = QHBoxLayout(self.central_widget)

        # Left side layout (existing controls)
        left_widget = QWidget()
        left_v_layout = QVBoxLayout(left_widget)

        # Connection layout
        connection_layout = QHBoxLayout()
        self.ip_label = QLabel("Server IP:")
        connection_layout.addWidget(self.ip_label)
        self.ip_edit = QLineEdit(SERVER_HOST_DEFAULT)
        connection_layout.addWidget(self.ip_edit)

        self.port_label = QLabel("Port:")
        connection_layout.addWidget(self.port_label)
        self.port_edit = QLineEdit(str(SERVER_PORT_DEFAULT))
        self.port_edit.setFixedWidth(60)
        connection_layout.addWidget(self.port_edit)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        connection_layout.addWidget(self.connect_button)

        self.updates_button = QPushButton("Start Updates")
        self.updates_button.setEnabled(False) # Enabled after connection
        self.updates_button.clicked.connect(self.toggle_updates)
        connection_layout.addWidget(self.updates_button)

        connection_layout.addStretch(1)
        left_v_layout.addLayout(connection_layout)

        # Read/Write Operations Layout
        rw_layout = QHBoxLayout()
        self.reg_combo_label = QLabel("Register:")
        rw_layout.addWidget(self.reg_combo_label)
        self.reg_combo = QComboBox()
        self.reg_combo.setMinimumWidth(200)
        self.populate_reg_combo()
        self.reg_combo.currentTextChanged.connect(self.on_reg_combo_changed)
        rw_layout.addWidget(self.reg_combo)

        self.addr_label = QLabel("Address:")
        rw_layout.addWidget(self.addr_label)
        self.addr_edit = QLineEdit()
        self.addr_edit.setPlaceholderText("e.g., 0x80080000")
        rw_layout.addWidget(self.addr_edit)

        self.val_label = QLabel("Value:")
        rw_layout.addWidget(self.val_label)
        self.val_edit = QLineEdit()
        self.val_edit.setPlaceholderText("e.g., 0x41200000 or 10 (for write)")
        rw_layout.addWidget(self.val_edit)

        self.read_button = QPushButton("Read")
        self.read_button.clicked.connect(self.read_register)
        rw_layout.addWidget(self.read_button)

        self.write_button = QPushButton("Write")
        self.write_button.clicked.connect(self.write_register)
        rw_layout.addWidget(self.write_button)

        rw_layout.addStretch(1)
        left_v_layout.addLayout(rw_layout)

        # Disable R/W UI initially, enable on connect
        self.reg_combo.setEnabled(False)
        self.addr_edit.setEnabled(False)
        self.val_edit.setEnabled(False)
        self.read_button.setEnabled(False)
        self.write_button.setEnabled(False)

        # Main data Table for register data (snapshot)
        self.tableWidget = QTableWidget()
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Register Name", "Value"])
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        left_v_layout.addWidget(self.tableWidget)

        top_level_layout.addWidget(left_widget, 2) # Add left widget with stretch factor 2

        # Right side layout (new display area for monitored registers)
        right_widget = QWidget()
        right_v_layout = QVBoxLayout(right_widget)

        display_group_box = QGroupBox("Monitored Registers")
        display_group_box_layout = QVBoxLayout(display_group_box) # Set layout for the QGroupBox

        self.display_reg_table = QTableWidget()
        self.display_reg_table.setColumnCount(2)
        self.display_reg_table.setHorizontalHeaderLabels(["Register Name", "Value"])
        self.display_reg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.display_reg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        # Populate the new table with display_registers
        self.display_reg_table.setRowCount(len(self.display_registers))
        for row, reg_info in enumerate(self.display_registers):
            name_item = QTableWidgetItem(reg_info["name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable) # Make name not editable

            value_item = QTableWidgetItem("N/A") # Initial value
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable) # Make value not editable initially

            self.display_reg_table.setItem(row, 0, name_item)
            self.display_reg_table.setItem(row, 1, value_item)

        display_group_box_layout.addWidget(self.display_reg_table)
        right_v_layout.addWidget(display_group_box)

        top_level_layout.addWidget(right_widget, 1) # Add right widget with stretch factor 1

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def populate_reg_combo(self):
        self.reg_combo.addItem("Select Register...", None) # Add a placeholder item
        if reg_dict and "ERROR_LOADING_REG_DICT" not in reg_dict:
            for name, reg_info in reg_dict.items(): # reg_dict.items() now yields name, dict
                self.reg_combo.addItem(name, reg_info) # Store full dict as item data
        else:
            self.reg_combo.addItem("Error loading registers", None)
            self.reg_combo.setEnabled(False)

    def on_reg_combo_changed(self, text):
        reg_info = self.reg_combo.currentData() # currentData() now returns the dict
        if reg_info and isinstance(reg_info, dict): # Check if it's a valid dict
            self.addr_edit.setText(hex(reg_info["address"]))
            # Optionally, you could display the type as well
            # reg_type = reg_info.get("type", "N/A")
            # self.statusBar().showMessage(f"Selected: {text}, Type: {reg_type}, Address: {hex(reg_info['address'])}")
        elif text == "Select Register..." or reg_info is None: # Clear if placeholder or no data
             self.addr_edit.setText("")

    # Helper to parse address/value inputs (supporting hex and dec)
    def _parse_input_value(self, text_value, field_name="Value"):
        if not text_value:
            self.statusBar().showMessage(f"Error: {field_name} cannot be empty.")
            return None
        try:
            if text_value.lower().startswith("0x"):
                return int(text_value, 16)
            return int(text_value)
        except ValueError:
            self.statusBar().showMessage(f"Error: Invalid {field_name} format. Use dec or 0xHEX.")
            return None

    @asyncSlot()
    async def update_display_registers_values(self):
        if self.writer is None or self.writer.is_closing():
            self.logger.info("Not connected, cannot update display registers.")
            return
        if not self.display_registers:
            self.logger.info("No registers marked for display.")
            return

        if self.is_updating_display_registers:
            self.logger.warning("Previous display register update was still in progress. Starting a new one.")
            # For simplicity, assuming any old timeout task will expire harmlessly or be replaced by a new one.

        self.logger.info("Requesting updates for display registers...")
        self.is_updating_display_registers = True
        # Create a copy of the list of dictionaries to avoid issues if display_registers itself is modified elsewhere
        self.pending_display_register_updates = [dict(item) for item in self.display_registers]


        original_pending_count = len(self.pending_display_register_updates)
        current_pending_idx = 0
        while current_pending_idx < len(self.pending_display_register_updates):
            reg_info = self.pending_display_register_updates[current_pending_idx]
            address = reg_info["address"]
            name = reg_info["name"]
            try:
                cmd = b"RD_RG"
                packed_addr = struct.pack('>I', address)
                self.writer.write(cmd + packed_addr)
                await self.writer.drain()
                self.logger.info(f"Sent READ command for display register {name} at {hex(address)}.")
                current_pending_idx += 1 # Move to next register
            except Exception as e:
                self.logger.error(f"Error sending read for display reg {name}: {e}")
                # Mark as error in table immediately if send fails
                for r in range(self.display_reg_table.rowCount()):
                    if self.display_reg_table.item(r, 0).text() == name:
                        error_item = QTableWidgetItem(f"Send Error")
                        error_item.setFlags(error_item.flags() & ~Qt.ItemIsEditable)
                        error_item.setForeground(Qt.red) # Ensure Qt is imported: from PyQt5.QtCore import Qt
                        self.display_reg_table.setItem(r, 1, error_item)
                        break
                # Remove from pending as we won't get a response for this one
                self.pending_display_register_updates.pop(current_pending_idx)
                # Do not increment current_pending_idx as the list has shifted

        if not self.pending_display_register_updates: # All failed to send or list was empty initially
            self.is_updating_display_registers = False
            self.logger.info("No pending display registers to update after send attempts (all failed to send or list was empty).")
            return

        # Schedule a task to reset the state if not all responses arrive within a timeout
        # This is only scheduled if we successfully sent at least one request
        asyncio.create_task(self.reset_display_update_state_after_timeout(timeout_seconds=5.0))

    async def reset_display_update_state_after_timeout(self, timeout_seconds):
        await asyncio.sleep(timeout_seconds)
        if self.is_updating_display_registers: # If still waiting after timeout
            self.logger.warning(f"Timeout waiting for all display register updates. Expected {len(self.pending_display_register_updates)} more responses.")
            # Mark remaining pending registers as timed out in the table
            # Iterate over a copy for safe removal if needed, though here we just mark
            for reg_info in list(self.pending_display_register_updates):
                name = reg_info["name"]
                for r in range(self.display_reg_table.rowCount()):
                    if self.display_reg_table.item(r, 0).text() == name:
                        timeout_item = QTableWidgetItem("Timeout")
                        timeout_item.setFlags(timeout_item.flags() & ~Qt.ItemIsEditable)
                        timeout_item.setForeground(Qt.red) # Ensure Qt is imported
                        self.display_reg_table.setItem(r, 1, timeout_item)
                        break
            self.pending_display_register_updates.clear()
            self.is_updating_display_registers = False # Reset state

    @asyncSlot()
    async def toggle_connection(self):
        if self.writer is None: # Not connected, so connect
            ip_address = self.ip_edit.text()
            try:
                port = int(self.port_edit.text())
                if not (0 <= port <= 65535):
                    raise ValueError("Port must be 0-65535")
            except ValueError as e:
                self.statusBar().showMessage(f"Error: Invalid port ({e}).")
                return

            self.statusBar().showMessage(f"Connecting to {ip_address}:{port}...")
            self.connect_button.setEnabled(False) # Disable while attempting
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(ip_address, port), timeout=5.0
                )
                self.logger.info(f"Connected to server at {ip_address}:{port}.")
                self.statusBar().showMessage("Connected.")
                self.connect_button.setText("Disconnect")
                self.updates_button.setEnabled(True)
                # Enable R/W UI
                self.reg_combo.setEnabled(True if reg_dict and "ERROR_LOADING_REG_DICT" not in reg_dict else False)
                self.addr_edit.setEnabled(True)
                self.val_edit.setEnabled(True)
                self.read_button.setEnabled(True)
                self.write_button.setEnabled(True)
                # Start the task to listen for server data and put it on the queue
                if self.receive_task is None or self.receive_task.done():
                    self.receive_task = self.loop.create_task(self.receive_server_data_into_queue())
                # Add this line:
                asyncio.create_task(self.update_display_registers_values())
            except asyncio.TimeoutError:
                self.logger.error("Connection timed out.")
                self.statusBar().showMessage("Connection failed: Timeout.")
                self.reader, self.writer = None, None
            except ConnectionRefusedError:
                self.logger.error("Connection refused.")
                self.statusBar().showMessage("Connection failed: Connection refused.")
                self.reader, self.writer = None, None
            except Exception as e:
                self.logger.error(f"Connection failed: {e}", exc_info=True)
                self.statusBar().showMessage(f"Connection failed: {e}")
                self.reader, self.writer = None, None
            finally:
                self.connect_button.setEnabled(True)
        else: # Connected, so disconnect
            self.logger.info("Disconnecting...")
            self.statusBar().showMessage("Disconnecting...")
            self.connect_button.setEnabled(False)

            self.is_receiving_updates = False
            self.ui_update_timer.stop() # Stop UI updates on disconnect
            self.updates_button.setText("Start Updates")
            self.updates_button.setEnabled(False)
            # Disable R/W UI
            self.reg_combo.setEnabled(False)
            self.addr_edit.setEnabled(False)
            self.val_edit.setEnabled(False)
            self.read_button.setEnabled(False)
            self.write_button.setEnabled(False)
            self.val_edit.setText("") # Clear value field on disconnect

            if self.receive_task and not self.receive_task.done():
                self.receive_task.cancel()
                try:
                    await self.receive_task # Allow task to process cancellation
                except asyncio.CancelledError:
                    self.logger.info("Receive task successfully cancelled during disconnect.")
                except Exception as e: # Should not happen if cancellation is handled
                    self.logger.error(f"Error awaiting cancelled receive_task: {e}", exc_info=True)

            if self.writer:
                try:
                    if not self.writer.is_closing():
                        self.writer.close()
                        await self.writer.wait_closed()
                except Exception as e:
                    self.logger.error(f"Error closing writer: {e}", exc_info=True)

            self.reader, self.writer, self.receive_task = None, None, None
            self.logger.info("Disconnected.")
            self.statusBar().showMessage("Disconnected.")
            self.connect_button.setText("Connect")
            self.tableWidget.setRowCount(0) # Clear table on disconnect
            self.connect_button.setEnabled(True)

    async def receive_server_data_into_queue(self):
        self.logger.info("Receiver task started.")
        try:
            while self.writer and not self.writer.is_closing():
                # Try to read a 5-byte header/command first
                prefix = await self.reader.readexactly(5)
                self.logger.debug(f"Received prefix: {prefix}")

                elif prefix == self.RESP_READ_SUCCESS:
                    packed_val = await self.reader.readexactly(4)
                    raw_int_value = struct.unpack('>I', packed_val)[0]

                    if self.is_updating_display_registers and self.pending_display_register_updates:
                        # Get the details of the register this response is for (FIFO assumption)
                        reg_being_updated = self.pending_display_register_updates.pop(0)
                        name = reg_being_updated["name"]
                        reg_type = reg_being_updated["type"]

                        display_value_str = ""
                        # Assuming int_bits_to_float function is available globally
                        if reg_type == "float":
                            float_val = int_bits_to_float(raw_int_value)
                            display_value_str = f"{float_val:.7g}"
                        else: # int type
                            display_value_str = str(raw_int_value) # Or hex(raw_int_value) as needed

                        # Update self.display_reg_table
                        updated_in_table = False
                        for r in range(self.display_reg_table.rowCount()):
                            if self.display_reg_table.item(r, 0).text() == name:
                                value_item = QTableWidgetItem(display_value_str)
                                value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
                                self.display_reg_table.setItem(r, 1, value_item)
                                self.logger.info(f"Display table updated for {name} with value {display_value_str}")
                                updated_in_table = True
                                break
                        if not updated_in_table:
                            self.logger.warning(f"Received update for {name}, but not found in display table. Value: {display_value_str}")

                        if not self.pending_display_register_updates: # All expected display registers updated
                            self.is_updating_display_registers = False
                            # Cancel any pending timeout task explicitly if we can store it.
                            # For now, it will just expire without action if it hasn't fired.
                            self.logger.info("All display registers updated successfully.")
                    else:
                        # This is a response for a user-initiated read from the main R/W controls
                        float_value = int_bits_to_float(raw_int_value)
                        float_display_str = f"{float_value:.7g}"
                        self.loop.call_soon_threadsafe(self.val_edit.setText, float_display_str)
                        status_message = f"Read successful: {float_display_str} (raw: {hex(raw_int_value)})"
                        self.loop.call_soon_threadsafe(self.statusBar().showMessage, status_message)
                        self.logger.info(status_message)
                elif prefix == self.RESP_READ_ERROR:
                    packed_len = await self.reader.readexactly(4)
                    msg_len = struct.unpack('>I', packed_len)[0]
                    error_msg_bytes = await self.reader.readexactly(msg_len)
                    error_msg = error_msg_bytes.decode('utf-8')

                    if self.is_updating_display_registers and self.pending_display_register_updates:
                        # Get the details of the register this error is for (FIFO assumption)
                        reg_being_updated = self.pending_display_register_updates.pop(0)
                        name = reg_being_updated["name"]
                        self.logger.error(f"Read error for display register {name} from server: {error_msg}")

                        # Update self.display_reg_table with error
                        updated_in_table = False
                        for r in range(self.display_reg_table.rowCount()):
                            if self.display_reg_table.item(r, 0).text() == name:
                                error_item = QTableWidgetItem(f"Error: {error_msg}")
                                error_item.setFlags(error_item.flags() & ~Qt.ItemIsEditable)
                                error_item.setForeground(Qt.red) # Ensure Qt is imported
                                self.display_reg_table.setItem(r, 1, error_item)
                                updated_in_table = True
                                break
                        if not updated_in_table:
                             self.logger.warning(f"Received error for {name}, but not found in display table. Error: {error_msg}")

                        if not self.pending_display_register_updates: # All expected display registers processed
                            self.is_updating_display_registers = False
                            # Cancel any pending timeout task here as well if possible.
                            self.logger.info("Finished display register update sequence (some with errors).")
                    else:
                        # Existing error handling for main R/W controls
                        self.logger.error(f"Read error from server (main R/W): {error_msg}")
                        self.loop.call_soon_threadsafe(self.statusBar().showMessage, f"Read error: {error_msg}")
                elif prefix == self.RESP_WRITE_SUCCESS:
                    self.logger.info("Write successful.")
                    self.loop.call_soon_threadsafe(self.statusBar().showMessage, "Write successful.")
                elif prefix == self.RESP_WRITE_ERROR:
                    packed_len = await self.reader.readexactly(4)
                    msg_len = struct.unpack('>I', packed_len)[0]
                    error_msg_bytes = await self.reader.readexactly(msg_len)
                    error_msg = error_msg_bytes.decode('utf-8')
                    self.logger.error(f"Write error from server: {error_msg}")
                    self.loop.call_soon_threadsafe(self.statusBar().showMessage, f"Write error: {error_msg}")

                elif prefix == self.REG_DATA_SNAPSHOT_HEADER[:5]:
                    remaining_header = await self.reader.readexactly(len(self.REG_DATA_SNAPSHOT_HEADER) - 5)
                    full_header = prefix + remaining_header
                    if full_header == self.REG_DATA_SNAPSHOT_HEADER:
                        packed_len = await self.reader.readexactly(4)
                        json_len = struct.unpack('>I', packed_len)[0]
                        if json_len == 0:
                            await self.ui_update_queue.put({})
                            self.logger.debug("Received empty snapshot.")
                            continue
                        json_bytes = await self.reader.readexactly(json_len)
                        snapshot_str = json_bytes.decode('utf-8')
                        try:
                            snapshot = json.loads(snapshot_str)
                            await self.ui_update_queue.put(snapshot)
                            self.logger.debug(f"Received and queued snapshot of {json_len} bytes.")
                        except json.JSONDecodeError as e:
                            self.logger.error(f"JSON decode error: {e}. Data: '{snapshot_str}'")
                    else:
                        self.logger.error(f"Corrupted/Unknown data stream. Expected snapshot header, got {full_header}")
                        await self.handle_disconnection_in_task()
                        break
                else:
                    self.logger.error(f"Unexpected prefix received: {prefix}. Expected R/W response or snapshot header part.")
                    await self.handle_disconnection_in_task()
                    break
        except asyncio.CancelledError:
            self.logger.info("Receiver task explicitly cancelled.")
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError) as e:
            self.logger.info(f"Connection lost in receiver task: {e}")
            await self.handle_disconnection_in_task()
        except Exception as e:
            self.logger.error(f"Unhandled error in receiver task: {e}", exc_info=True)
            await self.handle_disconnection_in_task()
        finally:
            self.logger.info("Receiver task finished.")
            # Ensure UI reflects disconnection if task ends unexpectedly while still "connected"
            if self.writer and not self.writer.is_closing():
                 self.logger.warning("Receiver task ended but writer still active. Forcing UI disconnect.")
                 # This situation might indicate an unhandled case or race condition.
                 # Forcing a UI update to "Disconnected" state.
                 await self.handle_disconnection_in_task()


    async def handle_disconnection_in_task(self):
        # This method is called from within the receiver task when a connection issue is detected.
        # It ensures the UI state is updated to reflect disconnection.
        if self.writer: # If we thought we were connected
            self.logger.info("handle_disconnection_in_task: Connection issue detected, ensuring UI disconnect.")
            # Call toggle_connection which will handle UI updates and resource cleanup
            # Need to schedule this on the loop as this is called from another task.
            self.loop.call_soon_threadsafe(asyncio.create_task, self.toggle_connection())


    @asyncSlot()
    async def toggle_updates(self):
        if self.writer is None or self.writer.is_closing():
            self.statusBar().showMessage("Not connected to server.")
            return

        if self.is_receiving_updates:
            # Currently receiving, so stop updates
            self.is_receiving_updates = False
            self.ui_update_timer.stop()
            self.updates_button.setText("Start Updates")
            self.statusBar().showMessage("UI updates stopped.")
            self.logger.info("UI updates stopped by user.")
        else:
            # Currently not receiving, so start updates
            self.is_receiving_updates = True
            # Process any items already in queue immediately, then start timer
            self.process_ui_queue()
            self.ui_update_timer.start(200)  # Update UI every 200ms
            self.updates_button.setText("Stop Updates")
            self.statusBar().showMessage("Receiving live updates...")
            self.logger.info("UI updates started by user.")

    def process_ui_queue(self):
        """Processes snapshots from the queue and updates the UI table."""
        if not self.is_receiving_updates and not self.ui_update_queue.empty():
             # If updates were stopped but queue still has items, process them once more
             self.logger.info("Processing remaining items in UI queue after updates stopped.")
        elif not self.is_receiving_updates:
            return # Do nothing if updates are stopped and queue is empty

        latest_snapshot = None
        items_processed_this_tick = 0
        try:
            # Process all items currently in the queue to show the latest state
            # In a very high-frequency scenario, this might still lag if UI rendering is slow.
            # A more advanced approach might only render the very last item if queue grows too large.
            while not self.ui_update_queue.empty():
                latest_snapshot = self.ui_update_queue.get_nowait()
                items_processed_this_tick +=1

            if latest_snapshot is not None:
                self.logger.debug(f"Processing {items_processed_this_tick} snapshot(s) from queue. Updating UI with last one.")
                self.tableWidget.setSortingEnabled(False) # Performance for large updates
                # self.tableWidget.setRowCount(0) # Clear table - can be slow for frequent updates

                # Efficiently update table: update existing items, add/remove rows if count changes
                current_row_count = self.tableWidget.rowCount()
                snapshot_len = len(latest_snapshot)

                if current_row_count != snapshot_len:
                    self.tableWidget.setRowCount(snapshot_len)

                row = 0
                for reg_name, value in latest_snapshot.items():
                    name_item = self.tableWidget.item(row, 0)
                    value_item = self.tableWidget.item(row, 1)

                    if not name_item: # Create new item if it doesn't exist
                        name_item = QTableWidgetItem()
                        self.tableWidget.setItem(row, 0, name_item)
                    name_item.setText(str(reg_name))

                    val_str = str(value)
                    if not value_item: # Create new item if it doesn't exist
                        value_item = QTableWidgetItem()
                        self.tableWidget.setItem(row, 1, value_item)
                    value_item.setText(val_str)

                    if isinstance(value, dict) and "error" in value: # Check original value for error content
                        value_item.setForeground(Qt.red)
                    elif "ERROR" in val_str.upper(): # Check string for "ERROR"
                        value_item.setForeground(Qt.red)
                    else:
                        value_item.setForeground(Qt.black) # Default color
                    row += 1

                if items_processed_this_tick > 0: # Only resize if actual update happened
                    self.tableWidget.resizeColumnsToContents()
                self.tableWidget.setSortingEnabled(True)
                self.logger.debug(f"UI updated with {len(latest_snapshot)} registers.")
            elif self.is_receiving_updates: # If timer is running but queue was empty
                self.logger.debug("UI update tick: No new data in queue.")

        except asyncio.QueueEmpty: # Should not happen with while not empty()
            self.logger.debug("UI update queue is empty.")
        except Exception as e:
            self.logger.error(f"Error processing UI update queue: {e}", exc_info=True)

    @asyncSlot()
    async def read_register(self):
        if self.writer is None or self.writer.is_closing():
            self.statusBar().showMessage("Not connected to server.")
            return

        address_str = self.addr_edit.text()
        abs_address = self._parse_input_value(address_str, "Address")
        if abs_address is None:
            return

        self.statusBar().showMessage(f"Reading from {hex(abs_address)}...")
        try:
            # CMD_READ_REG is 5 bytes, defined in server
            cmd = b"RD_RG"
            packed_addr = struct.pack('>I', abs_address)

            self.writer.write(cmd + packed_addr)
            await self.writer.drain()
            self.logger.info(f"Sent READ command for address {hex(abs_address)}.")

            # Add this line to trigger display registers update:
            asyncio.create_task(self.update_display_registers_values())

        except Exception as e:
            self.logger.error(f"Error sending read command: {e}", exc_info=True)
            self.statusBar().showMessage(f"Error sending read command: {e}")
            # Also trigger update here, as the action is "complete" (though failed)
            asyncio.create_task(self.update_display_registers_values())

    @asyncSlot()
    async def write_register(self):
        if self.writer is None or self.writer.is_closing():
            self.statusBar().showMessage("Not connected to server.")
            return

        reg_info = self.reg_combo.currentData()
        if not reg_info or not isinstance(reg_info, dict) : # "Select Register..." or invalid data
            self.statusBar().showMessage("Please select a valid register.")
            return

        abs_address = reg_info["address"] # Already an int
        reg_type = reg_info.get("type", "int") # Default to int if type not specified

        value_str = self.val_edit.text()
        value_to_write = None

        if reg_type == "float":
            try:
                float_val = float(value_str)
                # Convert float to its 32-bit big-endian binary representation, then to int
                packed_bytes = struct.pack('>f', float_val)
                value_to_write = int.from_bytes(packed_bytes, 'big')
            except ValueError:
                self.statusBar().showMessage(f"Error: Invalid float value '{value_str}'.")
                return
            except Exception as e: # Other struct/packing errors
                self.statusBar().showMessage(f"Error converting float: {e}")
                return
        else: # int or default
            value_to_write = self._parse_input_value(value_str, "Value")
            if value_to_write is None:
                return # Error message already shown by _parse_input_value
            if not (0 <= value_to_write <= 0xFFFFFFFF): # Check range for unsigned 32-bit int
                self.statusBar().showMessage("Error: Integer value out of range for 32-bit register (0 to 0xFFFFFFFF).")
                return

        # At this point, value_to_write is an integer (either the direct int or the float's bit pattern)
        self.statusBar().showMessage(f"Writing {value_str} (as {hex(value_to_write)}) to {reg_info.get('name', hex(abs_address))} ({reg_type})...")
        try:
            cmd = b"WR_RG"
            packed_addr = struct.pack('>I', abs_address)
            packed_val = struct.pack('>I', value_to_write) # Server expects a 32-bit unsigned int

            self.writer.write(cmd + packed_addr + packed_val)
            await self.writer.drain()
            self.logger.info(f"Sent WRITE command for {reg_info.get('name', hex(abs_address))} with value {value_str} (packed as {hex(value_to_write)}).")

            # Add this line to trigger display registers update:
            asyncio.create_task(self.update_display_registers_values())

        except Exception as e:
            self.logger.error(f"Error sending write command: {e}", exc_info=True)
            self.statusBar().showMessage(f"Error sending write command: {e}")
            # Also trigger update here
            asyncio.create_task(self.update_display_registers_values())

    @asyncClose
    async def closeEvent(self, event):
        self.logger.info("Close event triggered.")
        if self.writer: # If connected
            await self.toggle_connection() # Gracefully disconnect
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    client_win = AsyncClientApp(loop=loop)
    client_win.show()

    with loop:
        loop.run_forever()
