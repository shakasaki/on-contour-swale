### Testcircuit
import os
import numpy as np
import time
import matplotlib.pyplot as plt
os.chdir("/home/ohmpia/ohmpi")
from ohmpi.ohmpi import OhmPi
k = OhmPi()
k.test_mux()
k.run_measurement(quad=[17,19,21,23], tx_volt = 5., strategy = 'constant', dutycycle=0.5)
