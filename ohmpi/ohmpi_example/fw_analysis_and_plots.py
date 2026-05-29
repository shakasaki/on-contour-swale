# %% imports
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def compute_summary_statistics(fw_df: pd.DataFrame,
                               window_size: float = 0.33,
                               DC_correction: str = 'dynamic',
                               rounding_digits: int = 3) -> pd.DataFrame:
    """
    Compute summary statistics for the full waveform data.
    Parameters
    ----------
    fw_df : pd.DataFrame
        DataFrame containing the full waveform data with columns 
        ['a', 'b', 'm', 'n', 'time', 'current', 'voltage', 'polarity'].
    window_size : float, optional
        Size of the window to consider for statistics. A value of 1 takes the entire window,
        while a value of 0.33 takes the last third of the window. Default is 0.33.
        Can be anything above 0.1 and below 1.
    DC_correction : str, optional
        Method to compute the DC shift in each pulse. Options are 'dynamic' or 'static'.
        'dynamic' uses the DC values at each off pulse prior to a measurement.
         'static' uses the first DC pulse for each measurement (quadropole)
    rounding_digits : int, optional
        Number of digits to round the statistics to. Default is 3.
    Returns
    -------
    pd.DataFrame
        DataFrame with summary statistics for each measurement.
    fw_df : pd.DataFrame
        Original full-waveform dataframe including auxulliary columns used for statistics.
    """

    if window_size <= 0.1 or window_size > 1:
        raise ValueError("window_size must be between 0.1 and 1.")
    if DC_correction not in ['dynamic', 'static']:
        raise ValueError("DC_correction must be either 'dynamic' or 'static'.")
    if rounding_digits < 0 or not isinstance(rounding_digits, int):
        raise ValueError("rounding_digits must be a non-negative integer.")
    
    fw_df = fw_df.copy() # avoid changing the original DataFrame

    # Make sure polarity is integer for better handling
    fw_df['polarity'] = fw_df['polarity'].astype(int)

    # Create a column identifying unique electrode configurations
    fw_df['quadropole'] = fw_df[['a', 'b', 'm', 'n']].astype(str).agg('_'.join, axis=1)

    # Create a column with the pulse number for each quadropole
    fw_df['pulse'] = fw_df.groupby('quadropole')['polarity'].transform(
        lambda x: (x != x.shift()).cumsum().astype(int))

    # get the size and rank of each sample
    group_size = fw_df.groupby(['quadropole', 'polarity', 'pulse']).transform('size')
    group_rank = fw_df.groupby(['quadropole', 'polarity', 'pulse']).cumcount()

    # Create a valid column to indicate if the data point is in the desired window
    fw_df['valid'] = group_rank >= group_size*(1 - window_size)

    # if 'valid' and polarity is 0, set valid to False. 
    # This is to avoid using the off time data for statistics
    fw_df.loc[(fw_df['polarity'] == 0) & (fw_df['valid']), 'valid'] = False

    # use zero polarities to compute DC shift
    fw_df['DC'] = np.where(fw_df['polarity'] == 0, fw_df['voltage'], np.nan)

    # Compute the DC shift for each quadropole and between pulses
    fw_df['DC shift'] = fw_df.groupby(['quadropole', 'pulse'])['voltage'].transform(
        lambda x: x[fw_df['polarity'] == 0].mean())
    
    # Compute the mean, std and median over the chosen window length
    fw_df['mean voltage'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['voltage'].transform(
        lambda x: x[fw_df['valid']].mean())
    fw_df['std voltage'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['voltage'].transform(
        lambda x: x[fw_df['valid']].std())
    fw_df['median voltage'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['voltage'].transform(
        lambda x: x[fw_df['valid']].median())

    fw_df['mean current'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['current'].transform(
        lambda x: x[fw_df['valid']].mean())
    fw_df['std current'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['current'].transform(
        lambda x: x[fw_df['valid']].std())
    fw_df['median current'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['current'].transform(
        lambda x: x[fw_df['valid']].median())

    # Loop below is to compute the resistance using V=IR. We have 2 methods:
    # 1. Using the SP response as the initial voltage (static SP)
    # 2. Computing an SP response for each off time pulse (dynamic SP)
    # 3. Another option would be to interpolate the SP response between pulses, but this is not implemented here.

    # TODO: can vectorize this loop eventually
    for (quadropole, pulse), group in fw_df.groupby(['quadropole', 'pulse']):
        # Get the voltage and current for the group
        valid_mask = group['valid'].values # boolean mask
        # get indices of valid data points
        indices = group.index[valid_mask] # indices for pandas
        voltage = group['voltage'].values[valid_mask]
        current = group['current'].values[valid_mask]

        if sum(valid_mask) == 0:
            if pulse == 1:
                initial_dc_shift = group['DC shift'].mean()
            dc_shift = group['DC shift'].mean()
            continue
        else:
            if DC_correction == 'dynamic':
                fw_df.loc[indices, 'resistance'] = (voltage - dc_shift) / current
            elif DC_correction == 'static':
                fw_df.loc[indices, 'resistance'] = (voltage - initial_dc_shift) / current

    # compute statistics for resistance
    fw_df['mean resistance'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['resistance'].transform(
        lambda x: x[fw_df['valid']].mean())
    fw_df['std resistance'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['resistance'].transform(
        lambda x: x[fw_df['valid']].std())
    fw_df['median resistance'] = fw_df.groupby(['quadropole', 'polarity', 'pulse'])['resistance'].transform(
        lambda x: x[fw_df['valid']].median())

    # round off all floats in the DataFrame to 3 decimal places
    fw_df = fw_df.round(rounding_digits)

    # until now all statistics are computed for each pulse, 
    # now we want to compute the summary statistics for each quadropole

    # Create a new DataFrame with the statistics
    measurement_stats = fw_df[['quadropole', 'polarity', 'pulse', 
                        'mean voltage', 'std voltage', 'median voltage',
                        'mean current', 'std current', 'median current',
                        'mean resistance', 'std resistance', 'median resistance']].drop_duplicates()

    # remove polarities with zero
    measurement_stats = measurement_stats[measurement_stats['polarity'] != 0]

    # compute the overall mean, std and median for each quadropole
    measurement_stats = measurement_stats.groupby('quadropole').agg({
        'mean voltage': 'mean',
        'std voltage': 'std',
        'median voltage': 'median',
        'mean current': 'mean',
        'std current': 'std',
        'median current': 'median',
        'mean resistance': 'mean',
        'std resistance': 'std',
        'median resistance': 'median'
    }).reset_index()

    # expand quadropole column to separate columns for a, b, m, n
    measurement_stats[['a', 'b', 'm', 'n']] = measurement_stats['quadropole'].str.split('_', expand=True)
    measurement_stats = measurement_stats.round(rounding_digits)
    return measurement_stats, fw_df

    
# %% plot the waveform for a single quadropole


def plot_quadropole_measurements(fw_df : pd.DataFrame,
                                 quadropole: str,
                                 ) -> tuple:
    """
    Plot the measurements for a single quadropole.
    Parameters
    ----------
    fw_df : pd.DataFrame
        DataFrame containing the full waveform data with columns 
        ['time', 'current', 'voltage', 'polarity', 'quadropole', 'valid'].
    quadropole : str
        The quadropole identifier, e.g. '9_10_7_11'.

    Returns
    -------
        Figure and axes objects for the plot.
    """

    data_quadropole = fw_df[fw_df['quadropole'] == quadropole]
    if data_quadropole.empty:
        print(f"No data found for quadropole {quadropole}.")
        return None, None
    
    fig, axs = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
    valid = data_quadropole['valid'].astype(bool)

    axs[0].plot(data_quadropole['time'], 
                data_quadropole['current'], 
                label='Current', color='r')
    axs[0].set_ylabel('Current (mA)')
    axs[0].scatter(data_quadropole['time'][valid], 
                data_quadropole['current'][valid], 
                label='valid', color='g')
    axs[0].legend()

    axs[1].plot(data_quadropole['time'], 
                data_quadropole['voltage'], 
                label='Voltage', color='b')
    axs[1].set_ylabel('Voltage (mV)')
    axs[1].scatter(data_quadropole['time'][valid], 
                data_quadropole['voltage'][valid], 
                label='valid', color='g')
    axs[1].legend()

    # plot DC response and polarity on the same axis with dual y-axes
    ax2_twin = axs[2].twinx()
    
    # Plot polarity on left y-axis
    axs[2].plot(data_quadropole['time'], 
                data_quadropole['polarity'], 
                label='Polarity', color='y')
    axs[2].set_ylabel('Polarity', color='y')
    axs[2].tick_params(axis='y', labelcolor='y')
    
    # Plot DC shift on right y-axis
    ax2_twin.scatter(data_quadropole['time'], 
                     data_quadropole['DC shift'],
                     marker='x',
                     label='DC shift', color='violet')
    ax2_twin.set_ylabel('DC shift (mV)', color='violet')
    ax2_twin.tick_params(axis='y', labelcolor='violet')
    
    axs[2].set_xlabel('Time (s)')
    
    # Combine legends
    lines1, labels1 = axs[2].get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    axs[2].legend(lines1 + lines2, labels1 + labels2, loc='upper right')

    # plot the calculated resistance during the on time
    axs[3].scatter(data_quadropole['time'],
                   data_quadropole['resistance'],
                    label='Resistance (Ohm)', marker='x', color='violet')

    axs[3].set_ylabel('Resistance (Ohm)')
    axs[3].set_xlabel('Time (s)')
    axs[3].legend()
    plt.tight_layout()
    return fig, axs


# %% Additional analysis: Compute the DC shift during injection pulses and off times

def compare_dc_shift(fw_df: pd.DataFrame,
                     injection: bool = False) -> pd.DataFrame:
    """
    Compute the statistics for the direct current (DC) shift for each quadropole.
    The function either computes the DC shift during the injection pulses (polarity is -1 or 1)
    or during the off times (polarity is 0).

    Parameters
    ----------
    fw_df : pd.DataFrame
        DataFrame containing the full waveform data with columns 
        ['quadropole', 'polarity', 'pulse', 'voltage'].
    injection : bool, optional
        If True, compute the DC response during injection pulses (polarity is -1 or 1).
        If False, compute the DC response during off times
    Returns
    -------
    pd.DataFrame
        DataFrame with DC statistics.
    """
    if injection:
        # Filter for injection pulses (polarity -1 or 1)
        fw_df = fw_df[fw_df['polarity'].isin([-1, 1])]
    else:
        # Filter for off times (polarity 0)
        fw_df = fw_df[fw_df['polarity'] == 0]
    # Group by quadropole and compute mean, std, and median of voltage
    sp_response = fw_df.groupby('quadropole')['voltage'].agg(
        mean_dc='mean',
        std_dc='std',
        median_dc='median'
    ).reset_index()    
    return sp_response


# %%

fw_df = pd.read_csv('wenner_line_D_results_20250518T131754_fw.csv')  # Load your full waveform data here

measurement_stats, fw_df = compute_summary_statistics(fw_df, 
                                                      window_size=0.33, 
                                                      DC_correction='dynamic')

for quadropole in ['37_40_38_39']:
    print(f"Quadropole: {quadropole}")
    # get the stats with static DC
    measurement_stats_static, fw_df_static = compute_summary_statistics(fw_df, 
                                                        window_size=0.33, 
                                                        DC_correction='static')
    # get the stats with dynamic DC
    measurement_stats_dynamic, fw_df_dynamic = compute_summary_statistics(fw_df,
                                                        window_size=0.33,
                                                        DC_correction='dynamic')


    # Plot the quadropole data for the specified quadropole
    fig, axs = plot_quadropole_measurements(fw_df_static, quadropole)

    data_quadropole = fw_df_dynamic[fw_df_dynamic['quadropole'] == quadropole]
    # plot the calculated resistance during the on time
    axs[3].scatter(data_quadropole['time'],
                    data_quadropole['resistance'],
                    label='Resistance w dynamic DC correction (Ohm)', marker='x', color='cyan')
    axs[3].legend()

    plt.show()


run_tests = False

if run_tests:
    # tests (will raise errors as expected)
    measurement_stats, fw_df = compute_summary_statistics(fw_df, 
                                                        DC_correction='nonsense')

    measurement_stats, fw_df = compute_summary_statistics(fw_df, 
                                                        window_size=5)

    measurement_stats, fw_df = compute_summary_statistics(fw_df, 
                                                        rounding_digits=-1)




# %% Compute SP response for injection pulses
dc_injection = compute_dcompare_dc_shiftc_shift(fw_df, injection=True)
# Compute SP response for off times
dc_off = compare_dc_shift(fw_df, injection=False)


fig, ax = plt.subplots(2, 1, figsize=(5, 10))
# Plot SP response for injection pulses
ax[1].errorbar(dc_injection['quadropole'], 
            dc_injection['mean_dc'], 
            yerr=dc_injection['std_dc'], 
            fmt='o', 
            label='Injection DC', 
            color='r', 
            capsize=5)
# Plot SP response for off times
ax[1].errorbar(dc_off['quadropole'], 
            dc_off['mean_dc'], 
            yerr=dc_off['std_dc'], 
            fmt='o', 
            label='Off Time DC', 
            color='b', 
            capsize=5)

# plot quadropole labels vertically
ax[1].set_xticks(dc_injection['quadropole'])
ax[1].set_xticklabels(dc_injection['quadropole'], rotation=90)

ax[1].set_xlabel('Quadropole')
ax[1].set_ylabel('DC shift (mV)')
ax[1].legend()

# plot as a scatter plot comparison
ax[0].scatter(dc_injection['mean_dc'], 
           dc_off['mean_dc'], 
           color='r', 
           marker='o')
# plot the diagonal line
ax[0].plot([dc_injection['mean_dc'].min(), dc_injection['mean_dc'].max()], 
           [dc_off['mean_dc'].min(), dc_off['mean_dc'].max()], 
           color='y', linestyle='--', label='y=x')
ax[0].set_xlabel('DC during injection (mV)')
ax[0].set_ylabel('DC during off time (mV)')