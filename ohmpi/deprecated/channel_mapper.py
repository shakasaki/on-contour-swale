import pandas as pd
from gdp import DATA_DIR, OUTPUT_DIR
import numpy as np
from gdp.helpers.common_functions import create_directory
import os

# create output directory
output_directory = OUTPUT_DIR + 'ohmpi_sequences' + os.sep
create_directory(output_directory)

# load the desired sequence for one cable
electrodes = np.loadtxt(DATA_DIR + 'ohmpi/sequences/Dipole-Dipole 10 electrodes.txt', dtype='int')
sequence = pd.DataFrame(electrodes, columns=['A', 'B', 'M', 'N'])

# test circuit
test_circuit = pd.DataFrame(columns=['A', 'B', 'M', 'N'],
                            data=np.array([[124, 125, 126, 127]]))

# Name the sequence
sequence_prefix = 'dipdip_'

# Load the spreadsheet that contains the mapping
excel_file_path = DATA_DIR + 'ohmpi/MUX_boards_connectivity_test.xlsx'
df_channel_to_electrode = pd.read_excel(excel_file_path, sheet_name='channel to electrode')

# reproduce the sequence for lines A to J
all_cables = {}
for index, line in enumerate(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']):
    # get only rows for this line
    df_subset = df_channel_to_electrode.loc[df_channel_to_electrode['Line'] == line].copy()
    channel_mapping = dict(
        zip(df_subset['Electrode number on cable'], df_subset['Ohmpi channel']))
    line_df = sequence.applymap(lambda x: channel_mapping.get(x, x)).copy()
    # concatenate the dataframes
    line_df = pd.concat([test_circuit, line_df], ignore_index=True)
    # export the sequence to a file
    line_df.to_csv(output_directory + sequence_prefix + 'line_' + line + '.csv',
                   header=False, index=False, sep=' ')


# %% Create wenner sequences
# load the desired sequence for one cable
electrodes = np.loadtxt(DATA_DIR + 'ohmpi/sequences/Wenner 10 electrodes.txt', dtype='int')
sequence = pd.DataFrame(electrodes, columns=['A', 'B', 'M', 'N'])

# Name the sequence
sequence_prefix = 'wenner_'

# Load the spreadsheet that contains the mapping
excel_file_path = DATA_DIR + 'ohmpi/MUX_boards_connectivity_test.xlsx'
df_channel_to_electrode = pd.read_excel(excel_file_path, sheet_name='channel to electrode')


# reproduce the sequence for lines A to J
all_cables = {}
for index, line in enumerate(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']):
    # get only rows for this line
    df_subset = df_channel_to_electrode.loc[df_channel_to_electrode['Line'] == line].copy()
    channel_mapping = dict(
        zip(df_subset['Electrode number on cable'], df_subset['Ohmpi channel']))
    line_df = sequence.applymap(lambda x: channel_mapping.get(x, x)).copy()
    # concatenate the two dataframes
    line_df = pd.concat([test_circuit, line_df], ignore_index=True)
    # export the sequence to a file
    line_df.to_csv(output_directory + sequence_prefix + 'line_' + line + '.csv',
                   header=False, index=False, sep=' ')