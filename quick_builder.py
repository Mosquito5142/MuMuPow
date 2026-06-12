DEFAULT_COORDINATE_PRESETS = [
    {"name": "สมัคร: ช่อง Email", "x": 333.7, "y": 201.6},
    {"name": "สมัคร: ช่อง Password", "x": 333.7, "y": 242.6},
    {"name": "สมัคร: ช่องยืนยัน Password", "x": 333.7, "y": 281.5},
    {"name": "สมัคร: ปุ่มส่ง OTP", "x": 611.4, "y": 322.3},
    {"name": "สมัคร: ช่องกรอก OTP", "x": 333.7, "y": 325.3},
    {"name": "สมัคร: ปุ่มยืนยัน", "x": 485.5, "y": 402.2},
    {"name": "Login: ช่อง Email", "x": 450, "y": 211},
    {"name": "Login: ช่อง Password", "x": 450, "y": 260},
    {"name": "Login: ปุ่ม Login", "x": 451, "y": 293.5},
    {"name": "ปุ่ม Confirm", "x": 450, "y": 360},
    {"name": "ปุ่ม Close Ads", "x": 895, "y": 45},
]

KEY_CODES = {
    "BACK": "4",
    "HOME": "3",
    "MENU": "82",
    "ENTER": "66",
}


def _parse_coordinate(value):
    number = float(str(value).strip())
    if number.is_integer():
        return int(number)
    return number


def normalize_coordinate_preset(preset):
    name = str(preset.get("name", "")).strip()
    if not name:
        raise ValueError("Preset name is required")

    try:
        x = _parse_coordinate(preset.get("x", ""))
        y = _parse_coordinate(preset.get("y", ""))
    except ValueError as exc:
        raise ValueError("Preset coordinates must be numbers") from exc

    return {"name": name, "x": x, "y": y}


def normalize_coordinate_presets(presets):
    return [normalize_coordinate_preset(preset) for preset in presets]


def build_tap_step_from_preset(preset, delay=0.5):
    normalized = normalize_coordinate_preset(preset)
    return {
        "type": "tap",
        "x": str(normalized["x"]),
        "y": str(normalized["y"]),
        "delay": float(delay),
        "desc": f"คลิก {normalized['name']}",
    }


def build_text_step(text, delay=0.5):
    return {
        "type": "text",
        "text": str(text),
        "delay": float(delay),
        "desc": f"พิมพ์ {text}",
    }


def build_sleep_step(seconds):
    return {
        "type": "sleep",
        "seconds": float(seconds),
        "desc": f"รอ {float(seconds):g} วิ",
    }


def build_key_step(key_name, delay=0.3):
    key = str(key_name).upper()
    if key not in KEY_CODES:
        raise ValueError(f"Unsupported key: {key_name}")
    return {
        "type": "keyevent",
        "code": KEY_CODES[key],
        "delay": float(delay),
        "desc": f"กด {key}",
    }


def build_swipe_step(direction, delay=0.5):
    direction_key = str(direction).lower()
    if direction_key == "up":
        return {
            "type": "swipe",
            "x": "450",
            "y": "420",
            "x2": "450",
            "y2": "160",
            "delay": float(delay),
            "desc": "เลื่อนขึ้น",
        }
    if direction_key == "down":
        return {
            "type": "swipe",
            "x": "450",
            "y": "160",
            "x2": "450",
            "y2": "420",
            "delay": float(delay),
            "desc": "เลื่อนลง",
        }
    raise ValueError(f"Unsupported swipe direction: {direction}")
