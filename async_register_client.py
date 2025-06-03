import sys
import asyncio
import json
import struct
import logging

from qasync import QEventLoop, asyncSlot, asyncClose

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QStatusBar, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer # Added QTimer

# Constants
SERVER_HOST_DEFAULT = 'localhost'
SERVER_PORT_DEFAULT = 50005
REG_DATA_SNAPSHOT_HEADER = b"REG_SNAP" # 8 bytes

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__) # Moved to class as self.logger

class AsyncClientApp(QMainWindow):
    def __init__(self, loop=None):
        super().__init__()
        self.loop = loop or asyncio.get_event_loop()
        self.logger = logging.getLogger(__name__) # Logger as instance member
        self.initUI()

        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None
        self.receive_task: asyncio.Task = None
        self.is_receiving_updates = False
        self.ui_update_queue = asyncio.Queue()
        self.ui_update_timer = QTimer(self) # Initialize QTimer
        self.ui_update_timer.timeout.connect(self.process_ui_queue) # Connect its timeout signal

    def initUI(self):
        self.setWindowTitle("Async Register Viewer")
        self.setGeometry(100, 100, 700, 500)

        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

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
        self.updates_button.clicked.connect(self.toggle_updates) # Placeholder for now
        connection_layout.addWidget(self.updates_button)

        connection_layout.addStretch(1)
        main_layout.addLayout(connection_layout)

        # Table for register data
        self.tableWidget = QTableWidget()
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Register Name", "Value"])
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        main_layout.addWidget(self.tableWidget)

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

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
                self.updates_button.setEnabled(True) # Enable "Start Updates"
                # Start the task to listen for server data and put it on the queue
                if self.receive_task is None or self.receive_task.done():
                    self.receive_task = self.loop.create_task(self.receive_server_data_into_queue())
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
                header = await self.reader.readexactly(len(REG_DATA_SNAPSHOT_HEADER))
                if header == REG_DATA_SNAPSHOT_HEADER:
                    packed_len = await self.reader.readexactly(4)
                    json_len = struct.unpack('>I', packed_len)[0]

                    if json_len == 0: # Handle empty snapshot case if server sends it
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
                    self.logger.error(f"Unexpected header received: {header}. Expected: {REG_DATA_SNAPSHOT_HEADER}")
                    await self.handle_disconnection_in_task() # Treat as critical error
                    break
        except asyncio.CancelledError:
            self.logger.info("Receiver task explicitly cancelled.")
            # No need to call handle_disconnection_in_task here as cancellation is an external request
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
```
