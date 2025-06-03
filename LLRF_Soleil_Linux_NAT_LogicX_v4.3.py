from ConnectServer import ConnectServer
from PyQt5.QtWidgets import QMainWindow, QApplication
from reg_dict import reg_dict # Added import
import socket # Added import for socket.timeout
# # import matplotlib.pyplot as pyplt # Unused
from Plotter import CustomWidget
from PyQt5 import QtWidgets, uic
from pyqtgraph.Qt import QtCore
from PyQt5.QtCore import QDate, QTime, QDateTime, Qt
import pyqtgraph as pg
from mapping import mapping
# Python program to calculate
# cumulative moving averages using pandas
import pandas as pd
from qasync import QEventLoop
import sys
import time
# import re # Unused
# import string # Unused
# #from apscheduler.schedulers.blocking import BlockingScheduler # Unused
import struct
import numpy as np
import math
# import pandas as pd # Duplicate
from xlutils.copy import copy
import xlrd

from ctypes import *
import json
from functools import wraps # for decorator
import CS_bigdata

import line_profiler
from qt_material import apply_stylesheet
import pandas as pd
from datetime import datetime
import threading
from read_reg_list import extract_tango_registers
import asyncio
###

t = 0  # write/read config from line 0
n_bit = 5
# lock = threading.Lock() # Unused
# upload to gitlab
file = 'config.xlsx'
class llrf_graph_window(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load the UI Page
        self.plot_time = 1000
        self._pause_flag = False
        # # self.addr_adc01_gain = 0xb0010000 # Unused
        # #  self.addr_adc23_gain = 0xb0020000 # Unused
        self.ui = uic.loadUi("UI_llrf_4.3.ui", self)
        self.setWindowTitle("LLRF - Soleil - expert")
        self.user_mode()
        self.set_plot_ui()
        self.btn_fct()
        self.update_time_date()
        # timer for plot
        self.timer = QtCore.QTimer()
        self.timer.setInterval(self.plot_time)
        self.load_config()
        # self.n0 = 0 # Unused
        # self.n1 = 0 # Unused
        # self.n4 = 0 # Unused
        # self.n5 = 0 # Unused
        # self.n6 = 0 # Unused
        # self.n7 = 0 # Unused
        # self.n_buf_q = [[] for _ in range(8)] # Unused
        # self.n_buf_i = [[] for _ in range(8)] # Unused
        #self.child_pi_controler = None
        self.PI = 3.14159265

        #
        self.sw1 = 0
        #self.sw2 = 0 # sw2 = 0 for open loop, sw2 = 2048 for close loop
        self.sw3 = 0

        column = ['Time','Val_Ref']
        self.df = pd.DataFrame(columns=column)
        self.excel_file  = 'save_ref_val.xlsx'
        self.last_save_time = None

    def pause_restart(function):
    #     '''
    #     第一层函数为装饰器名称
    #     function：参数，即需要装饰的函数
    #     return：返回值wrapper，为了保持与原函数参数一致
        @wraps(function)
        def wrapper(self):
            '''
            内层函数，这个函数实现“添加额外功能”的任务
            *arg,**args：参数保持与需要装饰的函数参数一致，这里用*arg和**args代替
            '''
            #这里就是额外功能代码
            self.pause_update_plot()
            function(self)   #执行原函数
            #这里就是额外功能代码
            self.restart_update_plot()
            return function(self)

        return wrapper

    def IQ_phase_shift(self, phase):
       # print("phase is", phase)
        cos_angle = int((pow(2.0, 15.0) - 1) * np.cos(phase * np.pi / 180.0))
        sin_angle = int((pow(2.0, 15.0) - 1) * np.sin(phase * np.pi / 180.0))

        return (sin_angle << 16) | (cos_angle & 0xffff)

    def load_cav_loop_setting(self, amps_reg_name, phase_reg_name, loop_setting_reg_name): # Signature changed
        amp_cav_setpoint = self.read_val_from_reg(amps_reg_name)
        phase_cav_setpoint = self.read_val_from_reg(phase_reg_name)
        loop_setting = self.read_val_from_reg(loop_setting_reg_name)

        if amp_cav_setpoint is not None:
            self.ui_actual_mag.setText(str(amp_cav_setpoint))
        else:
            self.ui_actual_mag.setText("N/A")

        if phase_cav_setpoint is not None:
            self.ui_actual_pha.setText(str(phase_cav_setpoint))
        else:
            self.ui_actual_pha.setText("N/A")

        if loop_setting == 1:
            self.ui_radio_close.setChecked(True)
        elif loop_setting == 0:
            self.ui_radio_open.setChecked(True)
        else:
            self.ui_radio_open.setChecked(True)
            # print(f"Warning: Unexpected loop_setting value: {loop_setting} for {loop_setting_reg_name}")

    def hex_to_signed_int(self, hex_str):
        # Convert hexadecimal string to signed integer
        int_value = int(hex_str)
        # Check if the most significant bit (MSB) is set (indicating negative number)
        if int_value & 0x8000:
            int_value -= 0x10000  # Convert from 16-bit unsigned to signed
        return int_value

    def load_mapping(self):
        file = self.excel_path.text()
        # obj
        obj_mapping = mapping(file,'Name','Master Base Address')
        # dataFrame mapping
        df_mapping = obj_mapping.get_mapping()
        # print(df_mapping)
        '''
        BRAM data start address and one bloc size
        '''
        # BRAM 0 address
        self.bram0_addr=[]
        self.bram_addr =[]

        bram0_row = df_mapping[df_mapping['Name'].str.contains("/user_space/embedded_scope/axi_bram_ctrl_0")]
        self.bram0_addr= bram0_row['Master Base Address'].values[0]
        # find number of bram
        target_string = "/user_space/embedded_scope/axi_bram_ctrl"
        self.nbr_bram = df_mapping['Name'].str.contains(target_string).sum()
        # find each bram address
        for i in range(self.nbr_bram):
            self.bram_addr.append(self.bram0_addr + i * 0x2000)

        # to get bram start and end
        bram_end = '/user_space/embedded_scope/axi_bram_ctrl_'+str(self.nbr_bram-1)+'/S_AXI'
        bram_start ='/user_space/embedded_scope/axi_bram_ctrl_0/S_AXI'
        trig_acq = '/user_space/embedded_scope/axi_gpio_BRAM_Trig/S_AXI'

        # to get mapping start
        # find min ignore nan
        self.map_start =df_mapping['Master Base Address'].min(skipna=True)
        print(hex(self.map_start))
        self.map_end =df_mapping['Master Base Address'].max(skipna=True)

        self.trig_acq = df_mapping.loc[df_mapping['Name'] == trig_acq, 'Master Base Address'].values
        self.bram_start= df_mapping.loc[df_mapping['Name'] == bram_start, 'Master Base Address'].values
        self.bram_end = df_mapping.loc[df_mapping['Name'] == bram_end, 'Master Base Address'].values
        self.trig_acq = self.trig_acq[0]
        self.bram_start = self.bram_start[0]
        self.bram_end = self.bram_end[0]

        print(hex(self.trig_acq), hex(self.bram_start), hex(self.bram_end))
        self.bram_offset = []
        for addr in self.bram_addr:
            addr_offset = addr - self.map_start
            self.bram_offset.append(addr_offset)
        self.load_reg_mapping()

    def load_reg_mapping(self):
        file = self.excel_path_reg.text()
        obj_mapping = mapping(file,'Name','Master Base Address')
        df_mapping = obj_mapping.get_mapping()

        # file_path = "/home/lu/cross_compile/rf_manager_header.h" # This was original
        # register_dict_from_h = extract_tango_registers(file_path) # This was original
        # Using reg_dict from reg_dict.py now, so the above lines are not strictly needed for these values
        # However, self.xxx_addr are used elsewhere, so keep them for now, but ensure they are string names if used with new functions

        self.list_reg_offset = []
        self.list_reg_offset.append(self.trig_acq - self.map_start)
        self.list_reg_offset.append(self.bram_end - self.map_start)
        self.list_reg_offset.append(self.bram_start - self.map_start)
        self.list_reg_offset.append(self.nbr_bram)

        # These are now string names, not addresses from the header file
        self.cav_mag_setpoint_addr_str = "REG_CavMag_SetPoint"
        self.cav_phase_setpoint_addr_str = "REG_CavPhase_SetPoint"
        self.loop_close_open_addr_str = "REG_CavPI_Open_Close_Loop"
        self.cav_emulator_addr_str = "REG_Cavity_Emulator"

        self.adc0_low_resol_addr_str = "REG_ADC0gain"
        self.adc1_low_resol_addr_str = "REG_ADC1gain"
        self.adc2_low_resol_addr_str = "REG_ADC2gain"
        self.adc3_low_resol_addr_str = "REG_ADC3gain"

        self.adc0_high_resol_addr_str = "REG_Gain_Ctrl0"
        self.adc1_high_resol_addr_str = "REG_Gain_Ctrl1"
        self.adc2_high_resol_addr_str = "REG_Gain_Ctrl2"
        self.adc3_high_resol_addr_str = "REG_Gain_Ctrl3"

        self.update_msg('mappng loaded')
        self.str_list_reg_offset = [str(num) for num in self.list_reg_offset]
        for val in self.list_reg_offset:
            print(hex(val))
        # ... rest of the function ...

    def save_config(self):
        wb = xlrd.open_workbook(filename=file)
        new_wb = copy(wb)
        try:
            sheet1 = new_wb.get_sheet(0)
        except IndexError:
            sheet1 = new_wb.add_sheet('set')

        sheet1.write(t, 0, self.server_ip.text())
        sheet1.write(t, 1, self.server_port.text())
        sheet1.write(t, 2, self.ui_ph0_deg.text())
        sheet1.write(t, 3, self.ui_ph0_add.text())
        sheet1.write(t, 4, self.ui_ph1_deg.text())
        sheet1.write(t, 5, self.ui_ph1_add.text())
        sheet1.write(t, 6, self.ui_ph2_deg.text())
        sheet1.write(t, 7, self.ui_ph2_add.text())
        sheet1.write(t, 8, self.ui_ph3_deg.text())
        sheet1.write(t, 9, self.ui_ph3_add.text())
        sheet1.write(t, 10, self.excel_path.text())

        sheet1.write(t, 12, self.refresh_time.text())

        new_wb.save(file)
        self.update_msg('Configuration saved!!!')
    def load_config(self):
        wb = xlrd.open_workbook(filename=file)
        try:
            sheet1 = wb.sheet_by_index(0)
            self.server_ip.setText(sheet1.cell_value(t, 0))
            self.server_port.setText(sheet1.cell_value(t, 1))
            self.ui_ph0_deg.setText(sheet1.cell_value(t, 2))
            self.ui_ph0_add.setText(sheet1.cell_value(t, 3))
            self.ui_ph1_deg.setText(sheet1.cell_value(t, 4))
            self.ui_ph1_add.setText(sheet1.cell_value(t, 5))
            self.ui_ph2_deg.setText(sheet1.cell_value(t, 6))
            self.ui_ph2_add.setText(sheet1.cell_value(t, 7))
            self.ui_ph3_deg.setText(sheet1.cell_value(t, 8))
            self.ui_ph3_add.setText(sheet1.cell_value(t, 9))
            self.excel_path.setText(sheet1.cell_value(t, 10))

            self.refresh_time.setText(sheet1.cell_value(t, 12))
        except IndexError:
            new_wb = copy(wb)
            sheet1 = new_wb.add_sheet('set')
            sheet1.write(t, 0, self.server_ip.text())
            sheet1.write(t, 1, self.server_port.text())
            # ... (rest of the initial writes)
            new_wb.save(file)
            self.update_msg('first start')

        self.last_ch0_ph = self.ui_ph0_deg.text()
        self.last_ch1_ph = self.ui_ph1_deg.text()
        self.last_ch2_ph = self.ui_ph2_deg.text()
        self.last_ch3_ph = self.ui_ph3_deg.text()

        self.ui_ph0_deg.returnPressed.connect(self.check_val)
        self.ui_ph1_deg.returnPressed.connect(self.check_val)
        self.ui_ph2_deg.returnPressed.connect(self.check_val)
        self.ui_ph3_deg.returnPressed.connect(self.check_val)

        adc_gains = [ self.ui_adc0_gain, self.ui_adc1_gain, self.ui_adc2_gain, self.ui_adc3_gain ]
        for adc_gain in adc_gains: adc_gain.returnPressed.connect(self.set_adc_gain)

        high_res_adc_gains = [ self.ui_adc0_gain_2, self.ui_adc1_gain_2, self.ui_adc2_gain_2, self.ui_adc3_gain_2 ]
        for high_res_adc_gain in high_res_adc_gains: high_res_adc_gain.returnPressed.connect(self.set_high_resolution_adc_gain)

        self.ui_measure_times.returnPressed.connect(self.update_measure_times)

    @pause_restart
    def update_measure_times(self):
        self.fifo_q =[[] for _ in range(self.nbr_bram)]
        self.fifo_i = [[] for _ in range(self.nbr_bram)]
        self.I_moy = [[] for _ in range(self.nbr_bram)]
        self.Q_moy = [[] for _ in range(self.nbr_bram)]
        self.n_measure = np.zeros(self.nbr_bram)

    def update_time_date(self):
        self.time_date = QtCore.QTimer()
        self.time_date.setInterval(1000)
        self.time_date.timeout.connect(self.disp_time_date)
        self.time_date.start()

    def disp_time_date(self):
        td = QDateTime.currentDateTime()
        self.current_dt.setText(td.toString())

    def btn_fct(self):
        self.button_init.clicked.connect(self.connect_server)
        self.button_stop.clicked.connect(self.stop_connect)
        self.button_start.clicked.connect(self.start_acq)
        self.button_set_bram.clicked.connect(self.load_mapping)
        self.button_save_config.clicked.connect(self.save_config)
        self.ui_radio_open.clicked.connect(self.open_cav_loop)
        self.ui_radio_close.clicked.connect(self.close_cav_loop)
        self.ui_radio_with_emulator.clicked.connect(self.W_cav_emulator)
        self.ui_radio_without_emulator.clicked.connect(self.W_O_cav_emulator)
        self.btn_submit_ref.clicked.connect(self.submit_cav_setting)

    def load_cav_emulator_status(self, reg_name):
        flag = self.read_val_from_reg(reg_name)
        if flag == 1:
            self.ui_radio_with_emulator.setChecked(True)
        elif flag == 0:
            self.ui_radio_without_emulator.setChecked(True)
        else:
            self.ui_radio_without_emulator.setChecked(True)

    @pause_restart
    def W_O_cav_emulator(self):
        self.write_val_to_reg(self.cav_emulator_addr_str, 0)
        self.load_cav_emulator_status(self.cav_emulator_addr_str)

    @pause_restart
    def W_cav_emulator(self):
        self.write_val_to_reg(self.cav_emulator_addr_str, 1)
        self.load_cav_emulator_status(self.cav_emulator_addr_str)

    @pause_restart
    def close_cav_loop(self):
        self.write_val_to_reg(self.loop_close_open_addr_str, 0)
        self.load_cav_loop_setting(self.cav_mag_setpoint_addr_str, self.cav_phase_setpoint_addr_str, self.loop_close_open_addr_str)

    @pause_restart
    def open_cav_loop(self):
        self.write_val_to_reg(self.loop_close_open_addr_str, 1)
        self.load_cav_loop_setting(self.cav_mag_setpoint_addr_str, self.cav_phase_setpoint_addr_str, self.loop_close_open_addr_str)

    def volt2dbm(self,v):
        # ... (original content)
        if isinstance(v, (list, tuple)):
            vpp = max(v) - min(v)
            vpp = vpp/(pow(2,15)-1)
            return 10+20*np.log10(0.5*vpp)
        else:
            return 10*np.log10(v*v*1000/8/50)

    def adc_characterize(self):
        # ... (original content, assuming sml_ctl and get_data don't use the modified functions directly)
        pass

    def threading_submit_cav_setting(self): # This function seems to be unused if btn_submit_ref directly calls submit_cav_setting
        t=threading.Thread(target=self.submit_cav_setting,name='submit_cav_setting')
        t.start()
        t.join()
        self.update_msg('Cavity setting submitted!!')

    def submit_cav_setting(self):
        try:
            mag = float(self.ui_setpoint_mag.text())
            self.write_val_to_reg(self.cav_mag_setpoint_addr_str, mag)
            phase = float(self.ui_setpoint_pha.text())
            self.write_val_to_reg(self.cav_phase_setpoint_addr_str, phase)
            self.load_cav_loop_setting(self.cav_mag_setpoint_addr_str, self.cav_phase_setpoint_addr_str, self.loop_close_open_addr_str)
        except ValueError as e:
            self.update_msg(f"Error in cavity setting input: {e}")
        except Exception as e:
            self.update_msg(f"Failed to submit cavity settings: {e}")

    def calc_phase_angle(self, ch): # This function uses direct socket send, not write_val_to_reg
        # ... (original content)
        if ch == 0:
            phase = self.ui_ph0_deg.text()
            addr = self.ui_ph0_add.text()
        # ... (rest of elifs)
        try:
            ph = np.float(phase)
            self.mysocket.send(b"2")
            msg = str(ph) + ',' + addr
            self.mysocket.send(msg.encode())
            time.sleep(0.1)
            self.update_msg('Now, you are right, the phase updated!!')
        except ValueError:
            self.update_msg('You have enter number!!!')


    def user_mode(self):
        self.button_init.hide()
        self.button_start.hide()
        self.button_stop.hide()

    def set_plot_ui(self):
        # ... (original content)
        pass

    def first_plot(self):
        # ... (original content)
        pass

    def check_val(self):
        # ... (original content calls calc_phase_angle which is not changed for write_val_to_reg)
        pass

    def update_refresh_time(self):
        # ... (original content)
        pass

    def start_async_loop(self):
        # ... (original content)
        pass

    async def fetch_data(self):
        # ... (original content)
        pass

    def display_channel_data(self, channel, amp_avg, phi_avg, amp_std, phi_std):
        # ... (original content)
        pass

    def pause_update_plot(self):
        self._pause_flag = True
        # self._pause_time = self.update_refresh_time
        self.timer.stop()

    def write_val_to_reg(self, reg_name: str, value): # KEEP THE ALREADY MODIFIED VERSION
        if reg_name not in reg_dict:
            msg = f"Error: Register '{reg_name}' not found in reg_dict."
            print(msg)
            self.update_msg(msg)
            return

        reg_info = reg_dict[reg_name]
        address = reg_info["address"]
        reg_type = reg_info.get("type", "int")

        if hasattr(self, 'map_start') and self.map_start is not None and address >= self.map_start:
             offset_addr = address - self.map_start
        else:
             offset_addr = address

        self.mysocket.send(b"5")

        msg_payload_str = ""
        if reg_type == "float":
            try:
                val_float = float(value)
                packed_float = struct.pack('>f', val_float)
                integer_representation = int.from_bytes(packed_float, byteorder='big')
                msg_payload_str = str(integer_representation) + ',' + str(hex(offset_addr))
            except ValueError:
                self.update_msg(f"Error: Invalid float value '{value}' for {reg_name}.")
                return
            except Exception as e:
                self.update_msg(f"Error packing float for {reg_name}: {e}")
                return
        elif reg_type == "int":
            try:
                val_int = int(value)
                msg_payload_str = str(val_int) + ',' + str(hex(offset_addr))
            except ValueError:
                self.update_msg(f"Error: Invalid integer value '{value}' for {reg_name}.")
                return
        else:
            self.update_msg(f"Error: Unknown type '{reg_type}' for {reg_name}.")
            return

        i = 0
        ack_received = False
        original_timeout = self.mysocket.gettimeout()
        self.mysocket.settimeout(0.1)

        while i <= 20:
            try:
                response = self.mysocket.recv(512).decode()
                if response == 'waiting':
                    ack_received = True
                    break
            except socket.timeout: pass
            except Exception as e: break
            i += 1
            if i > 0 : time.sleep(0.01)

        self.mysocket.settimeout(original_timeout)

        if ack_received:
            self.mysocket.send(msg_payload_str.encode())
            self.update_msg(f"Wrote {value} ({reg_type}) to {reg_name} @ {hex(address)}")
        else:
            self.update_msg(f"No 'waiting' ack from server for {reg_name} after {i} attempts.")

    def read_val_from_reg(self, reg_name: str): # KEEP THE ALREADY MODIFIED VERSION
        if reg_name not in reg_dict:
            self.update_msg(f"Error: Register '{reg_name}' not found in reg_dict.")
            return None

        reg_info = reg_dict[reg_name]
        address = reg_info["address"]
        reg_type = reg_info.get("type", "int")

        if hasattr(self, 'map_start') and self.map_start is not None and address >= self.map_start:
             offset_addr = address - self.map_start
        else:
             offset_addr = address

        self.mysocket.send(b"4")
        time.sleep(0.1)
        self.mysocket.send(str(offset_addr).encode())
        time.sleep(0.1)

        msgServeur = ""
        original_timeout = self.mysocket.gettimeout()
        try:
            self.mysocket.settimeout(1.0)
            msgServeur = self.mysocket.recv(1024).decode()
        except socket.timeout:
            self.update_msg(f"Socket timeout reading from {reg_name}")
            return None
        except Exception as e:
            self.update_msg(f"Error reading from {reg_name}: {e}")
            return None
        finally:
            self.mysocket.settimeout(original_timeout)

        if not msgServeur:
            self.update_msg(f"No response from server for {reg_name}")
            return None

        try:
            if reg_type == "float":
                int_val = int(msgServeur, 16) if msgServeur.startswith("0x") or msgServeur.startswith("0X") else int(msgServeur)
                byte_data = int_val.to_bytes(4, byteorder='big', signed=False) # Floats are packed from unsigned int bit pattern
                float_val = struct.unpack('>f', byte_data)[0]
                self.update_msg(f"Read {float_val} ({reg_type}) from {reg_name} @ {hex(address)}")
                return float_val
            elif reg_type == "int":
                int_val = int(msgServeur, 16) if msgServeur.startswith("0x") or msgServeur.startswith("0X") else int(msgServeur)
                self.update_msg(f"Read {int_val} ({reg_type}) from {reg_name} @ {hex(address)}")
                return int_val
            else:
                self.update_msg(f"Unknown type {reg_type} for {reg_name}. Returning raw: {msgServeur}")
                return msgServeur
        except ValueError as e:
            self.update_msg(f"Error converting value for {reg_name}: '{msgServeur}', Error: {e}")
            return None
        except Exception as e:
            self.update_msg(f"General error processing value for {reg_name}: '{msgServeur}', Error: {e}")
            return None

    def int_to_hex_to_float(self,value: int) -> float: # Keep original as it might be used elsewhere
        if not (0 <= value < 2**32):
            raise ValueError("Integer must be in the range 0 to 2^32 - 1 (unsigned 32-bit).")
        hex_value = hex(value)
        print(f"Hexadecimal: {hex_value}")
        float_value = struct.unpack('!f', struct.pack('!I', value))[0]
        return float_value

    async def read_adc_gain(self, reg_name_adc0, reg_name_adc1, reg_name_adc2, reg_name_adc3): # Params changed
        reg_name_list = [reg_name_adc0, reg_name_adc1, reg_name_adc2, reg_name_adc3]
        ui_elements = [ self.ui_adc0_gain, self.ui_adc1_gain, self.ui_adc2_gain, self.ui_adc3_gain, ]
        await self.update_adc_gains_async(reg_name_list, ui_elements, decimal_places=2)

    async def update_adc_gains_async(self, reg_name_list, ui_elements, decimal_places=2): # Param changed
        loop = asyncio.get_event_loop()
        tasks = [self._read_and_update_ui(loop, reg_name, ui_element, decimal_places) for reg_name, ui_element in zip(reg_name_list, ui_elements)]
        try:
            await asyncio.gather(*tasks)
        except Exception as e: self.update_msg(f"Error updating gains: {e}")

    async def _read_and_update_ui(self, loop, reg_name, ui_element, decimal_places): # Param changed
        try:
            value = await loop.run_in_executor(None, self.read_val_from_reg, reg_name)
            if value is not None:
                if isinstance(value, float):
                    ui_element.setText(f"{value:.{decimal_places}f}")
                else:
                    ui_element.setText(str(value))
            else:
                ui_element.setText("N/A")
        except Exception as e:
            ui_element.setText("Error")

    async def read_high_resolution_adc_gain(self, reg_name_adc0, reg_name_adc1, reg_name_adc2, reg_name_adc3): # Params changed
        reg_name_list = [reg_name_adc0, reg_name_adc1, reg_name_adc2, reg_name_adc3]
        ui_elements = [ self.ui_adc0_gain_2, self.ui_adc1_gain_2, self.ui_adc2_gain_2, self.ui_adc3_gain_2, ]
        await self.update_adc_gains_async(reg_name_list, ui_elements, decimal_places=2)

    def set_adc_gain(self):
        try:
            self.write_val_to_reg(self.adc0_low_resol_addr_str, float(self.ui_adc0_gain.text()))
            self.write_val_to_reg(self.adc1_low_resol_addr_str, float(self.ui_adc1_gain.text()))
            self.write_val_to_reg(self.adc2_low_resol_addr_str, float(self.ui_adc2_gain.text()))
            self.write_val_to_reg(self.adc3_low_resol_addr_str, float(self.ui_adc3_gain.text()))
        except ValueError as e: self.update_msg(f"Invalid input for ADC gain: {e}")
        except Exception as e: self.update_msg(f"Error setting ADC gain: {e}")

    def set_high_resolution_adc_gain(self):
        try:
            self.write_val_to_reg(self.adc0_high_resol_addr_str, float(self.ui_adc0_gain_2.text()))
            self.write_val_to_reg(self.adc1_high_resol_addr_str, float(self.ui_adc1_gain_2.text()))
            self.write_val_to_reg(self.adc2_high_resol_addr_str, float(self.ui_adc2_gain_2.text()))
            self.write_val_to_reg(self.adc3_high_resol_addr_str, float(self.ui_adc3_gain_2.text()))
        except ValueError as e: self.update_msg(f"Invalid input for High Res ADC gain: {e}")
        except Exception as e: self.update_msg(f"Error setting High Res ADC gain: {e}")

    def restart_update_plot(self):
        self._pause_flag = False
        self.update_msg('Acquition restarted!!')

    async def start_acq_async(self):
        self.first_plot() # Assuming this is UI setup and synchronous

        tasks = [
            self.update_graph(),
            self.read_adc_gain(self.adc0_low_resol_addr_str, self.adc1_low_resol_addr_str,
                               self.adc2_low_resol_addr_str, self.adc3_low_resol_addr_str),
            self.read_high_resolution_adc_gain(self.adc0_high_resol_addr_str, self.adc1_high_resol_addr_str,
                                               self.adc2_high_resol_addr_str, self.adc3_high_resol_addr_str),
            self.load_cav_loop_setting(self.cav_mag_setpoint_addr_str, self.cav_phase_setpoint_addr_str,
                                       self.loop_close_open_addr_str),
            self.load_cav_emulator_status(self.cav_emulator_addr_str)
        ]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.update_msg(f"Error in async task: {result}")
            self.update_msg('Data acquisition sequence initiated/updated.')
        except Exception as e:
            self.update_msg(f"Critical async error: {e}")

    def start_acq(self):
        self.start_async_loop()
        asyncio.ensure_future(self.start_acq_async())

    def connect_server(self):
        try:
            obj_con_server = ConnectServer(self.server_ip.text(), int(self.server_port.text()))
            self.mysocket = obj_con_server.__create__()
            # Assuming self.str_list_reg_offset is already prepared correctly
            obj_con_server.connect_bram(self.str_list_reg_offset)
            self.update_msg('BRAVO!!! \n' + 'Now, you can start the acquisition.')
        except ConnectionRefusedError:
            self.update_msg('First, you must start the server !!!')
        except Exception as e: # Catch other potential errors
            self.update_msg(f'Connection failed: {e}')

    def update_channel(self):
        # ... (original content)
        pass

    def unpack_IQ_data(self, data):
        # ... (original content)
        pass

    def get_data_bram(self):
        # ... (original content)
        try:
            received_data = CS_bigdata.recv_msg(self.mysocket)
            if not received_data:
                self.update_msg("Received no data from the socket")
                return None
            format_data = "h" * (int(len(received_data)/2))
            tmp_bram = struct.unpack(format_data, received_data)
            return tmp_bram
        except Exception as e:
            self.update_msg(f"Error in get_data_bram: {e}")
            return None

    def threading_get_data(self):
        # ... (original content)
        pass

    def get_data(self):
        # ... (original content)
        pass

    def stop_connect(self):
        # ... (original content)
        pass

    def calc_amp_phase(self, Q, I,flag):
        # ... (original content)
        pass

    def mv_avg(self,fifo_list, n_measure, data_list, win_mv):
        # ... (original content)
        pass

    def save_data(self,t,val):
        # ... (original content)
        pass

    def threading_plotting_bram(self):
        # ... (original content)
        pass

    def plotting_bram(self):
        # ... (original content)
        pass

    def plot_realtime(self,i):
        # ... (original content)
        pass

    def get_calculated_data(self):
        # ... (original content)
        pass

    # Duplicated update_channel, removing one
    # def update_channel(self):
    #     for i, (amp_avg, phi_avg, amp_std, phi_std) in enumerate(self.calculated_data):
    #         bram = getattr(self, f'bram{i}', None)
    #         if bram is not None and bram.isChecked():
    #             amp_ui = getattr(self, f'ui_ch{i}_amp')
    #             phi_ui = getattr(self, f'ui_ch{i}_phi')
    #             amp_std_ui = getattr(self, f'ui_ch{i}_amp_std')
    #             phi_std_ui = getattr(self, f'ui_ch{i}_phi_std')
    #             amp_ui.setText(str(np.round(amp_avg, 4)))
    #             phi_ui.setText(str(np.round(phi_avg, n_bit)))
    #             amp_std_ui.setText(str(round(amp_std / amp_avg, n_bit)))
    #             phi_std_ui.setText(str(round(phi_std, n_bit)))

    async def update_graph(self):
        # ... (original content)
        pass

    def clear_plot(self):
        # ... (original content)
        pass

    def update_msg(self, msg):
        self.msgbox.clear()
        self.msgbox.setText(msg)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    myWin = llrf_graph_window()
    apply_stylesheet(app, theme='light_blue.xml')
    myWin.show()
    sys.exit(app.exec_())
