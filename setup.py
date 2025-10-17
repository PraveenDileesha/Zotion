"""
Automatic setup script for Zotion
Creates a virtual environment and installs all dependencies
"""
import os
import sys
import subprocess
import platform
from pathlib import Path
import shutil

def run_command(cmd, shell=False):
    """Run a command and return success status"""
    try:
        if shell:
            result = subprocess.run(cmd, check=True, text=True)
        else:
            result = subprocess.run(cmd, check=True, 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True, result.stdout.decode()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode()


def ensure_tkinter_installed():
    """Ensure tkinter is installed (mainly for Linux systems)."""
    try:
        import tkinter  # noqa: F401
        print("tkinter already available")
    except ImportError:
        if platform.system() == "Linux":
            print("Installing tkinter via apt...")
            success, output = run_command(["sudo", "apt-get", "install", "-y", "python3-tk"])
            if success:
                print("tkinter installed successfully")
            else:
                print(f"Could not install tkinter automatically:\n{output}")
        else:
            print("tkinter not found. Attempting to install via pip...")
            success, output = run_command([sys.executable, "-m", "pip", "install", "tk"])
            if success:
                print("tkinter installed successfully via pip")
            else:
                print(f"Could not install tkinter via pip:\n{output}")
                print("Please install tkinter manually if the GUI fails to start.")


def main():
    print("=" * 60)
    print("Zotion - Setup Script")
    print("=" * 60)
    print()
    
    script_dir = Path(__file__).parent.absolute()
    venv_dir = script_dir / "venv"
    
    print(f"Working directory: {script_dir}")
    print()
    
    py_version = sys.version_info
    if py_version < (3, 6):
        print("Python 3.6 or higher is required!")
        print(f"Current version: {py_version.major}.{py_version.minor}.{py_version.micro}")
        sys.exit(1)
    
    print(f"Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")
    print()
    
    print("Step 1: Creating virtual environment...")
    if venv_dir.exists():
        print(f"Virtual environment already exists at: {venv_dir}")
        response = input("Do you want to recreate it? (y/n): ").strip().lower()
        if response == 'y':
            print("Removing old virtual environment...")
            shutil.rmtree(venv_dir)
        else:
            print("Using existing virtual environment")
    
    if not venv_dir.exists():
        success, output = run_command([sys.executable, "-m", "venv", str(venv_dir)])
        if success:
            print(f"Virtual environment created at: {venv_dir}")
        else:
            print(f"Failed to create virtual environment: {output}")
            sys.exit(1)
    
    print()
    
    # Paths for pip/python inside venv
    if platform.system() == "Windows":
        pip_path = venv_dir / "Scripts" / "pip.exe"
        python_path = venv_dir / "Scripts" / "python.exe"
        activate_cmd = f"{venv_dir}\\Scripts\\activate"
    else:
        pip_path = venv_dir / "bin" / "pip"
        python_path = venv_dir / "bin" / "python"
        activate_cmd = f"source {venv_dir}/bin/activate"
    
    print("Step 2: Upgrading pip...")
    success, output = run_command([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    if success:
        print("pip upgraded successfully")
    else:
        print(f"Warning: Could not upgrade pip: {output}")
    print()
    
    print("Step 3: Installing dependencies...")
    dependencies = [
        "requests",
        "python-dotenv",
        "pyinstaller",
        "tk"  # tkinter via pip (for some platforms)
    ]
    
    for dep in dependencies:
        print(f"Installing {dep}...")
        success, output = run_command([str(pip_path), "install", dep])
        if success:
            print(f"{dep} installed successfully")
        else:
            print(f"Failed to install {dep}: {output}")
            sys.exit(1)
    
    print()
    print("Checking tkinter installation...")
    ensure_tkinter_installed()
    print()
    
    print("=" * 60)
    print("Setup completed successfully!")
    print("=" * 60)
    print()
    print("To run the application:")
    print()
    
    if platform.system() == "Windows":
        print(f"1. Activate the virtual environment:")
        print(f"   {activate_cmd}")
        print()
        print(f"2. Run the GUI:")
        print(f"   python zotion.py")
        print()
        print("Or use the run.bat file:")
        print("   run.bat")
    else:
        print(f"1. Activate the virtual environment:")
        print(f"   {activate_cmd}")
        print()
        print(f"2. Run the GUI:")
        print(f"   python zotion.py")
        print()
        print("Or use the run.sh file:")
        print("   ./run.sh")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
