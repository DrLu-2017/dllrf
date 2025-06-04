reg_dict = {
    # First stage ADC gain and polarity registers
    "REG_ADC0gain": {"address": 0x80080000, "type": "float"},
    "REG_ADC1gain": {"address": 0x80080004, "type": "float"},
    "REG_ADC2gain": {"address": 0x80080008, "type": "float"},
    "REG_ADC3gain": {"address": 0x8008000c, "type": "float"},
    "REG_ADC0Pol": {"address": 0x80080010, "type": "float"},
    "REG_ADC1Pol": {"address": 0x80080014, "type": "float"},
    "REG_ADC2Pol": {"address": 0x80080018, "type": "float"},
    "REG_ADC3Pol": {"address": 0x8008001c, "type": "float"},
    
    # Fine ADC gain control registers
    "REG_Gain_Ctrl0": {"address": 0x80080020, "type": "float"},
    "REG_Gain_Ctrl1": {"address": 0x80080024, "type": "float"},
    "REG_Gain_Ctrl2": {"address": 0x80080028, "type": "float"},
    "REG_Gain_Ctrl3": {"address": 0x8008002c, "type": "float"},
    
    # Amplitude loop settings
    "REG_AmpRefSetPoint": {"address": 0x80040000, "type": "float"},
    "REG_AmpPI_gain": {"address": 0x80040004, "type": "float"},
    "REG_AmpPI_DIV": {"address": 0x80040008, "type": "float"},
    "REG_AmpPI_int_step": {"address": 0x8004000c, "type": "float"},
    "REG_RefIQ": {"address": 0x8004007c, "type": "float"},
    
    # Magnet PI control and RF control
    "REG_MagPI_Open_Close_Loop": {"address": 0x8008007c, "type": "int"},
    "REG_interlock": {"address": 0x80090010, "type": "int", "display": True},          # Note: Active definition (SIMU version)
    "REG_RF_Sequence": {"address": 0x80090014, "type": "int", "display": True},
    "REG_On_Off_RF": {"address": 0x80090018, "type": "int", "display": True},
    
    # Phase rotation registers
    "REG_float_ph_shift0": {"address": 0x80080030, "type": "float", "display": True},
    "REG_float_ph_shift1": {"address": 0x80080034, "type": "float", "display": True},
    "REG_float_ph_shift2": {"address": 0x80080038, "type": "float", "display": True},
    "REG_float_ph_shift3": {"address": 0x8008003c, "type": "float", "display": True},
    
    # Cavity control registers
    "REG_CavMag_SetPoint": {"address": 0x80080040, "type": "float", "display": True},
    "REG_CavPhase_SetPoint": {"address": 0x80080044, "type": "float", "display": True},
    "REG_Cav_P_gain": {"address": 0x80080048, "type": "float"},
    "REG_Cav_I_gain": {"address": 0x8008004c, "type": "float"},
    "REG_Cav_P_DIV": {"address": 0x80080050, "type": "float"},
    "REG_Cav_I_DIV": {"address": 0x80080054, "type": "float"},
    "REG_Cav_PI_Reset": {"address": 0x80080058, "type": "int"},
    "REG_Cav_PI_IntegralReset": {"address": 0x8008005c, "type": "int"},
    "REG_Cav_PI_FlagauRF": {"address": 0x80080060, "type": "int"},
    "REG_CavPI_Open_Close_Loop": {"address": 0x80080064, "type": "int"},
    "REG_Cavity_Emulator": {"address": 0x80090004, "type": "int"},
    
    # Additional phase rotation
    "REG_float_ph_shift_Pinc": {"address": 0x80080068, "type": "float"},
    "REG_float_ph_shift_Vcav": {"address": 0x8008006c, "type": "float"},
    "REG_Tuner_Open_Close_Loop": {"address": 0x80090008, "type": "int"}
}