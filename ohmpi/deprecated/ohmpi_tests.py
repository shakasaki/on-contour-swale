import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import zipfile
import os
import glob

filename = 'dipdip_line_B_results_20250412T220501'
path = '/home/alexis/Downloads/ohmpi_SFI_data_April_2025/20250412/'

from gdp import OUTPUT_DIR
output_folder = os.path.join(OUTPUT_DIR, 'ohmpi_figures')
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# add a folder for the current day
day = path.split('/')[-1]
output_folder = os.path.join(output_folder, day)
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Find the zip file
zip_files = glob.glob(os.path.join(path, filename + '_fw.zip'))
if len(zip_files) == 0:
    raise FileNotFoundError("No zip file found in the specified path.")
zip_file = zip_files[0]
# Unzip the file
with zipfile.ZipFile(zip_file, 'r') as zip_ref:
    zip_ref.extractall(path)

data_fw = pd.read_csv(path + filename + '_fw.csv')

# group together all datasets that have the same A B M N values in the column
# 'A B M N' and then plot them
grouped_df = data_fw.groupby(['a', 'b', 'm', 'n']).agg(lambda x: list(x)).reset_index()




for fig_idx, row in grouped_df.iterrows():
    fig, ax = plt.subplots(1, 1, figsize=(10, 5))
    fig_name = f"A{row['a']}_B{row['b']}_M{row['m']}_N{row['n']}"
    ax.plot(row['time'], row['current'], '--',
            label='current', color='r')
    ax2 = ax.twinx()
    ax2.plot(row['time'], row['voltage'], label='voltage', color='b')
    ax.set_title(f"A: {row['a']}, B: {row['b']}, M: {row['m']}, N: {row['n']}")
    ax.set_xlabel('Time [ms]')
    ax.set_ylabel('Current (mA)')
    ax2.set_ylabel('Voltage (mV)')
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')
    # Check if the figure already exists
    fig_path = os.path.join(output_folder, f'quad_{fig_name}.png')
    if os.path.exists(fig_path):
        print(f"Figure {fig_name} already exists. Skipping...")
        fig_name = f"{fig_name}_repeat"
    # Save the figure
    fig.savefig(os.path.join(output_folder, f'quad_{fig_name}.png'), dpi=300)
