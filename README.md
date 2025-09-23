# OVA to Docker Converter

This tool converts OVA (Open Virtual Appliance), VMDK (Virtual Machine Disk), or VDI (VirtualBox Disk Image) files to Docker container format. It supports both Linux and Windows guest operating systems and handles advanced storage configurations including LVM (Logical Volume Manager).

Inspired by the work of [Andy Green, Ph.D.](https://andygreen.phd/2022/01/26/converting-vm-images-to-docker-containers/) and created by executeatwill.

## Features

- **Multiple Format Support**: Converts OVA, VMDK, and VDI files to Docker container format
- **Cross-Platform Guest Support**: Works with both Linux and Windows guest operating systems
- **Advanced Storage Support**: Handles LVM partitions and various filesystem types (ext2/3/4, NTFS, XFS, BTRFS)
- **Intelligent Detection**: Automatically detects OS type and filesystem format
- **Interactive Verification**: User-friendly filesystem verification with OS-specific prompts
- **Progress Tracking**: Progress bars for long-running operations
- **Flexible Options**: Keep temporary files for debugging, verbose logging
- **Smart Cleanup**: Proper cleanup of LVM volume groups and loop devices

## Requirements

### Required Tools
- Python 3.6+
- qemu-utils (for qemu-img)
- parted (for partition analysis)
- tar (for archive creation)
- util-linux (for losetup - loop device support)

### Optional Tools (for enhanced functionality)
- **lvm2** (for LVM partition support)
- **ntfs-3g** (for Windows NTFS filesystem support)

### Runtime Requirements
- Docker (for running the converted image)
- sudo privileges (required for mounting filesystems)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/executeatwill/ova-to-docker.git
   cd ova-to-docker
   ```

2. Install required system packages:

   **Ubuntu/Debian:**
   ```bash
   sudo apt-get update
   sudo apt-get install qemu-utils parted tar util-linux
   ```
   
   **For full functionality (including Windows and LVM support):**
   ```bash
   sudo apt-get install qemu-utils parted tar util-linux lvm2 ntfs-3g
   ```

   **RHEL/CentOS/Fedora:**
   ```bash
   sudo yum install qemu-img parted tar util-linux
   # For full functionality:
   sudo yum install qemu-img parted tar util-linux lvm2 ntfs-3g
   ```

3. No Python packages are required - the script uses only standard library modules.

## Usage

Run the script with sudo privileges:

```bash
sudo python3 ova-to-docker.py --input <input_file> --output <output_directory> [options]
```

### Options

- `--input`: Path to the input OVA, VMDK, or VDI file (required)
- `--output`: Path to the output directory for Docker container files (required)
- `--keepfiles`: Keep extracted files in the temp folder (optional)
- `-v, --verbose`: Enable verbose output (optional)

### Examples

**Basic usage with OVA file:**
```bash
sudo python3 ova-to-docker.py --input alpine_linux.ova --output ./docker_output
```

**Convert VDI file with verbose output:**
```bash
sudo python3 ova-to-docker.py --input windows_vm.vdi --output ./docker_output --verbose
```

**Keep temporary files for debugging:**
```bash
sudo python3 ova-to-docker.py --input complex_vm.vmdk --output ./docker_output --keepfiles
```

## Sample Output

### Linux Guest (Standard Partition)
```
$ sudo python3 ova-to-docker.py --input alpine_linux.ova --output ./docker_output
2025-09-22 17:15:23,173 - INFO - Extracting OVA file: alpine_linux.ova
tar -xvf 'alpine_linux.ova' -C './docker_output/temp': 100%|████████████████████████████████████████████████|
2025-09-22 17:15:25,190 - INFO - Converting ./docker_output/temp/alpine_linux-disk001.vmdk to RAW format
qemu-img convert -f vmdk './docker_output/temp/alpine_linux-disk001.vmdk' -O raw './docker_output/alpine_linux-disk001.raw': 100%|████████████████████████████████████████████████|
2025-09-22 17:15:26,995 - INFO - Getting partition information
2025-09-22 17:15:27,250 - INFO - Selected partition: {'number': 3, 'start': 584056832, 'end': 1073741823, 'size': 489684992, 'filesystem': 'ext4'}
2025-09-22 17:15:27,250 - INFO - Attempting to mount RAW file to /mnt/container
2025-09-22 17:15:27,463 - INFO - Detected filesystem type: ext4 for /dev/loop0
2025-09-22 17:15:27,480 - INFO - Mount successful

*** DETECTED: Linux filesystem (type: ext4) ***
This appears to be a Linux root filesystem suitable for containerization.
Does this look like a correct filesystem for containerization? (y/n): y

2025-09-22 17:15:29,935 - INFO - Creating tar file: ./docker_output/alpine_linux.tar.gz
sudo tar -C /mnt/container -czf './docker_output/alpine_linux.tar.gz' .: 100%|████████████████████████████████|
2025-09-22 17:15:33,346 - INFO - Cleaning up
Conversion successful.
```

### Windows Guest with LVM
```
$ sudo python3 ova-to-docker.py --input windows_server.ova --output ./docker_output
2025-09-22 18:20:15,105 - INFO - Extracting OVA file: windows_server.ova
2025-09-22 18:20:35,154 - INFO - Converting to RAW format
2025-09-22 18:20:45,470 - INFO - LVM physical volume detected
2025-09-22 18:20:45,480 - INFO - Found volume group: vg_windows
2025-09-22 18:20:45,490 - INFO - Selected root filesystem: /dev/vg_windows/lv_root (OS: windows)
2025-09-22 18:20:45,500 - INFO - Successfully mounted LVM volume (OS: windows)

*** DETECTED: Windows filesystem (type: ntfs) ***
Note: Windows containers require special handling and may not work as expected in Docker.
Consider using Windows containers or converting the application to run on Linux.
This appears to be a Windows filesystem. Continue anyway? (y/n): y

2025-09-22 18:20:50,935 - INFO - Excluding Windows system files from tar archive
Conversion successful.
```

## How It Works

1. **File Extraction**: Extracts OVA files and locates disk images (VMDK/VDI)
2. **Format Conversion**: Converts disk images to RAW format using qemu-img
3. **Partition Analysis**: Analyzes partition table and selects the largest partition
4. **Storage Detection**: Detects and handles LVM configurations if present
5. **Filesystem Mounting**: Mounts filesystems with appropriate drivers (ext4, NTFS, etc.)
6. **OS Detection**: Identifies whether the guest is Windows or Linux
7. **User Verification**: Interactive verification with OS-specific guidance
8. **Archive Creation**: Creates tar.gz with OS-appropriate file exclusions
9. **Cleanup**: Safely unmounts filesystems and deactivates LVM volumes

## Supported Formats and Filesystems

### Input Formats
- **OVA** (Open Virtual Appliance)
- **VMDK** (VMware Virtual Machine Disk)
- **VDI** (VirtualBox Disk Image)

### Supported Filesystems
- **Linux**: ext2, ext3, ext4, XFS, BTRFS, ReiserFS
- **Windows**: NTFS (requires ntfs-3g)
- **Storage**: LVM (Logical Volume Manager)

### Supported Guest Operating Systems
- **Linux distributions** (Ubuntu, CentOS, Alpine, Debian, etc.)
- **Windows** (Windows Server, Windows 10/11) - *with limitations*

## Creating and Running the Docker Container

After successful conversion, use the following commands:

1. **Import the tar.gz file as a Docker image:**
   ```bash
   docker import ./docker_output/your_image.tar.gz my-new-image:latest
   ```

2. **Run the new container:**
   ```bash
   docker run -it my-new-image:latest /bin/sh
   ```

   For Windows-based containers, you might need:
   ```bash
   docker run -it my-new-image:latest cmd
   ```

## Important Notes

### Windows Container Limitations
- Windows containers converted this way may not function properly in standard Docker Linux containers
- Consider using Windows containers on Windows hosts for Windows guest VMs
- Many Windows services and applications require specific Windows container base images
- System files like hiberfil.sys, pagefile.sys, and swapfile.sys are automatically excluded

### LVM Support
- Automatically detects and activates LVM volume groups
- Selects the most appropriate logical volume as the root filesystem
- Properly cleans up LVM resources after conversion

### Security Considerations
- The script requires sudo privileges for mounting filesystems
- Temporary mount points are created in /mnt/container
- All temporary resources are cleaned up after conversion

## Troubleshooting

### Common Issues

**Missing dependencies:**
The script will check for required tools and report any missing dependencies.

**Permission errors:**
Ensure you're running the script with sudo privileges.

**LVM detection issues:**
Make sure lvm2 package is installed for LVM support.

**Windows filesystem mounting:**
Install ntfs-3g for Windows NTFS support.

**Debugging:**
Use the `--verbose` flag for detailed output and `--keepfiles` to preserve temporary files for analysis.

### Getting Help

If you encounter issues:
1. Run with `--verbose` for detailed logs
2. Use `--keepfiles` to examine temporary files
3. Check system logs with `dmesg` for mount-related errors
4. Ensure all required dependencies are installed

## Credits

This tool was inspired by the work of [Andy Green, Ph.D.](https://andygreen.phd/2022/01/26/converting-vm-images-to-docker-containers/) and created by executeatwill.

Special thanks to the community contributors who helped add LVM, Windows, and VDI support.

## License

This project is licensed under the MIT License.
