import sys
import socket
import struct
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QStatusBar, QHeaderView
)
from PyQt5.QtCore import Qt

# Define constants at module or class level
START_CMD = b"STARTCMD"
REG_DATA_HEADER = b"REG_DATA"

class SimpleClientApp(QMainWindow):
    START_CMD = b"STARTCMD" # Can also be a class attribute
    REG_DATA_HEADER = b"REG_DATA"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Register Viewer")
        self.setGeometry(100, 100, 600, 400) # x, y, width, height
        self.initUI()

    def initUI(self):
        # Main widget and layout
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Connection layout
        connection_layout = QHBoxLayout()

        # Server IP input
        self.ip_label = QLabel("Server IP:")
        connection_layout.addWidget(self.ip_label)
        self.ip_input = QLineEdit("localhost")
        connection_layout.addWidget(self.ip_input)

        # Server Port input
        self.port_label = QLabel("Port:")
        connection_layout.addWidget(self.port_label)
        self.port_input = QLineEdit("50004")
        self.port_input.setFixedWidth(60)
        connection_layout.addWidget(self.port_input)

        # Connect button
        self.connect_button = QPushButton("Connect & Fetch Data")
        self.connect_button.clicked.connect(self.connect_and_fetch_data)
        connection_layout.addWidget(self.connect_button)
        
        connection_layout.addStretch(1) # Pushes elements to the left

        main_layout.addLayout(connection_layout)

        # Table for register data
        self.tableWidget = QTableWidget()
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Register Name", "Value"])
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        main_layout.addWidget(self.tableWidget)

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

    def connect_and_fetch_data(self):
        ip_address = self.ip_input.text()
        try:
            port = int(self.port_input.text())
            if not (0 <= port <= 65535):
                raise ValueError("Port number must be between 0 and 65535.")
        except ValueError as e:
            self.statusBar.showMessage(f"Error: Invalid port number. {e}")
            return

        self.statusBar.showMessage(f"Connecting to {ip_address}:{port}...")
        QApplication.processEvents() # Update the UI

        self.sock = None # Renamed from client_socket for clarity if used as instance member often
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5) # 5-second timeout for connection
            self.sock.connect((ip_address, port))
            self.statusBar.showMessage("Connected. Sending START command...")
            QApplication.processEvents()

            # Send STARTCMD
            self.sock.sendall(self.START_CMD) # Use class/instance attribute
            self.statusBar.showMessage("START command sent. Waiting for register data...")
            QApplication.processEvents()

            # Set timeout for receiving response header
            self.sock.settimeout(15.0) 

            # Receive 8-byte header
            header = self.sock.recv(len(self.REG_DATA_HEADER)) # Use constant for length
            if header != self.REG_DATA_HEADER:
                self.statusBar.showMessage(f"Error: Invalid data header received: {header.decode(errors='ignore')}")
                return

            # Receive 4-byte length for JSON string
            len_bytes = self.sock.recv(4)
            if len(len_bytes) < 4:
                self.statusBar.showMessage("Error: Did not receive complete length information for JSON payload.")
                return
            json_len = struct.unpack('>I', len_bytes)[0]
            self.statusBar.showMessage(f"Receiving {json_len} bytes of JSON data...")
            QApplication.processEvents()

            # Receive JSON string
            json_data_bytes = b''
            bytes_received = 0
            # Timeout for data reception is already set (15s)
            while bytes_received < json_len:
                chunk_size = min(4096, json_len - bytes_received) # Read in chunks
                chunk = self.sock.recv(chunk_size)
                if not chunk:
                    self.statusBar.showMessage("Error: Connection lost while receiving JSON data.")
                    return
                json_data_bytes += chunk
                bytes_received += len(chunk)
            
            json_data_str = json_data_bytes.decode('utf-8')
            
            # Deserialize JSON
            try:
                register_data = json.loads(json_data_str)
            except json.JSONDecodeError as e:
                self.statusBar.showMessage(f"Error: Could not decode JSON data: {e}")
                print(f"Problematic JSON string: '{json_data_str}'")
                return

            # Populate table
            self.tableWidget.setRowCount(0) # Clear existing rows
            self.tableWidget.setRowCount(len(register_data))
            
            row = 0
            for reg_name, value in register_data.items():
                self.tableWidget.setItem(row, 0, QTableWidgetItem(str(reg_name)))
                if isinstance(value, dict) and "error" in value:
                    item = QTableWidgetItem(f"Error: {value['error']}")
                    item.setForeground(Qt.red)
                else:
                    item = QTableWidgetItem(str(value))
                self.tableWidget.setItem(row, 1, item)
                row += 1
            
            self.tableWidget.resizeColumnsToContents()
            self.statusBar.showMessage("Data fetched and displayed successfully.", 5000) # Disappears after 5s

        except socket.timeout:
            self.statusBar.showMessage("Error: Connection or data reception timed out.")
        except socket.error as e: # Covers sendall, recv, connect errors
            self.statusBar.showMessage(f"Socket Error: {e}")
        except json.JSONDecodeError as e: # Specific error for JSON issues
            self.statusBar.showMessage(f"Error: Could not decode JSON data: {e}")
            # It might be useful to log the problematic string if possible, but not shown in status bar
        except Exception as e: # Generic catch-all for other unexpected errors
            self.statusBar.showMessage(f"An unexpected error occurred: {e}")
        finally:
            if self.sock:
                self.sock.close()
                self.sock = None # Good practice to nullify after closing

if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWin = SimpleClientApp()
    mainWin.show()
    sys.exit(app.exec_())
