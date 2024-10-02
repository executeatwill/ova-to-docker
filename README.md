# OVA to Docker Converter

This tool converts OVA (Open Virtual Appliance) or VMDK (Virtual Machine Disk) files to Docker container format. It was inspired by the work of [Andy Green, Ph.D.](https://andygreen.phd/2022/01/26/converting-vm-images-to-docker-containers/) and created by executeatwill.

## Features

- Converts both OVA and VMDK files to Docker container format
- Interactive filesystem verification
- Progress bars for long-running operations
- Option to keep temporary files for debugging
- Detailed logging

## Requirements

- Python 3.6+
- qemu-utils
- parted
- Docker (for running the converted image)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/executeatwill/ova-to-docker.git
   cd ova-to-docker
   ```

2. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Ensure you have `qemu-utils` and `parted` installed on your system:
   ```
   sudo apt-get install qemu-utils parted
   ```

## Usage

Run the script with sudo privileges:

```
sudo python3 ova-to-docker.py --input <input_file> --output <output_directory> [options]
```

### Options

- `--input`: Path to the input OVA or VMDK file (required)
- `--output`: Path to the output directory for Docker container files (required)
- `--keepfiles`: Keep extracted files in the temp folder (optional)
- `-v, --verbose`: Enable verbose output (optional)

### Example

```
sudo python3 ova-to-docker.py --input alpine_linux.ova --output ./docker_output
```

## Successful Run
```
$ sudo python3 ova-to-docker.py --input alpine_linux.ova --output ./docker_output
2024-10-02 17:15:23,173 - INFO - Extracting OVA file: alpine_linux.ova
tar -xvf 'alpine_linux.ova' -C './docker_output/temp': 100%|████████████████████████████████████████████████|
2024-10-02 17:15:25,190 - INFO - Converting ./docker_output/temp/alpine_linux-disk001.vmdk to RAW format
qemu-img convert -f vmdk './docker_output/temp/alpine_linux-disk001.vmdk' -O raw './docker_output/alpine_linux-disk001.raw': 100%|████████████████████████████████████████████████|
2024-10-02 17:15:26,995 - INFO - Getting partition information
2024-10-02 17:15:27,250 - INFO - Selected partition: {'number': 3, 'start': 584056832, 'end': 1073741823, 'size': 489684992, 'filesystem': 'ext4'}
2024-10-02 17:15:27,250 - INFO - Attempting to mount RAW file to /mnt/container
2024-10-02 17:15:27,463 - INFO - Mount successful
2024-10-02 17:15:27,463 - INFO - Displaying contents of the mounted filesystem:
total 46
drwxr-xr-x 22 root root  1024 Oct  2 08:22 .
drwxr-xr-x 14 root root  4096 Oct  2 17:15 ..
drwxr-xr-x  2 root root  4096 Oct  2 08:21 bin
drwxr-xr-x  2 root root  1024 Oct  2 08:21 boot
drwxr-xr-x  2 root root  1024 Oct  2 08:21 dev
drwxr-xr-x 30 root root  3072 Oct  2 08:54 etc
drwxr-xr-x  3 root root  1024 Oct  2 08:21 home
drwxr-xr-x 10 root root  1024 Oct  2 08:21 lib
drwx------  2 root root 12288 Oct  2 08:21 lost+found
drwxr-xr-x  5 root root  1024 Oct  2 08:21 media
drwxr-xr-x  2 root root  1024 Oct  2 08:21 mnt
drwxr-xr-x  2 root root  1024 Oct  2 08:21 opt
drwxr-xr-x  2 root root  1024 Oct  2 08:21 proc
drwx------  2 root root  1024 Oct  2 08:25 root
drwxr-xr-x  2 root root  1024 Oct  2 08:21 run
drwxr-xr-x  2 root root  6144 Oct  2 08:21 sbin
drwxr-xr-x  2 root root  1024 Oct  2 08:21 srv
drwxr-xr-x  2 root root  1024 Oct  2 08:22 swap
drwxr-xr-x  2 root root  1024 Oct  2 08:21 sys
drwxrwxrwt  2 root root  1024 Oct  2 08:21 tmp
drwxr-xr-x  8 root root  1024 Oct  2 08:21 usr
drwxr-xr-x 11 root root  1024 Oct  2 08:22 var
Does this look like a correct Linux root filesystem? (y/n): y
2024-10-02 17:15:29,935 - INFO - Creating tar file: ./docker_output/alpine_linux.tar.gz
sudo tar -C /mnt/container -czf './docker_output/alpine_linux.tar.gz' .: 100%|████████████████████████████████|
2024-10-02 17:15:33,346 - INFO - Cleaning up
2024-10-02 17:15:33,388 - INFO - Removing temporary files
Conversion successful.
RAW file: ./docker_output/alpine_linux-disk001.raw
Tar file: ./docker_output/alpine_linux.tar.gz

To create a Docker image, run:
docker import ./docker_output/alpine_linux.tar.gz my-new-image:latest

To run the new container:
docker run -it my-new-image:latest /bin/sh
```

## How It Works

1. The script extracts the OVA file (if applicable) and locates the VMDK file.
2. It converts the VMDK to a RAW format using qemu-img.
3. The script then analyzes the partition table of the RAW image.
4. It mounts the largest partition (assumed to be the root filesystem).
5. The user is prompted to verify if the mounted filesystem looks correct.
6. If confirmed, the script creates a tar.gz archive of the filesystem.
7. Finally, it provides instructions on how to create and run a Docker container from the generated tar.gz file.

## Creating and Running the Docker Container

After successful conversion, use the following commands to create and run your Docker container:

1. Import the tar.gz file as a Docker image:
   ```
   docker import ./docker_output/your_image.tar.gz my-new-image:latest
   ```

2. Run the new container:
   ```
   docker run -it my-new-image:latest /bin/sh
   ```

## Troubleshooting

If you encounter any issues, try running the script with the `--verbose` flag for more detailed output. You can also use the `--keepfiles` option to preserve temporary files for debugging.

## Credits

This tool was inspired by the work of [Andy Green, Ph.D.](https://andygreen.phd/2022/01/26/converting-vm-images-to-docker-containers/) and created by executeatwill.

## License

This project is licensed under the MIT License.
