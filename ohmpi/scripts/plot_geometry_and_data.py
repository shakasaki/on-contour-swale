# %% imports
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def plot_statistics(statistics: pd.DataFrame):
    # group the quadropoles together and plot the voltage, current and highlight the last third of each pulse

    """
    Plot the statistics of the measurements.
    Parameters
    ----------
    statistics : pd.DataFrame
        DataFrame containing the statistics of the measurements.
    """
    # group by quadropole, polarity and pulse
    grouped = statistics.groupby(['quadropole'])
    for eid, group in grouped:
    # Filter for mean voltage and current
        fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        axs[0].plot(group['time'], group['current'], label='Current', color='r')
        axs[0].set_ylabel('Current (mA)')
        axs[0].set_title(f'Current for {eid}')
        #axs[0].axvline(x=last_third['time'].iloc[0], color='g', linestyle='--', label='Start of last third')
        axs[0].legend()
        axs[1].plot(group['time'], group['voltage'], label='Voltage', color='b')
        axs[1].set_ylabel('Voltage (mV)')
        #axs[1].axvline(x=last_third['time'].iloc[0], color='g', linestyle='--', label='Start of last third')
        axs[1].legend()
        axs[2].plot(group['time'], group['polarity'], label='Polarity', color='k')
        axs[2].set_ylabel('Polarity')
        axs[2].set_xlabel('Time (s)')
        #axs[2].axvline(x=last_third['time'].iloc[0], color='g', linestyle='--', label='Start of last third')
        axs[2].legend()
        plt.tight_layout()
        plt.savefig(os.path.join(outdir, f'statistics_{eid}.png'), dpi=300)
        plt.close(fig)


def plot_fw_data(fw_df: pd.DataFrame, 
                 output_path: str):

    tracedic = {}
    for key, sdf in fw_df.groupby(['a', 'b', 'm', 'n']):
        tracedic[' '.join([str(a) for a in key])] = sdf

    # Example key to visualize
    # Loop over all keys in tracedic
    num = 0
    for key in list(tracedic.keys()):
        sdf = tracedic[key]
        a, b, m, n = map(int, key.split())
        # --- Plotting ---
        fig = plt.figure(figsize=(12, 8))
        gs = fig.add_gridspec(4, 2)

        # --- Geometry Plot (full left column) ---
        ax1 = fig.add_subplot(gs[:, 0])
        ax1.scatter(geometry_df['X_av'], 
                    geometry_df['Y_av'], 
                    color='lightgray',
                    s=20)
        for _, row in geometry_df.iterrows():
            ax1.text(row['X_av'] + 0.01, row['Y_av'], str(row['Electrode number for survey']), fontsize=7)

        # Highlight A, B, M, N
        labels = ['A', 'B', 'M', 'N']
        coords = []
        symbols = ['s', 's', 'd', 'd']
        for i, idx in enumerate([a, b, m, n]):
            elec = geometry_df[geometry_df['Ohmpi channel'] == idx]
            try:
                x, y = elec.iloc[0][['X_av', 'Y_av']]
                coords.append((x, y))
                ax1.scatter(x, y,
                            s=80,
                            marker=symbols[i],
                            color='red' if i < 2 else 'blue',
                            label=labels[i])
                ax1.text(x, y + 0.2, 
                        labels[i], 
                        color='red' if i < 2 else 'blue',
                        fontsize=9, 
                        weight='bold')
                prefix = ''
            except IndexError:
                print('Electrode test')
                ax1.text(3,10, 
                        'Test circuit', 
                        color='red',
                        fontsize=9, 
                        weight='bold')
                prefix = 'test_circuit'
        ax1.set_xlabel('X [m]')
        ax1.set_ylabel('Y [m]')
        ax1.set_title(f"Electrode Geometry\nA={a} B={b} M={m} N={n}")
        ax1.axis('equal')
        ax1.legend()

        # --- Iab (Current) Plot (top right) ---
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.plot(sdf['time'], sdf['current'], 'r-')
        #ax2.set_title('Current (Iab)')
        ax2.set_xlabel('Time [s]')
        ax2.set_ylabel('Current [mA]')
        # set y lim to the abs max of the range
        ax2.set_ylim(-sdf['current'].abs().max() * 1.1, 
                     sdf['current'].abs().max() * 1.1)

        # --- Vmn (Voltage) ---
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.plot(sdf['time'], sdf['voltage'], 'b-')
        #ax3.set_title('Voltage (Vmn)')
        ax3.set_xlabel('Time [s]')
        ax3.set_ylabel('Voltage [mV]')

        # --- Polarity plot ---
        ax4 = fig.add_subplot(gs[2, 1])
        ax4.plot(sdf['time'], 
                 sdf['polarity'], 
                 'b-')
        #ax4.set_title('Polarity (-n)')
        ax4.set_xlabel('Time [s]')
        ax4.set_ylabel('Polarity [-]')

        # --- Polarity plot ---
        ax5 = fig.add_subplot(gs[3, 1])
        ax5.plot(sdf['time'], 
                 sdf['channel_mn'], 
                 'b-')
        #ax5.set_title('Self Potential response')
        ax5.set_xlabel('Time [s]')
        ax5.set_ylabel('SP [mV]')

        num += 1
        plt.tight_layout()
        plt.savefig(os.path.join(output_path, 
                                 f'Fig_{str(num + 1)}_{prefix}_{params[0]}_{params[2]}_{key}.png'), dpi=300)
        #plt.show()
        plt.close(fig)


# %%
# Set the directory where the data files are located
datadir = './data/20250613/'
outdir = './plots/'
fw_dir = './data/20250613/fw/'
os.makedirs(fw_dir, exist_ok=True)
os.makedirs(outdir, exist_ok=True)

import matplotlib as mpl

mpl.rcParams.update({
    # Backgrounds
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',

    # Text and ticks
    'text.color': 'black',
    'axes.labelcolor': 'black',
    'xtick.color': 'black',
    'ytick.color': 'black',

    # Spines
    'axes.edgecolor': 'black',
})


# unzip all files in the data directory
fnames = os.listdir(datadir)
print(fnames)
fnames = [f for f in fnames if f.endswith('.zip')]

# remove all files in fw_dir
for fname in os.listdir(fw_dir):
    os.remove(os.path.join(fw_dir, fname))

for fname in fnames:
    os.system(f'unzip {os.path.join(datadir, fname)} -d {fw_dir}')

fnames = os.listdir(fw_dir)
fnames = [f for f in fnames if f.endswith('_fw.csv')]
print(fnames)


# Load geometry data
geometry_df = pd.read_excel('merged_electrode_table.xlsx')
geometry_df = geometry_df.dropna(subset=['X_av', 'Y_av'])
geometry_df['Electrode number for survey'] = geometry_df['Electrode number for survey'].astype(int)


for file_name in fnames:
    print(f'Processing file: {file_name}')
    # Read the file
    if 'gradient' not in file_name:
	    fw_df = pd.read_csv(fw_dir + file_name)
	    # Extract the parameters from the filename
	    params = file_name.split('_')[0:4]
	    plot_fw_data(fw_df, outdir)

# %%
