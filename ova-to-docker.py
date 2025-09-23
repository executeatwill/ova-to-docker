#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import logging
import shutil
import time
import json
import re
from tqdm import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(command, check=True, show_progress=False):
    try:
        if show_progress:
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            with tqdm(total=100, desc=command[:50], bar_format='{l_bar}{bar}') as pbar:
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
    disk_files = [f for f in os.listdir(temp_dir) if f.endswith(('.vmdk', '.vdi'))]
    if not disk_files:
        raise ValueError("No VMDK or VDI file found in the OVA archive")
    return os.path.join(temp_dir, disk_files[0])

def get_partition_info(raw_file):
    logger.info("Getting partition information")
    partition_info, _ = run_command(f"parted -ms '{raw_file}' unit B print")
    partitions = []
    for line in partition_info.splitlines():
        if line.startswith('BYT;'):
            continue
        # Skip the disk information line that contains the full path
        if ':' in line and (line.startswith('/') or '/' in line.split(':')[0]):
            parts = line.split(':')
            # Check if this is the disk info line (contains path and size info)
            if len(parts) >= 6 and 'B:' in line:
                continue
        
        parts = line.split(':')
        if len(parts) >= 5:
            try:
                # Only process if first part looks like a partition number
                partition_num = parts[0].strip()
                if partition_num.isdigit():
                    partitions.append({
                        'number': int(partition_num),
                        'start': int(parts[1].rstrip('B')),
                        'end': int(parts[2].rstrip('B')),
                        'size': int(parts[3].rstrip('B')),
                        'filesystem': parts[4]
                    })
            except (ValueError, IndexError) as e:
                logger.warning(f"Skipping invalid partition entry: {line}")
                logger.warning(f"Error: {str(e)}")
    
    if not partitions:
        logger.error("No valid partitions found. Raw parted output:")
        logger.error(partition_info)
        raise ValueError("No valid partitions found in the RAW image")
    
    return partitions

def setup_loop_device(raw_file, offset):
    """Set up a loop device for the partition at the given offset"""
    logger.info(f"Setting up loop device for offset {offset}")
    
    # Find an available loop device
    stdout, _ = run_command("sudo losetup -f")
    loop_device = stdout.strip()
    
    # Set up the loop device with offset
    run_command(f"sudo losetup -o {offset} {loop_device} '{raw_file}'")
    
    return loop_device

def cleanup_loop_device(loop_device):
    """Clean up a loop device"""
    try:
        run_command(f"sudo losetup -d {loop_device}", check=False)
    except:
        pass

def detect_lvm_and_get_volumes(loop_device):
    """Detect if the loop device contains LVM and get logical volumes"""
    try:
        # Check if it's an LVM physical volume
        stdout, stderr = run_command(f"sudo pvs {loop_device}", check=False)
        if stderr or "No matching physical volume" in stdout:
            return None, []
        
        logger.info(f"LVM physical volume detected on {loop_device}")
        
        # Get volume group name
        stdout, _ = run_command(f"sudo pvs --noheadings -o vg_name {loop_device}")
        vg_name = stdout.strip()
        
        if not vg_name or vg_name == "":
            logger.warning("No volume group found")
            return None, []
        
        logger.info(f"Found volume group: {vg_name}")
        
        # Activate the volume group
        run_command(f"sudo vgchange -ay {vg_name}")
        
        # Get logical volumes
        stdout, _ = run_command(f"sudo lvs --noheadings -o lv_path {vg_name}")
        lv_paths = [lv.strip() for lv in stdout.strip().split('\n') if lv.strip()]
        
        logger.info(f"Found logical volumes: {lv_paths}")
        
        return vg_name, lv_paths
        
    except Exception as e:
        logger.warning(f"LVM detection failed: {str(e)}")
        return None, []

def cleanup_lvm(vg_name):
    """Clean up LVM volume group"""
    if vg_name:
        try:
            run_command(f"sudo vgchange -an {vg_name}", check=False)
            logger.info(f"Deactivated volume group: {vg_name}")
        except:
            pass

def detect_filesystem_type(device_path):
    """Detect the filesystem type of a device"""
    try:
        stdout, _ = run_command(f"sudo blkid -o value -s TYPE {device_path}", check=False)
        fs_type = stdout.strip()
        logger.info(f"Detected filesystem type: {fs_type} for {device_path}")
        return fs_type
    except:
        return None

def detect_os_type(mount_point):
    """Detect if the mounted filesystem is Windows or Linux"""
    try:
        # Check for Windows indicators
        ls_stdout, _ = run_command(f"sudo ls -la {mount_point}", check=False)
        
        windows_indicators = ['Windows', 'Program Files', 'Program Files (x86)', 'ProgramData', 'Users']
        linux_indicators = ['etc', 'usr', 'var', 'bin', 'sbin', 'root', 'home']
        
        windows_score = sum(1 for indicator in windows_indicators if indicator in ls_stdout)
        linux_score = sum(1 for indicator in linux_indicators if indicator in ls_stdout)
        
        logger.info(f"OS Detection - Windows score: {windows_score}, Linux score: {linux_score}")
        
        if windows_score > linux_score:
            return 'windows'
        elif linux_score > 0:
            return 'linux'
        else:
            return 'unknown'
            
    except Exception as e:
        logger.warning(f"Could not detect OS type: {str(e)}")
        return 'unknown'

def try_mount_with_filesystem(device_path, mount_point, fs_type=None):
    """Try to mount a device with various filesystem options"""
    mount_attempts = []
    
    if fs_type:
        if fs_type in ['ntfs', 'fuseblk']:
            # Windows NTFS filesystem
            mount_attempts = [
                f"sudo mount -t ntfs-3g {device_path} {mount_point}",
                f"sudo mount -t ntfs {device_path} {mount_point}",
                f"sudo mount -o ro {device_path} {mount_point}"
            ]
        elif fs_type in ['ext2', 'ext3', 'ext4']:
            # Linux ext filesystems
            mount_attempts = [
                f"sudo mount -t {fs_type} {device_path} {mount_point}",
                f"sudo mount -t {fs_type} -o norecovery {device_path} {mount_point}",
                f"sudo mount -o ro {device_path} {mount_point}"
            ]
        elif fs_type in ['xfs', 'btrfs', 'reiserfs']:
            # Other Linux filesystems
            mount_attempts = [
                f"sudo mount -t {fs_type} {device_path} {mount_point}",
                f"sudo mount -o ro {device_path} {mount_point}"
            ]
    
    # Generic attempts if no specific filesystem or as fallback
    mount_attempts.extend([
        f"sudo mount {device_path} {mount_point}",
        f"sudo mount -o ro {device_path} {mount_point}"
    ])
    
    for mount_cmd in mount_attempts:
        logger.info(f"Trying mount command: {mount_cmd}")
        try:
            _, mount_error = run_command(mount_cmd, check=False)
            if not mount_error:
                # Verify mount was successful
                try:
                    run_command(f"sudo test -d {mount_point}")
                    logger.info("Mount successful")
                    return True
                except:
                    logger.warning("Mount point not accessible after mount")
                    continue
            else:
                logger.warning(f"Mount attempt failed: {mount_error}")
        except Exception as e:
            logger.warning(f"Mount attempt error: {str(e)}")
            continue
    
    return False

def find_root_filesystem(lv_paths):
    """Find the logical volume that contains the root filesystem (Linux or Windows)"""
    root_candidates = []
    
    for lv_path in lv_paths:
        try:
            # Get filesystem info
            fs_type = detect_filesystem_type(lv_path)
            logger.info(f"Filesystem info for {lv_path}: {fs_type}")
            
            # Check if it contains common root filesystem indicators
            temp_mount = f"/tmp/lv_check_{os.path.basename(lv_path)}"
            try:
                run_command(f"sudo mkdir -p {temp_mount}", check=False)
                
                # Try to mount and check contents
                if try_mount_with_filesystem(lv_path, temp_mount, fs_type):
                    # Check for root filesystem indicators
                    ls_stdout, _ = run_command(f"sudo ls {temp_mount}", check=False)
                    
                    # Check for both Windows and Linux indicators
                    windows_indicators = ['Windows', 'Program Files', 'Program Files (x86)', 'ProgramData', 'Users']
                    linux_indicators = ['etc', 'usr', 'var', 'bin', 'sbin']
                    
                    windows_score = sum(1 for indicator in windows_indicators if indicator in ls_stdout)
                    linux_score = sum(1 for indicator in linux_indicators if indicator in ls_stdout)
                    total_score = windows_score + linux_score
                    
                    os_type = 'windows' if windows_score > linux_score else 'linux' if linux_score > 0 else 'unknown'
                    
                    root_candidates.append({
                        'path': lv_path,
                        'mount_point': temp_mount,
                        'score': total_score,
                        'os_type': os_type,
                        'fs_type': fs_type,
                        'contents': ls_stdout
                    })
                    
                    logger.info(f"LV {lv_path} has score {total_score} ({os_type})")
                    # Don't unmount yet, we'll use the best candidate
                else:
                    run_command(f"sudo rmdir {temp_mount}", check=False)
                    
            except Exception as e:
                logger.warning(f"Could not check LV {lv_path}: {str(e)}")
                run_command(f"sudo rmdir {temp_mount}", check=False)
                
        except Exception as e:
            logger.warning(f"Could not get info for LV {lv_path}: {str(e)}")
    
    # Clean up non-selected mounts and find the best candidate
    if root_candidates:
        # Sort by score (number of root indicators found)
        best_candidate = max(root_candidates, key=lambda x: x['score'])
        
        # Clean up other mounts
        for candidate in root_candidates:
            if candidate != best_candidate:
                try:
                    run_command(f"sudo umount {candidate['mount_point']}", check=False)
                    run_command(f"sudo rmdir {candidate['mount_point']}", check=False)
                except:
                    pass
        
        logger.info(f"Selected root filesystem: {best_candidate['path']} (score: {best_candidate['score']}, OS: {best_candidate['os_type']})")
        return best_candidate['path'], best_candidate['mount_point'], best_candidate['os_type'], best_candidate['fs_type']
    
    return None, None, None, None

def mount_partition_or_lvm(raw_file, partition):
    """Mount a partition, handling both regular filesystems and LVM, supporting Windows and Linux"""
    mount_point = "/mnt/container"
    loop_device = None
    vg_name = None
    lv_mount_point = None
    os_type = 'unknown'
    fs_type = None
    
    try:
        # First ensure mount point is clean
        try:
            run_command(f"sudo umount -f {mount_point}", check=False)
        except:
            pass

        # Recreate mount point with proper permissions
        run_command("sudo rm -rf /mnt/container")
        run_command("sudo mkdir -p /mnt/container")
        run_command("sudo chmod 755 /mnt/container")

        # Set up loop device for the partition
        loop_device = setup_loop_device(raw_file, partition['start'])
        
        # Detect filesystem type
        fs_type = detect_filesystem_type(loop_device)
        
        # Check if this is an LVM partition
        vg_name, lv_paths = detect_lvm_and_get_volumes(loop_device)
        
        if vg_name and lv_paths:
            # Handle LVM
            logger.info("Handling LVM partition")
            
            # Find the root filesystem among logical volumes
            root_lv, lv_mount_point, os_type, fs_type = find_root_filesystem(lv_paths)
            
            if root_lv and lv_mount_point:
                # Move the LV mount to our standard mount point
                run_command(f"sudo umount {lv_mount_point}")
                run_command(f"sudo rmdir {lv_mount_point}")
                
                if try_mount_with_filesystem(root_lv, mount_point, fs_type):
                    # Detect OS type after mounting
                    if os_type == 'unknown':
                        os_type = detect_os_type(mount_point)
                    logger.info(f"Successfully mounted LVM volume {root_lv} to {mount_point} (OS: {os_type})")
                    return mount_point, loop_device, vg_name, os_type, fs_type
                else:
                    raise Exception(f"Failed to mount LVM volume {root_lv}")
            else:
                raise Exception("No suitable root filesystem found in LVM volumes")
        
        else:
            # Handle regular filesystem
            logger.info(f"Handling regular filesystem partition (type: {fs_type})")
            
            if try_mount_with_filesystem(loop_device, mount_point, fs_type):
                # Detect OS type after mounting
                os_type = detect_os_type(mount_point)
                logger.info(f"Successfully mounted partition to {mount_point} (OS: {os_type})")
                return mount_point, loop_device, None, os_type, fs_type
            else:
                # Fallback: try with offset-based mounting for non-LVM partitions
                logger.info("Trying offset-based mounting as fallback")
                mount_options = [
                    f"loop,offset={partition['start']},type={fs_type}" if fs_type else f"loop,offset={partition['start']}",
                    f"loop,offset={partition['start']}",
                    f"loop,ro,offset={partition['start']}"
                ]

                for options in mount_options:
                    mount_command = f"sudo mount -o {options} '{raw_file}' {mount_point}"
                    logger.info(f"Trying mount command: {mount_command}")
                    
                    try:
                        _, mount_error = run_command(mount_command, check=False)
                        if not mount_error:
                            # Verify mount was successful
                            try:
                                run_command(f"sudo test -d {mount_point}")
                                os_type = detect_os_type(mount_point)
                                logger.info(f"Offset mount successful (OS: {os_type})")
                                return mount_point, loop_device, None, os_type, fs_type
                            except:
                                logger.warning("Mount point not accessible after mount")
                                continue
                        else:
                            logger.warning(f"Mount attempt failed: {mount_error}")
                    except Exception as e:
                        logger.warning(f"Mount attempt error: {str(e)}")
                        continue

                raise Exception("All mount attempts failed")
            
    except Exception as e:
        # Clean up on failure
        if lv_mount_point:
            try:
                run_command(f"sudo umount {lv_mount_point}", check=False)
                run_command(f"sudo rmdir {lv_mount_point}", check=False)
            except:
                pass
        
        if vg_name:
            cleanup_lvm(vg_name)
        
        if loop_device:
            cleanup_loop_device(loop_device)
        
        raise e

def cleanup_mount(mount_point, loop_device=None, vg_name=None):
    """Helper function to safely clean up mounts and LVM"""
    try:
        # Check if the mount point is actually mounted
        _, stderr = run_command("mountpoint -q " + mount_point, check=False)
        if not stderr:
            # Try gentle unmount first
            run_command(f"sudo umount {mount_point}", check=False)
            time.sleep(1)
            
            # If still mounted, force unmount
            _, stderr = run_command("mountpoint -q " + mount_point, check=False)
            if not stderr:
                run_command(f"sudo umount -f {mount_point}", check=False)
    except:
        pass
    
    # Clean up LVM
    if vg_name:
        cleanup_lvm(vg_name)
    
    # Clean up loop device
    if loop_device:
        cleanup_loop_device(loop_device)
    
    # Clean up mount point
    try:
        run_command(f"sudo rm -rf {mount_point}", check=False)
    except:
        pass

def user_verify_filesystem(mount_point, os_type='unknown', fs_type=None):
    logger.info("Displaying contents of the mounted filesystem:")
    contents, _ = run_command(f"sudo ls -la {mount_point}")
    print(contents)
    
    if os_type == 'windows':
        print(f"\n*** DETECTED: Windows filesystem (type: {fs_type}) ***")
        print("Note: Windows containers require special handling and may not work as expected in Docker.")
        print("Consider using Windows containers or converting the application to run on Linux.")
    elif os_type == 'linux':
        print(f"\n*** DETECTED: Linux filesystem (type: {fs_type}) ***")
        print("This appears to be a Linux root filesystem suitable for containerization.")
    else:
        print(f"\n*** DETECTED: Unknown filesystem (type: {fs_type}) ***")
        print("Unable to determine the operating system type.")

    while True:
        if os_type == 'windows':
            user_input = input("This appears to be a Windows filesystem. Continue anyway? (y/n): ").lower()
        else:
            user_input = input("Does this look like a correct filesystem for containerization? (y/n): ").lower()
            
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
    loop_device = None
    vg_name = None
    
    try:
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Support OVA, VMDK, and VDI formats
        if input_file.lower().endswith('.ova'):
            disk_file = extract_ova(input_file, temp_dir)
        elif input_file.lower().endswith(('.vmdk', '.vdi')):
            disk_file = input_file
        else:
            raise ValueError("Input file must be .ova, .vmdk, or .vdi format")

        # Determine input format for qemu-img
        input_format = 'vmdk' if disk_file.lower().endswith('.vmdk') else 'vdi'
        
        raw_file = os.path.join(output_dir, os.path.splitext(os.path.basename(disk_file))[0] + ".raw")
        logger.info(f"Converting {disk_file} (format: {input_format}) to RAW format")
        run_command(f"qemu-img convert -f {input_format} '{disk_file}' -O raw '{raw_file}'", show_progress=True)

        partitions = get_partition_info(raw_file)
        if not partitions:
            raise ValueError("No partitions found in the RAW image")

        # Select the largest partition
        root_partition = max(partitions, key=lambda x: x['size'])
        logger.info(f"Selected partition: {root_partition}")

        mount_point, loop_device, vg_name, os_type, fs_type = mount_partition_or_lvm(raw_file, root_partition)

        if not user_verify_filesystem(mount_point, os_type, fs_type):
            logger.info("User indicated the filesystem is not correct. Stopping conversion.")
            return None, None

        tar_file = os.path.join(output_dir, os.path.splitext(os.path.basename(input_file))[0] + ".tar.gz")
        logger.info(f"Creating tar file: {tar_file}")
        
        # Add exclusions for Windows-specific files that don't work well in containers
        exclusions = ""
        if os_type == 'windows':
            exclusions = "--exclude='hiberfil.sys' --exclude='pagefile.sys' --exclude='swapfile.sys' --exclude='System Volume Information'"
            logger.info("Excluding Windows system files from tar archive")
        
        run_command(f"sudo tar -C {mount_point} {exclusions} -czf '{tar_file}' .", show_progress=True)

        return raw_file, tar_file

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return None, None

    finally:
        logger.info("Cleaning up")
        cleanup_mount(mount_point, loop_device, vg_name)

        if not keep_files:
            logger.info("Removing temporary files")
            if raw_file and os.path.exists(raw_file):
                os.remove(raw_file)
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            logger.info(f"Keeping extracted files in: {temp_dir}")

def main():
    parser = argparse.ArgumentParser(
        description="Convert OVA, VMDK, or VDI to Docker container format (supports LVM, Windows & Linux)",
        epilog="Example: %(prog)s --input alpine_linux.ova --output ./docker_output"
    )
    parser.add_argument("--input", required=True, help="Input OVA, VMDK, or VDI file")
    parser.add_argument("--output", required=True, help="Output directory for Docker container files")
    parser.add_argument("--keepfiles", action="store_true", help="Keep extracted files in the temp folder")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Check for required tools
    required_tools = ['qemu-img', 'parted', 'tar']
    missing_tools = []
    
    for tool in required_tools:
        try:
            run_command(f"which {tool}", check=True)
        except:
            missing_tools.append(tool)
    
    if missing_tools:
        logger.error(f"Missing required tools: {', '.join(missing_tools)}")
        logger.error("Please install the missing tools and try again.")
        sys.exit(1)

    # Check for optional tools and warn if missing
    optional_tools = {
        'ntfs-3g': 'Windows NTFS filesystem support',
        'pvs': 'LVM support (lvm2 package)',
        'losetup': 'Loop device support (util-linux package)'
    }
    
    for tool, description in optional_tools.items():
        try:
            run_command(f"which {tool}", check=True)
        except:
            logger.warning(f"Optional tool '{tool}' not found - {description} may not work")

    raw_file, tar_file = convert_to_raw(args.input, args.output, args.keepfiles)
    
    if raw_file and tar_file:
        print(f"Conversion successful.")
        print(f"RAW file: {raw_file}")
        print(f"Tar file: {tar_file}")
        print("\nTo create a Docker image, run:")
        print(f"docker import {tar_file} my-new-image:latest")
        print("\nTo run the new container:")
        print("docker run -it my-new-image:latest /bin/sh")
        print("\nNote: Windows containers may require additional configuration and")
        print("may not work properly in standard Docker Linux containers.")
    else:
        print("Conversion failed or was stopped by the user.")
        sys.exit(1)

if __name__ == "__main__":
    main()
