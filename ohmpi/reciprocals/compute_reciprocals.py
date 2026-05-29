import sys
from pathlib import Path

def shift_abmn_with_check(filename):
    original = Path(filename)
    reciprocal_file = original.with_name(f"reciprocal_{original.name}")
    forward_file = original.with_name(f"forward_{original.name}")

    with open(original, 'r') as infile:
        lines = [line.strip() for line in infile if line.strip()]
    
    original_set = set()
    forward_lines = []
    reciprocal_lines = []
    duplicate_count = 0

    # Collect all original entries
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            print(f"Skipping invalid line: {line}")
            continue
        original_set.add(tuple(parts))

    for entry in original_set:
        A, B, M, N = entry
        recip = (M, N, A, B)

        if recip in original_set:
            duplicate_count += 1
        else:
            reciprocal_lines.append(f"{M} {N} {A} {B}")
            forward_lines.append(f"{A} {B} {M} {N}")

    # Write reciprocal and forward files
    # if empty do not create the file
    if not reciprocal_lines:
        print("No new reciprocal entries generated. Skipping reciprocal file creation.")
        reciprocal_file = None
    else:
        with open(reciprocal_file, 'w') as f:
            f.write("\n".join(reciprocal_lines) + "\n")
    if not forward_lines:
        print("No forward entries to retain. Skipping forward file creation.")
        forward_file = None
    else:
        with open(forward_file, 'w') as f:
            f.write("\n".join(forward_lines) + "\n")

    print(f"✅ Reciprocal file saved as: {reciprocal_file}")
    print(f"✅ Forward file (excluding known reciprocals) saved as: {forward_file}")
    print(f"\n🔁 Summary:")
    print(f"  Total unique entries in original file: {len(original_set)}")
    print(f"  Entries that already have reciprocals in original file: {duplicate_count}")
    print(f"  New reciprocal entries generated: {len(reciprocal_lines)}")
    print(f"  Forward entries retained: {len(forward_lines)}")


for line in ['A', 'B', 'C', 'D', 'E']:
    print(f"Processing dipdip_line_{line}.csv")
    shift_abmn_with_check(f'sequences/dipdip_line_{line}.csv')

for line in ['A', 'B', 'C', 'D', 'E']:
    print(f"Processing wenner_line_{line}.csv")
    shift_abmn_with_check(f'sequences/wenner_line_{line}.csv')

shift_abmn_with_check(f'sequences/gradient_array.csv')
