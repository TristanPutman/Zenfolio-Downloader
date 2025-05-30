"""First-time setup utility for Zenfolio downloader."""

import os
import shutil
from pathlib import Path
from typing import Optional
import getpass

def check_env_file_exists() -> bool:
    """Check if .env file exists."""
    return Path(".env").exists()

def copy_env_sample() -> bool:
    """Copy .env.sample to .env if it doesn't exist."""
    env_sample = Path(".env.sample")
    env_file = Path(".env")
    
    if not env_sample.exists():
        print("❌ Error: .env.sample file not found!")
        return False
    
    if not env_file.exists():
        try:
            shutil.copy2(env_sample, env_file)
            print("✅ Created .env file from .env.sample")
            return True
        except Exception as e:
            print(f"❌ Error copying .env.sample to .env: {e}")
            return False
    
    return True

def read_env_file() -> dict:
    """Read current .env file contents."""
    env_vars = {}
    env_file = Path(".env")
    
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        except Exception as e:
            print(f"❌ Error reading .env file: {e}")
    
    return env_vars

def write_env_file(env_vars: dict) -> bool:
    """Write environment variables to .env file."""
    env_file = Path(".env")
    
    try:
        # Read the original file to preserve comments and structure
        original_lines = []
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                original_lines = f.readlines()
        
        # Update the file
        with open(env_file, 'w', encoding='utf-8') as f:
            for line in original_lines:
                line = line.rstrip()
                if line and not line.startswith('#') and '=' in line:
                    key, _ = line.split('=', 1)
                    key = key.strip()
                    if key in env_vars:
                        f.write(f"{key}={env_vars[key]}\n")
                    else:
                        f.write(line + '\n')
                else:
                    f.write(line + '\n')
        
        return True
    except Exception as e:
        print(f"❌ Error writing .env file: {e}")
        return False

def validate_directory(path: str) -> bool:
    """Validate that a directory path exists or can be created."""
    try:
        dir_path = Path(path).expanduser().resolve()
        
        if dir_path.exists():
            if not dir_path.is_dir():
                print(f"❌ Path exists but is not a directory: {dir_path}")
                return False
            if not os.access(dir_path, os.W_OK):
                print(f"❌ Directory is not writable: {dir_path}")
                return False
            return True
        else:
            # Try to create the directory
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created directory: {dir_path}")
            return True
    except Exception as e:
        print(f"❌ Error with directory path '{path}': {e}")
        return False

def prompt_for_username() -> Optional[str]:
    """Prompt user for Zenfolio username."""
    print("\n📝 Zenfolio Username Setup")
    print("Enter your Zenfolio username (the one you use to log into zenfolio.com)")
    
    while True:
        username = input("Username: ").strip()
        if username:
            return username
        print("❌ Username cannot be empty. Please try again.")

def prompt_for_password() -> Optional[str]:
    """Prompt user for Zenfolio password."""
    print("\n🔐 Zenfolio Password Setup")
    print("Enter your Zenfolio password (input will be hidden for security)")
    
    while True:
        password = getpass.getpass("Password: ").strip()
        if password:
            # Confirm password
            confirm = getpass.getpass("Confirm password: ").strip()
            if password == confirm:
                return password
            else:
                print("❌ Passwords don't match. Please try again.")
        else:
            print("❌ Password cannot be empty. Please try again.")

def prompt_for_output_directory() -> Optional[str]:
    """Prompt user for output directory."""
    print("\n📁 Download Directory Setup")
    print("Enter the directory where downloaded files should be saved.")
    print("Examples: /home/user/Photos, C:\\Users\\User\\Pictures, ./downloads")
    
    while True:
        directory = input("Download directory: ").strip()
        if directory:
            if validate_directory(directory):
                return directory
            print("Please try a different directory path.")
        else:
            print("❌ Directory path cannot be empty. Please try again.")

def check_required_settings() -> tuple[bool, list[str]]:
    """Check if required settings are configured."""
    env_vars = read_env_file()
    missing = []
    
    # Check username
    username = env_vars.get('ZENFOLIO_USERNAME', '')
    if not username or username == 'your_zenfolio_username':
        missing.append('ZENFOLIO_USERNAME')
    
    # Check password
    password = env_vars.get('ZENFOLIO_PASSWORD', '')
    if not password or password == 'your_zenfolio_password':
        missing.append('ZENFOLIO_PASSWORD')
    
    # Check output directory
    output_dir = env_vars.get('DEFAULT_OUTPUT_DIR', '')
    if not output_dir or output_dir == './downloads':
        # ./downloads is the default, but let's check if user wants to change it
        missing.append('DEFAULT_OUTPUT_DIR')
    
    return len(missing) == 0, missing

def run_first_time_setup(force: bool = False) -> bool:
    """Run the first-time setup process."""
    print("🚀 Zenfolio Downloader - First Time Setup")
    print("=" * 50)
    
    # Ensure .env file exists
    if not copy_env_sample():
        return False
    
    # Check if setup is needed
    if not force:
        is_configured, missing = check_required_settings()
        if is_configured:
            print("✅ Configuration appears to be complete!")
            
            # Ask if they want to reconfigure
            while True:
                reconfigure = input("\nWould you like to run setup anyway? (y/n): ").strip().lower()
                if reconfigure in ['y', 'yes']:
                    break
                elif reconfigure in ['n', 'no']:
                    return True
                else:
                    print("Please enter 'y' for yes or 'n' for no.")
    
    # Read current settings
    env_vars = read_env_file()
    
    # Prompt for username
    username = prompt_for_username()
    if not username:
        return False
    env_vars['ZENFOLIO_USERNAME'] = username
    
    # Prompt for password
    password = prompt_for_password()
    if not password:
        return False
    env_vars['ZENFOLIO_PASSWORD'] = password
    
    # Prompt for output directory
    output_dir = prompt_for_output_directory()
    if not output_dir:
        return False
    env_vars['DEFAULT_OUTPUT_DIR'] = output_dir
    
    # Save settings
    if write_env_file(env_vars):
        print("\n✅ Setup completed successfully!")
        print(f"   Username: {username}")
        print(f"   Download directory: {output_dir}")
        print("\n🔒 Your password has been securely saved to the .env file.")
        print("📝 You can edit the .env file manually to adjust other settings.")
        return True
    else:
        print("\n❌ Failed to save configuration!")
        return False

def should_run_setup() -> bool:
    """Determine if first-time setup should be run."""
    if not check_env_file_exists():
        return True
    
    is_configured, missing = check_required_settings()
    return not is_configured