reg_dict = {
    # First stage ADC gain and polarity registers
    "REG_ADC0gain": 0x80080000,
    "REG_ADC1gain": 0x80080004,
    "REG_ADC2gain": 0x80080008,
    "REG_ADC3gain": 0x8008000c,
    "REG_ADC0Pol": 0x80080010,
    "REG_ADC1Pol": 0x80080014,
    "REG_ADC2Pol": 0x80080018,
    "REG_ADC3Pol": 0x8008001c,
    
    # Fine ADC gain control registers
    "REG_Gain_Ctrl0": 0x80080020,
    "REG_Gain_Ctrl1": 0x80080024,
    "REG_Gain_Ctrl2": 0x80080028,
    "REG_Gain_Ctrl3": 0x8008002c,
    
    # Amplitude loop settings
    "REG_AmpRefSetPoint": 0x80040000,
    "REG_AmpPI_gain": 0x80040004,
    "REG_AmpPI_DIV": 0x80040008,
    "REG_AmpPI_int_step": 0x8004000c,
    "REG_RefIQ": 0x8004007c,
    
    # Magnet PI control and RF control
    "REG_MagPI_Open_Close_Loop": 0x8008007c,
    "REG_interlock": 0x80090010,          # Note: Active definition (SIMU version)
    "REG_RF_Sequence": 0x80090014,
    "REG_On_Off_RF": 0x80090018,
    
    # Phase rotation registers
    "REG_float_ph_shift0": 0x80080030,
    "REG_float_ph_shift1": 0x80080034,
    "REG_float_ph_shift2": 0x80080038,
    "REG_float_ph_shift3": 0x8008003c,
    
    # Cavity control registers
    "REG_CavMag_SetPoint": 0x80080040,
    "REG_CavPhase_SetPoint": 0x80080044,
    "REG_Cav_P_gain": 0x80080048,
    "REG_Cav_I_gain": 0x8008004c,
    "REG_Cav_P_DIV": 0x80080050,
    "REG_Cav_I_DIV": 0x80080054,
    "REG_Cav_PI_Reset": 0x80080058,
    "REG_Cav_PI_IntegralReset": 0x8008005c,
    "REG_Cav_PI_FlagauRF": 0x80080060,
    "REG_CavPI_Open_Close_Loop": 0x80080064,
    "REG_Cavity_Emulator": 0x80090004,
    
    # Additional phase rotation
    "REG_float_ph_shift_Pinc": 0x80080068,
    "REG_float_ph_shift_Vcav": 0x8008006c,
    "REG_Tuner_Open_Close_Loop": 0x80090008
}