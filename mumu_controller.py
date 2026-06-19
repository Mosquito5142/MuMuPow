import subprocess
import os
import re
import time
import json
import base64
import cv2
import numpy as np
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor


# Characters that the on-device shell (/system/bin/sh) interprets when running
# `input text ...`. They must be backslash-escaped or the text gets mangled /
# truncated silently. Space is sent as the special token %s (an `input` quirk).
_ADB_TEXT_SPECIAL = set(" '\"`$&|;<>()*\\!?#~{}[]^")


def escape_adb_text(text):
    """Escapes a string so `adb shell input text` sends it verbatim.

    Without this, passwords/emails containing shell metacharacters such as
    & ( ) < > | ; ' " $ ` are interpreted by the device shell and the account
    silently fails to log in. Returns the escaped token string.
    """
    out = []
    for ch in str(text):
        if ch == " ":
            out.append("%s")
        elif ch in _ADB_TEXT_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _parse_bounds(bounds):
    """Parses a uiautomator bounds string '[l,t][r,b]' into a center (x, y) point."""
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", bounds or "")
    if not m:
        return None
    left, top, right, bottom = (int(v) for v in m.groups())
    return (left + right) // 2, (top + bottom) // 2


def find_element_center(xml_text, text=None, resource_id=None, partial=True):
    """Finds a UI element by visible text or resource-id in a uiautomator XML dump.

    Returns (found, center_x, center_y, info). Searches `text` against the node's
    text and content-desc; `resource_id` against resource-id (exact or, if partial,
    substring). resource_id takes precedence when both are given.
    """
    if not xml_text:
        return False, 0, 0, "empty UI dump"
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return False, 0, 0, f"XML parse error: {e}"

    want_text = (text or "").strip()
    want_id = (resource_id or "").strip()
    if not want_text and not want_id:
        return False, 0, 0, "no search text/id given"

    for node in root.iter("node"):
        rid = node.get("resource-id", "")
        ntext = node.get("text", "")
        ndesc = node.get("content-desc", "")
        if want_id:
            matched = (rid == want_id) or (partial and bool(rid) and want_id in rid)
        else:
            candidates = [h for h in (ntext, ndesc) if h]
            matched = any(want_text in h for h in candidates) if partial else any(want_text == h for h in candidates)
        if matched:
            center = _parse_bounds(node.get("bounds", ""))
            if center:
                label = rid or ntext or ndesc
                return True, center[0], center[1], f"matched '{label}'"

    return False, 0, 0, f"no element matching '{want_id or want_text}'"


def list_ui_elements(xml_text):
    """Returns labelled/interactable elements from a uiautomator dump (for inspection)."""
    items = []
    if not xml_text:
        return items
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for node in root.iter("node"):
        text = node.get("text", "").strip()
        rid = node.get("resource-id", "").strip()
        desc = node.get("content-desc", "").strip()
        if not (text or rid or desc):
            continue
        items.append({
            "text": text,
            "resource_id": rid,
            "content_desc": desc,
            "clickable": node.get("clickable") == "true",
            "center": _parse_bounds(node.get("bounds", "")),
        })
    return items


class MuMuController:
    def __init__(self, adb_path=None):
        self.adb_path = adb_path or self.find_adb()
        self.common_ports = self.load_ports()

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

    def run_adb_bytes(self, args, timeout=15):
        """Like run_adb_cmd but returns raw bytes (for binary output such as exec-out screencap).

        Returns (success, stdout_bytes) on success, or (False, error_string) on failure.
        """
        if not self.adb_path:
            return False, "ADB path not specified"

        cmd = [self.adb_path] + args
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # No text/encoding -> stdout stays raw bytes (binary-safe)
            res = subprocess.run(
                cmd,
                capture_output=True,
                startupinfo=startupinfo,
                timeout=timeout,
            )
            if res.returncode == 0:
                return True, res.stdout
            return False, res.stderr.decode("utf-8", errors="ignore").strip()
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

    def get_unique_devices(self, connected_devices):
        """Filters out duplicate connections to the same physical emulator."""
        unique_devices = []
        seen_serials = set()
        
        def get_device_serial(device_id):
            # Query device serial number with a low timeout (2 seconds)
            success, serial = self.run_adb_cmd(["-s", device_id, "shell", "getprop", "ro.serialno"], timeout=2)
            if success and serial.strip():
                return device_id, serial.strip()
            # Fallback to MAC address
            success, mac = self.run_adb_cmd(["-s", device_id, "shell", "cat", "/sys/class/net/wlan0/address"], timeout=2)
            if success and mac.strip():
                return device_id, mac.strip()
            return device_id, device_id # Fallback to itself

        if connected_devices:
            with ThreadPoolExecutor(max_workers=max(1, len(connected_devices))) as executor:
                results = list(executor.map(get_device_serial, connected_devices))

            for device_id, serial in results:
                if serial not in seen_serials:
                    seen_serials.add(serial)
                    unique_devices.append(device_id)
                else:
                    # Disconnect duplicate connection to keep ADB clean
                    self.disconnect_device(device_id)
        
        return unique_devices

    def load_ports(self):
        """Loads ports from ports.json if it exists, otherwise returns empty list."""
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        ports_file = os.path.join(base_dir, "ports.json")
        if os.path.exists(ports_file):
            try:
                with open(ports_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        custom_ports = []
                        for p in data:
                            try:
                                custom_ports.append(int(p))
                            except (ValueError, TypeError):
                                continue
                        if custom_ports:
                            return sorted(list(set(custom_ports)))
            except Exception as e:
                print(f"Error loading ports.json: {e}")
        
        return []

    def scan_and_connect_all(self):
        """Scans all common emulator ports and connects to open ones, disconnecting closed ones."""
        import socket
        
        # Reload ports from file or defaults dynamically
        self.common_ports = self.load_ports()

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

        with ThreadPoolExecutor(max_workers=max(1, len(self.common_ports))) as executor:
            results = list(executor.map(process_port, self.common_ports))
            
        for log_msg, is_conn in results:
            if log_msg:
                logs.append(log_msg)
                
        connected = self.get_connected_devices()
        unique_connected = self.get_unique_devices(connected)
        logs.append(f"📱 Current active devices: {', '.join(unique_connected) if unique_connected else 'None'}")
        return unique_connected, "\n".join(logs)

    # Individual device shell commands
    def tap(self, device_id, x, y):
        """Taps coordinate (x, y) on the specified device."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "tap", str(x), str(y)])

    def swipe(self, device_id, x1, y1, x2, y2, duration=300):
        """Swipes from (x1, y1) to (x2, y2) on the specified device."""
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])

    def input_text(self, device_id, text):
        """Inputs text on the specified device, escaping shell metacharacters.

        See escape_adb_text(): emails/passwords with characters like
        & ( ) < > | ; ' " $ ` would otherwise be mangled by the device shell.
        Note: `input text` is ASCII-only — for Thai/Unicode use input_text_unicode().
        """
        escaped_text = escape_adb_text(text)
        return self.run_adb_cmd(["-s", device_id, "shell", "input", "text", escaped_text])

    # --- Unicode / Thai text input via ADBKeyboard ---
    ADB_KEYBOARD_PKG = "com.android.adbkeyboard"
    ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"

    def current_ime(self, device_id):
        """Returns (success, current_default_input_method_id)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "settings", "get", "secure", "default_input_method"])

    def input_text_unicode(self, device_id, text):
        """Inputs text that may contain Unicode/Thai.

        ASCII text goes through the normal `input text`. Non-ASCII text requires
        ADBKeyboard to be the active IME and is sent as base64 via broadcast.
        Returns (success, message).
        """
        text = str(text)
        if text.isascii():
            return self.input_text(device_id, text)

        ok, ime = self.current_ime(device_id)
        if not ok or "adbkeyboard" not in (ime or "").lower():
            return False, "ต้องเปิดใช้ ADBKeyboard ก่อนถึงจะพิมพ์ภาษาไทย/Unicode ได้ (ปุ่มในแท็บตั้งค่า)"

        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return self.run_adb_cmd(["-s", device_id, "shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64])

    def is_adb_keyboard_installed(self, device_id):
        ok, out = self.run_adb_cmd(["-s", device_id, "shell", "pm", "list", "packages", self.ADB_KEYBOARD_PKG])
        return bool(ok and self.ADB_KEYBOARD_PKG in (out or ""))

    def install_adb_keyboard(self, device_id, apk_path):
        return self.run_adb_cmd(["-s", device_id, "install", "-r", apk_path], timeout=60)

    def enable_adb_keyboard(self, device_id):
        """Enables and activates ADBKeyboard as the current IME. Returns (success, msg)."""
        self.run_adb_cmd(["-s", device_id, "shell", "ime", "enable", self.ADB_KEYBOARD_IME])
        return self.run_adb_cmd(["-s", device_id, "shell", "ime", "set", self.ADB_KEYBOARD_IME])

    def reset_ime(self, device_id):
        """Restores the device's default keyboard (so manual play works normally again)."""
        return self.run_adb_cmd(["-s", device_id, "shell", "ime", "reset"])

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

    def capture_screenshot_bytes(self, device_id):
        """Captures a screenshot straight to memory via `exec-out screencap -p`.

        Faster than take_screenshot(): one command, no on-device temp file, no pull.
        Returns (True, png_bytes) or (False, error_string).
        """
        success, data = self.run_adb_bytes(["-s", device_id, "exec-out", "screencap", "-p"])
        if not success:
            return False, data
        if not data:
            return False, "Empty screenshot output"
        return True, data

    def dump_ui(self, device_id):
        """Dumps the current screen's UI hierarchy as XML via uiautomator.

        Returns (True, xml_str) or (False, error_string). Returns a friendly error
        for game canvases (Unity/Cocos) where uiautomator sees no elements.
        """
        # Write the dump on-device, then read it back (more reliable than /dev/tty)
        self.run_adb_cmd(["-s", device_id, "shell", "uiautomator", "dump", "/sdcard/window_dump.xml"], timeout=15)
        ok, data = self.run_adb_bytes(["-s", device_id, "exec-out", "cat", "/sdcard/window_dump.xml"])
        if not ok:
            return False, data
        xml_text = data.decode("utf-8", errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data)
        if "<hierarchy" not in xml_text and "<node" not in xml_text:
            return False, "ไม่พบ element บนหน้าจอนี้ (อาจเป็นหน้าจอเกมที่ uiautomator อ่านไม่ได้)"
        return True, xml_text

    def take_screenshot(self, device_id, local_path):
        """Saves a screenshot to local_path. Prefers in-memory exec-out, falls back to screencap+pull.

        Kept for callers that need a file on disk (e.g. user-requested screenshot step).
        """
        # Fast path: exec-out straight to file (no on-device temp file)
        success, data = self.capture_screenshot_bytes(device_id)
        if success:
            try:
                with open(local_path, "wb") as f:
                    f.write(data)
                return True, local_path
            except Exception as e:
                return False, f"Failed to write screenshot file: {e}"

        # Fallback: legacy screencap -> pull -> rm (for emulators without exec-out)
        safe_id = device_id.replace(":", "_").replace(".", "_")
        remote_path = f"/data/local/tmp/screen_{safe_id}.png"
        ok, out = self.run_adb_cmd(["-s", device_id, "shell", "screencap", "-p", remote_path])
        if not ok:
            return False, f"Failed to take screenshot: {out}"
        ok, out = self.run_adb_cmd(["-s", device_id, "pull", remote_path, local_path])
        self.run_adb_cmd(["-s", device_id, "shell", "rm", remote_path])
        return ok, out

    def _match_template(self, screen, template, threshold):
        """Core OpenCV matchTemplate on already-loaded images. Returns (found, x, y, msg)."""
        if screen is None or template is None:
            return False, 0, 0, "Failed to load screenshot or template image"
        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= threshold:
            h, w, _ = template.shape
            click_x = int(max_loc[0] + w / 2)
            click_y = int(max_loc[1] + h / 2)
            return True, click_x, click_y, f"Match found (confidence: {max_val:.2f})"
        return False, 0, 0, f"No match found (best confidence: {max_val:.2f})"

    def find_image_in_bytes(self, screen_bytes, template_path, threshold=0.8):
        """Finds template_path within a screenshot held in memory (PNG bytes)."""
        try:
            if not os.path.exists(template_path):
                return False, 0, 0, "Template image file not found"
            if not screen_bytes:
                return False, 0, 0, "Empty screenshot data"
            screen = cv2.imdecode(np.frombuffer(screen_bytes, np.uint8), cv2.IMREAD_COLOR)
            template = cv2.imread(template_path)
            return self._match_template(screen, template, threshold)
        except Exception as e:
            return False, 0, 0, str(e)

    def find_image_on_screen(self, screen_path, template_path, threshold=0.8):
        """Finds template_path image on a screenshot file using OpenCV matchTemplate."""
        try:
            if not os.path.exists(screen_path):
                return False, 0, 0, "Screenshot file not found"
            if not os.path.exists(template_path):
                return False, 0, 0, "Template image file not found"
            screen = cv2.imread(screen_path)
            template = cv2.imread(template_path)
            return self._match_template(screen, template, threshold)
        except Exception as e:
            return False, 0, 0, str(e)
