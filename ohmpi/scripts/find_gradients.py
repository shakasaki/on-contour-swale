"""
Gradient Array Generator with All Valid Permutations and Reciprocals

This script:
- Loads a merged electrode table
- Identifies all 4-electrode combinations that:
    * Come from 4 different lines
    * Are spaced according to constraints
    * Are approximately collinear
- For each valid 4-electrode combination:
    * Generates all 4! = 24 permutations
    * Filters permutations where {A,B} and {M,N} are disjoint
    * Stores valid ABMN configurations
    * Also stores reciprocals: B-A-N-M
- Exports:
    * ABMN configurations
    * Reciprocal configurations
    * PNG visualizations for each ABMN
"""

import pandas as pd
import numpy as np
import itertools
import matplotlib.pyplot as plt
import os

def compute_distance(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))

def is_approximately_linear(points, tolerance=0.1):
    x, y = points[:, 0], points[:, 1]
    coeffs = np.polyfit(x, y, 1)
    y_fit = np.polyval(coeffs, x)
    return np.all(np.abs(y - y_fit) <= tolerance)

def export_reciprocals(df):
    reciprocal_df = df.copy()
    reciprocal_df['A'], reciprocal_df['B'] = df['B'], df['A']
    reciprocal_df['M'], reciprocal_df['N'] = df['N'], df['M']
    reciprocal_df['A_label'], reciprocal_df['B_label'] = df['B_label'], df['A_label']
    reciprocal_df['M_label'], reciprocal_df['N_label'] = df['N_label'], df['M_label']
    return reciprocal_df[['A', 'B', 'M', 'N']]


def generate_all_valid_abmn(df, 
                            min_spacing=0.7, 
                            max_spacing=3.0, 
                            linearity_tolerance=0.1,
                            within_same_line: bool = True,
                            ):
    results = []

    df = df.set_index('Electrode number for survey')
    all_coords = df[['X_av', 'Y_av']].to_dict('index')
    channels = df['Ohmpi channel'].to_dict()
    lines = df['Line'].to_dict()

    all_electrodes = sorted(all_coords.keys())

    for base_combo in itertools.combinations(all_electrodes, 4):
        
        # Line-based filtering
        line_set = {lines[i] for i in base_combo}
        if within_same_line:
            if len(line_set) > 1:
                continue
        else:
            if len({lines[i] for i in base_combo}) < 4:
                continue



        base_pts = np.array([[all_coords[i]['X_av'], all_coords[i]['Y_av']] for i in base_combo])

        # All pairwise spacing check
        too_close = False
        for i, j in itertools.combinations(range(4), 2):
            if compute_distance(base_pts[i], base_pts[j]) < min_spacing:
                too_close = True
                break
        if too_close:
            continue

        # Linearity check
        if not is_approximately_linear(base_pts, tolerance=linearity_tolerance):
            continue

        # Now check all ABMN permutations
        for perm in itertools.permutations(base_combo):
            A, B, M, N = perm
            if len({A, B, M, N}) < 4:
                continue
            if {A, B}.intersection({M, N}):
                continue
            pts = np.array([[all_coords[i]['X_av'], all_coords[i]['Y_av']] for i in [A, B, M, N]])
            adj_dists = [compute_distance(pts[i], pts[i + 1]) for i in range(3)]
            if not all(d <= max_spacing for d in adj_dists):
                continue

            results.append({
                'A': channels[A], 'B': channels[B], 'M': channels[M], 'N': channels[N],
                'A_label': A, 'B_label': B, 'M_label': M, 'N_label': N,
                'X_coords': [all_coords[i]['X_av'] for i in [A, B, M, N]],
                'Y_coords': [all_coords[i]['Y_av'] for i in [A, B, M, N]],
                'Lines': [lines[i] for i in [A, B, M, N]]
            })

    fw_array = pd.DataFrame(results)
    reciprocals = export_reciprocals(fw_array)
    return fw_array, reciprocals


def plot_gradient(row, df, path):
    plt.figure(figsize=(8, 6))
    plt.scatter(df['X_av'], df['Y_av'], color='lightgray')
    for _, r in df.iterrows():
        plt.text(r['X_av'] + 0.01, r['Y_av'], str(r['Electrode number for survey']), fontsize=7, color='gray')
    x_vals, y_vals = row['X_coords'], row['Y_coords']
    labels = ['A', 'B', 'M', 'N']
    colors = ['red', 'orange', 'green', 'blue']
    for x, y, l, c in zip(x_vals, y_vals, labels, colors):
        plt.scatter(x, y, color=c, s=80)
        plt.text(x + 0.01, y, l, fontsize=9, color=c, weight='bold')
    plt.title(f"A={row['A']}, B={row['B']}, M={row['M']}, N={row['N']}")
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

def export_array(df : pd.DataFrame,
                 initial_df: pd.DataFrame,
                 name : str, 
                 out_dir : str,
                 add_test_circuit : bool = True,
                 plot_array : bool = True):
    df.copy()
    df.to_excel(os.path.join(out_dir, name + ".xlsx"), index=False)
    df[['A', 'B', 'M', 'N']].to_csv(os.path.join(out_dir, name + ".csv"),
                                        index=False,
                                        header=False,
                                        sep=' ')
    if add_test_circuit:
        with open(os.path.join(out_dir, name + ".csv"), 'r+') as f:
            lines = f.readlines()
            lines.insert(0, "60 61 62 64\n")
            lines.insert(1, "62 64 60 61\n")
            f.seek(0)
            f.writelines(lines)
    if plot_array:
        for idx, row in df.iterrows():
            plot_path = os.path.join(out_dir, "plots", f"{name}_{idx:04d}.png")
            plot_gradient(row, initial_df, plot_path)




infile = "merged_electrode_table.xlsx"
out_dir = "array_outputs"
os.makedirs(out_dir, exist_ok=True)
os.makedirs(os.path.join(out_dir, "plots"), exist_ok=True)

df = pd.read_excel(infile)
df['Electrode number for survey'] = df['Electrode number for survey'].astype(int)
df = df.dropna(subset=['X_av', 'Y_av'])

lines, lines_reciprocal = generate_all_valid_abmn(df,
                                                  min_spacing=1,
                                                  max_spacing=5.0,
                                                  linearity_tolerance=0.1,
                                                  within_same_line=False)

print(f"✅ Exported {len(lines)} ABMN configs and reciprocals.")


export_array(df=lines,
             initial_df=df,
             name="lines", out_dir=out_dir)

# %%