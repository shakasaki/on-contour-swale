# loop over all folders and look for zip files inside and unzip them
import os
import zipfile
def unzip_files_in_directory(directory,
                             output_directory=None):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.zip'):
                zip_path = os.path.join(root, file)
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(output_directory)
                    print(f"Unzipped: {zip_path}")
                except zipfile.BadZipFile:
                    print(f"Bad zip file: {zip_path}")
                except Exception as e:
                    print(f"Error unzipping {zip_path}: {e}")

directory = '/home/alexis/Downloads/map electrodes/data'
output_directory = '/home/alexis/Downloads/map electrodes/fw_data'

if not os.path.exists(output_directory):
    os.makedirs(output_directory)
unzip_files_in_directory(directory, output_directory)
