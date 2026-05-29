import csv
import os
import math # Import math for potential future use, though not strictly needed here
import matplotlib.pyplot as plt
import pandas as pd

# --- Configuration ---
num_lines = 6
electrodes_per_line = 10
electrode_spacing = 1.0  # meters (along the line)
line_spacing = 1.0       # meters (between lines)
start_z = 0.0            # Depth/height coordinate
output_filename = 'electrode_geometry.csv'
# --- End Configuration ---

electrode_coords = {} # Dictionary to store {electrode_number: (x, y, z)}

print("Generating hypothetical electrode geometry...")
print(f"Parameters: {num_lines} lines, {electrodes_per_line} electrodes/line")
print(f"Electrode spacing: {electrode_spacing}m, Line spacing: {line_spacing}m")

electrode_number = 1
for line_idx in range(num_lines): # 0 to 5
    x_coord = line_idx * line_spacing
    for elec_idx in range(electrodes_per_line): # 0 to 9
        y_coord = elec_idx * electrode_spacing
        z_coord = start_z
        electrode_coords[electrode_number] = (x_coord, y_coord, z_coord)
        electrode_number += 1

# --- Write to CSV ---

try:
    with open(output_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        # Write header
        writer.writerow(['Electrode', 'X', 'Y', 'Z'])
        # Write data
        for num, coords in sorted(electrode_coords.items()): # Sort by electrode number
            writer.writerow([num, coords[0], coords[1], coords[2]])

    print("-" * 30)
    print(f"Successfully generated geometry for {len(electrode_coords)} electrodes.")
    print(f"Geometry data saved to: {os.path.abspath(output_filename)}")

except Exception as e:
    print(f"An error occurred while writing the CSV: {e}")

# convert dictionary to DataFrame for easier manipulation
electrode_df = pd.DataFrame.from_dict(electrode_coords, 
                                      orient='index', 
                                      columns=['X', 'Y', 'Z'])
plt.scatter(electrode_df['X'], electrode_df['Y'])
plt.show()

# Optional: Print first few coordinates as a check
# print("\nSample Coordinates:")
# for i in range(1, min(6, len(electrode_coords) + 1)):
#     print(f"Electrode {i}: {electrode_coords[i]}")
# if len(electrode_coords) > 10:
#     print(f"Electrode 11: {electrode_coords[11]}")


