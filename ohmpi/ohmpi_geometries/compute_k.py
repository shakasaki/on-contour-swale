import itertools
import csv
import os
import math
import sys # For handling potential errors

# --- Configuration ---
num_lines = 6
electrodes_per_line = 10
electrode_spacing = 1.0  # meters (along the line)
line_spacing = 1.0       # meters (between lines)
start_z = 0.0            # Depth/height coordinate
output_filename = 'combinations_with_K.csv'
# Set to True to load geometry from 'electrode_geometry.csv'
# Set to False to generate geometry internally (faster for this script)
load_geometry_from_file = True
geometry_input_filename = 'electrode_geometry.csv'

# --- End Configuration ---

# --- Electrode Geometry Generation (or Loading) ---
electrode_coords = {} # Dictionary to store {electrode_number: (x, y, z)}
num_electrodes = num_lines * electrodes_per_line

if load_geometry_from_file:
    print(f"Loading electrode geometry from {geometry_input_filename}...")
    try:
        with open(geometry_input_filename, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader) # Skip header
            for row in reader:
                if len(row) >= 4:
                    try:
                        num = int(row[0])
                        x = float(row[1])
                        y = float(row[2])
                        z = float(row[3])
                        electrode_coords[num] = (x, y, z)
                    except ValueError:
                        print(f"Warning: Skipping invalid row in geometry file: {row}")
        if len(electrode_coords) != num_electrodes:
             print(f"Warning: Loaded {len(electrode_coords)} coordinates, but expected {num_electrodes}.")
             print("Ensure the geometry file matches the configuration.")
        print(f"Loaded coordinates for {len(electrode_coords)} electrodes.")
    except FileNotFoundError:
        print(f"Error: Geometry file '{geometry_input_filename}' not found.")
        print("Please generate the geometry file first or set load_geometry_from_file=False.")
        sys.exit(1) # Exit if file not found and loading is requested
    except Exception as e:
        print(f"An error occurred while loading the geometry file: {e}")
        sys.exit(1)
else:
    print("Generating electrode geometry internally...")
    electrode_number = 1
    for line_idx in range(num_lines): # 0 to 5
        x_coord = line_idx * line_spacing
        for elec_idx in range(electrodes_per_line): # 0 to 9
            y_coord = elec_idx * electrode_spacing
            z_coord = start_z
            electrode_coords[electrode_number] = (x_coord, y_coord, z_coord)
            electrode_number += 1
    print(f"Generated coordinates for {len(electrode_coords)} electrodes.")

# --- Helper Functions ---

def calculate_distance(p1_coords, p2_coords):
    """Calculates the Euclidean distance between two 3D points."""
    return math.sqrt(
        (p1_coords[0] - p2_coords[0])**2 +
        (p1_coords[1] - p2_coords[1])**2 +
        (p1_coords[2] - p2_coords[2])**2
    )

def calculate_geometric_factor(coords_a, coords_b, coords_m, coords_n):
    """Calculates the 3D geometric factor K."""
    r_am = calculate_distance(coords_a, coords_m)
    r_bm = calculate_distance(coords_b, coords_m)
    r_an = calculate_distance(coords_a, coords_n)
    r_bn = calculate_distance(coords_b, coords_n)

    # Prevent division by zero if electrodes coincide (shouldn't happen with distinct A,B,M,N)
    # Also handle the case where the denominator terms cancel out perfectly.
    term1 = 1.0 / r_am if r_am > 1e-9 else float('inf')
    term2 = 1.0 / r_bm if r_bm > 1e-9 else float('inf')
    term3 = 1.0 / r_an if r_an > 1e-9 else float('inf')
    term4 = 1.0 / r_bn if r_bn > 1e-9 else float('inf')

    denominator = (term1 - term2) - (term3 - term4)

    if abs(denominator) < 1e-9: # Check if denominator is close to zero
        # This configuration is problematic (e.g., symmetrical setup where VM=VN)
        # Return infinity or NaN, or handle as needed. Let's return 'inf'.
        return float('inf')
    elif any(t == float('inf') for t in [term1, term2, term3, term4]):
         # If any distance was zero, resulting term is inf, K should be 0
         return 0.0
    else:
        k_factor = 2.0 * math.pi / denominator
        return k_factor

# --- Main Combination Generation and Calculation ---

electrodes = list(range(1, num_electrodes + 1))
combinations_count = 0
skipped_count = 0
total_combinations_to_process = 3 * math.comb(num_electrodes, 4) # Calculate expected total

print(f"\nGenerating combinations and calculating K factors for {num_electrodes} electrodes...")
print(f"Output file: {output_filename}")
print(f"Expected total combinations: {total_combinations_to_process}")

try:
    # Open the output CSV file for writing
    with open(output_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['A', 'B', 'M', 'N', 'K_Factor']) # Write header

        # Iterate through all unique combinations of 4 distinct electrodes
        for combo in itertools.combinations(electrodes, 4):
            e1, e2, e3, e4 = sorted(combo) # Ensures e1 < e2 < e3 < e4

            # Get coordinates for the chosen electrodes
            coords1 = electrode_coords[e1]
            coords2 = electrode_coords[e2]
            coords3 = electrode_coords[e3]
            coords4 = electrode_coords[e4]

            # --- Generate and process the 3 unique configurations ---

            # Config 1: A=e1, B=e2, M=e3, N=e4
            k1 = calculate_geometric_factor(coords1, coords2, coords3, coords4)
            if k1 != float('inf'):
                writer.writerow([e1, e2, e3, e4, k1])
                combinations_count += 1
            else:
                skipped_count += 1

            # Config 2: A=e1, B=e3, M=e2, N=e4
            k2 = calculate_geometric_factor(coords1, coords3, coords2, coords4)
            if k2 != float('inf'):
                writer.writerow([e1, e3, e2, e4, k2])
                combinations_count += 1
            else:
                skipped_count += 1

            # Config 3: A=e1, B=e4, M=e2, N=e3
            k3 = calculate_geometric_factor(coords1, coords4, coords2, coords3)
            if k3 != float('inf'):
                 writer.writerow([e1, e4, e2, e3, k3])
                 combinations_count += 1
            else:
                 skipped_count += 1

            # --- Progress Indicator ---
            processed_count = combinations_count + skipped_count
            if processed_count % 10000 == 0 and processed_count > 0:
                 progress = (processed_count / total_combinations_to_process) * 100
                 print(f"Processed {processed_count}/{total_combinations_to_process} combinations ({progress:.2f}%)...", end='\r')


    print("\n" + "-" * 30) # Newline after progress indicator
    print(f"Successfully processed combinations.")
    print(f"Written {combinations_count} valid combinations with K factors.")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} combinations due to near-zero denominator in K calculation.")
    print(f"Data saved to: {os.path.abspath(output_filename)}")

except KeyError as e:
     print(f"\nError: Electrode number {e} not found in coordinates dictionary.")
     print("This might happen if loading from a file that doesn't match the expected number of electrodes.")
except Exception as e:
    print(f"\nAn error occurred during processing: {e}")

