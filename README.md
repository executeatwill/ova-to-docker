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
