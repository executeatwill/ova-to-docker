#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import logging
import shutil
import time
from tqdm import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(command, check=True, show_progress=False):
    try:
        if show_progress:
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            with tqdm(total=100, desc=command, bar_format='{l_bar}{bar}') as pbar:
                while process.poll() is None:
                    time.sleep(0.1)
                    pbar.update(1)
                pbar.update(100 - pbar.n)  # Ensure the bar reaches 100%
            stdout, stderr = process.communicate()
        else:
            result = subprocess.run(command, check=check, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = result.stdout, result.stderr
        return stdout, stderr
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.cmd}")
        logger.error(f"Error output: {e.stderr}")
        raise

def extract_ova(ova_file, temp_dir):
    logger.info(f"Extracting OVA file: {ova_file}")
    run_command(f"tar -xvf '{ova_file}' -C '{temp_dir}'", show_progress=True)
    vmdk_files = [f for f in os.listdir(temp_dir) if f.endswith('.vmdk')]
    if not vmdk_files:
        raise ValueError("No VMDK file found in the OVA archive")
    return os.path.join(temp_dir, vmdk_files[0])

def get_partition_info(raw_file):
    logger.info("Getting partition information")
    partition_info, _ = run_command(f"parted -ms '{raw_file}' unit B print")
    partitions = []
    for line in partition_info.splitlines():
        if line.startswith('BYT;'):
            continue
        if line.startswith('/dev/'):
            continue
        parts = line.split(':')
        if len(parts) >= 5:
            try:
                partitions.append({
                    'number': int(parts[0]),
                    'start': int(parts[1].rstrip('B')),
                    'end': int(parts[2].rstrip('B')),
                    'size': int(parts[3].rstrip('B')),
                    'filesystem': parts[4]
                })
            except ValueError as e:
                logger.warning(f"Skipping invalid partition entry: {line}")
                logger.warning(f"Error: {str(e)}")
    
    if not partitions:
        logger.error("No valid partitions found. Raw parted output:")
        logger.error(partition_info)
        raise ValueError("No valid partitions found in the RAW image")
    
    return partitions

def mount_raw_image(raw_file, partition):
    mount_point = "/mnt/container"
    logger.info(f"Attempting to mount RAW file to {mount_point}")
    run_command(f"sudo mkdir -p {mount_point}")

    mount_options = [
        f"loop,ro,offset={partition['start']}",
        f"loop,ro,offset={partition['start']},type={partition['filesystem']}",
        f"loop,ro,norecovery,offset={partition['start']}"
    ]

    for options in mount_options:
        mount_command = f"sudo mount -o {options} '{raw_file}' {mount_point}"
        logger.info(f"Trying mount command: {mount_command}")
        
        _, mount_error = run_command(mount_command, check=False)
        if not mount_error:
            logger.info("Mount successful")
            return mount_point
        else:
            logger.warning(f"Mount attempt failed: {mount_error}")

    raise Exception("All mount attempts failed")

def user_verify_filesystem(mount_point):
    logger.info("Displaying contents of the mounted filesystem:")
    contents, _ = run_command(f"sudo ls -la {mount_point}")
    print(contents)

    while True:
        user_input = input("Does this look like a correct Linux root filesystem? (y/n): ").lower()
        if user_input in ['y', 'yes']:
            return True
        elif user_input in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")

def convert_to_raw(input_file, output_dir, keep_files):
    temp_dir = os.path.join(output_dir, 'temp')
    mount_point = "/mnt/container"
    raw_file = ""
    
    try:
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)
        
        if input_file.lower().endswith('.ova'):
            vmdk_file = extract_ova(input_file, temp_dir)
        elif input_file.lower().endswith('.vmdk'):
            vmdk_file = input_file
        else:
            raise ValueError("Input file must be either .ova or .vmdk")

        raw_file = os.path.join(output_dir, os.path.splitext(os.path.basename(vmdk_file))[0] + ".raw")
        logger.info(f"Converting {vmdk_file} to RAW format")
        run_command(f"qemu-img convert -f vmdk '{vmdk_file}' -O raw '{raw_file}'", show_progress=True)

        partitions = get_partition_info(raw_file)
        if not partitions:
            raise ValueError("No partitions found in the RAW image")

        # Select the largest partition
        root_partition = max(partitions, key=lambda x: x['size'])
        logger.info(f"Selected partition: {root_partition}")

        mount_point = mount_raw_image(raw_file, root_partition)

        if not user_verify_filesystem(mount_point):
            logger.info("User indicated the filesystem is not correct. Stopping conversion.")
            return None, None

        tar_file = os.path.join(output_dir, os.path.splitext(os.path.basename(input_file))[0] + ".tar.gz")
        logger.info(f"Creating tar file: {tar_file}")
        run_command(f"sudo tar -C {mount_point} -czf '{tar_file}' .", show_progress=True)

        return raw_file, tar_file

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return None, None

    finally:
        logger.info("Cleaning up")
        try:
            run_command(f"sudo umount {mount_point}")
        except:
            pass

        if not keep_files:
            logger.info("Removing temporary files")
            if raw_file and os.path.exists(raw_file):
                os.remove(raw_file)
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            logger.info(f"Keeping extracted files in: {temp_dir}")

def main():
    parser = argparse.ArgumentParser(
        description="Convert OVA or VMDK to Docker container format",
        epilog="Example: %(prog)s --input alpine_linux.ova --output ./docker_output"
    )
    parser.add_argument("--input", required=True, help="Input OVA or VMDK file")
    parser.add_argument("--output", required=True, help="Output directory for Docker container files")
    parser.add_argument("--keepfiles", action="store_true", help="Keep extracted files in the temp folder")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    raw_file, tar_file = convert_to_raw(args.input, args.output, args.keepfiles)
    
    if raw_file and tar_file:
        print(f"Conversion successful.")
        print(f"RAW file: {raw_file}")
        print(f"Tar file: {tar_file}")
        print("\nTo create a Docker image, run:")
        print(f"docker import {tar_file} my-new-image:latest")
        print("\nTo run the new container:")
        print("docker run -it my-new-image:latest /bin/sh")
    else:
        print("Conversion failed or was stopped by the user.")
        sys.exit(1)

if __name__ == "__main__":
    main()
