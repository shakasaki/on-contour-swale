"""
Merge Electrode Coordinate and Channel Mapping Tables with Plotting

This script:
1. Loads two Excel files:
   - One with average X, Y, Z coordinates for each electrode.
   - One with channel mappings linking electrodes to Ohmpi channels.
2. Merges the tables using line label and electrode number on cable.
3. Filters based on user-specified lines (e.g., A–E).
4. Saves the merged result as an Excel file.
5. Plots the spatial distribution of electrodes.

Author: Your Name
Date: YYYY-MM-DD
"""

import pandas as pd
import matplotlib.pyplot as plt


def load_excel_file(filepath: str) -> pd.DataFrame:
    """
    Load an Excel file into a pandas DataFrame.

    Args:
        filepath (str): Path to the Excel file.

    Returns:
        pd.DataFrame: Loaded DataFrame.
    """
    return pd.read_excel(filepath)


def merge_electrode_data(
    coords_df: pd.DataFrame,
    mapping_df: pd.DataFrame,
    include_lines: list
) -> pd.DataFrame:
    """
    Merge coordinate and mapping data based on Line and Electrode number.

    Args:
        coords_df (pd.DataFrame): DataFrame with electrode coordinates.
        mapping_df (pd.DataFrame): DataFrame with Ohmpi channel mappings.
        include_lines (list): List of line labels to include (e.g., ['A', 'B']).

    Returns:
        pd.DataFrame: Merged and filtered DataFrame.
    """
    # Select and rename columns for merging
    coords = coords_df[['Line', 'Electrode number', 'X_av', 'Y_av', 'Z_av']].copy()
    coords.rename(columns={'Electrode number': 'Electrode number on cable'}, inplace=True)

    # Select relevant columns from mapping table
    mapping = mapping_df[
        ['Ohmpi channel', 'Electrode number on cable', 'Line', 'Electrode number for survey']
    ].copy()

    # Merge both tables
    merged = pd.merge(mapping, coords, on=['Line', 'Electrode number on cable'], how='inner')

    # Filter by selected lines
    filtered = merged[merged['Line'].isin(include_lines)]

    return filtered


def plot_electrodes(df: pd.DataFrame) -> None:
    """
    Plot the electrode positions using average X and Y coordinates.

    Args:
        df (pd.DataFrame): Merged DataFrame with coordinates and labels.
    """
    plt.figure(figsize=(10, 8))
    plt.scatter(df['X_av'], df['Y_av'], color='blue', label='Electrodes')

    for _, row in df.iterrows():
        label = str(int(row['Electrode number for survey'])) if not pd.isna(row['Electrode number for survey']) else '?'
        plt.text(row['X_av'] + 0.01, row['Y_av'] + 0.01, label, fontsize=8)

    plt.xlabel('Average X Coordinate')
    plt.ylabel('Average Y Coordinate')
    plt.title('Electrode Positions')
    plt.grid(True)
    plt.axis('equal')
    plt.legend()
    plt.tight_layout()
    plt.show()


def main():
    # === USER CONFIGURATION ===
    coords_file = "relative coordinates electrodes.xlsx"
    mapping_file = "MUX_boards_connectivity_test.xlsx"
    output_file = "merged_electrode_table.xlsx"
    selected_lines = ['A', 'B', 'C', 'D', 'E']  # Modify this list to include specific lines

    # === PROCESSING ===
    coords_df = load_excel_file(coords_file)
    mapping_df = load_excel_file(mapping_file)

    merged_df = merge_electrode_data(coords_df, mapping_df, selected_lines)

    # Save to Excel
    merged_df.to_excel(output_file, index=False)
    print(f"Merged table saved as '{output_file}'.")

    # Plot the electrodes
    plot_electrodes(merged_df)


if __name__ == "__main__":
    main()
