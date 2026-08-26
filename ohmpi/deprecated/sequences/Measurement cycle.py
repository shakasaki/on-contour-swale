import os
import numpy as np
import time
import datetime
import matplotlib.pyplot as plt
from ohmpi.ohmpi import OhmPi

# Change directory to the appropriate location
os.chdir("/home/ohmpi2/ohmpi")

# Measurement with Python API
k = OhmPi()  # this loads default parameters from the disk

# Set parameters
k.settings['injection_duration'] = 0.5  # injection time in seconds
k.settings['nb_stack'] = 1  # one stack is two half-cycles
k.settings['nbr_meas'] = 1  # number of times the sequence is repeated
k.settings['export_path'] = "/home/ohmpi/ohmpi2/data/measurements_SF2024/" #(path where to export the data, timestamp will be added to filename)
   
 # Load sequence
k.load_sequence('ABMN.txt')    # load sequence from a local file

# Run contact resistance check
k.rs_check()

# Run sequence
k.run_sequence()
