import itertools
import csv
import os

# --- Configuration ---
num_electrodes = 60
output_filename = 'electrode_combinations.csv'
# --- End Configuration ---

# Generate electrode numbers (1 to num_electrodes)
electrodes = list(range(1, num_electrodes + 1))

# Counter for generated combinations
combinations_count = 0

print(f"Generating unique electrode combinations for {num_electrodes} electrodes...")
print(f"Output file: {output_filename}")

try:
    # Open the CSV file for writing
    with open(output_filename, 'w', newline='') as csvfile:
        # Create a CSV writer object
        writer = csv.writer(csvfile)

        # Write the header row
        writer.writerow(['A', 'B', 'M', 'N'])

        # Iterate through all unique combinations of 4 distinct electrodes
        # itertools.combinations ensures each set of 4 is considered only once
        for combo in itertools.combinations(electrodes, 4):
            # Sort the combination to easily identify the electrodes
            # Ensures e1 < e2 < e3 < e4
            e1, e2, e3, e4 = sorted(combo)

            # Generate the 3 unique measurement configurations for this set.
            # We enforce A < B and M < N by selection.
            # We enforce omitting reciprocals by ensuring A < M.

            # Configuration 1:
            # Pairs: {e1, e2} and {e3, e4}
            # Assign A, B = e1, e2 and M, N = e3, e4 (since e1 < e3)
            writer.writerow([e1, e2, e3, e4])
            combinations_count += 1

            # Configuration 2:
            # Pairs: {e1, e3} and {e2, e4}
            # Assign A, B = e1, e3 and M, N = e2, e4 (since e1 < e2)
            writer.writerow([e1, e3, e2, e4])
            combinations_count += 1

            # Configuration 3:
            # Pairs: {e1, e4} and {e2, e3}
            # Assign A, B = e1, e4 and M, N = e2, e3 (since e1 < e2)
            writer.writerow([e1, e4, e2, e3])
            combinations_count += 1

            # Optional: Print progress periodically for large numbers
            # if combinations_count % 100000 == 0:
            #    print(f"Generated {combinations_count} combinations...")

    print("-" * 30)
    print(f"Successfully generated {combinations_count} unique combinations.")
    print(f"Data saved to: {os.path.abspath(output_filename)}")
    # Expected count: 3 * C(60, 4) = 3 * 487635 = 1462905
    print(f"Expected combinations: {3 * len(list(itertools.combinations(electrodes, 4)))}")


except Exception as e:
    print(f"An error occurred: {e}")


