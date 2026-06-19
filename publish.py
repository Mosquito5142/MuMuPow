import os
import sys
import subprocess
import shutil

def run_cmd(command, shell=True):
    print(f"\n> Running: {command}")
    result = subprocess.run(command, shell=shell, text=True)
    if result.returncode != 0:
        print(f"❌ Error: Command failed with exit code {result.returncode}")
        return False
    return True

def check_gh_installed():
    try:
        result = subprocess.run("gh --version", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return True
    except Exception:
        pass
    return False

def check_gh_auth():
    try:
        result = subprocess.run("gh auth status", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "Logged in to github.com" in result.stdout or "Logged in to github.com" in result.stderr:
            return True
    except Exception:
        pass
    return False

def main():
    print("==========================================")
    print("🚀 MuMupow Release Publisher Script")
    print("==========================================")

    # 1. Check gh CLI
    if not check_gh_installed():
        print("❌ Error: GitHub CLI ('gh') is not installed on your system.")
        print("💡 Please install it first using: winget install --id GitHub.cli")
        sys.exit(1)

    if not check_gh_auth():
        print("⚠️ Warning: GitHub CLI is not logged in.")
        print("👉 Running 'gh auth login' to authenticate...")
        if not run_cmd("gh auth login"):
            print("❌ Authentication failed. Please run 'gh auth login' manually first.")
            sys.exit(1)

    # 2. Ask for version
    default_version = ""
    try:
        # Try to get last tag as suggestion
        result = subprocess.run("git describe --tags --abbrev=0", shell=True, stdout=subprocess.PIPE, text=True)
        if result.returncode == 0:
            last_tag = result.stdout.strip()
            print(f"Latest Git Tag found: {last_tag}")
            # Suggest next patch version
            if last_tag.startswith("v"):
                parts = last_tag[1:].split(".")
                if len(parts) == 3 and parts[2].isdigit():
                    parts[2] = str(int(parts[2]) + 1)
                    default_version = "v" + ".".join(parts)
    except Exception:
        pass

    version_prompt = f"Enter version tag (e.g. v1.0.1) [{default_version}]: " if default_version else "Enter version tag (e.g. v1.0.0): "
    version = input(version_prompt).strip()
    if not version:
        version = default_version
    if not version:
        print("❌ Error: Version tag cannot be empty.")
        sys.exit(1)

    # Validate version format (should start with v)
    if not version.startswith("v"):
        version = "v" + version

    # 3. Ask to build the EXE first
    build_choice = input("Do you want to compile MuMupow.exe using PyInstaller? (y/n) [y]: ").strip().lower()
    if build_choice in ("", "y", "yes"):
        print("\n🔨 Compiling MuMupow.exe...")
        # Clean build directories
        for folder in ["build", "dist"]:
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder)
                except Exception as e:
                    print(f"⚠️ Warning: Could not clean folder '{folder}': {e}")
        
        # Run pyinstaller
        if not run_cmd("python -m PyInstaller --clean MuMupow.spec"):
            print("❌ Compilation failed!")
            sys.exit(1)
        
        # Copy file to root
        src_exe = os.path.join("dist", "MuMupow.exe")
        dest_exe = "./MuMupow.exe"
        if os.path.exists(src_exe):
            try:
                shutil.copy2(src_exe, dest_exe)
                print(f"✅ Compiled and copied to {dest_exe}")
            except Exception as e:
                print(f"❌ Error copying {src_exe} to {dest_exe}: {e}")
                sys.exit(1)
        else:
            print(f"❌ Error: Compiled executable not found at {src_exe}")
            sys.exit(1)

    # Double check executable exists
    exe_path = "./MuMupow.exe"
    if not os.path.exists(exe_path):
        print(f"❌ Error: {exe_path} does not exist. Cannot create release without the executable.")
        sys.exit(1)

    # 4. Ask for release options
    notes_choice = input("Do you want GitHub to automatically generate release notes? (y/n) [y]: ").strip().lower()
    generate_notes = notes_choice in ("", "y", "yes")

    notes = ""
    if not generate_notes:
        notes = input("Enter release notes description: ").strip()

    is_prerelease = input("Is this a Pre-release? (y/n) [n]: ").strip().lower() in ("y", "yes")

    # 5. Build and execute gh release create command
    cmd = f'gh release create {version} "{exe_path}" --title "{version}"'
    if generate_notes:
        cmd += " --generate-notes"
    elif notes:
        cmd += f' --notes "{notes}"'
    else:
        cmd += ' --notes ""'

    if is_prerelease:
        cmd += " --prerelease"

    print("\n🚀 Creating GitHub Release...")
    if run_cmd(cmd):
        print(f"\n🎉 Successfully published release {version}!")
        # Print URL
        try:
            repo_res = subprocess.run("git config --get remote.origin.url", shell=True, stdout=subprocess.PIPE, text=True)
            if repo_res.returncode == 0:
                repo_url = repo_res.stdout.strip()
                if repo_url.endswith(".git"):
                    repo_url = repo_url[:-4]
                if repo_url.startswith("git@github.com:"):
                    repo_url = "https://github.com/" + repo_url[15:]
                print(f"🔗 View Release at: {repo_url}/releases/tag/{version}")
        except Exception:
            pass
    else:
        print("❌ Failed to publish release.")

if __name__ == "__main__":
    main()
