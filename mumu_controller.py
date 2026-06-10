import subprocess
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

class MuMuController:
    def __init__(self, adb_path=None):
        self.adb_path = adb_path or self.find_adb()
        # Common emulator ports to scan:
        # 7555: MuMu Player 6
        # 16384, 16400, 16416, 16432, 16448, 16464, 16480, 16496: MuMu Player 12
        # 5554, 5556, 5558, 5560, 5562: LDPlayer, Nox, MEMu
        self.common_ports = [
            7555, 
            16384, 16400, 16416, 16432, 16448, 16464, 16480, 16496,
            5554, 5556, 5558, 5560, 5562
        ]

    def find_adb(self):
        """Attempts to find the ADB executable path."""
        # 1. Try system PATH
        try:
            res = subprocess.run(["where", "adb"], capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip().split("\n")[0]
        except Exception:
            pass

        # 2. Try default Android SDK path
        user_home = os.path.expanduser("~")
        sdk_adb = os.path.join(user_home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe")
        if os.path.exists(sdk_adb):
            return sdk_adb

        # 3. Try standard LDPlayer path
        ld_adb = r"C:\LDPlayer\LDPlayer9\adb.exe"
        if os.path.exists(ld_adb):
            return ld_adb

        # Default fall back (assumes it might be on PATH or globally resolved)
        return "adb"

    def run_adb_cmd(self, args, timeout=10):
        """Helper to run a raw ADB command."""
        if not self.adb_path:
            return False, "ADB path not specified"
        
        cmd = [self.adb_path] + args
        try:
            # Running with shell=True on Windows to avoid console popup window flashing
            # and startupinfo to hide CMD window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            res = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                startupinfo=startupinfo,
                timeout=timeout,
                encoding='utf-8', 
                errors='ignore'
            )
            return (res.returncode == 0, res.stdout.strip() if res.returncode == 0 else res.stderr.strip())
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def connect_device(self, ip_port):
        """Connects to a specific emulator port."""
        if not ip_port.startswith("127.0.0.1:"):
            if ":" not in ip_port:
                ip_port = f"127.0.0.1:{ip_port}"
        success, output = self.run_adb_cmd(["connect", ip_port])
        return success, output

    def disconnect_device(self, ip_port):
        """Disconnects a specific emulator port."""
        success, output = self.run_adb_cmd(["disconnect", ip_port])
        return success, output

    def get_connected_devices(self):
        """Lists all currently connected devices/emulators."""
        success, output = self.run_adb_cmd(["devices"])
        devices = []
        if success:
            lines = output.split("\n")
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r'\s+', line)
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])
        return devices

    def scan_and_connect_all(self):
        """Scans all common emulator ports and connects to open ones, disconnecting closed ones."""
        import socket
        
        def is_port_open(port):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    return s.connect_ex(('127.0.0.1', port)) == 0
            except Exception:
                return False

        logs = []
        logs.append("🔍 Starting auto-scan of common emulator ports...")
        
        # We run the connects/disconnects in parallel
        def process_port(port):
            addr = f"127.0.0.1:{port}"
            if is_port_open(port):
                success, out = self.connect_device(addr)
                if success and ("connected" in out.lower() or "already" in out.lower()):
                    return f"✅ Connected to {addr}", True
            else:
                # If port is closed but ADB thinks it is connected, disconnect it to clear ghost connection
                self.disconnect_device(addr)
            return None, False

        with ThreadPoolExecutor(max_workers=len(self.common_ports)) as executor:
            results = list(executor.map(process_port, self.common_ports))
            
        for log_msg, is_conn in results:
            if log_msg:
                logs.append(log_msg)
                
        connected = self.get_connected_devices()
        logs.append(f"📱 Current active devices: {', '.join(connected) if connected else 'None'}")
        return connected, "\n".join(logs)

    # Individual device shell commands
    def tap(self, device_id, x, y):
        """Taps coordinate (x, y) on the specified device."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "tap", str(x), str(y)])

    def swipe(self, device_id, x1, y1, x2, y2, duration=300):
        """Swipes from (x1, y1) to (x2, y2) on the specified device."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])

    def input_text(self, device_id, text):
        """Inputs text on the specified device (escapes space for adb input)."""
        # ADB 'input text' interprets '%s' as spaces
        escaped_text = text.replace(" ", "%s")
        # escape special characters like & | < > ( ) [ ] { } ^ = ; ! ' " ` ~
        # standard text input from user is email/password so simple escape is fine
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "text", escaped_text])

    def keyevent(self, device_id, code):
        """Sends keyevent code (e.g. 4 for Back, 3 for Home)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "keyevent", str(code)])

    def get_resolution(self, device_id):
        """Queries the screen size of the device."""
        success, out = self.run_adb_cmd(["-s", device_id, "shell", "wm", "size"])
        if success:
            match = re.search(r'Physical size:\s*(\d+x\d+)', out)
            if match:
                return match.group(1)
        return "Unknown"

    def get_dpi(self, device_id):
        """Queries the DPI density of the device."""
        success, out = self.run_adb_cmd(["-s", device_id, "shell", "wm", "density"])
        if success:
            match = re.search(r'Physical density:\s*(\d+)', out)
            if match:
                return match.group(1)
        return "Unknown"

    def start_app(self, device_id, package_activity):
        """Starts an application on the specified device (package/activity)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "am", "start", "-n", package_activity])

    def stop_app(self, device_id, package):
        """Stops an application on the specified device (package name)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "am", "force-stop", package])

    def clear_app(self, device_id, package):
        """Clears application data on the specified device (package name)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "pm", "clear", package])

    # Multi-device action runners (Parallelized)
    def run_parallel_action(self, devices, action_func, *args):
        """Runs action_func(device_id, *args) on all specified devices in parallel."""
        results = {}
        def worker(device_id):
            try:
                success, output = action_func(device_id, *args)
                return device_id, success, output
            except Exception as e:
                return device_id, False, str(e)

        with ThreadPoolExecutor(max_workers=max(1, len(devices))) as executor:
            fut_results = executor.map(worker, devices)

        for device_id, success, output in fut_results:
            results[device_id] = (success, output)
        return results
