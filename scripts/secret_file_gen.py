import os
import subprocess
import sys


def delete_file(filepath):
    """
    Deletes a file from the filesystem.

    Args:
        filepath (str): The path to the file to be deleted.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be deleted due to insufficient permissions.
        Exception: For any other errors during file deletion.
    """
    try:
        os.remove(filepath)
        print(f"Deleted file: {filepath}")
    except FileNotFoundError:
        print(f"File not found: {filepath}")
    except PermissionError:
        print(f"No permission to delete: {filepath}")
    except Exception as e:
        print(f"Error deleting file: {e}")


def encrypt_file(input_file, output_file):
    """
    Encrypts a file using the `sops` command-line tool.

    Args:
        input_file (str): The path to the input file to be encrypted.
        output_file (str): The path where the encrypted file will be saved.

    Raises:
        SystemExit: If the input file does not exist or encryption fails.
    """
    if not os.path.isfile(input_file):
        print(f"Error: Input file '{input_file}' does not exist.")
        sys.exit(1)

    try:
        subprocess.run(
            ["sops", "--output", output_file, "--encrypt", input_file], check=True
        )
        print(f"Encrypted file saved as: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Encryption failed: {e}")
        sys.exit(1)


def handle_secrets(school_arg, env_arg):
    """
    Handles the encryption and cleanup of secret files.

    Args:
        school_arg (str): The name of the school.
        env_arg (str): The environment (e.g., 'staging', 'prod').

    This function:
    2. Encrypts the plain YAML file.
    3. Deletes the plain YAML file after encryption.
    """
    encrypt_file(
        os.path.join("deployments", school_arg, "secrets", f"{env_arg}.plain.yaml"),
        os.path.join("deployments", school_arg, "secrets", f"{env_arg}.yaml"),
    )
    delete_file(
        os.path.join("deployments", school_arg, "secrets", f"{env_arg}.plain.yaml")
    )
    print("Secret file generation and encryption completed.")
