from ConnectServer import ConnectServer
from PyQt5.QtWidgets import QMainWindow, QApplication
import matplotlib as plt
import matplotlib.pyplot as pyplt
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
import re
import string
#from apscheduler.schedulers.blocking import BlockingScheduler
import struct
import numpy as np
import math
# import pandas as pd
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
lock = threading.Lock()
# upload to gitlab
file = 'config.xlsx'
class llrf_graph_window(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load the UI Page
        self.plot_time = 1000
        self._pause_flag = False
        # self.addr_adc01_gain = 0xb0010000
        #  self.addr_adc23_gain = 0xb0020000
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
        self.n0 = 0
        self.n1 = 0
        self.n4 = 0
        self.n5 = 0
        self.n6 = 0
        self.n7 = 0
        self.n_buf_q = [[] for _ in range(8)]
        self.n_buf_i = [[] for _ in range(8)]
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
    
    def load_cav_loop_setting(self,amps_addr,phase_addr,loop_setting_addr):
        amp_cav_setpoint= self.read_val_from_reg(amps_addr)
        phase_cav_setpoint= self.read_val_from_reg(phase_addr)
        loop_setting = self.read_val_from_reg(loop_setting_addr)
        print(amp_cav_setpoint,phase_cav_setpoint,loop_setting)
        self.ui_actual_mag.setText(str(amp_cav_setpoint))
        self.ui_actual_pha.setText(str(phase_cav_setpoint))
        if loop_setting == 1:
            self.ui_radio_close.setChecked(True)
            
        else:
            self.ui_radio_open.setChecked(True)
        
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
        
       #  self.trig_acq = df_mapping.get_address(trig_acq)
       #  self.bram_start= df_mapping.get_address(bram_start)
       #  self.bram_end = df_mapping.get_address(bram_end)
        ## in master Base address column find address of 
        self.trig_acq = df_mapping.loc[df_mapping['Name'] == trig_acq, 'Master Base Address'].values
        self.bram_start= df_mapping.loc[df_mapping['Name'] == bram_start, 'Master Base Address'].values
        self.bram_end = df_mapping.loc[df_mapping['Name'] == bram_end, 'Master Base Address'].values
        self.trig_acq = self.trig_acq[0]
        self.bram_start = self.bram_start[0]    
        self.bram_end = self.bram_end[0]

        #  print(self.bram_end, self.bram_start, self.trig_acq)
        print(hex(self.trig_acq), hex(self.bram_start), hex(self.bram_end))
        # bram offset = bram address - mapping start address
        self.bram_offset = []
        for addr in self.bram_addr:
            addr_offset = addr - self.map_start
            self.bram_offset.append(addr_offset)
        self.load_reg_mapping()
    
    def load_reg_mapping(self): 
        file = self.excel_path_reg.text()
        # obj 
        obj_mapping = mapping(file,'Name','Master Base Address')
        # dataFrame mapping 
        df_mapping = obj_mapping.get_mapping()
   
        file_path = "/home/lu/cross_compile/rf_manager_header.h"
        register_dict = extract_tango_registers(file_path)
        
        self.list_reg_offset = []
        # for val in list_reg_addr: 
        #     val[1]=obj_mapping.get_address(val[0])
        #     self.list_reg_offset.append(val
        # [1] - self.map_start)

        self.list_reg_offset.append(self.trig_acq - self.map_start) # last value of these 3 values in list_reg_offset
        self.list_reg_offset.append(self.bram_end - self.map_start)
        self.list_reg_offset.append(self.bram_start - self.map_start) # first value in list_reg_offset
        self.list_reg_offset.append(self.nbr_bram)
       # print({register_dict["REG_CavMag_SetPoint"]}) 

        self.cav_mag_setpoint_addr = register_dict["REG_CavMag_SetPoint"]
        self.cav_phase_setpoint_addr = register_dict["REG_CavPhase_SetPoint"]
        self.loop_close_open_addr = register_dict["REG_CavPI_Open_Close_Loop"]

        self.phase_shifter0_addr = register_dict["REG_float_ph_shift0"]
        self.phase_shifter1_addr = register_dict["REG_float_ph_shift1"]
        self.phase_shifter2_addr = register_dict["REG_float_ph_shift2"]
        self.phase_shifter3_addr = register_dict["REG_float_ph_shift3"]
        
        self.adc0_low_resol_addr = register_dict["REG_ADC0gain"]
        self.adc1_low_resol_addr = register_dict["REG_ADC1gain"]
        self.adc2_low_resol_addr = register_dict["REG_ADC2gain"]
        self.adc3_low_resol_addr = register_dict["REG_ADC3gain"]

        self.adc0_high_resol_addr = register_dict["REG_Gain_Ctrl0"]
        self.adc1_high_resol_addr = register_dict["REG_Gain_Ctrl1"]
        self.adc2_high_resol_addr = register_dict["REG_Gain_Ctrl2"]
        self.adc3_high_resol_addr = register_dict["REG_Gain_Ctrl3"]

        self.cav_emulator_addr =register_dict["REG_Cavity_Emulator"]
        # print(self.list_reg_offset)
        self.update_msg('mappng loaded')
        self.str_list_reg_offset = [str(num) for num in self.list_reg_offset]
        # self.update_msg(str_list_reg_offset)
        for val in self.list_reg_offset:
            print(hex(val))
        dict = {'1K': 1024,
                '2K': 2 * 1024,
                '4K': 4 * 1024,
                '8K': 8 * 1024,
                '16K': 16 * 1024,
                '24K': 24 * 1024}
        # display bram size

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
            self.update_msg('first start')

        self.last_ch0_ph = self.ui_ph0_deg.text()
        self.last_ch1_ph = self.ui_ph1_deg.text()
        self.last_ch2_ph = self.ui_ph2_deg.text()
        self.last_ch3_ph = self.ui_ph3_deg.text()

       
       

        self.ui_ph0_deg.returnPressed.connect(self.check_val)
        self.ui_ph1_deg.returnPressed.connect(self.check_val)
        self.ui_ph2_deg.returnPressed.connect(self.check_val)
        self.ui_ph3_deg.returnPressed.connect(self.check_val)
        
 
        adc_gains = [
            self.ui_adc0_gain,
            self.ui_adc1_gain,
            self.ui_adc2_gain,
            self.ui_adc3_gain
        ]

        for adc_gain in adc_gains:
            adc_gain.returnPressed.connect(self.set_adc_gain)

        high_res_adc_gains = [
            self.ui_adc0_gain_2,
            self.ui_adc1_gain_2,
            self.ui_adc2_gain_2,
            self.ui_adc3_gain_2
        ]

        for high_res_adc_gain in high_res_adc_gains:
            high_res_adc_gain.returnPressed.connect(self.set_high_resolution_adc_gain)

        self.ui_measure_times.returnPressed.connect(self.update_measure_times)
        # self.ui_16bit_low.returnPressed.connect(self.read_val_from_ui)
        # self.ui_16bit_high.returnPressed.connect(self.read_val_from_ui)
   
    @pause_restart 
    def update_measure_times(self):
        
        self.fifo_q =[[] for _ in range(self.nbr_bram)]    
        self.fifo_i = [[] for _ in range(self.nbr_bram)]
        #     self.fifo_q =[[] for _ in range(9)]    
        #     self.fifo_i = [[] for _ in range(9)]
        # else:   
        #     self.fifo_q =[[] for _ in range(int(self.ui_measure_times.text()))]    
        #     self.fifo_i = [[] for _ in range(int(self.ui_measure_times.text()))]
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
       # self.button_pause.clicked.connect(self.pause_update_plot)
       # self.button_restart.clicked.connect(self.restart_update_plot)
        self.button_save_config.clicked.connect(self.save_config)
       # self.button_adc_charac.clicked.connect(self.adc_characterize)
        self.ui_radio_open.clicked.connect(self.open_cav_loop)
        self.ui_radio_close.clicked.connect(self.close_cav_loop)
        self.ui_radio_with_emulator.clicked.connect(self.W_cav_emulator)
        self.ui_radio_without_emulator.clicked.connect(self.W_O_cav_emulator)

        self.btn_submit_ref.clicked.connect(self.submit_cav_setting)#self.threading_submit_cav_setting) #

    def load_cav_emulator_status(self,address):
        flag = self.read_val_from_reg(address)
        if flag == 1:
            self.ui_radio_with_emulator.setChecked(True)
        else:
            self.ui_radio_without_emulator.setChecked(True)

    @pause_restart 
    def W_O_cav_emulator(self):
        self.write_val_to_reg(0, self.cav_emulator_addr)
        self.ui_radio_without_emulator.setChecked(True)
    @pause_restart
    def W_cav_emulator(self):
        self.write_val_to_reg(1, self.cav_emulator_addr)
        self.ui_radio_with_emulator.setChecked(True)

    @pause_restart
    def close_cav_loop(self):
        self.write_val_to_reg(0, self.loop_close_open_addr)
        self.ui_radio_close.setChecked(False)
    @pause_restart
    def open_cav_loop(self):
        self.write_val_to_reg(1, self.loop_close_open_addr)
        self.ui_radio_open.setChecked(True)
 
    def volt2dbm(self,v):
        # for 50 Ohm system
        if isinstance(v, (list, tuple)):
            vpp = max(v) - min(v)
            vpp = vpp/(pow(2,15)-1)  # convert to volt
            #print(f'max val:{max(v)} et min val:{min(v)}')
            #print(vpp)
            return 10+20*np.log10(0.5*vpp)
        else:
            # v is value vpp
            return 10*np.log10(v*v*1000/8/50)
    def adc_characterize(self):
        input_level =[round(x * 0.1, 12) for x in range(0, 121)]
        print(input_level)
        sml_ctl.open_dev()
        adc1_bram2 = []
        adc2_bram2 = []
        adc3_bram3 = []
        adc4_bram3 = []
        for cmd in input_level:
            cmd_str = 'POW ' + str(cmd) + 'dBm'
            sml_ctl.inst.write(cmd_str)
            time.sleep(0.1)
            self.get_data()
            # calc_amp_phase method with flag = 1 to get amplitude list of one BRAM
            # return [amp, pha] list
            # max() find the max value in amp list
            print(cmd)
            adc1_bram2.append(self.volt2dbm(self.buf_q[2]))
            adc2_bram2.append(self.volt2dbm(self.buf_i[2]))
            adc3_bram3.append(self.volt2dbm(self.buf_q[3]))
            adc4_bram3.append(self.volt2dbm(self.buf_i[3]))

            #adc_bram3_max.append(max(self.calc_amp_phase(self.buf_q[3], self.buf_i[3], 1)[0]))
        #adc1_bram2_max = self.volt2dbm(adc1_bram2_max)
        #adc2_bram2_max = self.volt2dbm(adc2_bram2_max)
        #adc3_bram3_max = self.volt2dbm(adc3_bram3_max)
        #adc4_bram3_max = self.volt2dbm(adc4_bram3_max)
        input_level = [ i-6 for i in input_level]
        fig, ax_plot = pyplt.subplots()
        ax_plot.plot(input_level, adc1_bram2,'r--', label = 'ADC1 from bram2')
        ax_plot.plot(input_level, adc2_bram2, 'g', label='ADC2 from bram2')
        ax_plot.plot(input_level, adc3_bram3,'b', label = 'ADC3 from bram3')
        ax_plot.plot(input_level, adc4_bram3, 'o', label='ADC4 from bram3')

        ax_plot.legend()
        ax_plot.set_xlabel('Input power (dBm)')
        ax_plot.set_ylabel('ADC measured power(dBm)')
        pyplt.show()
    def threading_submit_cav_setting(self):
        t=threading.Thread(target=self.submit_cav_setting,name='submit_cav_setting')
        t.start()
        t.join()
        self.update_msg('Cavity setting submitted!!')
    def submit_cav_setting(self):
        mag = float(self.ui_setpoint_mag.text())
        self.write_val_to_reg(mag, self.cav_mag_setpoint_addr)
        phase = float(self.ui_setpoint_pha.text())
        self.write_val_to_reg(phase, self.cav_phase_setpoint_addr)
        self.load_cav_loop_setting(self.cav_mag_setpoint_addr, self.cav_phase_setpoint_addr, self.loop_close_open_addr)
    def calc_phase_angle(self, ch):
        if ch == 0:
            phase = self.ui_ph0_deg.text()
            addr = self.ui_ph0_add.text()
        elif ch == 1:
            phase = self.ui_ph1_deg.text()
            addr = self.ui_ph1_add.text()
        elif ch == 2:
            phase = self.ui_ph2_deg.text()
            addr = self.ui_ph2_add.text()
        elif ch == 3:
            phase = self.ui_ph3_deg.text()
            addr = self.ui_ph3_add.text()
        elif ch == 4:
            phase = self.ui_ph4_deg.text()
            addr = self.ui_ph4_add.text()
        try:
            ph = np.float(phase)
            self.mysocket.send(b"2")

            msg = str(ph) + ',' + addr
            #print(msg)
            self.mysocket.send(msg.encode())
            time.sleep(0.1)
            
            self.update_msg('Now, you are right, the phase updated!!')
        except ValueError:
            self.update_msg('You have enter number!!!')

    def user_mode(self):
        self.button_init.hide()
        self.button_start.hide()
        self.button_stop.hide()
        # self.button_adc_charac.hide()
    def set_plot_ui(self):
        self.max_range = 32000
        self.plt_data = self.rtplot.addPlot(
            labels={'left': 'Level', 'bottom': 'data points'})  # change here for plt_i in seperated plot
        
        self.bram0.setChecked(1)
        self.bram1.setChecked(1)
        self.bram2.setChecked(0)
        self.bram3.setChecked(0)
        self.bram4.setChecked(1)
        self.bram5.setChecked(1)
        self.bram6.setChecked(0)
        self.bram7.setChecked(0)
        
    def first_plot(self):
        self.fifo_q =[[] for _ in range(self.nbr_bram)]    
        self.fifo_i = [[] for _ in range(self.nbr_bram)]

        self.I_moy = [[] for _ in range(self.nbr_bram)]
        self.Q_moy = [[] for _ in range(self.nbr_bram)]
        self.n_measure = np.zeros(self.nbr_bram)
        line_w = 2
        sympole_s = 5
        self.plt_curve_q = [0]*self.nbr_bram
        self.plt_curve_i = [0]*self.nbr_bram

        pen=[0]*self.nbr_bram*2
        plt

        color_line =['g','b','r',(128,0,0),'k',(180,165,0),(128,0,128),(0,255,255), (0,0,0),(192,192,192),'g']
        #**********************************************#
        for k in range(self.nbr_bram):
            pen[k] = pg.mkPen(color=color_line[k], width=line_w, style=QtCore.Qt.DashLine)

        for i in range(self.nbr_bram):
            self.plt_curve_q[i] = self.plt_data.plot(self.buf_q[i], pen=color_line[i])
            self.plt_curve_i[i] = self.plt_data.plot(self.buf_i[i], pen=pen[i])
    #def update_plot(self):
    #   
    #    self.timer.timeout.connect(self.update_graph)
    #    self.timer.timeout.connect(self.update_refresh_time)

    def check_val(self):
        if (self.last_ch0_ph != self.ui_ph0_deg.text()) & (self.ui_ph0_deg.text()!=''):
            self.calc_phase_angle(0)
            self.last_ch0_ph = self.ui_ph0_deg.text()

        if (self.last_ch1_ph != self.ui_ph1_deg.text()) & (self.ui_ph1_deg.text()!=''):
            self.calc_phase_angle(1)
            self.last_ch1_ph = self.ui_ph1_deg.text()

        if (self.last_ch2_ph != self.ui_ph2_deg.text()) & (self.ui_ph2_deg.text()!=''):
            self.calc_phase_angle(2)
            self.last_ch2_ph = self.ui_ph2_deg.text()

        if (self.last_ch3_ph != self.ui_ph3_deg.text()) & (self.ui_ph3_deg.text()!=''):
            self.calc_phase_angle(3)
            self.last_ch3_ph = self.ui_ph3_deg.text()


        time.sleep(0.05)
    def update_refresh_time(self):
        try:
            t =int(self.refresh_time.text())
            if (t & t > 0):
                self.timer.setInterval(t)
        except ValueError:
                pass

        if (t & t > 0):
            self.timer.setInterval(t)
    def start_async_loop(self):
        """启动 asyncio 事件循环与 PyQt 集成"""
        loop = QEventLoop()  # 使用 QEventLoop 替代原生事件循环
        asyncio.set_event_loop(loop)  # 设置 QEventLoop 为当前事件循环

        # 使用 QTimer 来定期运行 asyncio 的事件循环
 
        self.timer.timeout.connect(lambda: loop.call_soon(loop.stop))
        self.timer.timeout.connect(self.update_refresh_time)

        if self._pause_flag:
            self.update_msg('Acquition paused!!')
        else:
            self.timer.start()

        asyncio.ensure_future(self.fetch_data())  # 启动异步任务
        loop.run_forever()
    async def fetch_data(self):
        self.mysocket.send(b"1")
        self.tmp_bram = []
        self.buf_q = [[] for _ in range(self.nbr_bram)]
        self.buf_i = [[] for _ in range(self.nbr_bram)]
        self.I_moy = [[] for _ in range(self.nbr_bram)]
        self.Q_moy = [[] for _ in range(self.nbr_bram)]
        self.channel_updated = [False] * self.nbr_bram  # Reset channel update flags

        """ Get data from server """
        for i in range(self.nbr_bram):
            self.tmp_bram.append(self.get_data_bram())

        """ Unpack IQ value one bram by one bram """
        for j, one_bram in enumerate(self.tmp_bram):
            self.buf_i[j] = one_bram[0::2]
            self.buf_q[j] = one_bram[1::2]

        # Update UI data
        if self.ui_measure_times.text():
            win_mv = 0  # int(self.ui_measure_times.text())
            for i in range(self.nbr_bram):
                if not self.channel_updated[i]:  # Check if the channel has been updated
                    if win_mv == 0:
                        self.I_moy[i] = np.mean(self.buf_i[i])
                        self.Q_moy[i] = np.mean(self.buf_q[i])
                        [amp_avg, phi_avg] = self.calc_amp_phase(self.Q_moy[i], self.I_moy[i], 0)
                        [amp_std, phi_std] = self.calc_amp_phase(self.buf_q[i], self.buf_i[i], 1)
                    else:
                        try:
                            [self.I_moy[i], self.fifo_i[i], self.n_measure[i]] = self.mv_avg(
                                self.fifo_i[i], self.n_measure[i], self.buf_i[i], win_mv
                            )
                            [self.Q_moy[i], self.fifo_q[i], self.n_measure[i]] = self.mv_avg(
                                self.fifo_q[i], self.n_measure[i], self.buf_q[i], win_mv
                            )
                        except IndexError as err:
                            print(err)
                            print("Moving means error")
                            break
                        [amp_avg, phi_avg] = self.calc_amp_phase(self.Q_moy[i], self.I_moy[i], 0)
                        [amp_std, phi_std] = self.calc_amp_phase(
                            self.fifo_q[i][0], self.fifo_i[i][0], 1
                        )

                    if getattr(self, f"bram{i}", None) and getattr(self, f"bram{i}").isChecked():
                        self.display_channel_data(i, amp_avg, phi_avg, amp_std, phi_std)
                        self.channel_updated[i] = True  # Mark the channel as updated
        asyncio.ensure_future(self.fetch_data())

    def display_channel_data(self, channel, amp_avg, phi_avg, amp_std, phi_std):
        """ Display data for a specific channel """
        ui_amp = getattr(self, f"ui_ch{channel}_amp", None)
        ui_phi = getattr(self, f"ui_ch{channel}_phi", None)
        ui_amp_std = getattr(self, f"ui_ch{channel}_amp_std", None)
        ui_phi_std = getattr(self, f"ui_ch{channel}_phi_std", None)

        if ui_amp:
            ui_amp.setText(str(np.round(amp_avg, 2)))
        if ui_phi:
            ui_phi.setText(str(np.round(phi_avg, 2)))
        if ui_amp_std:
            ui_amp_std.setText(str(round(np.std(amp_std) / amp_avg, 2)))
        if ui_phi_std:
            ui_phi_std.setText(str(round(np.std(phi_std), 2)))


    def pause_update_plot(self):
        self._pause_flag = True
        self._pause_time = self.update_refresh_time
        # stop timer
        self.timer.stop()

    def write_val_to_reg(self,val,addr):
        self.mysocket.send(b"5")

        if addr < self.map_start:
            offset_addr = addr
        else:
            offset_addr = addr-self.map_start
            offset_addr = addr-self.map_start
        try:
            msg = str(val) + ',' + str(hex(offset_addr))
        except err as TypeError:
            print(err)
        while self.mysocket.recv(512).decode() != 'waiting':
            print(f'Waiting for sending register information')
            i=i+1
            if i > 20:
                break
        else:
            self.mysocket.send(msg.encode())
        try:
            self.update_msg('You write '+ str(val) +' to register @'+str(hex(addr)))
        except TypeError as err:
            print(err)
    def read_val_from_reg(self,reg_addr:int):
        self.mysocket.send(b"4")
        time.sleep(0.1)
        offset_addr = 0
        if reg_addr < self.map_start:
            offset_addr = reg_addr
        else:
            offset_addr = reg_addr-self.map_start
        
        self.mysocket.send(str(offset_addr).encode())
        time.sleep(0.05)
        msgServeur = self.mysocket.recv(1024).decode()
        return msgServeur
 
    def int_to_hex_to_float(self,value: int) -> float:
        '''
        Convert an integer to a hexadecimal representation,
        then interpret it as a float using its bit pattern.

        Args:
            value (int): The integer to convert.

        Returns:
            float: The float value interpreted from the integer's bit pattern.
        '''
        # Ensure the integer fits in 4 bytes (32 bits)
        if not (0 <= value < 2**32):
            raise ValueError("Integer must be in the range 0 to 2^32 - 1 (unsigned 32-bit).")
        
        # Convert integer to hexadecimal string
        hex_value = hex(value)
        print(f"Hexadecimal: {hex_value}")

        # Interpret the integer as a float using struct
        float_value = struct.unpack('!f', struct.pack('!I', value))[0]
        return float_value
    async def read_adc_gain(self, addr_adc0, addr_adc1, addr_adc2, addr_adc3):
        """异步读取 ADC 增益值并更新到 UI"""
        addr_list = [addr_adc0, addr_adc1, addr_adc2, addr_adc3]
        ui_elements = [
            self.ui_adc0_gain,
            self.ui_adc1_gain,
            self.ui_adc2_gain,
            self.ui_adc3_gain,
        ]

        # 异步更新 ADC 增益值
        await self.update_adc_gains_async(addr_list, ui_elements, decimal_places=2)


    
    async def update_adc_gains_async(self, addr_list, ui_elements, decimal_places=2):
        """异步读取地址值并更新到 UI 元素"""
        loop = asyncio.get_event_loop()  # 获取事件循环
        tasks = []

        for addr, ui_element in zip(addr_list, ui_elements):
            # 异步调度读取和 UI 更新
            tasks.append(self._read_and_update_ui(loop, addr, ui_element, decimal_places))

        # 并发执行所有任务
        await asyncio.gather(*tasks)

    async def _read_and_update_ui(self, loop, addr, ui_element, decimal_places):
        """单个地址值的异步读取与更新"""
        try:
            # 假设 read_val_from_reg 是同步的，用 run_in_executor 包装为异步
            value = await loop.run_in_executor(None, self.read_val_from_reg, addr)
            # 更新到 UI
            ui_element.setText(f"{value:.{decimal_places}f}")
        except Exception as e:
            # 处理异常并更新到 UI
            print(f"Error updating ADC gain for addr {addr}: {e}")
            ui_element.setText("Error")

    async def read_high_resolution_adc_gain(self,addr_adc0,addr_adc1,addr_adc2,addr_adc3):
        addr_list = [addr_adc0, 
                     addr_adc1, 
                     addr_adc2,
                     addr_adc3]
        ui_elements = [
        self.ui_adc0_gain_2,
        self.ui_adc1_gain_2,
        self.ui_adc2_gain_2,
        self.ui_adc3_gain_2,
        ]
        # 异步更新 ADC 增益值
        await self.update_adc_gains_async(addr_list, ui_elements, decimal_places=2)
   
    def set_adc_gain(self):
       #(cos_angle << 16) | (sin_angle & 0xfff)
        adc0 = float(self.ui_adc0_gain.text())
        adc1 = float(self.ui_adc1_gain.text()) 
        adc2 = float(self.ui_adc2_gain.text())
        adc3 = float(self.ui_adc3_gain.text())

        self.write_val_to_reg(adc0,self.adc0_low_resol_addr)
        self.write_val_to_reg(adc1,self.adc1_low_resol_addr)
        self.write_val_to_reg(adc2,self.adc2_low_resol_addr)
        self.write_val_to_reg(adc3,self.adc3_low_resol_addr)
    def set_high_resolution_adc_gain(self):
         #(cos_angle << 16) | (sin_angle & 0xffff)
        adc0 = float(self.ui_adc0_gain_2.text())
        adc1 = float(self.ui_adc1_gain_2.text()) 
        adc2 = float(self.ui_adc2_gain_2.text())
        adc3 = float(self.ui_adc3_gain_2.text())
    
        self.write_val_to_reg(adc0,self.adc0_high_resol_addr)
        self.write_val_to_reg(adc1,self.adc1_high_resol_addr)
        self.write_val_to_reg(adc2,self.adc2_high_resol_addr)
        self.write_val_to_reg(adc3,self.adc3_high_resol_addr)


    def restart_update_plot(self):
        self._pause_flag = False
        # self.update_gui()
        self.update_msg('Acquition restarted!!')
    async def start_acq_async(self):
        """异步执行数据采集相关任务"""
        # 启动所有需要执行的异步任务
        tasks = [
            self.first_plot(),
            self.update_graph(),
            self.read_adc_gain(self.adc0_low_resol_addr,
                                self.adc1_low_resol_addr,
                                self.adc2_low_resol_addr,
                                self.adc3_low_resol_addr),
            self.read_high_resolution_adc_gain(self.adc0_high_resol_addr,
                                                self.adc1_high_resol_addr,
                                                self.adc2_high_resol_addr,
                                                self.adc3_high_resol_addr),
            self.load_cav_loop_setting(self.cav_mag_setpoint_addr,
                                        self.cav_phase_setpoint_addr,
                                        self.loop_close_open_addr),
            self.load_cav_emulator_status(self.cav_emulator_addr)
        ]

        # 执行所有任务
        results = await asyncio.gather(*tasks)

        # 更新消息
        self.update_msg('Data acquisition started!!')

        # 如果需要处理任务返回结果，可以在此处理
        return results
    def start_acq(self):
        #for i in range(4):
        #    self.calc_phase_angle(i)  
        #try:
        #    self.threading_get_data()
        #except NameError as err:
        #    print(err)
        #
        # 启动 asyncio 主循环
        self.start_async_loop()
        # 将任务包装为异步任务
        asyncio.ensure_future(self.start_acq_async())
    
    def connect_server(self):
        # create obj of connectserver
       
        try:
            obj_con_server = ConnectServer(self.server_ip.text(), int(self.server_port.text()))

        # create socket connect without bram
            self.mysocket = obj_con_server.__create__()
            # connect to bram
            obj_con_server.connect_bram(self.str_list_reg_offset)

            self.update_msg('BRAVO!!! \n' + 'Now, you can start the acquisition.')
        except ConnectionRefusedError:
            self.update_msg('First, you must start the server !!!')
    def update_channel(self):
        for i, (amp_avg, phi_avg, amp_std, phi_std) in enumerate(self.calculated_data):
            bram = getattr(self, f'bram{i}', None)
            if bram is not None and bram.isChecked():
                # 动态获取 UI 控件
                amp_ui = getattr(self, f'ui_ch{i}_amp')
                phi_ui = getattr(self, f'ui_ch{i}_phi')
                amp_std_ui = getattr(self, f'ui_ch{i}_amp_std')
                phi_std_ui = getattr(self, f'ui_ch{i}_phi_std')

                # 更新显示
                amp_ui.setText(str(np.round(amp_avg, 4)))
                phi_ui.setText(str(np.round(phi_avg, n_bit)))
                amp_std_ui.setText(str(round(amp_std / amp_avg, n_bit)))
                phi_std_ui.setText(str(round(phi_std, n_bit)))
    
    def unpack_IQ_data(self, data):
            # Seperate I/Q data from bram_data block

        self.buf_q = [[] for _ in range(self.nbr_bram)]
        self.buf_i = [[] for _ in range(self.nbr_bram)]

        for txt in data:
            format_data = "h" * (int(len(txt)/2))  
            txt = struct.unpack(format_data, txt)
            self.buf_q.append(txt[0::2])
            self.buf_i.append(txt[1::2])
    def get_data_bram(self):
        try: 
            """ get data length from server """
            received_data = CS_bigdata.recv_msg(self.mysocket)
            if not received_data:  # Check if None or empty
                self.update_msg("Received no data from the socket")
                return None  # Exit gracefully if no data
            format_data = "h" * (int(len(received_data)/2))  
            tmp_bram = struct.unpack(format_data, received_data)
            return tmp_bram
        except Exception as e:
            self.update_msg(f"Error in get_data_bram: {e}")
            return None   
        data_length = 8192
        """ To get data  """
        # 定义已接收数据大小为0
        received_length = 0
        # 定义已接收数据为0
        received_data = bytes()
        # while received_length < data_length:
        #     r_data = self.mysocket.recv(1024*8)  # 接受的数据是bytes类型
        #     received_length += len(r_data)
        #     received_data += r_data
            
        # else:
        #     self.mysocket.send(b'ok')
        #     # print(f'received {data_length} bytes')
        #     format_data = "h" * (int(len(received_data)/2))  
        #     tmp_bram = struct.unpack(format_data, received_data)
        #     return tmp_bram

    def threading_get_data(self):
        t = threading.Thread(target=self.get_data,name='get_data')
        t.start()
        t.join()
        #self.update_msg('Data acquisition!!')
    def get_data(self):
        self.mysocket.send(b"1")
        self.tmp_bram = []
        self.buf_q = [[] for _ in range(self.nbr_bram)]
        self.buf_i = [[] for _ in range(self.nbr_bram)]
        """ get data from server """
        i =0 
        while i<self.nbr_bram:
            self.tmp_bram.append(self.get_data_bram())
            i+=1
        """
        upack IQ value one bram by one bram
        """
        for j, one_bram in enumerate(self.tmp_bram):
            # print(f'bram {j}: {len(one_bram)}')
            self.buf_i[j]  = one_bram[0::2]
            self.buf_q[j]  = one_bram[1::2]

   
            # print(f'buf_q {j}: {self.buf_q[j]}')
   
        Iout = []
        Qout = []
        f = float(2**15)
        ph = np.radians(ph)
        for i in range(len(I)):
            Iout.append(float(I[i])*f*np.cos(ph)-float(Q[i])*f*np.sin(ph))
            Qout.append(float(I[i])*f*np.sin(ph)+float(Q[i])*f*np.cos(ph))
            # print(Iout[0],Qout[0])
        return [Iout,Qout]
    
    def stop_connect(self):
        self.mysocket.send(b'0')
        self.update_msg("Stopped!! Click 'init. connect ' to connect to the server!!!")
        self.timer.stop()
        self.clear_plot()
    def calc_amp_phase(self, Q, I,flag):
        amp=[]
        phi=[]
        if flag == 1:
            for q, i in zip(Q, I):
                try:
                    amp.append(np.sqrt(np.square(q) + np.square(i)))
                    phi.append(np.degrees(np.arctan2(q,i)))
                    #print(q,i)
                except ValueError:
                    print("value err list")
        else:
                try:
                    amp = np.sqrt(Q**2+ I**2)
                    phi = np.degrees(np.arctan2(Q,I))
                except ValueError:
                    print("value err val")
        return [amp, phi]
 
    def mv_avg(self,fifo_list, n_measure, data_list, win_mv):
        '''
            Moving average
        '''
        if n_measure < win_mv*2:
            fifo_list.append(data_list)
            n_measure = n_measure + 1
            out_avg = np.mean(fifo_list)
        else: 
            fifo_list.pop(0)
            fifo_list.append(data_list)
            out_avg = np.mean(fifo_list)
        return [out_avg, fifo_list, n_measure]  
    def save_data(self,t,val):
        self.df = self.df.append({'Time': t, 'Val_Ref':val }, ignore_index=True)
        self.df.to_excel(self.excel_file, index=False)
        self.last_save_time = datetime.now()
    def threading_plotting_bram(self):
        self.timer.timeout.connect(self.threading_get_data)
        if self.plotting.isChecked():
            t=threading.Thread(target=self.plotting_bram,name='threading_plotting')
            t.start()
            t.join()
    def plotting_bram(self):
        self.clear_plot()
        
        for i in range(self.nbr_bram):
            if i==0 and self.bram0.isChecked():
                self.plot_realtime(i)
            if i==1 and self.bram1.isChecked():
                self.plot_realtime(i)
            if i==2 and self.bram2.isChecked():
                self.plot_realtime(i)
            if i==3 and self.bram3.isChecked():
                self.plot_realtime(i)
            if i==4 and self.bram4.isChecked():
                self.plot_realtime(i)
            if i==5 and self.bram5.isChecked():
                self.plot_realtime(i)
            if i==6 and self.bram6.isChecked():
                self.plot_realtime(i)
            if i==7 and self.bram7.isChecked():
                self.plot_realtime(i)
            if i==8 and self.bram8.isChecked():
                self.plot_realtime(i)    
    def plot_realtime(self,i):
        self.plt_curve_q[i].setData(self.buf_q[i])
        self.plt_curve_i[i].setData(self.buf_i[i])
        self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
        self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)
    def get_calculated_data(self):
       
        self.mysocket.send(b'3')
         # 接收数据长度
        data_length = struct.unpack('I', self.mysocket.recv(4))[0]
        # print(f"数据长度: {data_length}")

        # 接收实际数据
        data = self.mysocket.recv(data_length)

        # 解包数据
        rows = len(data) // (4 * 4)  # 每行4个float，每个float 4字节
        self.calculated_data = [
            struct.unpack('4f', data[i * 16:(i + 1) * 16])
            for i in range(rows)
        ]
    
        # print("接收到的数据:")
        # for row in unpacked_data:
        #     print(row)
    def update_channel(self):
        for i, (amp_avg, phi_avg, amp_std, phi_std) in enumerate(self.calculated_data):
            bram = getattr(self, f'bram{i}', None)
            if bram is not None and bram.isChecked():
                # 动态获取 UI 控件
                amp_ui = getattr(self, f'ui_ch{i}_amp')
                phi_ui = getattr(self, f'ui_ch{i}_phi')
                amp_std_ui = getattr(self, f'ui_ch{i}_amp_std')
                phi_std_ui = getattr(self, f'ui_ch{i}_phi_std')

                # 更新显示
                amp_ui.setText(str(np.round(amp_avg, 4)))
                phi_ui.setText(str(np.round(phi_avg, n_bit)))
                amp_std_ui.setText(str(round(amp_std / amp_avg, n_bit)))
                phi_std_ui.setText(str(round(phi_std, n_bit)))
       

    async def update_graph(self):
        if self.ui_measure_times.text():

            win_mv = int(self.ui_measure_times.text())
            for i in range(self.nbr_bram):
                
                            
                """print(i)
                print('self.I moy ', self.I_moy[i])
                print('self.Q moy ', self.Q_moy[i])
                print('n_measure0: ', self.n_measure[i])
                print('fifo_i length: ',len(self.fifo_i[i]))
                print('fifo_q length: ',len(self.fifo_q[i]))"""
                
                if win_mv == 0: 
                    self.I_moy[i]=(np.mean(self.buf_i[i]))
                    self.Q_moy[i]=(np.mean(self.buf_q[i]))
                    #print(self.I_moy[i])
                    # self.fifo_i[i]=self.buf_i[i]
                    # self.fifo_q[i]=self.buf_q[i]
                    [amp_avg, phi_avg] = self.calc_amp_phase(self.Q_moy[i], self.I_moy[i], 0)   # calc amp and phase RMS
                    [amp_std, phi_std] = self.calc_amp_phase(self.buf_q[i], self.buf_i[i], 1) # calc amp and phase std
                else:
                    try: 
                        # t1 = time.time()
                        [self.I_moy[i],self.fifo_i[i],self.n_measure[i]] = self.mv_avg(self.fifo_i[i], self.n_measure[i], self.buf_i[i], win_mv)
                        [self.Q_moy[i],self.fifo_q[i],self.n_measure[i]] = self.mv_avg(self.fifo_q[i], self.n_measure[i], self.buf_q[i], win_mv)
                        # t2 = time.time()
                        # print(f'time(ms): {t2-t1}')
                    except IndexError as err:
                        print(err)
                        print('moving means error')
                        # self.update_msg(err)
                        break
                    [amp_avg, phi_avg] =self.calc_amp_phase(self.Q_moy[i], self.I_moy[i], 0)   # calc amp and phase RMS
                    [amp_std, phi_std] = self.calc_amp_phase(self.fifo_q[i][0], self.fifo_i[i][0], 1) # calc amp and phase std
            
                if i==0 and self.bram0.isChecked():
                    # 4 IQ plots
                    n = min(len(self.buf_q[i]), len(self.buf_i[i])) 
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                    # real time plot
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)'''
                    # display value
                    self.ui_ch0_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch0_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch0_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch0_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                    if self.last_save_time is None or (datetime.now() - self.last_save_time).seconds >= 30 * 60:  # save data every 10 minutes
                        self.save_data(current_time, np.round(amp_avg, 4))
                if i==1 and self.bram1.isChecked():
                    # 4 IQ plots
                    n = min(len(self.buf_q[i]), len(self.buf_i[i])) 
                    
                    # real time plot
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)'''
                    self.ui_ch1_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch1_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch1_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch1_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                if i==2 and self.bram2.isChecked(): 
                    # 4 IQ plots
                    n = min(len(self.buf_q[i]), len(self.buf_i[i])) 
                    
                    # real time plot
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)'''
                    self.ui_ch2_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch2_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch2_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch2_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                if i==3 and self.bram3.isChecked():
                    # 4 IQ plots
                    n = min(len(self.buf_q[i]), len(self.buf_i[i])) 
                    
                    # real time plot
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)'''
                    self.ui_ch3_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch3_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch3_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch3_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                if i==4 and self.bram4.isChecked(): 
                    # 4 IQ plots
                    n = min(len(self.buf_q[i]), len(self.buf_i[i])) 

                    # real time plot
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)'''
                    self.ui_ch4_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch4_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch4_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch4_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                if i==5 and self.bram5.isChecked():
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)'''

                    self.ui_ch5_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch5_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch5_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch5_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                    # write cavity magnitude and phase to PI control window
                    # if self.child_pi_controler:
                    #     self.child_pi_controler.ui_cav_mag.setText(str(round(amp_avg, 2)))
                    #     self.child_pi_controler.ui_cav_phase.setText(str(round(phi_avg, n_bit)))
                if i==6 and self.bram6.isChecked():
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)
                    '''

                    self.ui_ch6_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch6_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch6_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch6_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                if i==7 and self.bram7.isChecked():
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)
                    '''
                    self.ui_ch7_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch7_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch7_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch7_phi_std.setText(str(round(np.std(phi_std), n_bit)))
                if i==8 and self.bram8.isChecked():
                    '''self.plt_curve_q[i].setData(self.buf_q[i])
                    self.plt_curve_i[i].setData(self.buf_i[i])
                    self.plt_curve_q[i].setPos(len(self.buf_q[i]), 0)
                    self.plt_curve_i[i].setPos(len(self.buf_i[i]), 0)
                    '''
                    self.ui_ch8_amp.setText(str(np.round(amp_avg, 2)))
                    self.ui_ch8_phi.setText(str(np.round(phi_avg, n_bit)))
                    self.ui_ch8_amp_std.setText(str(round(np.std(amp_std)/amp_avg, n_bit)))
                    self.ui_ch8_phi_std.setText(str(round(np.std(phi_std), n_bit)))
    def clear_plot(self):
        i=0
        try:
            for i in range(self.nbr_bram):
                self.plt_curve_q[i].clear()
                self.plt_curve_i[i].clear()
                i=i+1
        except AttributeError:
            self.update_msg('Err')

    def update_msg(self, msg):
        self.msgbox.clear()
        self.msgbox.setText(msg)

if __name__ == '__main__':
    # global sml_ctl
    # global tuner_ctl
    
    app = QApplication(sys.argv)
    myWin = llrf_graph_window()
    apply_stylesheet(app, theme='light_blue.xml')
    myWin.show()
    # sml_ctl = SML01.signal_generator_window()
    
    # myWin.button_SML01.clicked.connect(sml_ctl.show)
    # myWin0(tuner_ctl.show)
    sys.exit(app.exec_())

