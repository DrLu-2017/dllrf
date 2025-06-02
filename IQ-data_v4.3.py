# -- coding: utf-8 --**
import os
import socket
import sys
import time
from pathlib import Path
import subprocess
import rw_mio
import struct
import math
import re
import json
import CS_bigdata
import statistics
from register_map import registers
#ip_server = '172.17.3.61'
ip_server = '192.168.87.90'
port_server = 50003

'''
bram_size_in_8b  = 8192  # for two bram total 8k=8*1024
bram_size_in_16b = bram_size_in_8b/2 # 4096
one_bram_size_in_16b = int(bram_size_in_16b/2)  # for two bram block
one_bram_size_in_8b = int(bram_size_in_8b/2)
'''
class server_socket(object):
    def __init__(self,ip_server,port_server):
        #Source Server IP
        self.HOST = ip_server # '172.16.6.85'
        self.PORT = port_server
        # self.__create__()
        # self.__wait__(mySocket)

    def __create__(self):
        # 1) création du socket :
        #socket.setdefaulttimeout(30)
       # TCP/IP 
        self.mysocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.mysocket.bind((self.HOST, self.PORT))
        except socket.error:
            print ("Socket Failed!!!")
            sys.exit()

        ##########################
    def close_connect(self):
            # 6) Fermeture de la connexion :
            self.connexion.close()
            print ("Disconnected.")
    def chunks(self,arr,n):
        return [arr[i:i+n] for i in range(0, len(arr), n)]
    def unpack_IQ_data(self, data):
            # Seperate I/Q data from bram_data block

        self.buf_q = [[] for _ in range(self.nbr_bram)]
        self.buf_i = [[] for _ in range(self.nbr_bram)]

        for txt in self.bram_data:
            format_data = "h" * (int(len(txt)/2))  
            txt = struct.unpack(format_data, txt)
            self.buf_q.append(txt[0::2])
            self.buf_i.append(txt[1::2])

    def get_data(self):
        """_summary_
        Read bram data one by one from mapping offset
        """
        # one BRAM = 8K bytes
        self.bram_data =[]
        for offset in self.bram_start_offset:
            # print(f'offset:{hex(offset)}')
            # print(f'offset:{hex(offset)}')
            txt = self.rw_bram.read(offset, 8*1024) # 8K  lines , each line has 4 bytes,
                                        # but, only 1 line has data every 4 lines
                                        # so, finally, 8K * 4 / 4 = 8 K bytes        
            format_data = "h" * (int(len(txt)/2))  
            # tmp = struct.unpack(format_data, txt)
            # buf_q = tmp[0::2]
            # print(buf_q)
            # print(f'len buf_q:{len(buf_q)}')
            self.bram_data.append(txt)
    def send_data(self):
        """_summary_
        Send bram data one by one to client
        it wait the client return 'ok' to send next bram

        """
        for i, data in enumerate(self.bram_data):
        
            data_length = len(data)
            # print(f"each bram length:{len(data)}")
            CS_bigdata.send_msg(self.connexion,data)
            # the first bram , bram0 to client, then it wait ok 
            # if i == 0:
            #     CS_bigdata.send_msg(self.connexion,data)
            
            # while self.connexion.recv(2) != b'ok':
            #     print('waiting for ok')
            # else:
            #     CS_bigdata.send_msg(self.connexion,data)
    def trig_data_calculate(self):
        
        self.get_data_to_calcule()
        self.calculate_data()
        self.send_calculated_data(self.calc_ch)
              
    def calculate_std(self,data):
        # 计算平均值
        mean = sum(data) / len(data)
        # 计算方差
        variance = sum((x - mean) ** 2 for x in data) / len(data)
        # 返回标准差
        return math.sqrt(variance)  


    def get_data_to_calcule(self):
        """_summary_
        Read bram data one by one from mapping offset
        """
        # one BRAM = 8K bytes
        self.bram_data =[]
        for offset in self.bram_start_offset:
            #print(f'offset:{hex(offset)}')
            # print(f'offset:{hex(offset)}')
            txt = self.rw_bram.read(offset, 8*1024) # 8K  lines , each line has 4 bytes,
                                        # but, only 1 line has data every 4 lines
                                        # so, finally, 8K * 4 / 4 = 8 K bytes        
            format_data = "h" * (int(len(txt)/2))  
            tmp = struct.unpack(format_data, txt)
            # buf_q = tmp[0::2]
            # print(buf_q)
            # print(f'len buf_q:{len(buf_q)}')
            self.bram_data.append(tmp)
    def calc_amp_phase(self, Q, I,flag):
        """
        Calculate amplitude and phase of I/Q data

        Parameters:
        Q (list or numpy array): Q data
        I (list or numpy array): I data
        flag (int): 0 for numpy array, 1 for list
        """
        amp=[]
        phi=[]
        if flag == 1:
            for q, i in zip(Q, I):
                try:
                    amp.append(math.sqrt(q * q + i * i))
                    phi.append(math.degrees(math.atan2(q,i)))
                    #print(q,i)
                except ValueError:
                    print("value err list")
        else:
                try:
                    amp = math.sqrt(Q**2+ I**2)
                    phi = math.degrees(math.atan2(Q,I))
                except ValueError:
                    print("value err val")
        return [amp, phi]
    def calculate_data(self):
        self.calc_ch =[[None] * 4 for _ in range(self.nbr_bram)]
        n_bit = 4
        for i, data in enumerate(self.bram_data):

            data_length = len(data)
            buf_i = data[0::2]
            buf_q  = data[1::2]
            mean_i = (statistics.mean(buf_i))
            mean_q = (statistics.mean(buf_q))
            [amp_avg, phi_avg] = self.calc_amp_phase(mean_q, mean_i, 0)   # calc amp and phase RMS
            [amp_std, phi_std] = self.calc_amp_phase(buf_q, buf_i, 1) # calc amp and phase std    
            
            amp_avg = round(amp_avg, 2)
            phi_avg = round(phi_avg, n_bit)
            amp_std = round(self.calculate_std(amp_std), n_bit)
            phi_std = round(self.calculate_std(phi_std), n_bit)#str(round(statistics.std(phi_std), n_bit))
            self.calc_ch[i] = [amp_avg, phi_avg, amp_std,  phi_std]  
    def pack_data(self,data):
        packed = b''
        for row in data:
            packed += struct.pack('4f', *row)  # 每行 4 个浮点数
        return packed     
    def send_calculated_data(self,data):
        try:
        # 数据打包
            binary_data = self.pack_data(data)
            
            # 发送数据长度
            self.connexion.sendall(struct.pack('I', len(binary_data)))  # 先发送数据长度
            # data_to_send = data[0] 
            # self.connexion.send(json.dumps(data_to_send).encode('utf-8'))
            # 发送实际数据
            self.connexion.sendall(binary_data)
            # print("data sent successfully")
        except Exception as e:
            print(f"Err: {e}")

    def trig_data_send(self):

        self.get_data()
        self.send_data()
        self.bram_data=[]

 
    def signed_to_unsigned_16bit(self, signed_value):
        if signed_value < 0:
            return signed_value + 2**16
        return signed_value

    def write_any_reg32(self):
        self.connexion.send(b'waiting')
        msgClient = self.connexion.recv(32)
        msg = msgClient.decode().split(',')
        try:
            print(msg)
            print('val')
            print(msg[0])
            print('addr')
            print(msg[1])
            val = float(msg[0])
            offset_addr = int(msg[1],16)
            val = self.float_to_hex(val)
            
            #print('You write '+ hex(val) + ' to ' + hex(offset_addr))
            #if str(hex(offset_phase_addr)) in ['0x30000','0x40000','0x50000','0x60000']:
            self.rw_bram.write32(offset_addr,int(val,16))
        except IndexError:
            print('index error')
            pass
    def dec_to_hex_to_float(self,value: int) -> float:
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
    def read_any_reg(self):
        msgClient = self.connexion.recv(1024).decode()
        print(f'reg address:{hex(int(msgClient))}')
        data = self.rw_bram.read32(int(msgClient))
        data = self.dec_to_hex_to_float(data)
        print(f'***read data***: {data}')
        self.connexion.send(str(data).encode())

    def read_reg(self,offset_addr):
        # print(self.offset_tuner)
        # print(offset_addr)
        
        data = self.rw_bram.read32(offset_addr)
       # print(data)
        self.connexion.send(str(data).encode())

    def mem_cmd(self,msg_list):
       
        # bram start address
        self.bram0_start_addr = 0x30002000 #msg_list[0]
        self.offset_trig =      0x30020000 #msg_list[2]
        # print(f'bram0_start_addr:{hex(self.bram0_start_addr)}')
        # print(f'offset_trig:{hex(self.offset_trig)}')
        ''' BRAM map length '''
        self.map_len =  0xF0000000#msg_list[1]-msg_list[0]
        ''' One bram size '''
        self.data_size = 8*1024
        ''' nb. of bram 2 or 4 '''
        self.nbr_bram = 10 # msg_list[-3] 
        self.num_val = int(self.data_size/2*self.nbr_bram)
        
        self.data_map_start = 0x80000000# msg_list[-2]
        # self.data_map_end = 0x #msg_list[-1]
        # self.data_map_len = 0x40000000# self.data_map_end - self.data_map_start
        # self.bram_start_addr = []*(self.nbr_bram+1)
        self.bram_start_offset = []*(self.nbr_bram)

        for i in range(self.nbr_bram):
            self.bram_start_offset.append(self.bram0_start_addr+i*self.data_size)
            
            # self.bram_start_offset.append(self.bram_start_addr[i] - self.data_map_start)
            # print(hex(self.bram_start_offset[i]))
      
        '''
        Number of values is presented by 16 bits
        BRAM size is presented by 8 bits
        '''
    def float_to_hex(self,f):
        # Pack the float into 4 bytes using IEEE 754 single-precision format
        packed = struct.pack('>f', f)
        # Unpack the 4 bytes as an unsigned integer and convert to hex
        return hex(struct.unpack('>I', packed)[0])

    def to_unsigned_32bit(self, value):
    # """将整数转换为 32 位无符号整数（补码表示）"""
        return value & 0xFFFFFFFF

    def phase_cmd(self):
        msgClient = self.connexion.recv(1024)
        msg = msgClient.decode().split(',')
        try:
            print(msg)
            print('phase')
            print(msg[0])
            print('address')
            print(msg[1])
            phase_angle = float(msg[0])
            offset_phase_addr = int(msg[1],16)
            phase_angle = self.float_to_hex(phase_angle)
            print(f'phase_angle: {phase_angle}')
            # print(self.float_to_hex(phase_angle))
            # print(hex(offset_phase_addr))
            # int_phase_angle = int(phase_angle)
            # unsigned_phase_angle = self.float_to_hex(int_phase_angle)

            # if str(hex(offset_phase_addr)) in ['0x40000','0x50000','0x60000','0x70000','0x80000','0x90000','0xA0000','0xB0000','0xC0000','0xD0000','0xE0000','0xF0000']:
            self.rw_bram.write32(offset_phase_addr,int(phase_angle,16))
            print('phase updated')
        except IndexError:
            print('index error')
            pass

    def __processing__(self):
        self.mysocket.listen()
       # can accpet multiple clients 
        while 1: 
            # 3) Attente de la requête de connexion d'un client :
            print ("Server ready, waiting for requests ...")
            # 4) Etablissement de la connexion :
            self.connexion, self.adresse = self.mysocket.accept()
            print ("Client connected, adresse IP %s, port %s" % (self.adresse[0], self.adresse[1]))
            '''
            Memory config. from client
            connected to BRAM and send message to client
            '''
            #self.mysocket.setdefaulttimeout = 60
            msgClient = self.connexion.recv(4096)
            msg_str = eval(msgClient.decode('utf-8'))
            for val in msg_str:
                print(hex(int(val)))
      
            self.mem_cmd(list(map(int, msg_str))) 
            
            self.rw_bram = rw_mio.MMIO(self.data_map_start, self.map_len)

            '''
             Trigger
             Get data from BRAM
             Send to client
            '''
            while 1:
                '''
                    offset for trigger
                '''
                msgClient = self.connexion.recv(2)
     
                # print('Command:', msgClient.decode())
                # cmd_res = os.popen(msgClient.decode()).read()

                #print(msgClient)
                if msgClient.decode() == "8":  # To read data from BRAM
                    '''
                    set reference mag 
                    '''
                    self.ref_mag_setting()
                if msgClient.decode() == "7":  # To read data from BRAM
                    '''
                    ramp the output reference
                    '''
                    self.ramping_mag_phase(0)

                if msgClient.decode() == "6":  # To read data from BRAM
                    '''
                    ramp the output reference
                    '''
                    self.ramping_mag_phase(1)

                if msgClient.decode() == "5":  # To read data from BRAM
                    '''
                    write specific 32bit register
                    '''
                    self.write_any_reg32()

                if msgClient.decode() == "4":  # To any register @give address 
                    '''
                    read specific register
                    '''
                    self.read_any_reg()


                if msgClient.decode() == "3":  # To read register for tuner
                    '''
                    send calculated data to client
                    '''
                    self.trig_data_calculate()

                if msgClient.decode() == "2":  # To read data from BRAM
                    '''
                    Phase config. from Client
                    '''
                    self.phase_cmd()
                    #print("next time")
                    '''
                    Continued signal
                    '''
                if msgClient.decode() == "1":  # To read data from BRAM
                   
                    self.trig_data_send()
                    '''
                    Stop
                    '''
                if msgClient.decode()== "0":
                    self.close_connect()
                    break

myserver = server_socket(ip_server, port_server)
print('Connected to server '+ ip_server +' '+ str(port_server))
myserver.__create__()
myserver.__processing__()
