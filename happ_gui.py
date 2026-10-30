import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, scrolledtext, filedialog
import uuid
import json
import random
import re
import string
import base64
import urllib.parse
import threading
import os
import sys
import time
import shutil
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

import requests as plain_requests

try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5, ChaCha20_Poly1305
except ImportError:
    import tkinter as _tk
    _r = _tk.Tk()
    _r.withdraw()
    _tk.messagebox.showerror("Ошибка", "Нужны библиотеки:\npip install pycryptodome requests curl_cffi paramiko")
    sys.exit(1)

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    import socks as pysocks
    HAS_SOCKS = True
except ImportError:
    HAS_SOCKS = False


APP_NAME = "HappDecoder"
APP_VERSION = "1.0.0"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    if "compiled" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0] or sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "HappDecoder")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = app_dir()
    return d


for _name in ("device_profile.json", "router_config.json", "crypt5_keys.json"):
    _dst = os.path.join(config_dir(), _name)
    _src = os.path.join(app_dir(), _name)
    if not os.path.exists(_dst) and os.path.exists(_src):
        try:
            shutil.copyfile(_src, _dst)
        except Exception:
            pass

PROFILE_PATH = os.path.join(config_dir(), "device_profile.json")
ROUTER_CONFIG_PATH = os.path.join(config_dir(), "router_config.json")
C5_KEYS_PATH = os.path.join(config_dir(), "crypt5_keys.json")

PAD = 20
GAP = 6
ROW_GAP = (0, 6)

LOCALES = ["ru-RU", "en-US", "en-GB", "de-DE", "fr-FR", "tr-TR", "nl-NL", "fi-FI", "es-ES", "pl-PL"]
IMPERSONATE_POOL = ["chrome", "firefox", "safari", "edge", "safari_ios"]

UTLS_ALLOWED = {
    "chrome", "firefox", "safari", "edge", "ios", "android", "360", "qq",
    "random", "randomized", "ios13", "ios14", "ios15", "ios16", "ios17",
    "android4", "unsafe"
}


def _fp(v):
    v = (v or "").lower()
    return v if v in UTLS_ALLOWED else "chrome"


PARSE_STATS = {"raw": 0, "unique": 0}


def pretty_name(s):
    if not s:
        return s
    out = []
    i = 0
    n = len(s)
    while i < n:
        o = ord(s[i])
        if 0x1F1E6 <= o <= 0x1F1FF and i + 1 < n:
            o2 = ord(s[i + 1])
            if 0x1F1E6 <= o2 <= 0x1F1FF:
                out.append("[" + chr(65 + o - 0x1F1E6) + chr(65 + o2 - 0x1F1E6) + "]")
                i += 2
                continue
        out.append(s[i])
        i += 1
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def extract_country(name):
    m = re.search(r"\[([A-Z]{2})\]", name or "")
    return m.group(1) if m else "??"


class ToolTip:
    def __init__(self, widget, text, delay=400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tw = None
        self._after = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, event=None):
        self._unschedule()
        self._after = self.widget.after(self.delay, self._show)

    def _unschedule(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        if self.tw or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            sw = self.widget.winfo_screenwidth()
            tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.attributes("-topmost", True)
            frame = tk.Frame(tw, bg="#fffbe6", highlightbackground="#d9c36a", highlightthickness=1)
            tk.Label(
                frame,
                text=self.text,
                justify="left",
                bg="#fffbe6",
                fg="#4a3f10",
                font=("Segoe UI", 9),
                padx=10,
                pady=7,
                wraplength=min(460, sw - 80)
            ).pack()
            frame.pack()
            tw.update_idletasks()
            if x + tw.winfo_reqwidth() > sw - 8:
                x = sw - tw.winfo_reqwidth() - 8
            tw.wm_geometry(f"+{x}+{y}")
            self.tw = tw
        except Exception:
            self.tw = None

    def _hide(self, event=None):
        self._unschedule()
        if self.tw:
            try:
                self.tw.destroy()
            except Exception:
                pass
            self.tw = None


def tip(widget, text):
    ToolTip(widget, text)
    return widget


def _ios(label, ver, model, names):
    ua_ver = ver.replace(".", " ")
    base = (
        f"Mozilla/5.0 (iPhone; CPU iPhone OS {ua_ver} like Mac OS X) "
        f"AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{ver} Mobile/15E148 Safari/604.1"
    )
    return {
        "os": "iOS",
        "ver": ver,
        "model": model,
        "impersonate": "safari_ios",
        "ua": base + " Happ/4.3.0",
        "names": names,
        "mobile": True
    }


def _android(label, ver, model, names=None):
    base = (
        f"Mozilla/5.0 (Linux; Android {ver}; {model}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/125.0.6422.113 Mobile Safari/537.36"
    )
    return {
        "os": "Android",
        "ver": ver,
        "model": model,
        "impersonate": "chrome",
        "ua": base + " Happ/4.3.0",
        "names": names or [model],
        "mobile": True
    }


DEVICES = {
    "iPhone 15 Pro Max (iOS)": _ios("iPhone 15 Pro Max", "17.5", "iPhone15,3",
                                    ["iPhone 15 Pro Max", "iPhone 15 Pro", "iPhone 14 Pro"]),
    "iPhone 13 (iOS)": _ios("iPhone 13", "18.0", "iPhone14,5",
                            ["iPhone 13", "iPhone 13 mini", "iPhone 13 Pro"]),
    "iPhone 12 (iOS)": _ios("iPhone 12", "17.6", "iPhone13,2",
                            ["iPhone 12", "iPhone 12 mini", "iPhone 12 Pro"]),
    "iPhone 11 (iOS)": _ios("iPhone 11", "17.5", "iPhone12,1",
                            ["iPhone 11", "iPhone 11 Pro", "iPhone 11 Pro Max"]),
    "iPhone XR (iOS)": _ios("iPhone XR", "17.6", "iPhone11,8",
                            ["iPhone XR", "iPhone XS", "iPhone XS Max"]),
    "iPhone SE 2022 (iOS)": _ios("iPhone SE 2022", "17.4", "iPhone14,6",
                                 ["iPhone SE 2022", "iPhone SE 2020"]),
    "Samsung Galaxy A54 (Android)": _android("Galaxy A54", "14", "SM-A546B", ["Galaxy A54", "Galaxy A54 5G"]),
    "Samsung Galaxy A55 (Android)": _android("Galaxy A55", "14", "SM-A556B", ["Galaxy A55", "Galaxy A55 5G"]),
    "Samsung Galaxy A34 (Android)": _android("Galaxy A34", "13", "SM-A346B", ["Galaxy A34", "Galaxy A34 5G"]),
    "Samsung Galaxy S21 FE (Android)": _android("Galaxy S21 FE", "13", "SM-G990B", ["Galaxy S21 FE", "Galaxy S21"]),
    "Samsung Galaxy S24 Ultra (Android)": _android("Galaxy S24 Ultra", "14", "SM-S928B",
                                                   ["Galaxy S24 Ultra", "Galaxy S24+", "Galaxy S23 Ultra"]),
    "Xiaomi Redmi Note 12 (Android)": _android("Redmi Note 12", "13", "Redmi Note 12",
                                               ["Redmi Note 12", "Redmi Note 12S"]),
    "Xiaomi Redmi Note 13 Pro (Android)": _android("Redmi Note 13 Pro", "14", "Redmi Note 13 Pro",
                                                   ["Redmi Note 13 Pro", "Redmi Note 13"]),
    "Xiaomi POCO X6 Pro (Android)": _android("POCO X6 Pro", "14", "POCO X6 Pro",
                                             ["POCO X6 Pro", "POCO X6", "POCO X5 Pro"]),
    "Xiaomi Redmi 12 (Android)": _android("Redmi 12", "13", "Redmi 12", ["Redmi 12", "Redmi 12C", "Redmi 10"]),
    "Realme 11 Pro (Android)": _android("Realme 11 Pro", "13", "RMX3771",
                                        ["Realme 11 Pro", "Realme 11", "Realme C55"]),
    "Oppo Reno 11 (Android)": _android("Oppo Reno 11", "14", "CPH2601",
                                       ["Oppo Reno 11", "Oppo Reno 8", "Oppo A78"]),
    "Vivo Y36 (Android)": _android("Vivo Y36", "13", "V2244", ["Vivo Y36", "Vivo Y27", "Vivo V29"]),
    "Honor X9a (Android)": _android("Honor X9a", "12", "ANY-NX1",
                                    ["Honor X9a", "Honor X8a", "Honor Magic5 Lite"]),
    "OnePlus Nord CE 3 (Android)": _android("OnePlus Nord CE 3", "14", "CPH2491",
                                            ["OnePlus Nord CE 3", "OnePlus Nord 2T", "OnePlus 9"]),
    "Motorola Moto G84 (Android)": _android("Moto G84", "14", "XT2347-2",
                                            ["Moto G84", "Moto G54", "Moto G73"]),
    "Google Pixel 8 Pro (Android)": _android("Pixel 8 Pro", "14", "Pixel 8 Pro",
                                             ["Pixel 8 Pro", "Pixel 8", "Pixel 7a"]),
    "MacBook Pro (macOS)": {
        "os": "macOS",
        "ver": "14.5",
        "model": "MacBookPro18,1",
        "impersonate": "safari",
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15 Happ/4.3.0",
        "names": ["MacBook Pro 14", "MacBook Air M2", "iMac 24"],
        "mobile": False
    },
    "Windows 11 PC": {
        "os": "Windows",
        "ver": "11",
        "model": "Desktop",
        "impersonate": "chrome",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Happ/4.3.0",
        "names": ["Desktop PC", "ASUS ROG", "Lenovo Legion"],
        "mobile": False
    },
    "Linux (Ubuntu)": {
        "os": "Linux",
        "ver": "24.04",
        "model": "Ubuntu",
        "impersonate": "chrome",
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Happ/4.3.0",
        "names": ["Ubuntu Desktop", "Fedora Workstation"],
        "mobile": False
    },
}

# ---------------------------------------------------------------------------
# Client identity, ported from NetShift 0.9.12
# (fe-app-netshift/src/helpers/clientIdentity.ts). Panels like Remnawave serve a
# subscription only to the app/device it was issued for and check User-Agent,
# X-HWID, X-Device-OS, X-Ver-OS and X-Device-Model, so these must look native.
# ---------------------------------------------------------------------------
_HEX = "0123456789abcdef"
_ALNUM = "0123456789abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"
_HOSTCHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

ANDROID_MODELS = ["CPH2747", "SM-A556E", "SM-S721B", "SM-S938B", "SM-S918N", "2112123AG"]
IPHONE_MODELS = ["iPhone 15 Pro Max", "iPhone 16 Pro Max", "iPhone 17 Pro",
                 "iPhone 13", "iPhone 16", "iPhone 15 Pro"]

CLIENT_IDENTITY_PROFILES = {
    "Happ": {
        "Android": {
            "hwid": "android", "device_os": "Android",
            "variants": [("Happ/4.7.1/Android/{install}", v)
                         for v in ("16", "15", "14", "13")],
            "models": ANDROID_MODELS,
        },
        "AndroidTV": {
            "hwid": "android", "device_os": "AndroidTV",
            "variants": [("Happ/4.7.1/AndroidTV/{install}", v)
                         for v in ("14", "12", "11")],
            "models": ["MiTV-MOOQ1", "MiTV-AFKR0", "VONTAR H618", "4K PA Google TV"],
        },
        "iOS": {
            "hwid": "apple", "device_os": "iOS",
            "variants": [("Happ/6.1.0/ios/2610091516618", v)
                         for v in ("26.6.2", "26.6.1", "27.0.1")],
            "models": IPHONE_MODELS,
        },
        "macOS": {
            "hwid": "apple", "device_os": "macOS",
            "variants": [("Happ/6.1.0/macos catalyst/2610091518671", v)
                         for v in ("27.0.1", "26.6.2", "15.7.9")],
            "models": ["Mac", "MacBook", "iMac"],
        },
        "Windows": {
            "hwid": "uuid", "device_os": "Windows",
            "variants": [("Happ/4.5.4/Windows/2610141139602", v)
                         for v in ("11_10.0.26200", "10_10.0.19045", "11_10.0.26100")],
            "models": ["DESKTOP-{host}_x86_64"],
        },
    },
    "INCY": {
        "Android": {
            "hwid": "incy", "device_os": "Android",
            "variants": [("INCY/3.7.9/android Dalvik/2.1.0", v)
                         for v in ("16", "15", "14", "13")],
            "models": ["samsung SM-S938B", "samsung SM-A546E", "samsung SM-A556E",
                       "Xiaomi 24116RACCG", "Xiaomi 2311DRK48G"],
        },
        "iOS": {
            "hwid": "incy", "device_os": "iOS",
            "variants": [
                ("INCY/2.6.4/ios CFNetwork/3896.100.1.2.1 Darwin/27.0.0", "27.0.1"),
                ("INCY/2.6.4/ios CFNetwork/3860.700.2 Darwin/25.6.0", "26.6.2"),
                ("INCY/2.6.4/ios CFNetwork/3860.700.2 Darwin/25.6.0", "26.6.1"),
            ],
            "models": IPHONE_MODELS,
        },
        "Mac OS X": {
            "hwid": "incy", "device_os": "Mac OS X",
            "variants": [
                ("INCY/3.8.8/mac os x Dalvik/21.0.11+10-LTS", "26.6.2"),
                ("INCY/3.8.8/mac os x Dalvik/21.0.11+10-LTS", "15.3.1"),
            ],
            "models": ["Mac OS X aarch64"],
        },
        "Windows 11": {
            "hwid": "incy", "device_os": "Windows 11",
            "variants": [("INCY/3.9.0/windows 11 Dalvik/21.0.12+8-LTS", "10.0")],
            "models": ["Windows 11 amd64"],
        },
        "Windows 10": {
            "hwid": "incy", "device_os": "Windows 10",
            "variants": [("INCY/3.8.10/windows 10 Dalvik/21.0.12+8-LTS", "10.0")],
            "models": ["Windows 10 amd64"],
        },
    },
}

CLIENT_CHOICES = ["— не маскировать —", "Happ", "INCY"]
CLIENT_PLATFORMS = {
    "Happ": ["Android", "AndroidTV", "iOS", "macOS", "Windows"],
    "INCY": ["Android", "iOS", "Mac OS X", "Windows 11", "Windows 10"],
}

# What platforms/devices of the built-in list map to (app, platform).
DEVICE_PLATFORM = {
    "iOS": ("Happ", "iOS"),
    "Android": ("Happ", "Android"),
    "macOS": ("Happ", "macOS"),
    "Windows": ("Happ", "Windows"),
    "Linux": ("Happ", "Android"),
}


def _rchars(alphabet, length):
    return "".join(random.choice(alphabet) for _ in range(length))


def _fill_template(template):
    out = template
    while "{install}" in out:
        out = out.replace("{install}", random.choice("123456789") + _rchars(_DIGITS, 19), 1)
    while "{host}" in out:
        out = out.replace("{host}", _rchars(_HOSTCHARS, 7), 1)
    return out


def _identity_hwid(kind):
    if kind == "android":          # Happ on Android: 64-bit Android ID
        return _rchars(_HEX, 16)
    if kind == "apple":            # Happ on iOS/macOS: 16 base36 chars
        return _rchars(_ALNUM, 16)
    if kind == "uuid":             # Happ on Windows: UUID v4
        return str(uuid.uuid4())
    if kind == "incy":             # INCY: SHA-256 cut to UUID layout, upper case
        h = _rchars(_HEX, 32).upper()
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    return str(uuid.uuid4())


def generate_client_identity(app, platform, fixed_hwid=None, model_override=None):
    """Build the exact UA/HWID/OS/model a real Happ or INCY install sends."""
    profile = (CLIENT_IDENTITY_PROFILES.get(app) or {}).get(platform)
    if not profile:
        return None
    ua_tpl, os_version = random.choice(profile["variants"])
    model = model_override or _fill_template(random.choice(profile["models"]))
    return {
        "app": app,
        "platform": platform,
        "ua": _fill_template(ua_tpl),
        "hwid": fixed_hwid or _identity_hwid(profile["hwid"]),
        "device_os": profile["device_os"],
        "os_version": os_version,
        "device_model": model,
        "impersonate": "safari_ios" if platform in ("iOS", "macOS", "Mac OS X") else "chrome",
        "mobile": platform in ("Android", "AndroidTV", "iOS"),
    }


# User-Agents NetShift 0.9.12 probes when a panel serves a different body per
# client (subscriptions and auto-probing in helpers.sh):
# SUBSCRIPTION_USER_AGENT_CANDIDATES + SUBSCRIPTION_USER_AGENT_XRAY_CANDIDATES.
UA_FALLBACKS = [
    "v2rayN", "Happ", "Hiddify", "Clash.Meta", "ClashMetaForAndroid",
    "Happ/1.0.0", "v2rayN/7.0.0", "v2rayNG/1.9.0",
]
DEFAULT_ACCEPT_LANGUAGE = "ru-RU,en,*"


def build_subscription_headers(ident, ua=None):
    """Headers a Happ/INCY install sends. Mirrors NetShift 0.9.12
    _wget_subscription_request: User-Agent, X-HWID, X-Device-OS,
    X-Device-Model, X-Ver-OS, Accept-Language, X-Device-Locale."""
    d = ident["dev"]
    locale = (ident.get("locale") or "ru-RU")
    headers = {
        "User-Agent": ua or ident.get("ua") or d.get("ua", ""),
        "Accept": "*/*",
        "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
        "X-HWID": ident["hwid"],
        "X-Device-OS": d.get("os_header") or d.get("os", ""),
        "X-Ver-OS": str(d.get("ver", "")),
        "X-Device-Model": d.get("model", ""),
        "X-Device-Locale": locale.split("-")[0].upper()[:2],
    }
    if ident.get("name"):
        headers["X-Device-Name"] = ident["name"]
    return headers


def dev_from_identity(ident):
    """Turn a generated identity into the device record the UI/proxy code uses."""
    return {
        "os": ident["device_os"],
        "ver": ident["os_version"],
        "model": ident["device_model"],
        "ua": ident["ua"],
        "impersonate": ident["impersonate"],
        "mobile": ident["mobile"],
        "os_header": ident["device_os"],
        "names": [ident["device_model"]],
        "client": ident["app"],
    }


PKCS1_KEYS_B64 = [
    "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"
]


def shuffle_blocks(text, block_size, order):
    out = bytearray()
    full_len = (len(text) // block_size) * block_size
    for i in range(0, full_len, block_size):
        block = text[i:i + block_size]
        for idx in order:
            out.append(block[idx])
    out.extend(text[full_len:])
    return bytes(out)


def m4842j(text):
    return shuffle_blocks(text, 2, [1, 0])


def permute4(text):
    return shuffle_blocks(text, 4, [2, 3, 0, 1])


def b64_decode_bytes(text):
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    for b64_func in (base64.b64decode, base64.urlsafe_b64decode):
        for candidate in (text, text.rstrip("=")):
            padded = candidate + "=" * ((4 - len(candidate) % 4) % 4)
            try:
                return b64_func(padded)
            except Exception:
                pass
    raise Exception("Invalid Base64")


def load_pkcs1_key(b64_key):
    b64_key = "".join(b64_key.split())
    lines = [b64_key[i:i + 64] for i in range(0, len(b64_key), 64)]
    pem = "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END RSA PRIVATE KEY-----"
    return RSA.import_key(pem)


def decrypt_crypt5_payload(payload, c5_keys):
    shuffled = permute4(payload.encode("utf-8"))
    if len(shuffled) < 8:
        raise Exception("Слишком короткий payload")
    marker = (shuffled[:4] + shuffled[-4:]).decode("utf-8")
    body = shuffled[4:-4]
    if len(body) < 23:
        raise Exception("Слишком короткое тело")
    if marker not in c5_keys:
        raise Exception(f"Неизвестный маркер {marker}")
    nonce = body[:12]
    rest = body[12:]
    layouts = [False, True] if (rest and chr(rest[0]).isdigit()) else [True, False]
    last_err = None
    for salted in layouts:
        try:
            if salted:
                salt, cursor = rest[2:10], rest[10:]
            else:
                salt, cursor = None, rest
            dc = 0
            for b in cursor:
                if chr(b).isdigit():
                    dc += 1
                else:
                    break
            if dc == 0:
                raise Exception("Не найдена длина сегмента")
            seg_len = int(cursor[:dc].decode("utf-8"))
            packed = cursor[dc:]
            if len(packed) < 1 + seg_len:
                raise Exception("Сегмент обрезан")
            seg = packed[1:1 + seg_len]
            rsa_ct = packed[1 + seg_len:]
            rsa_key = RSA.import_key(b64_decode_bytes(c5_keys[marker]))
            plain = PKCS1_v1_5.new(rsa_key).decrypt(b64_decode_bytes(rsa_ct.decode("utf-8")), sentinel=b"")
            if plain == b"":
                raise Exception("Ошибка RSA")
            value = b64_decode_bytes(m4842j(plain).decode("utf-8"))
            if len(value) != 32:
                raise Exception("Неверная длина ключа")
            chacha_key = bytes(a ^ b for a, b in zip(value, (salt * 4)[:32])) if salted else value
            ct_with_tag = b64_decode_bytes(seg.decode("utf-8"))
            if len(ct_with_tag) < 17:
                raise Exception("Сегмент слишком короткий")
            ct, mac = ct_with_tag[:-16], ct_with_tag[-16:]
            pt = ChaCha20_Poly1305.new(key=chacha_key, nonce=nonce).decrypt_and_verify(ct, mac)
            return base64.b64decode(m4842j(pt).decode("utf-8")).decode("utf-8")
        except Exception as e:
            last_err = e
    raise last_err if last_err else Exception("Crypt5: не удалось расшифровать")


_PKCS1_CACHE = None
_C5_KEYS_CACHE = None


def _pkcs1_keys():
    global _PKCS1_CACHE
    if _PKCS1_CACHE is None:
        _PKCS1_CACHE = [load_pkcs1_key(k) for k in PKCS1_KEYS_B64]
    return _PKCS1_CACHE


def load_c5_keys():
    global _C5_KEYS_CACHE
    if _C5_KEYS_CACHE is not None:
        return _C5_KEYS_CACHE
    if not os.path.exists(C5_KEYS_PATH):
        url = "https://raw.githubusercontent.com/LeeeeT/happ-decryptor/main/public/data/crypt5-keys.json"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, C5_KEYS_PATH)
        except Exception:
            r = http_get(url, timeout=20)
            with open(C5_KEYS_PATH, "wb") as f:
                f.write(r.content)
    with open(C5_KEYS_PATH, encoding="utf-8") as f:
        _C5_KEYS_CACHE = json.load(f)
    return _C5_KEYS_CACHE


def decrypt_link(value):
    value = (value or "").strip()
    if value.startswith("happ://add/"):
        return value[len("happ://add/"):]
    pkcs1_keys = _pkcs1_keys()
    prefixes = [
        ("happ://crypt5/", 4),
        ("happ://crypt4/", 3),
        ("happ://crypt3/", 2),
        ("happ://crypt2/", 1),
        ("happ://crypt/", 0)
    ]
    mode, payload = -1, value
    for p, m in prefixes:
        if value.startswith(p):
            mode, payload = m, value[len(p):]
            break
    if mode == -1:
        return value
    if mode != 4:
        encrypted = b64_decode_bytes(payload)
        last_err = None
        for m in [mode] + [x for x in range(4) if x != mode]:
            try:
                cipher = PKCS1_v1_5.new(pkcs1_keys[m])
                block_size = 128 if m == 0 else 512
                if len(encrypted) % block_size != 0:
                    continue
                plaintext = b""
                success = True
                for i in range(0, len(encrypted), block_size):
                    dec = cipher.decrypt(encrypted[i:i + block_size], sentinel=b"")
                    if dec == b"":
                        success = False
                        break
                    plaintext += dec
                if success:
                    return plaintext.decode("utf-8")
            except Exception as e:
                last_err = e
        raise Exception(f"Ошибка RSA: {last_err} (ни один ключ не подошел)")
    return decrypt_crypt5_payload(payload, load_c5_keys())


def fix_encoding(s):
    if not s:
        return s
    if any("\u0400" <= c <= "\u04FF" or "\U0001F1E0" <= c <= "\U0001F1FF" for c in s):
        return s
    best, best_score = s, 0
    for src_enc in ("latin1", "cp1252", "iso-8859-1"):
        try:
            raw = s.encode(src_enc)
        except Exception:
            continue
        try:
            candidate = raw.decode("utf-8")
        except Exception:
            continue
        score = 0
        if len(candidate) < len(s):
            score += (len(s) - len(candidate)) * 10
        if any("\u0400" <= c <= "\u04FF" for c in candidate):
            score += 100
        if any("\U0001F1E0" <= c <= "\U0001F1FF" for c in candidate):
            score += 50
        if score > best_score:
            best_score, best = score, candidate
    return best


SCHEMES = (
    "vless://", "vmess://", "hysteria://", "hysteria2://", "hy2://",
    "trojan://", "ss://", "socks://", "socks5://", "socks4://", "socks4a://",
    "tuic://", "shadowtls://", "anytls://",
    "naive+https://", "naive+quic://"
)

# NetShift 0.9.12 (sing-box-extended) parses these schemes itself:
# vless | vmess | trojan | ss | hysteria2 | tuic | anytls | socks4/4a/5 | naive.
# Legacy hysteria:// (v1) is not in NetShift's candidate list — skip it on upload.
NETSHIFT_PROTOS = {
    "vless", "vmess", "trojan", "ss", "hysteria2",
    "tuic", "anytls", "socks", "socks4", "socks4a", "socks5", "naive"
}
# Podkop 0.7.24 accepts only these (luci-app-podkop validateProxyUrl):
# vless://, ss://, trojan://, socks4/5://, hysteria2://hy2://
PODKOP_PROTOS = {"vless", "trojan", "ss", "hysteria2", "socks4", "socks4a", "socks5", "socks"}

# AnyTLS landed in sing-box 1.12; NetShift skips it on older cores.
PROTO_MIN_VERSION = {"anytls": (1, 12)}

PROTO_ALIASES = {
    "hy2": "hysteria2",
    "socks5": "socks5",
    "socks": "socks5",
    "socks4": "socks4",
    "socks4a": "socks4a",
    "shadowsocks": "ss",
    "naive+https": "naive",
    "naive+quic": "naive",
}

SKIP_TAGS = {"direct", "block", "loopback", "loop_to_cdn", "freedom", "blackhole", "dns"}


def link_scheme(link):
    """Raw scheme of a proxy link (lowercased), e.g. 'hy2', 'anytls', 'socks5'."""
    return (link or "").split("://", 1)[0].strip().lower()


def link_proto(link):
    """Normalized protocol name used everywhere inside the app."""
    s = link_scheme(link)
    return PROTO_ALIASES.get(s, s)


def is_supported_by(service, link):
    """Whether the router service can parse this link format."""
    proto = link_proto(link)
    if service == "Podkop":
        return proto in PODKOP_PROTOS
    return proto in NETSHIFT_PROTOS


def _b64enc(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return base64.b64encode(s).decode("ascii")


def _q(v, safe=""):
    return urllib.parse.quote(str(v), safe=safe) if v not in (None, "", False) else ""


def link_dedup_key(link):
    try:
        u = urllib.parse.urlsplit(link)
        scheme = u.scheme.lower()
        if scheme == "hy2":
            scheme = "hysteria2"
        if scheme == "vmess":
            try:
                v = json.loads(base64.b64decode(u.netloc).decode("utf-8", errors="ignore"))
                return "|".join([
                    "vmess", str(v.get("add", "")), str(v.get("port", "")),
                    str(v.get("id", "")), str(v.get("net", "")),
                    str(v.get("tls", "")), str(v.get("sni", "")),
                    str(v.get("path", "")), str(v.get("host", "")),
                    str(v.get("type", ""))
                ])
            except Exception:
                return link.split("#", 1)[0]
        q = urllib.parse.parse_qs(u.query)
        scheme = PROTO_ALIASES.get(scheme, scheme)
        hp_host, hp_port = _hostport_from_netloc(u.netloc)
        core = [scheme, hp_host.lower(), str(hp_port), (u.username or "")]
        for k in ("type", "security", "sni", "pbk", "sid", "path", "host",
                  "serviceName", "mode", "flow", "alpn", "fp", "insecure",
                  "allowInsecure", "mport", "ports", "hop-interval", "hop_interval",
                  "obfs", "obfs-password", "congestion_control", "udp_relay_mode"):
            core.append(",".join(q.get(k, [])))
        return "|".join(core)
    except Exception:
        return link.split("#", 1)[0]


def dedup_links(links):
    seen, out = set(), []
    for l in links:
        k = link_dedup_key(l)
        if k not in seen:
            seen.add(k)
            out.append(l)
    return out


def _sb_tls_params(ob):
    """TLS/reality params from a sing-box outbound ('tls' object)."""
    tls = ob.get("tls") or {}
    if not isinstance(tls, dict) or not tls.get("enabled"):
        return "none", {}
    p = {}
    if tls.get("server_name"):
        p["sni"] = tls["server_name"]
    utls = tls.get("utls") or {}
    if isinstance(utls, dict) and utls.get("fingerprint"):
        p["fp"] = utls["fingerprint"]
    reality = tls.get("reality") or {}
    sec = "tls"
    if isinstance(reality, dict) and reality.get("enabled"):
        sec = "reality"
        p["pbk"] = reality.get("public_key", "")
        p["sid"] = reality.get("short_id", "")
    alpn = tls.get("alpn")
    if alpn:
        p["alpn"] = ",".join(alpn) if isinstance(alpn, list) else str(alpn)
    if tls.get("insecure"):
        p["allowInsecure"] = "1"
    return sec, p


def _sb_transport_params(ob):
    """Transport params from a sing-box outbound ('transport' object)."""
    tr = ob.get("transport") or {}
    if not isinstance(tr, dict):
        return "tcp", {"type": "tcp"}
    net = (tr.get("type") or "tcp").lower()
    p = {"type": net}
    if net in ("ws", "httpupgrade", "xhttp"):
        if tr.get("path"):
            p["path"] = tr["path"]
        host = (tr.get("headers") or {}).get("Host")
        if host:
            p["host"] = host
    elif net == "grpc":
        p["serviceName"] = tr.get("service_name", "") or tr.get("serviceName", "")
    elif net == "http":
        if tr.get("path"):
            p["path"] = tr["path"]
        host = tr.get("host")
        if isinstance(host, list):
            host = ",".join(host)
        if host:
            p["host"] = host
    return net, p


def _build_from_singbox(ob, remarks, tag):
    """sing-box outbound -> share link (NetShift panels often answer with
    sing-box JSON, not Xray JSON)."""
    typ = (ob.get("type") or "").lower()
    addr = ob.get("server", "") or ob.get("address", "")
    port = ob.get("server_port") or 443
    ports = ob.get("server_ports")
    name = _q(f"{remarks} | {tag}" if remarks else tag, safe="-.~!$&'()*+,;=:@")
    sec, sp = _sb_tls_params(ob)
    net, tp = _sb_transport_params(ob)
    host = _q(addr, safe="-.[]")
    if not addr:
        return None

    if typ == "vless":
        params = dict(tp)
        params["security"] = sec
        if ob.get("flow"):
            params["flow"] = ob["flow"]
        if ob.get("packet_encoding"):
            params["packetEncoding"] = ob["packet_encoding"]
        params.update({k: v for k, v in sp.items() if v})
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in ("", None, False)})
        return f"vless://{_q(ob.get('uuid', ''))}@{host}:{port}?{qs}" + (f"#{name}" if name else "")
    if typ == "vmess":
        vmess = {
            "v": "2",
            "ps": urllib.parse.unquote(name) if name else "vmess",
            "add": addr,
            "port": port,
            "id": ob.get("uuid", ""),
            "aid": ob.get("alter_id", 0),
            "scy": ob.get("security", "auto") or "auto",
            "net": net,
            "type": "none",
            "host": tp.get("host", ""),
            "path": tp.get("path", "") if net != "grpc" else tp.get("serviceName", ""),
            "tls": sec if sec in ("tls", "reality") else "",
            "sni": sp.get("sni", ""),
            "alpn": sp.get("alpn", ""),
            "fp": sp.get("fp", ""),
        }
        if sec == "reality":
            vmess["pbk"] = sp.get("pbk", "")
            vmess["sid"] = sp.get("sid", "")
        return "vmess://" + _b64enc(json.dumps(vmess, separators=(",", ":")))
    if typ == "trojan":
        params = dict(tp)
        params["security"] = sec
        params.update({k: v for k, v in sp.items() if v})
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in ("", None, False)})
        return f"trojan://{_q(ob.get('password', ''))}@{host}:{port}?{qs}" + (f"#{name}" if name else "")
    if typ in ("shadowsocks", "ss"):
        userinfo = _b64enc(f"{ob.get('method', 'aes-256-gcm')}:{ob.get('password', '')}")
        tail = f"#{name}" if name else ""
        if ob.get("plugin"):
            opts = ob.get("plugin_opts", "")
            plugin = ob["plugin"] + (f";{opts}" if opts else "")
            return f"ss://{userinfo}@{host}:{port}?plugin={urllib.parse.quote(plugin, safe='')}{tail}"
        return f"ss://{userinfo}@{host}:{port}{tail}"
    if typ in ("hysteria2", "hysteria"):
        params = {}
        if sp.get("sni"):
            params["sni"] = sp["sni"]
        if sp.get("alpn"):
            params["alpn"] = sp["alpn"]
        obfs = ob.get("obfs") or {}
        if isinstance(obfs, dict) and obfs.get("type"):
            params["obfs"] = obfs["type"]
            if obfs.get("password"):
                params["obfs-password"] = obfs["password"]
        if ob.get("up_mbps"):
            params["upmbps"] = ob["up_mbps"]
        if ob.get("down_mbps"):
            params["downmbps"] = ob["down_mbps"]
        if ports:
            params["mport"] = ",".join(ports) if isinstance(ports, list) else str(ports)
        if ob.get("hop_interval"):
            params["hop-interval"] = str(ob["hop_interval"]).rstrip("s")
        scheme = "hysteria2" if typ == "hysteria2" else "hysteria"
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in ("", None, False)})
        return f"{scheme}://{_q(ob.get('password', ''))}@{host}:{port}?{qs}" + (f"#{name}" if name else "")
    if typ == "tuic":
        params = {}
        if sp.get("sni"):
            params["sni"] = sp["sni"]
        if sp.get("alpn"):
            params["alpn"] = sp["alpn"]
        if ob.get("congestion_control"):
            params["congestion_control"] = ob["congestion_control"]
        if ob.get("udp_relay_mode"):
            params["udp_relay_mode"] = ob["udp_relay_mode"]
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in ("", None, False)})
        user = f"{_q(ob.get('uuid', ''))}:{_q(ob.get('password', ''))}"
        return f"tuic://{user}@{host}:{port}?{qs}" + (f"#{name}" if name else "")
    if typ == "anytls":
        params = {}
        if sp.get("sni"):
            params["sni"] = sp["sni"]
        if sp.get("alpn"):
            params["alpn"] = sp["alpn"]
        if sp.get("allowInsecure"):
            params["insecure"] = "1"
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in ("", None, False)})
        return f"anytls://{_q(ob.get('password', ''))}@{host}:{port}?{qs}" + (f"#{name}" if name else "")
    if typ in ("socks", "socks5", "socks4"):
        version = str(ob.get("version", "5"))
        cred = ""
        if ob.get("username"):
            cred = f"{_q(ob.get('username'))}:{_q(ob.get('password', ''))}@"
        return f"socks{version}://{cred}{host}:{port}" + (f"#{name}" if name else "")
    return None


def extract_links_from_clash(data):
    """Clash/Mihomo 'proxies:' YAML -> share links."""
    proxies = (data or {}).get("proxies") if isinstance(data, dict) else None
    if not isinstance(proxies, list):
        return []
    raw_links = []
    for p in proxies:
        if not isinstance(p, dict):
            continue
        typ = str(p.get("type", "")).lower()
        addr = p.get("server", "")
        port = p.get("port", 443)
        name = _q(str(p.get("name", "") or ""), safe="-.~!$&'()*+,;=:@")
        if not addr:
            continue
        sni = p.get("servername") or p.get("sni") or ""
        fp = p.get("client-fingerprint") or ""
        alpn = p.get("alpn")
        if isinstance(alpn, list):
            alpn = ",".join(str(a) for a in alpn)
        ws = p.get("ws-opts") or {}
        grpc = p.get("grpc-opts") or {}
        network = p.get("network") or ("ws" if ws else ("grpc" if grpc else "tcp"))
        host = ""
        path = ""
        service = grpc.get("grpc-service-name", "")
        if ws:
            path = ws.get("path", "")
            host = (ws.get("headers") or {}).get("Host", "")
        reality = p.get("reality-opts") or {}
        security = "reality" if reality else ("tls" if p.get("tls") else "none")
        base = {"type": network, "security": security}
        if sni:
            base["sni"] = sni
        if fp:
            base["fp"] = fp
        if alpn:
            base["alpn"] = alpn
        if path:
            base["path"] = path
        if host:
            base["host"] = host
        if service:
            base["serviceName"] = service
        if reality:
            base["pbk"] = reality.get("public-key", "")
            base["sid"] = reality.get("short-id", "")
        if p.get("skip-cert-verify"):
            base["allowInsecure"] = "1"
        qs = urllib.parse.urlencode({k: v for k, v in base.items() if v not in ("", None, False)})
        try:
            if typ == "vless":
                link = f"vless://{_q(p.get('uuid', ''))}@{_q(addr, safe='-.[]')}:{port}?{qs}"
                if p.get("flow"):
                    link += f"&flow={urllib.parse.quote(str(p['flow']))}"
                raw_links.append(link + (f"#{name}" if name else ""))
            elif typ == "vmess":
                vmess = {
                    "v": "2", "ps": urllib.parse.unquote(name) if name else "vmess",
                    "add": addr, "port": port, "id": p.get("uuid", ""),
                    "aid": p.get("alterId", 0), "scy": p.get("cipher", "auto") or "auto",
                    "net": network, "type": "none", "host": host,
                    "path": path if network != "grpc" else service,
                    "tls": "tls" if p.get("tls") else "",
                    "sni": sni, "alpn": alpn or "", "fp": fp,
                }
                raw_links.append("vmess://" + _b64enc(json.dumps(vmess, separators=(",", ":"))))
            elif typ == "trojan":
                raw_links.append(
                    f"trojan://{_q(p.get('password', ''))}@{_q(addr, safe='-.[]')}:{port}?{qs}"
                    + (f"#{name}" if name else ""))
            elif typ == "ss":
                userinfo = _b64enc(f"{p.get('cipher', 'aes-256-gcm')}:{p.get('password', '')}")
                link = f"ss://{userinfo}@{_q(addr, safe='-.[]')}:{port}"
                if p.get("plugin"):
                    plugin = str(p["plugin"])
                    if p.get("plugin-opts"):
                        opts = p["plugin-opts"]
                        if isinstance(opts, dict):
                            opts = ";".join(f"{k}={v}" for k, v in opts.items())
                        plugin += f";{opts}"
                    link += f"?plugin={urllib.parse.quote(plugin, safe='')}"
                raw_links.append(link + (f"#{name}" if name else ""))
            elif typ in ("hysteria2", "hy2"):
                extra = {}
                if p.get("obfs"):
                    extra["obfs"] = p["obfs"]
                    extra["obfs-password"] = p.get("obfs-password", "")
                if p.get("ports"):
                    extra["mport"] = p["ports"]
                if p.get("hop-interval"):
                    extra["hop-interval"] = p["hop-interval"]
                if p.get("up"):
                    extra["upmbps"] = p["up"]
                if p.get("down"):
                    extra["downmbps"] = p["down"]
                q2 = dict(base)
                q2.update(extra)
                qs2 = urllib.parse.urlencode({k: v for k, v in q2.items() if v not in ("", None, False)})
                raw_links.append(
                    f"hysteria2://{_q(p.get('password', ''))}@{_q(addr, safe='-.[]')}:{port}?{qs2}"
                    + (f"#{name}" if name else ""))
            elif typ == "tuic":
                extra = {}
                if p.get("congestion-controller"):
                    extra["congestion_control"] = p["congestion-controller"]
                if p.get("udp-relay-mode"):
                    extra["udp_relay_mode"] = p["udp-relay-mode"]
                q2 = dict(base)
                q2.update(extra)
                qs2 = urllib.parse.urlencode({k: v for k, v in q2.items() if v not in ("", None, False)})
                user = f"{_q(p.get('uuid', ''))}:{_q(p.get('password', ''))}"
                raw_links.append(f"tuic://{user}@{_q(addr, safe='-.[]')}:{port}?{qs2}"
                                 + (f"#{name}" if name else ""))
            elif typ == "anytls":
                raw_links.append(
                    f"anytls://{_q(p.get('password', ''))}@{_q(addr, safe='-.[]')}:{port}?{qs}"
                    + (f"#{name}" if name else ""))
            elif typ.startswith("socks"):
                cred = ""
                if p.get("username"):
                    cred = f"{_q(p['username'])}:{_q(p.get('password', ''))}@"
                raw_links.append(
                    f"socks5://{cred}{_q(addr, safe='-.[]')}:{port}" + (f"#{name}" if name else ""))
        except Exception:
            continue
    return raw_links


def extract_links_from_json(data):
    raw_links = []
    configs = data if isinstance(data, list) else [data]
    for config in configs:
        if not isinstance(config, dict):
            continue
        remarks = fix_encoding(str(config.get("remarks", "") or ""))
        for outbound in config.get("outbounds", []) or []:
            if not isinstance(outbound, dict):
                continue
            tag = outbound.get("tag", "") or ""
            if not tag or tag.lower() in SKIP_TAGS:
                continue
            proto = (outbound.get("protocol") or outbound.get("type") or "").lower()
            # sing-box config (NetShift / panels answering with sing-box JSON)
            if "server" in outbound and "server_port" in outbound:
                link = _build_from_singbox(outbound, remarks, tag)
                if link:
                    raw_links.append(link)
                continue
            settings = outbound.get("settings") or {}
            stream = outbound.get("streamSettings") or {}
            name = _q(f"{remarks} | {tag}" if remarks else tag, safe="-.~!$&'()*+,;=:@")
            try:
                link = None
                if proto == "vless":
                    link = _build_vless(settings, stream, name)
                elif proto == "vmess":
                    link = _build_vmess(settings, stream, name)
                elif proto == "trojan":
                    link = _build_trojan(settings, stream, name)
                elif proto in ("ss", "shadowsocks"):
                    link = _build_ss(settings, stream, name)
                elif proto in ("hysteria", "hysteria2"):
                    link = _build_hysteria(proto, settings, stream, name)
                elif proto == "socks":
                    link = _build_socks(settings, name)
                else:
                    continue
                if link:
                    raw_links.append(link)
            except Exception:
                continue
    unique = dedup_links(raw_links)
    PARSE_STATS["raw"] = len(raw_links)
    PARSE_STATS["unique"] = len(unique)
    return unique


def _get_addr_port(settings, stream):
    vnext = settings.get("vnext") or []
    if vnext:
        srv = vnext[0]
        users = srv.get("users") or [{}]
        return srv.get("address", ""), srv.get("port", 443), users[0]
    servers = settings.get("servers") or []
    if servers:
        s = servers[0]
        users = s.get("users") or s.get("password") or s.get("auth")
        return s.get("address", ""), s.get("port", 443), users
    return (
        settings.get("address") or settings.get("server") or "",
        settings.get("port", 443),
        settings.get("auth") or settings.get("password") or ""
    )


def _tls_params(stream):
    sec = (stream.get("security") or "none").lower()
    p = {}
    if sec == "reality":
        r = stream.get("realitySettings") or {}
        p["sni"] = r.get("serverName", "")
        p["fp"] = _fp(r.get("fingerprint"))
        p["pbk"] = r.get("publicKey", "")
        p["sid"] = r.get("shortId", "")
        if r.get("spiderX"):
            p["spx"] = r.get("spiderX")
    elif sec == "tls":
        t = stream.get("tlsSettings") or {}
        p["sni"] = t.get("serverName", "")
        p["fp"] = _fp(t.get("fingerprint"))
        alpn = t.get("alpn")
        if isinstance(alpn, list):
            p["alpn"] = ",".join(alpn)
        elif alpn:
            p["alpn"] = alpn
        if t.get("allowInsecure"):
            p["allowInsecure"] = "1"
    return sec, p


def _transport_params(stream):
    net = (stream.get("network") or "tcp").lower()
    p = {"type": net}
    if net == "ws":
        w = stream.get("wsSettings") or {}
        if w.get("path"):
            p["path"] = w["path"]
        h = (w.get("headers") or {}).get("Host")
        if h:
            p["host"] = h
    elif net == "grpc":
        g = stream.get("grpcSettings") or {}
        if g.get("serviceName"):
            p["serviceName"] = g["serviceName"]
    elif net in ("xhttp", "splithttp"):
        x = stream.get(net + "Settings") or stream.get("xhttpSettings") or {}
        if x.get("path"):
            p["path"] = x["path"]
        if x.get("host"):
            p["host"] = x["host"]
        if x.get("mode"):
            p["mode"] = x["mode"]
    elif net == "httpupgrade":
        h = stream.get("httpupgradeSettings") or {}
        if h.get("path"):
            p["path"] = h["path"]
        if h.get("host"):
            p["host"] = h["host"]
    elif net == "http":
        h = stream.get("httpSettings") or {}
        if h.get("path"):
            p["path"] = h["path"]
        hs = h.get("host")
        if isinstance(hs, list):
            p["host"] = ",".join(hs)
        elif hs:
            p["host"] = hs
    return net, p


def _build_vless(settings, stream, name):
    addr, port, user = _get_addr_port(settings, stream)
    if not addr or not user:
        return None
    uid = user.get("id", "")
    flow = user.get("flow", "")
    net, tp = _transport_params(stream)
    sec, sp = _tls_params(stream)
    params = dict(tp)
    params["security"] = sec
    if flow:
        params["flow"] = flow
    params.update({k: v for k, v in sp.items() if v})
    params = {k: v for k, v in params.items() if v not in ("", None, False)}
    qs = urllib.parse.urlencode(params)
    return f"vless://{_q(uid)}@{_q(addr, safe='-.[]')}:{port}?{qs}" + (f"#{name}" if name else "")


def _build_vmess(settings, stream, name):
    addr, port, user = _get_addr_port(settings, stream)
    if not addr or not user:
        return None
    net, tp = _transport_params(stream)
    sec, sp = _tls_params(stream)
    vmess = {
        "v": "2",
        "ps": urllib.parse.unquote(name) if name else "vmess",
        "add": addr,
        "port": port,
        "id": user.get("id", ""),
        "aid": user.get("alterId", 0),
        "scy": user.get("security", "auto"),
        "net": net,
        "type": "none",
        "host": tp.get("host", ""),
        "path": tp.get("path", "") if net != "grpc" else tp.get("serviceName", ""),
        "tls": sec if sec in ("tls", "reality") else "",
        "sni": sp.get("sni", ""),
        "alpn": sp.get("alpn", ""),
        "fp": sp.get("fp", ""),
    }
    if sec == "reality":
        vmess["tls"] = "reality"
        vmess["pbk"] = sp.get("pbk", "")
        vmess["sid"] = sp.get("sid", "")
    return "vmess://" + _b64enc(json.dumps(vmess, separators=(",", ":")))


def _build_trojan(settings, stream, name):
    addr, port, auth = _get_addr_port(settings, stream)
    if not addr or not auth:
        return None
    pwd = auth if isinstance(auth, str) else (auth[0].get("password", "") if isinstance(auth, list) and auth else "")
    net, tp = _transport_params(stream)
    sec, sp = _tls_params(stream)
    params = dict(tp)
    params["security"] = sec
    params.update({k: v for k, v in sp.items() if v})
    params = {k: v for k, v in params.items() if v not in ("", None, False)}
    qs = urllib.parse.urlencode(params)
    return f"trojan://{_q(pwd)}@{_q(addr, safe='-.[]')}:{port}?{qs}" + (f"#{name}" if name else "")


def _build_ss(settings, stream, name):
    servers = settings.get("servers") or []
    if not servers:
        return None
    s = servers[0]
    addr, port = s.get("address", ""), s.get("port", 443)
    method, pwd = s.get("method", "aes-256-gcm"), s.get("password", "")
    if not addr or not pwd:
        return None
    userinfo = _b64enc(f"{method}:{pwd}")
    link = f"ss://{userinfo}@{_q(addr, safe='-.[]')}:{port}"
    plugin = s.get("plugin") or ""
    if plugin:
        opts = s.get("pluginOpts") or s.get("plugin_opts") or ""
        link += f"?plugin={urllib.parse.quote(plugin + (f';{opts}' if opts else ''), safe='')}"
    return link + (f"#{name}" if name else "")


def _build_hysteria(proto, settings, stream, name):
    addr, port, _ = _get_addr_port(settings, stream)
    if not addr:
        return None
    hs = stream.get("hysteriaSettings") or {}
    auth = (
        settings.get("auth") or settings.get("password") or
        hs.get("auth") or hs.get("password") or ""
    )
    version = settings.get("version") or hs.get("version") or 2
    sec, sp = _tls_params(stream)
    params = {"sni": sp.get("sni", ""), "insecure": sp.get("allowInsecure", "0")}
    if sp.get("alpn"):
        params["alpn"] = sp["alpn"]
    scheme = "hysteria2" if int(version or 2) == 2 else "hysteria"
    up = settings.get("up") or settings.get("up_mbps") or hs.get("up") or ""
    down = settings.get("down") or settings.get("down_mbps") or hs.get("down") or ""
    if up:
        params["upmbps"] = up
    if down:
        params["downmbps"] = down
    obfs = settings.get("obfs") or hs.get("obfs")
    if obfs:
        params["obfs"] = obfs
    obfs_pw = (settings.get("obfs-password") or settings.get("obfs_password")
               or hs.get("obfs-password") or hs.get("obfs_password") or "")
    if obfs_pw:
        params["obfs-password"] = obfs_pw
    # NetShift 0.9.12 port hopping: mport/ports + hop-interval
    hop = settings.get("mport") or settings.get("ports") or hs.get("mport") or hs.get("ports") or ""
    if hop:
        params["mport"] = hop
    hop_int = (settings.get("hop-interval") or settings.get("hop_interval")
               or hs.get("hop-interval") or hs.get("hop_interval") or "")
    if hop_int:
        params["hop-interval"] = str(hop_int).rstrip("s")
    params = {k: v for k, v in params.items() if v not in ("", None, False)}
    qs = urllib.parse.urlencode(params)
    return f"{scheme}://{_q(auth)}@{_q(addr, safe='-.[]')}:{port}?{qs}" + (f"#{name}" if name else "")


def _build_socks(settings, name):
    servers = settings.get("servers") or []
    if not servers:
        return None
    s = servers[0]
    addr, port = s.get("address", ""), s.get("port", 1080)
    users = s.get("users") or []
    if users:
        u = users[0]
        return f"socks://{_b64enc(u.get('user', '') + ':' + u.get('pass', ''))}@{_q(addr, safe='-.[]')}:{port}" + (
            f"#{name}" if name else "")
    return f"socks://{_q(addr, safe='-.[]')}:{port}" + (f"#{name}" if name else "")


def _split_host_port(hostport, default_port=443):
    hostport = (hostport or "").strip()
    if hostport.startswith("["):
        m = re.match(r"\[([^\]]+)\]:(\d+)", hostport)
        if m:
            return m.group(1), int(m.group(2))
        return hostport.strip("[]"), default_port
    if hostport.count(":") == 1:
        h, p = hostport.rsplit(":", 1)
        try:
            return h, int(p)
        except ValueError:
            return hostport, default_port
    return hostport, default_port


def _port_first(value, default=443):
    """First usable TCP/UDP port from '443', '443,8443' or '20000-30000'."""
    if isinstance(value, int):
        return value
    v = str(value or "").strip()
    if not v:
        return default
    m = re.search(r"\d+", v)
    if not m:
        return default
    try:
        p = int(m.group(0))
        return p if 0 < p < 65536 else default
    except Exception:
        return default


def _hostport_from_netloc(netloc, default_port=443):
    """Split 'host:port' / '[v6]:port' / 'host:443,8443' without raising."""
    h = (netloc or "").rsplit("@", 1)[-1]
    if h.startswith("["):
        m = re.match(r"\[(.+?)\](?::(.*))?$", h)
        if m:
            return m.group(1), (m.group(2) or default_port)
        return h.strip("[]"), default_port
    if ":" in h:
        host, _, p = h.rpartition(":")
        return host, (p or default_port)
    return h, default_port


def parse_proxy_link(link):
    def _dec_b64(s):
        if not s:
            return ""
        s = str(s)
        pad = "=" * (-len(s) % 4)
        for fn in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                return fn(s + pad).decode("utf-8", "ignore")
            except Exception:
                pass
        return ""

    info = {
        "proto": "?",
        "scheme": "",
        "addr": "",
        "port": 443,
        "ports": "",
        "sni": None,
        "security": "none",
        "name": "",
        "params": {},
        "link": link,
        "description": "",
        "fragment": "",
        "noises": "",
        "type": "tcp",
        "path": "",
        "host": "",
        "service": "",
        "alpn": "",
        "fp": "",
        "allow_insecure": "",
    }
    try:
        u = urllib.parse.urlsplit(link)
        q = urllib.parse.parse_qs(u.query)
        scheme = u.scheme.lower()
        proto = PROTO_ALIASES.get(scheme, scheme)
        info["scheme"] = scheme
        info["proto"] = proto
        info["params"] = {k: v[0] for k, v in q.items()}

        fragment_str = u.fragment or ""
        if "?" in fragment_str:
            title_part, meta_part = fragment_str.split("?", 1)
            info["name"] = urllib.parse.unquote(title_part)
            meta_qs = urllib.parse.parse_qs(meta_part)
            if "serverDescription" in meta_qs:
                info["description"] = _dec_b64(meta_qs["serverDescription"][0])
        else:
            info["name"] = urllib.parse.unquote(fragment_str)

        addr, port_raw = _hostport_from_netloc(u.netloc)
        port = _port_first(port_raw)
        if not isinstance(port_raw, int) and not str(port_raw).isdigit():
            info["ports"] = str(port_raw)
        sni = (q.get("sni") or q.get("peer") or [None])[0]
        security = (q.get("security") or ["none"])[0]
        info["fragment"] = (q.get("fragment") or [""])[0]
        info["noises"] = (q.get("noises") or [""])[0]

        # Transport/security parameters shared by all link styles.
        info["type"] = (q.get("type") or ["tcp"])[0].lower() or "tcp"
        info["path"] = (q.get("path") or [""])[0]
        info["host"] = (q.get("host") or [""])[0]
        info["service"] = (q.get("serviceName") or q.get("service_name") or [""])[0]
        info["alpn"] = (q.get("alpn") or [""])[0]
        info["fp"] = (q.get("fp") or [""])[0]
        info["allow_insecure"] = (q.get("allowInsecure") or q.get("insecure") or [""])[0]

        if proto == "vmess":
            try:
                vmess = json.loads(_dec_b64(u.netloc))
                addr = vmess.get("add", "") or addr
                port = _port_first(vmess.get("port", 443))
                sni = vmess.get("sni") or sni
                security = vmess.get("tls", "none") or "none"
                if security not in ("tls", "reality"):
                    security = "none"
                info["name"] = vmess.get("ps", "") or info["name"]
                info["uuid"] = vmess.get("id", "")
                info["alter_id"] = vmess.get("aid", 0)
                info["cipher"] = vmess.get("scy", "auto")
                info["type"] = (vmess.get("net") or info["type"] or "tcp").lower()
                info["path"] = vmess.get("path", "") or info["path"]
                info["host"] = vmess.get("host", "") or info["host"]
                info["fp"] = vmess.get("fp", "") or info["fp"]
                info["alpn"] = vmess.get("alpn", "") or info["alpn"]
                if vmess.get("pbk"):
                    info["pbk"] = vmess["pbk"]
                    info["sid"] = vmess.get("sid", "")
            except Exception:
                pass
        elif proto in ("hysteria2", "hysteria"):
            info["password"] = urllib.parse.unquote(u.username or "")
            info["obfs"] = (q.get("obfs") or [""])[0]
            info["obfs_password"] = (q.get("obfs-password") or q.get("obfs_password") or [""])[0]
            # NetShift 0.9.12: port hopping via mport|ports + hop-interval|hop_interval
            hop = (q.get("mport") or q.get("ports") or [""])[0]
            if hop:
                info["ports"] = urllib.parse.unquote(hop).replace("+", " ")
            info["hop_interval"] = (q.get("hop-interval") or q.get("hop_interval")
                                    or q.get("mportHopInt") or q.get("mport_hop_int") or [""])[0]
            info["up"] = (q.get("upmbps") or q.get("up") or [""])[0]
            info["down"] = (q.get("downmbps") or q.get("down") or [""])[0]
            info["alpn"] = info["alpn"] or "h3"
            security = f"hy2 obfs={info['obfs']}" if info["obfs"] else "hy2"
            if info["ports"]:
                security += f" hop={info['ports']}"
        elif proto == "tuic":
            info["uuid"] = urllib.parse.unquote(u.username or "")
            info["password"] = urllib.parse.unquote(u.password or "")
            info["congestion"] = (q.get("congestion_control") or q.get("congestion") or ["bbr"])[0]
            info["udp_relay_mode"] = (q.get("udp_relay_mode") or q.get("udp-relay-mode") or ["native"])[0]
            info["alpn"] = info["alpn"] or "h3"
            security = f"tuic {info['congestion']}"
        elif proto == "anytls":
            # anytls://password@host:port?sni=...&insecure=1&alpn=h2,http/1.1 (sing-box 1.12+)
            info["password"] = urllib.parse.unquote(u.username or "")
            security = "anytls"
        elif proto == "shadowtls":
            info["password"] = urllib.parse.unquote(u.password or u.username or "")
            info["version"] = (q.get("version") or ["3"])[0]
            security = "shadowtls"
        elif proto in ("naiveproxy", "naive"):
            info["username"] = urllib.parse.unquote(u.username or "")
            info["password"] = urllib.parse.unquote(u.password or "")
            security = "naiveproxy"
        elif proto == "ss":
            raw_userinfo = (u.netloc or "").split("@")[0]
            decoded = _dec_b64(raw_userinfo)
            if "@" in decoded and ":" in decoded.split("@", 1)[1]:
                # legacy format: ss://base64(method:password@host:port)
                creds, _, hostport = decoded.partition("@")
                addr, port_raw = _hostport_from_netloc(hostport)
                port = _port_first(port_raw)
                decoded = creds
            if ":" in decoded:
                info["method"], info["password"] = decoded.split(":", 1)
            plugin = (q.get("plugin") or [""])[0]
            if plugin:
                info["plugin"], _, info["plugin_args"] = plugin.partition(";")
                security = f"ss + {info['plugin']}"
            else:
                security = f"ss {info.get('method', '')}"
        elif proto in ("socks5", "socks4", "socks4a", "socks"):
            if u.username is not None and u.password is not None:
                info["username"] = urllib.parse.unquote(u.username)
                info["password"] = urllib.parse.unquote(u.password)
            elif u.username is not None:
                raw_user = urllib.parse.unquote(u.username)
                decoded_user = _dec_b64(raw_user)
                if decoded_user and ":" in decoded_user:
                    info["username"], info["password"] = decoded_user.split(":", 1)
                else:
                    info["username"] = raw_user
                    info["password"] = ""
            else:
                raw_full = u.netloc or ""
                if raw_full and not any(ch in raw_full for ch in ":@"):
                    decoded_full = _dec_b64(raw_full)
                    if decoded_full:
                        if "://" in decoded_full:
                            try:
                                u2 = urllib.parse.urlsplit(decoded_full)
                                if u2.username is not None:
                                    info["username"] = urllib.parse.unquote(u2.username)
                                    info["password"] = urllib.parse.unquote(u2.password or "")
                                if u2.hostname:
                                    addr = u2.hostname
                                if u2.port:
                                    port = u2.port
                            except Exception:
                                pass
                        elif "@" in decoded_full:
                            userinfo, _, hostport = decoded_full.partition("@")
                            if ":" in userinfo:
                                info["username"], info["password"] = userinfo.split(":", 1)
                            else:
                                info["username"] = userinfo
                            if hostport:
                                addr, port_raw = _hostport_from_netloc(hostport)
                                port = _port_first(port_raw)
            security = proto
        elif proto == "vless":
            info["uuid"] = urllib.parse.unquote(u.username or "")
            info["flow"] = (q.get("flow") or [""])[0]
            info["pbk"] = (q.get("pbk") or [""])[0]
            info["sid"] = (q.get("sid") or [""])[0]
            info["packet_encoding"] = (q.get("packetEncoding") or [""])[0]
        elif proto == "trojan":
            info["password"] = urllib.parse.unquote(u.username or "")

        if security == "reality" and not info["fp"]:
            info["fp"] = "chrome"
        info["addr"], info["port"], info["sni"], info["security"] = addr, port, sni, security
    except Exception:
        pass
    return info


def _b64_text_candidates(text):
    """Plausible decodings of a base64 body (panels use std or url-safe, with
    and without padding and line breaks)."""
    cleaned = re.sub(r"\s+", "", text or "")
    if len(cleaned) < 16 or not re.fullmatch(r"[A-Za-z0-9+/_\-=]+", cleaned):
        return []
    out = []
    for fn in (base64.b64decode, base64.urlsafe_b64decode):
        for cand in (cleaned, cleaned.rstrip("="),
                     cleaned.replace("-", "+").replace("_", "/")):
            padded = cand + "=" * (-len(cand) % 4)
            try:
                data = fn(padded)
            except Exception:
                continue
            if not data:
                continue
            dec = data.decode("utf-8", errors="ignore").strip()
            if dec and dec not in out:
                out.append(dec)
    return out


def _links_from_structured(text):
    """Xray JSON, sing-box JSON or Clash/Mihomo YAML body -> links."""
    s = (text or "").strip()
    if not s:
        return []
    if s.startswith(("[", "{")):
        try:
            data = json.loads(s)
        except Exception:
            data = None
        if data is not None:
            links = extract_links_from_json(data)
            if links:
                return links
            if isinstance(data, dict) and isinstance(data.get("proxies"), list):
                return dedup_links(extract_links_from_clash(data))
    if HAS_YAML and re.search(r"^proxies\s*:", s, re.M):
        try:
            return dedup_links(extract_links_from_clash(yaml.safe_load(s)))
        except Exception:
            pass
    return []


def parse_subscription_text(text):
    text = (text or "").strip()
    if not text:
        return []
    result = _links_from_structured(text)
    if not result:
        for decoded in _b64_text_candidates(text):
            result = _links_from_structured(decoded)
            if not result and any(decoded.startswith(s) for s in SCHEMES):
                result = [l.strip() for l in decoded.splitlines() if l.strip().startswith(SCHEMES)]
            if result:
                break
    if not result:
        result = [l.strip() for l in text.splitlines() if l.strip().startswith(SCHEMES)]
    unique = dedup_links(result)
    PARSE_STATS["raw"] = len(result)
    PARSE_STATS["unique"] = len(unique)
    return unique


def _quic_initial_packet(version_bytes, total_size=1200):
    dcid = os.urandom(8)
    scid = os.urandom(8)
    pn = b"\x00\x00\x00\x00"
    fixed = 1 + 4 + 1 + 8 + 1 + 8 + 1 + 2 + 4
    payload_len = max(0, total_size - fixed)
    length = len(pn) + payload_len
    lv = bytes([0x40 | ((length >> 8) & 0x3F), length & 0xFF])
    hdr = (
        bytes([0xC3]) + version_bytes +
        bytes([len(dcid)]) + dcid +
        bytes([len(scid)]) + scid +
        b"\x00" + lv
    )
    return hdr + pn + os.urandom(payload_len)


def check_quic_alive(info, timeout=6):
    host, port = info["addr"], info["port"]
    if not host:
        return ("dead", None, "нет адреса")
    for ver in (b"\x1a\x2a\x3a\x4a", b"\x4a\x4a\x4a\x4a"):
        s = None
        try:
            ip = socket.gethostbyname(host)
            pkt = _quic_initial_packet(ver)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            t0 = time.time()
            s.sendto(pkt, (ip, port))
            data, _ = s.recvfrom(2048)
            if data:
                return ("alive", int((time.time() - t0) * 1000), "QUIC ответил (Version Negotiation)")
        except socket.timeout:
            continue
        except socket.gaierror:
            return ("dead", None, "DNS не резолвится")
        except OSError:
            return ("dead", None, "UDP недоступен")
        except Exception:
            continue
        finally:
            try:
                if s:
                    s.close()
            except Exception:
                pass
    return ("unknown", None, "UDP молчит: фильтр провайдера или сервер недоступен")


def check_tcp_tls(info, timeout=6, force_tls=False):
    host, port = info["addr"], _port_first(info.get("port"))
    sni = info.get("sni") or host
    use_tls = force_tls or info.get("security") in ("reality", "tls", "anytls", "shadowtls")
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            if use_tls and sni:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with ctx.wrap_socket(sock, server_hostname=sni) as ssock:
                    return ("alive", int((time.time() - t0) * 1000), f"TCP+TLS OK · {sni}")
            return ("alive", int((time.time() - t0) * 1000), "TCP OK")
    except socket.timeout:
        return ("dead", None, "таймаут")
    except socket.gaierror:
        return ("dead", None, "DNS не резолвится")
    except ssl.SSLError:
        return ("unknown", None, "TLS отклонён (возможно shadowtls/обфускация)")
    except OSError as e:
        return ("dead", None, str(e)[:40])


def check_tcp_basic(info, timeout=6, label="TCP"):
    host, port = info["addr"], _port_first(info.get("port"))
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            return ("alive", int((time.time() - t0) * 1000), f"{label} OK")
    except socket.timeout:
        return ("dead", None, "таймаут")
    except socket.gaierror:
        return ("dead", None, "DNS не резолвится")
    except OSError as e:
        return ("dead", None, str(e)[:40])


def check_link(link, timeout=6):
    info = parse_proxy_link(link)
    if not info["addr"]:
        return ("dead", None, "нет адреса")
    proto = info["proto"]
    if proto in ("hysteria2", "hysteria", "tuic"):
        return check_quic_alive(info, timeout)
    if proto in ("trojan", "anytls", "shadowtls"):
        return check_tcp_tls(info, timeout, force_tls=True)
    if proto in ("vless", "vmess"):
        return check_tcp_tls(info, timeout)
    if proto == "ss":
        return check_tcp_basic(info, timeout, "SS")
    if proto in ("socks5", "socks4", "socks4a", "http", "https", "naive"):
        return check_tcp_basic(info, timeout, proto.upper())
    return check_tcp_basic(info, timeout, "TCP")


def http_get(url, timeout=30, headers=None, impersonate="chrome", proxy=None):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    if HAS_CURL_CFFI:
        s = cffi_requests.Session(impersonate=impersonate, proxies=proxies)
        return s.get(url, headers=headers or {}, timeout=timeout)
    return plain_requests.get(url, headers=headers or {}, timeout=timeout, proxies=proxies)


def build_proxy_url(sub_url, ident, fmt):
    q = urllib.parse.quote
    d = ident["dev"]
    parts = ["ua=happ", f"hwid={q(ident['hwid'], safe='')}"]
    parts += [f"os={q(d['os'], safe='')}", f"ver={q(d['ver'], safe='')}", f"model={q(d['model'], safe='')}"]
    if ident["locale"]:
        parts.append(f"locale={q(ident['locale'], safe='')}")
    parts.append(fmt)
    return f"https://happy-decoder.cc/p/{','.join(parts)}/{q(sub_url, safe='')}"


def build_proxy_query_url(sub_url, ident):
    q = urllib.parse.quote
    d = ident["dev"]
    params = {
        "u": sub_url,
        "ua": "happ",
        "hwid": ident["hwid"],
        "os": d["os"],
        "ver": d["ver"],
        "model": d["model"]
    }
    if ident["locale"]:
        params["locale"] = ident["locale"]
    return "https://happy-decoder.cc/p/?" + urllib.parse.urlencode(params)


def fetch_via_public_proxy(sub_url, ident, log_fn, proxy=None, anon=False):
    variants = [
        (build_proxy_url(sub_url, ident, "json"), "/p/ → Xray JSON"),
        (build_proxy_url(sub_url, ident, "txt"), "/p/ → txt"),
        (build_proxy_query_url(sub_url, ident), "/p/ → as-is"),
    ]
    last = None
    for api_url, label in variants:
        for attempt in (1, 2):
            try:
                if anon:
                    time.sleep(random.uniform(0.4, 1.8))
                imp = ident["impersonate"] if anon else "chrome"
                log_fn(f"🛰 Канал A ({label}), попытка {attempt}...")
                resp = http_get(api_url, timeout=45, impersonate=imp, proxy=proxy)
                if resp.status_code == 200 and (resp.text or "").strip():
                    links = parse_subscription_text(resp.text)
                    if links:
                        log_fn(f"✅ Канал A сработал: {len(links)} уникальных серверов")
                        return links
                    last = Exception("пустой ответ прокси")
                else:
                    last = Exception(f"HTTP {resp.status_code}")
                log_fn(f"⚠️ {last}")
            except Exception as e:
                last = e
                log_fn(f"⚠️ {str(e)[:70]}")
                if proxy:
                    raise
                time.sleep(2)
    raise last or Exception("Канал A недоступен")


def fetch_direct(sub_url, ident, log_fn, proxy=None, anon=False):
    bad = (401, 403, 404, 429, 500, 502, 503, 504)
    dev = ident["dev"]
    native_ua = ident.get("ua") or dev.get("ua", "")
    # NetShift 0.9.12 probes a whitelist of well-known clients: panels often
    # return a different (or no) body depending on the User-Agent.
    ua_plan = [native_ua]
    if " Happ/" in native_ua:
        ua_plan.append(native_ua.split(" Happ/")[0])
    ua_plan.extend(UA_FALLBACKS)
    ua_plan.append("singbox/1.12.0")
    seen, strategies = set(), []
    for ua in ua_plan:
        if ua in seen:
            continue
        seen.add(ua)
        strategies.append((ua, random.choice(IMPERSONATE_POOL) if anon else dev["impersonate"]))
        if len(strategies) >= 10:
            break
    strategies.insert(1, (native_ua, "chrome"))
    last = None
    for ua, impersonate in strategies:
        headers = build_subscription_headers(ident, ua=ua)
        for attempt in (1, 2):
            try:
                if anon:
                    time.sleep(random.uniform(0.4, 1.8))
                short_ua = ua if len(ua) <= 34 else ua[:31] + "…"
                log_fn(f"🌐 Канал B (UA={short_ua}, TLS={impersonate}), попытка {attempt}...")
                resp = http_get(sub_url, timeout=30, headers=headers, impersonate=impersonate, proxy=proxy)
                if resp.status_code in bad:
                    raise Exception(f"HTTP {resp.status_code}")
                body = resp.text or ""
                if body.strip() and parse_subscription_text(body):
                    log_fn(f"✅ Канал B сработал: {len(body)} байт (UA={short_ua})")
                    return body
                last = Exception(f"HTTP {resp.status_code}: тело не похоже на подписку")
                log_fn(f"⚠️ {last}")
            except Exception as e:
                last = e
                log_fn(f"⚠️ {str(e)[:70]}")
                if proxy:
                    raise
                time.sleep(1)
    raise last or Exception("Канал B недоступен")


def check_tor_proxy(proxy_str):
    proxy_str = (proxy_str or "").strip()
    if not proxy_str:
        return False, "Прокси не указан"
    p = proxy_str if "://" in proxy_str else "socks5://" + proxy_str
    try:
        real_ip = (http_get("https://api.ipify.org?format=json", timeout=10).json() or {}).get("ip", "?")
    except Exception:
        real_ip = "?"
    proxy_ip, last_err = None, None
    if HAS_CURL_CFFI:
        try:
            s = cffi_requests.Session(impersonate="chrome", proxies={"http": p, "https": p})
            r = s.get("https://api.ipify.org?format=json", timeout=15)
            proxy_ip = r.json().get("ip")
        except Exception as e:
            last_err = e
    if proxy_ip is None and HAS_SOCKS:
        try:
            u = urllib.parse.urlsplit(p)
            host, port = u.hostname or "127.0.0.1", u.port or 9050
            s = pysocks.socksocket()
            s.set_proxy(pysocks.SOCKS5, host, port)
            s.settimeout(15)
            s.connect(("api.ipify.org", 443))
            ctx = ssl.create_default_context()
            ss = ctx.wrap_socket(s, server_hostname="api.ipify.org")
            ss.sendall(b"GET /?format=json HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
            chunks = []
            while True:
                c = ss.recv(4096)
                if not c:
                    break
                chunks.append(c)
            ss.close()
            body = b"".join(chunks).split(b"\r\n\r\n", 1)[-1]
            proxy_ip = json.loads(body.decode()).get("ip")
        except Exception as e:
            last_err = e
    if proxy_ip is None:
        return False, f"Прокси недоступен: {str(last_err)[:60]}"
    if proxy_ip == real_ip:
        return False, f"⚠️ IP не изменился ({proxy_ip}) — прокси не работает"
    msg = f"✅ IP скрыт: {real_ip} → {proxy_ip}"
    try:
        t = http_get("https://check.torproject.org/api/ip", timeout=12, proxy=p).json()
        if t.get("IsTor"):
            msg += " · это Tor"
    except Exception:
        pass
    return True, msg


def load_profile():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            p = json.load(f)
        if p.get("device") in DEVICES and p.get("hwid") and p.get("name"):
            return p
    except Exception:
        pass
    return None


def save_profile(device_key, name, hwid, client=None, platform=None):
    try:
        data = {"device": device_key, "name": name, "hwid": hwid}
        if client:
            data["client"] = client
        if platform:
            data["platform"] = platform
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_router_config():
    try:
        with open(ROUTER_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_router_config(cfg):
    try:
        with open(ROUTER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


UPLOAD_MODES = [
    ("urltest", "⚡ Автовыбор лучшего сервера",
     ("urltest", "urltest_proxy_links", "list"),
     ("urltest", "urltest_proxy_links", "list")),
    ("urltest_text", "⚡ Автовыбор лучшего — текстовым блоком",
     ("urltest_text", "urltest_proxy_links_text", "text"),
     ("urltest", "urltest_proxy_links", "list")),
    ("selector", "🖐 Ручной выбор сервера",
     ("selector", "selector_proxy_links", "list"),
     ("selector", "selector_proxy_links", "list")),
    ("selector_text", "🖐 Ручной выбор — текстовым блоком",
     ("selector_text", "selector_proxy_links_text", "text"),
     ("selector", "selector_proxy_links", "list")),
    ("url", "📄 Один общий список ссылок",
     ("url", "proxy_string", "text"),
     ("url", "proxy_string", "text")),
    # NetShift 0.9.12: the router fetches the subscription itself and sends the
    # spoofed X-HWID / X-Device-* identity, refreshing it on a schedule.
    ("subscription", "🔐 Подписка с HWID-подменой (NetShift 0.9.12+)",
     ("subscription", "subscription_url", "scalar"), None),
]

MODE_LABELS_NETSHIFT = [m[1] for m in UPLOAD_MODES]
MODE_LABELS_PODKOP = [m[1] for m in UPLOAD_MODES if m[3] is not None and m[0] in ("urltest", "selector", "url")]

ALL_LINK_OPTS = (
    "proxy_string",
    "selector_proxy_links",
    "urltest_proxy_links",
    "selector_proxy_links_text",
    "urltest_proxy_links_text"
)

# Options NetShift 0.9.12 reads when a section is a subscription feed.
SUBSCRIPTION_OPTS = (
    "subscription_url",
    "subscription_hwid",
    "subscription_device_os",
    "subscription_os_version",
    "subscription_device_model",
    "subscription_user_agent",
    "subscription_update_interval",
)

SUBSCRIPTION_INTERVALS = ["30m", "1h", "3h", "6h", "12h", "1d"]

UPLOAD_SOURCES = [
    "Все живые серверы (по умолчанию)",
    "Топ-N живых по пингу",
    "🔲 Выбрать вручную... (откроется окно)",
    "🔲 Выбрать вручную из живых...",
    "Все полученные ссылки",
]


def mode_target(service, label):
    for key, lab, ns, pk in UPLOAD_MODES:
        if lab == label:
            if service == "Netshift":
                return ns
            return pk or ns
    return ("urltest", "urltest_proxy_links", "list")


def _shq(value):
    """Quote a value for /bin/sh (single quotes, embedded quotes escaped)."""
    return "'" + str(value).replace("'", "'\\''") + "'"


def mode_kind(label):
    for key, lab, _ns, _pk in UPLOAD_MODES:
        if lab == label:
            return key
    return "urltest"


def _sb_duration(value, default="30s"):
    """'30' / '30s' / '1m' -> sing-box duration string."""
    v = str(value or "").strip()
    if not v:
        return default
    if re.fullmatch(r"\d+", v):
        return v + "s"
    return v


def _sb_port_list(info):
    """Return (server_port, server_ports, hop_interval) for port hopping."""
    raw = (info.get("ports") or "").replace("+", " ").replace(",", " ")
    ports = []
    for tok in raw.split():
        tok = tok.strip().replace("-", ":")
        if re.fullmatch(r"\d+(:\d+)?", tok):
            ports.append(tok)
    port = _port_first(info.get("port"))
    if not ports:
        return port, None, None
    if str(port) not in ports and not any(":" in p for p in ports):
        ports.insert(0, str(port))
    return port, ports or None, _sb_duration(info.get("hop_interval"))


def _sb_tls(info, default_alpn=None, force=False):
    sec = (info.get("security") or "none").lower()
    enabled = force or sec in ("tls", "reality")
    if not enabled:
        return None
    tls = {"enabled": True, "server_name": info.get("sni") or info["addr"]}
    alpn = info.get("alpn") or default_alpn
    if alpn:
        alpn_list = [a for a in re.split(r"[,\s]+", str(alpn)) if a]
        if alpn_list:
            tls["alpn"] = alpn_list
    fp = info.get("fp") or ""
    if sec == "reality":
        # REALITY needs uTLS; insecure is meaningless there.
        tls["utls"] = {"enabled": True, "fingerprint": fp or "chrome"}
        tls["reality"] = {
            "enabled": True,
            "public_key": info.get("pbk", ""),
            "short_id": info.get("sid", ""),
        }
    else:
        if fp:
            tls["utls"] = {"enabled": True, "fingerprint": fp}
        tls["insecure"] = True
    frag = info.get("fragment")
    if frag:
        parts = frag.split(",")
        if len(parts) >= 3:
            tls["fragment"] = {"length": parts[0], "interval": parts[1], "packets": parts[2]}
            if len(parts) >= 4:
                tls["fragment"]["max_split"] = parts[3]
    return tls


def _sb_transport(info):
    net = (info.get("type") or "tcp").lower()
    if net in ("tcp", "raw", ""):
        return None
    if net in ("ws", "httpupgrade", "xhttp"):
        tr = {"type": net}
        if info.get("path"):
            tr["path"] = info["path"]
        if info.get("host"):
            tr["headers"] = {"Host": info["host"]}
        return tr
    if net == "grpc":
        return {"type": "grpc", "service_name": info.get("service") or info.get("path") or ""}
    if net == "http":
        tr = {"type": "http"}
        if info.get("host"):
            tr["host"] = [h for h in str(info["host"]).split(",") if h]
        if info.get("path"):
            tr["path"] = info["path"]
        return tr
    return None


def _sb_outbound(info, tag):
    """Build one sing-box 1.12+/1.14 outbound from a parsed link."""
    proto = info["proto"]
    addr = info.get("addr")
    if not addr:
        return None
    port, port_list, hop_interval = _sb_port_list(info)
    ob = {"type": proto, "tag": tag, "server": addr}

    if proto == "vless":
        ob["server_port"] = port
        ob["uuid"] = info.get("uuid", "")
        if info.get("flow"):
            ob["flow"] = info["flow"]
        if info.get("packet_encoding"):
            ob["packet_encoding"] = info["packet_encoding"]
        tls = _sb_tls(info)
        if tls:
            ob["tls"] = tls
        tr = _sb_transport(info)
        if tr:
            ob["transport"] = tr
    elif proto == "vmess":
        ob["server_port"] = port
        ob["uuid"] = info.get("uuid", "")
        ob["security"] = info.get("cipher") or "auto"
        ob["alter_id"] = int(info.get("alter_id") or 0)
        tls = _sb_tls(info)
        if tls:
            ob["tls"] = tls
        tr = _sb_transport(info)
        if tr:
            ob["transport"] = tr
    elif proto == "trojan":
        ob["server_port"] = port
        ob["password"] = info.get("password", "")
        tls = _sb_tls(info, force=True)
        if tls:
            ob["tls"] = tls
        tr = _sb_transport(info)
        if tr:
            ob["transport"] = tr
    elif proto == "ss":
        ob["type"] = "shadowsocks"
        ob["server_port"] = port
        ob["method"] = info.get("method", "aes-256-gcm")
        ob["password"] = info.get("password", "")
        if info.get("plugin"):
            ob["plugin"] = info["plugin"]
            if info.get("plugin_args"):
                ob["plugin_opts"] = info["plugin_args"]
    elif proto in ("hysteria2", "hysteria"):
        ob["type"] = "hysteria2"
        ob["server_port"] = port
        if port_list:
            ob["server_ports"] = port_list
            if hop_interval:
                ob["hop_interval"] = hop_interval
        ob["password"] = info.get("password", "")
        if info.get("obfs"):
            ob["obfs"] = {"type": info["obfs"], "password": info.get("obfs_password", "")}
        if info.get("up"):
            ob["up_mbps"] = int(info["up"]) if str(info["up"]).isdigit() else info["up"]
        if info.get("down"):
            ob["down_mbps"] = int(info["down"]) if str(info["down"]).isdigit() else info["down"]
        tls = _sb_tls(info, default_alpn="h3", force=True)
        if tls:
            ob["tls"] = tls
    elif proto == "tuic":
        ob["server_port"] = port
        ob["uuid"] = info.get("uuid", "")
        ob["password"] = info.get("password", "")
        ob["congestion_control"] = info.get("congestion") or "bbr"
        ob["udp_relay_mode"] = info.get("udp_relay_mode") or "native"
        tls = _sb_tls(info, default_alpn="h3", force=True)
        if tls:
            ob["tls"] = tls
    elif proto == "anytls":
        # sing-box 1.12+; NetShift 0.9.12 adds the anytls:// link type.
        ob["server_port"] = port
        ob["password"] = info.get("password", "")
        tls = _sb_tls(info, default_alpn="h2,http/1.1", force=True)
        if tls:
            ob["tls"] = tls
    elif proto == "shadowtls":
        try:
            ob["version"] = int(info.get("version", 3))
        except Exception:
            ob["version"] = 3
        ob["server_port"] = port
        ob["password"] = info.get("password", "")
        tls = _sb_tls(info, force=True)
        if tls:
            ob["tls"] = tls
    elif proto in ("socks5", "socks4", "socks4a"):
        ob["type"] = "socks"
        ob["server_port"] = port
        ob["version"] = "4a" if proto == "socks4a" else ("4" if proto == "socks4" else "5")
        if info.get("username"):
            ob["username"] = info["username"]
            ob["password"] = info.get("password", "")
    else:
        return None
    return ob


def export_singbox(links, filename):
    """Modern (sing-box 1.12+, NetShift 0.9.12 / Podkop 0.7.24 cores) config.

    Uses the post-1.10 schema: tun 'address', route 'action' rules, no
    'inet4_address'/'sniff'/'dns-out', realm/reality/anytls and Hysteria2
    port hopping (server_ports + hop_interval)."""
    outbounds, used_tags = [], set()
    for i, link in enumerate(links, 1):
        info = parse_proxy_link(link)
        base = pretty_name(info.get("name") or "") or f"server-{i}"
        tag, cnt = base, 1
        while tag in used_tags:
            tag = f"{base} ({cnt})"
            cnt += 1
        try:
            ob = _sb_outbound(info, tag)
        except Exception:
            ob = None
        if ob:
            used_tags.add(tag)
            outbounds.append(ob)

    tags = [o["tag"] for o in outbounds]
    groups = []
    if outbounds:
        groups.append({"type": "urltest", "tag": "auto",
                       "outbounds": tags,
                       "url": "https://www.gstatic.com/generate_204",
                       "interval": "3m", "tolerance": 50})
        groups.append({"type": "selector", "tag": "proxy",
                       "outbounds": ["auto"] + tags + ["direct"]})

    config = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [{"tag": "google", "type": "udp", "server": "8.8.8.8"}],
            "final": "google",
            "strategy": "prefer_ipv4",
        },
        "inbounds": [{
            "type": "tun",
            "tag": "tun-in",
            "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
            "auto_route": True,
            "strict_route": False,
            "stack": "mixed",
        }],
        "outbounds": groups + outbounds + [{"type": "direct", "tag": "direct"}],
        "route": {
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
            ],
            "final": "proxy" if outbounds else "direct",
            "auto_detect_interface": True,
        },
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return filename


def _clash_opts(info):
    """Shared Clash/Mihomo transport + TLS options (ws/grpc/reality)."""
    p = {}
    net = (info.get("type") or "tcp").lower()
    if net in ("ws", "httpupgrade"):
        ws = {"path": info.get("path") or "/"}
        if info.get("host"):
            ws["headers"] = {"Host": info["host"]}
        p["ws-opts"] = ws
        p["network"] = "ws"
    elif net == "grpc":
        p["grpc-opts"] = {"grpc-service-name": info.get("service") or info.get("path") or ""}
        p["network"] = "grpc"
    elif net == "http":
        opts = {"path": [info["path"]] if info.get("path") else ["/"]}
        if info.get("host"):
            opts["headers"] = {"Host": [h for h in str(info["host"]).split(",") if h]}
        p["http-opts"] = opts
        p["network"] = "http"
    if info.get("sni"):
        p["servername"] = info["sni"]
    if info.get("fp"):
        p["client-fingerprint"] = info["fp"]
    if info.get("alpn"):
        p["alpn"] = [a for a in re.split(r"[,\s]+", str(info["alpn"])) if a]
    sec = (info.get("security") or "none").lower()
    if sec == "reality" or info.get("pbk"):
        p["tls"] = True
        p["reality-opts"] = {"public-key": info.get("pbk", ""),
                             "short-id": info.get("sid", "")}
        p.setdefault("client-fingerprint", "chrome")
    elif sec == "tls":
        p["tls"] = True
    return p


def _clash_proxy(info, name):
    proto = info["proto"]
    p = {"name": name, "server": info.get("addr"), "port": _port_first(info.get("port")),
         "udp": True, "skip-cert-verify": True}

    if proto == "vless":
        p.update(_clash_opts(info))
        p.update({"type": "vless", "uuid": info.get("uuid", ""), "udp": True})
        if info.get("flow"):
            p["flow"] = info["flow"]
        if "tls" not in p:
            p["tls"] = (info.get("security") or "").lower() in ("tls", "reality")
        p["servername"] = info.get("sni") or info["addr"]
    elif proto == "vmess":
        p.update(_clash_opts(info))
        p.update({
            "type": "vmess",
            "uuid": info.get("uuid", ""),
            "alterId": int(info.get("alter_id") or 0),
            "cipher": info.get("cipher") or "auto",
            "servername": info.get("sni") or info["addr"],
            "tls": bool(p.get("tls")),
        })
    elif proto == "trojan":
        p.update(_clash_opts(info))
        p.update({"type": "trojan", "password": info.get("password", ""), "tls": True,
                  "servername": info.get("sni") or info["addr"]})
    elif proto == "ss":
        p = {"name": name, "type": "ss", "server": info.get("addr"),
             "port": _port_first(info.get("port")), "udp": True,
             "cipher": info.get("method", "aes-256-gcm"),
             "password": info.get("password", "")}
        if info.get("plugin"):
            p["plugin"] = info["plugin"]
            opts = {}
            for k, v in re.findall(r"(\w+)=([^;]*)", info.get("plugin_args", "")):
                opts[k] = v
            if opts:
                p["plugin-opts"] = opts
    elif proto in ("hysteria2", "hysteria"):
        p = {"name": name, "type": "hysteria2", "server": info.get("addr"),
             "port": _port_first(info.get("port")), "password": info.get("password", ""),
             "sni": info.get("sni") or info["addr"], "skip-cert-verify": True}
        _, port_list, hop_interval = _sb_port_list(info)
        if port_list:
            p["ports"] = ",".join(port_list)
            if hop_interval:
                p["hop-interval"] = hop_interval
        if info.get("obfs"):
            p["obfs"] = info["obfs"]
            p["obfs-password"] = info.get("obfs_password", "")
        if info.get("up"):
            p["up"] = str(info["up"])
        if info.get("down"):
            p["down"] = str(info["down"])
        if info.get("alpn"):
            p["alpn"] = [a for a in re.split(r"[,\s]+", str(info["alpn"])) if a]
    elif proto == "tuic":
        p = {"name": name, "type": "tuic", "server": info.get("addr"),
             "port": _port_first(info.get("port")),
             "uuid": info.get("uuid", ""), "password": info.get("password", ""),
             "sni": info.get("sni") or info["addr"],
             "congestion-controller": info.get("congestion") or "bbr",
             "udp-relay-mode": info.get("udp_relay_mode") or "native",
             "alpn": [a for a in re.split(r"[,\s]+", str(info.get("alpn") or "h3")) if a],
             "skip-cert-verify": True}
    elif proto == "anytls":
        p.update({"type": "anytls", "password": info.get("password", ""),
                  "sni": info.get("sni") or info["addr"]})
        p.pop("udp", None)
        if info.get("fp"):
            p["client-fingerprint"] = info["fp"]
        if info.get("alpn"):
            p["alpn"] = [a for a in re.split(r"[,\s]+", str(info["alpn"])) if a]
    elif proto == "shadowtls":
        try:
            version = int(info.get("version", 3))
        except Exception:
            version = 3
        p.update({"type": "shadowtls", "password": info.get("password", ""),
                  "version": version, "sni": info.get("sni") or info["addr"]})
    elif proto in ("socks5", "socks4", "socks4a"):
        p = {"name": name, "type": "socks5", "server": info.get("addr"),
             "port": _port_first(info.get("port")), "udp": True}
        if info.get("username"):
            p["username"] = info["username"]
            p["password"] = info.get("password", "")
    else:
        return None
    return p


def export_clash(links, filename):
    if not HAS_YAML:
        raise ImportError("Нужен PyYAML: pip install pyyaml")
    proxies, names = [], []
    for i, link in enumerate(links, 1):
        info = parse_proxy_link(link)
        name = pretty_name(info.get("name") or "") or f"Server-{i}"
        base, cnt = name, 1
        while name in names:
            name = f"{base} ({cnt})"
            cnt += 1
        try:
            proxy = _clash_proxy(info, name)
        except Exception:
            proxy = None
        if not proxy or not proxy.get("server"):
            continue
        names.append(name)
        proxies.append(proxy)

    config = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "127.0.0.1:9090",
        "dns": {
            "enable": True,
            "enhanced-mode": "fake-ip",
            "nameserver": ["8.8.8.8", "1.1.1.1"],
            "fake-ip-filter": ["*.lan", "*.local", "+.msftconnecttest.com",
                               "+.msftncsi.com", "localhost.ptlogin2.qq.com"],
        },
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "AUTO-SELECT",
                "type": "url-test",
                "proxies": names,
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
            },
            {
                "name": "FALLBACK",
                "type": "fallback",
                "proxies": names,
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
            },
            {
                "name": "SELECT",
                "type": "select",
                "proxies": ["AUTO-SELECT", "FALLBACK"] + names + ["DIRECT"],
            },
        ],
        "rules": ["MATCH,SELECT"],
    }
    with open(filename, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return filename


def export_qr_codes(links, folder):
    if not HAS_QRCODE:
        raise ImportError("Нужен qrcode: pip install qrcode")
    os.makedirs(folder, exist_ok=True)
    generated = []
    for i, link in enumerate(links, 1):
        info = parse_proxy_link(link)
        name = pretty_name(info.get("name") or "") or f"server-{i}"
        safe_name = re.sub(r"[^\w\-]", "_", name)[:40]
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        fn = os.path.join(folder, f"{i:03d}_{safe_name}.png")
        img.save(fn)
        generated.append(fn)
    return generated


class RouterSSH:
    def __init__(self, host, port, user, password, service="Podkop"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.service = service
        self.client = None
        self.actual_cfg = None

    def cfg_name(self):
        return "podkop" if self.service == "Podkop" else "netshift"

    def resolved_cfg(self):
        return self.actual_cfg or self.cfg_name()

    def connect(self):
        if not HAS_PARAMIKO:
            raise Exception("paramiko не установлена. Выполните: pip install paramiko")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            self.host,
            port=self.port,
            username=self.user,
            password=self.password,
            timeout=10,
            allow_agent=False,
            look_for_keys=False
        )

    def disconnect(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    def exec_cmd(self, cmd, timeout=60):
        if not self.client:
            raise Exception("Нет подключения к роутеру")
        stdin, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        return out, err, code

    def write_remote_file(self, path, content):
        stdin, stdout, stderr = self.client.exec_command(f"cat > {path}", timeout=30)
        if isinstance(content, str):
            content = content.encode("utf-8")
        stdin.channel.sendall(content)
        stdin.channel.shutdown_write()
        code = stdout.channel.recv_exit_status()
        err = stderr.read().decode("utf-8", errors="ignore")
        if code != 0:
            raise Exception(f"Не удалось записать {path}: {err.strip() or 'код ' + str(code)}")

    def detect_config(self):
        first = self.cfg_name()
        second = "netshift" if first == "podkop" else "podkop"
        for name in (first, second):
            out, err, code = self.exec_cmd(f"uci show {name} 2>/dev/null | head -n 1")
            if out.strip():
                self.actual_cfg = name
                return name
        self.actual_cfg = None
        return None

    def get_sections(self):
        cfg = self.resolved_cfg()
        out, err, code = self.exec_cmd(f"uci show {cfg} 2>/dev/null")
        if not out.strip():
            out2, _, _ = self.exec_cmd("which uci >/dev/null 2>&1 && echo OK || echo NOUCI")
            if "NOUCI" in out2:
                raise Exception(f"На устройстве нет uci — это не OpenWrt? ({self.host})")
            raise Exception(f"Конфиг '{cfg}' пуст или отсутствует.")
        info = {}
        counts = defaultdict(int)
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith(cfg + "."):
                continue
            parts = line[len(cfg) + 1:].split("=", 1)
            if len(parts) != 2:
                continue
            keypath, rawval = parts
            kp = keypath.split(".")
            if len(kp) != 2:
                continue
            sec, key = kp
            value = rawval.strip().strip("'\"")
            info.setdefault(sec, {})[key] = value
            if key in ALL_LINK_OPTS and value:
                counts[(sec, key)] += 1
        sections = []
        for sec, d in info.items():
            if d.get("connection_type") != "proxy":
                continue
            pctype = d.get("proxy_config_type", "?")
            links = sum(counts.get((sec, o), 0) for o in ALL_LINK_OPTS)
            sections.append({
                "id": sec,
                "name": d.get("description") or sec,
                "pctype": pctype,
                "links": links,
                "sub_url": d.get("subscription_url", ""),
                "failover": d.get("failover_direct", "0") == "1",
            })
        sections.sort(key=lambda s: s["id"])
        return sections

    def upload_links(self, section_ids, links, delete_old, target, log_fn,
                     identity=None, sub_url=None, failover_direct=False,
                     update_interval="1h"):
        cfg = self.resolved_cfg()
        pctype, opt, style = target
        results = []

        # NetShift 0.9.12: subscription section — the router fetches the feed
        # itself and sends the spoofed client identity.
        if pctype == "subscription":
            if not sub_url or not str(sub_url).startswith("http"):
                raise Exception("Нет расшифрованного URL подписки — получите ссылку заново")
            if self.service != "Netshift":
                raise Exception("Режим «подписка» есть только в NetShift 0.9.12+")
            ident = identity or {}
            dev = ident.get("dev") or {}
            values = {
                "subscription_url": sub_url,
                "subscription_hwid": ident.get("hwid", ""),
                "subscription_device_os": dev.get("os_header") or dev.get("os", ""),
                "subscription_os_version": str(dev.get("ver", "")),
                "subscription_device_model": dev.get("model", ""),
                "subscription_user_agent": ident.get("ua", ""),
                "subscription_update_interval": update_interval,
            }
            log_fn(f"🔐 Подписка на роутере: {len(values)} параметров идентичности "
                   f"({dev.get('client') or dev.get('os')} · {dev.get('model')})")
            for sec in section_ids:
                script = [f"uci set {cfg}.{sec}.connection_type='proxy'",
                          f"uci set {cfg}.{sec}.proxy_config_type='subscription'"]
                for k, v in values.items():
                    script.append(f"uci set {cfg}.{sec}.{k}={_shq(v)}")
                if failover_direct:
                    script.append(f"uci set {cfg}.{sec}.failover_direct='1'")
                script.append(f"uci commit {cfg}")
                out, err, code = self.exec_cmd("\n".join(script))
                if code != 0:
                    results.append((sec, False, err.strip()[:200] or f"код {code}"))
                    log_fn(f"❌ Секция '{sec}': {err.strip()[:150] or 'код ' + str(code)}")
                else:
                    results.append((sec, True, ""))
                    log_fn(f"✅ Секция '{sec}': подписка записана "
                           f"(HWID {values['subscription_hwid'][:8]}…, обновление {update_interval})")
            return self._restart_and_verify(cfg, results, log_fn, subscription=True)

        # Link modes: drop what the installed service cannot parse.
        supported, skipped = [], defaultdict(int)
        for link in links:
            if is_supported_by(self.service, link):
                supported.append(link)
            else:
                skipped[link_scheme(link)] += 1
        if skipped:
            log_fn("⚠️ " + self.service + " не поддерживает и пропускает: "
                   + ", ".join(f"{k}={v}" for k, v in sorted(skipped.items())))
        if not supported:
            raise Exception("Ни одна ссылка не подходит выбранному сервису")
        links = supported

        tmp = "/tmp/_decoder_links.txt"
        self.write_remote_file(tmp, "\n".join(links) + "\n")
        log_fn(f"📄 Файл с {len(links)} ссылками загружен на роутер")
        for sec in section_ids:
            clear_block = ""
            if delete_old:
                deletes = " ".join(f"{cfg}.{sec}.{o}" for o in ALL_LINK_OPTS)
                clear_block = f"for o in {deletes}; do uci delete $o 2>/dev/null; done\n"
            if style == "text":
                if delete_old:
                    write_block = f"uci set {cfg}.{sec}.{opt}=\"$(sed '/^$/d' {tmp})\"\n"
                else:
                    write_block = (
                        f"cur=$(uci -q get {cfg}.{sec}.{opt})\n"
                        f"{{ printf '%s\\n' \"$cur\"; sed '/^$/d' {tmp}; }} > /tmp/_merge.txt\n"
                        f"uci set {cfg}.{sec}.{opt}=\"$(cat /tmp/_merge.txt)\"\n"
                        f"rm -f /tmp/_merge.txt\n"
                    )
            else:
                write_block = (
                    f"while IFS= read -r l; do\n"
                    f"  [ -n \"$l\" ] && uci add_list {cfg}.{sec}.{opt}=\"$l\"\n"
                    f"done < {tmp}\n"
                )
            failover_block = ""
            if failover_direct and self.service == "Netshift":
                failover_block = f"uci set {cfg}.{sec}.failover_direct='1'\n"
            script = (
                f"uci set {cfg}.{sec}.connection_type='proxy'\n"
                f"uci set {cfg}.{sec}.proxy_config_type='{pctype}'\n"
                f"{clear_block}{write_block}{failover_block}"
                f"uci commit {cfg}\n"
            )
            out, err, code = self.exec_cmd(script)
            if code != 0:
                results.append((sec, False, err.strip()[:200] or f"код {code}"))
                log_fn(f"❌ Секция '{sec}': {err.strip()[:150] or 'код ' + str(code)}")
            else:
                results.append((sec, True, ""))
                extra = " · failover_direct" if failover_block else ""
                log_fn(f"✅ Секция '{sec}': залито ({pctype} → {opt}, {len(links)} ссылок){extra}")
        return self._restart_and_verify(cfg, results, log_fn)

    def _restart_and_verify(self, cfg, results, log_fn, subscription=False):
        out, err, code = self.exec_cmd(f"/etc/init.d/{cfg} restart >/dev/null 2>&1; echo RC=$?")
        log_fn(f"🔄 Перезапуск сервиса {cfg}: {out.strip() or err.strip()}")
        time.sleep(3)
        log_out, _, _ = self.exec_cmd(f"logread 2>/dev/null | grep -Ei '{cfg}|sing-box' | tail -n 25")
        bad = [l for l in log_out.splitlines()
               if any(w in l.lower() for w in ("error", "fatal", "failed", "invalid", "unsupported"))]
        if bad:
            log_fn("⚠️ sing-box сообщил об ошибках:")
            for l in bad[:8]:
                log_fn("   " + l.strip()[:170])
        else:
            log_fn("✅ Лог роутера чист: sing-box extended поднялся без ошибок парсинга")
        alive_out, _, _ = self.exec_cmd("pidof sing-box || pgrep -f sing-box || echo NONE")
        pid = alive_out.strip().splitlines()[0] if alive_out.strip() else "NONE"
        if pid not in ("", "NONE"):
            log_fn(f"🩺 Процесс sing-box работает (pid {pid})")
        else:
            log_fn("🩺 Процесс sing-box НЕ ЗАПУЩЕН — смотрите ошибки выше")
        if subscription:
            log_fn("ℹ️ Первая загрузка подписки на роутере может занять несколько секунд; "
                   "если серверов нет — проверьте журнал и доступность URL с роутера.")
        self.exec_cmd("rm -f /tmp/_decoder_links.txt /tmp/_merge.txt 2>/dev/null")
        return results


BG, CARD, BORDER = "#f4f6f9", "#ffffff", "#dfe5ee"
TEXT, MUTED, ACCENT = "#2b3440", "#7a869a", "#3b7ddd"
GREEN, RED, PURPLE, ORANGE = "#2fa36b", "#d9534f", "#7c5cbf", "#e69b2c"

HWID_MODES = ["новый на каждый запрос", "новый на запуск", "фиксированный (из поля)"]
STATUS_ORDER = {"alive": 0, "unknown": 1, "pending": 2, "dead": 3}
STATUS_ICON = {"alive": "✅ жив", "unknown": "❓ UDP?", "pending": "— нет данных", "dead": "❌ мёртв"}


class DecoderApp:
    def __init__(self, root):
        self.root = root
        root.title(f"Декодер подписок {APP_VERSION}")
        root.configure(bg=BG)
        self.links_result = []
        self.rows = []
        self.iid2link = {}
        self.manual_selected_links = []
        self.session_hwid = str(uuid.uuid4())
        self._session_hwids = {}
        self.sub_url = None
        self.router_sections = []
        self.section_vars = {}
        self._tree_font = tkfont.Font(family="Segoe UI", size=10)

        st = ttk.Style()
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT)
        st.configure("Title.TLabel", background=BG, foreground="#1f2a3a", font=("Segoe UI", 16, "bold"))
        st.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("Head.TLabel", background=CARD, foreground="#1f2a3a", font=("Segoe UI", 10, "bold"))
        st.configure("TButton", background=ACCENT, foreground="white", padding=(12, 8),
                     borderwidth=0, font=("Segoe UI", 10, "bold"))
        st.map("TButton", background=[("active", "#2f66b5"), ("disabled", "#c3cddb")])
        st.configure("Green.TButton", background=GREEN)
        st.map("Green.TButton", background=[("active", "#268457"), ("disabled", "#c3cddb")])
        st.configure("Soft.TButton", background="#e8edf5", foreground="#2b3440")
        st.map("Soft.TButton", background=[("active", "#d8e1ef")])
        st.configure("Orange.TButton", background=ORANGE)
        st.map("Orange.TButton", background=[("active", "#c78519"), ("disabled", "#c3cddb")])
        st.configure("Purple.TButton", background=PURPLE)
        st.map("Purple.TButton", background=[("active", "#65499d")])
        st.configure("TEntry", fieldbackground="white", foreground=TEXT, borderwidth=1, padding=6)
        st.configure("TCombobox", fieldbackground="white", background="white",
                     arrowcolor=ACCENT, borderwidth=1, padding=5)
        st.map("TCombobox", fieldbackground=[("readonly", "white")])
        st.configure("TSpinbox", fieldbackground="white", foreground=TEXT, borderwidth=1, padding=4)
        st.configure("Anon.TCheckbutton", background=CARD, foreground="#5b4a8a", font=("Segoe UI", 10, "bold"))
        st.configure("TCheckbutton", background=CARD, foreground=TEXT)
        st.map("TCheckbutton", background=[("active", CARD)])
        st.map("Anon.TCheckbutton", background=[("active", CARD)])
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background="#e4e9f2", foreground=TEXT,
                     padding=(18, 8), font=("Segoe UI", 10, "bold"))
        st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT)])
        st.configure("Treeview", background="white", fieldbackground="white",
                     foreground=TEXT, rowheight=30, borderwidth=0, relief="flat")
        st.configure("Treeview.Heading", background="#eef2f8", foreground="#1f2a3a", font=("Segoe UI", 9, "bold"))
        st.map("Treeview", background=[("selected", "#dce8fb")])
        st.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e4e9f2",
                     borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT)

        hdr = ttk.Frame(root)
        hdr.pack(fill="x", padx=PAD, pady=(14, 6))
        ttk.Label(hdr, text="🔓 Декодер подписок", style="Title.TLabel").pack(side="left")
        ttk.Label(hdr, text="© Алексей Мармеладов, 2026 г.", style="Sub.TLabel").pack(side="right", padx=(0, 8))
        help_btn = ttk.Button(hdr, text="?", style="Soft.TButton", width=3, command=self.show_guide)
        help_btn.pack(side="right", padx=(0, 4))
        tip(help_btn, "Как пользоваться программой")
        about_btn = ttk.Button(hdr, text="i", style="Soft.TButton", width=3, command=self.show_about)
        about_btn.pack(side="right", padx=(0, 4))
        tip(about_btn, "О программе и её возможностях")

        bar = ttk.Frame(root)
        bar.pack(fill="x", side="bottom", padx=PAD, pady=(0, 8))
        self.progress_bar = ttk.Progressbar(bar, mode="indeterminate", length=110,
                                            style="Horizontal.TProgressbar")
        self.progress_bar.pack(side="left", padx=(0, 10))
        self.status_var = tk.StringVar(value="Готов к работе")
        lbl_status = ttk.Label(bar, textvariable=self.status_var, style="Sub.TLabel", anchor="w")
        lbl_status.pack(side="left", fill="x", expand=True)
        tip(lbl_status, "Текущее состояние программы: дешифровка, загрузка, проверка, заливка.")
        tip(self.progress_bar, "Индикатор фоновой задачи: крутится, пока программа работает.")

        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Сбросить всё", command=self.reset_all)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=root.quit)
        menubar.add_cascade(label="Файл", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="📖 Как пользоваться", command=self.show_guide)
        help_menu.add_command(label="ℹ️ О программе", command=self.show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)
        root.config(menu=menubar)

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        tab1 = ttk.Frame(self.nb)
        tab2 = ttk.Frame(self.nb)
        tab3 = ttk.Frame(self.nb)
        self.nb.add(tab1, text="  ⚙️  Декодер  ")
        self.nb.add(tab2, text="  🔗  Ссылки и проверка  ")
        self.nb.add(tab3, text="  🌐  Роутер  ")

        c1 = self.card(tab1)
        row_link = ttk.Frame(c1, style="Card.TFrame")
        row_link.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row_link, text="Ссылка:", style="Card.TLabel").pack(side="left")
        self.link_var = tk.StringVar()
        e_link = ttk.Entry(row_link, textvariable=self.link_var, font=("Consolas", 10))
        e_link.pack(side="left", fill="x", expand=True, padx=(8, 6))
        tip(e_link, "Вставьте happ://crypt…, happ://add/URL или прямой https:// URL подписки.")
        b_paste = ttk.Button(row_link, text="📋 Вставить", style="Soft.TButton", command=self.paste_link)
        b_paste.pack(side="left")
        tip(b_paste, "Вставить ссылку из буфера обмена.")

        c2 = self.card(tab1)
        self.anon_var = tk.BooleanVar(value=True)
        cb_anon = ttk.Checkbutton(c2, text="👻 Анонимный режим (минимум следов для сервиса)",
                                  variable=self.anon_var, style="Anon.TCheckbutton",
                                  command=self.on_anon_toggle)
        cb_anon.pack(anchor="w", pady=ROW_GAP)
        row_h = ttk.Frame(c2, style="Card.TFrame")
        row_h.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row_h, text="HWID:", style="Card.TLabel").pack(side="left")
        self.hwid_mode_var = tk.StringVar(value=HWID_MODES[0])
        cb_hw = ttk.Combobox(row_h, textvariable=self.hwid_mode_var, values=HWID_MODES, state="readonly")
        cb_hw.pack(side="left", fill="x", expand=True, padx=(8, 12))
        self.rotate_ident_var = tk.BooleanVar(value=False)
        cb_rot = ttk.Checkbutton(row_h, text="🎭 ротация устройства и региона", variable=self.rotate_ident_var)
        cb_rot.pack(side="left")
        row_t = ttk.Frame(c2, style="Card.TFrame")
        row_t.pack(fill="x", pady=ROW_GAP)
        self.tor_var = tk.BooleanVar(value=False)
        cb_tor = ttk.Checkbutton(row_t, text="🧅 Tor/SOCKS5:", variable=self.tor_var)
        cb_tor.pack(side="left")
        self.proxy_var = tk.StringVar(value="socks5://127.0.0.1:9050")
        e_proxy = ttk.Entry(row_t, textvariable=self.proxy_var, font=("Consolas", 9))
        e_proxy.pack(side="left", fill="x", expand=True, padx=(8, 12))
        self.no_disk_var = tk.BooleanVar(value=True)
        cb_disk = ttk.Checkbutton(row_t, text="💾 не сохранять профиль на диск", variable=self.no_disk_var)
        cb_disk.pack(side="left")
        self.anon_hint = ttk.Label(c2, style="Card.TLabel", foreground=MUTED, text="", wraplength=760)
        self.anon_hint.pack(anchor="w", pady=(2, 0))

        c3 = self.card(tab1)
        ttk.Label(c3, text="Клиент подписки (маскировка как в NetShift 0.9.12)",
                  style="Head.TLabel").pack(anchor="w", pady=ROW_GAP)
        row_c = ttk.Frame(c3, style="Card.TFrame")
        row_c.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row_c, text="Приложение:", style="Card.TLabel").pack(side="left")
        self.client_var = tk.StringVar(value="Happ")
        cb_client = ttk.Combobox(row_c, textvariable=self.client_var, values=CLIENT_CHOICES,
                                 state="readonly", width=20)
        cb_client.pack(side="left", padx=(8, 14))
        cb_client.bind("<<ComboboxSelected>>", lambda e: self.on_client_change())
        tip(cb_client, "Панели Remnawave отдают подписку только «своему» приложению.\n"
                       "Happ / INCY — точные User-Agent и HWID, как у реальных установок\n"
                       "(Android, Android TV, iOS, macOS, Windows).\n"
                       "«не маскировать» — старое поведение по списку устройств ниже.")
        ttk.Label(row_c, text="Платформа:", style="Card.TLabel").pack(side="left")
        self.client_platform_var = tk.StringVar(value="Android")
        self.cb_platform = ttk.Combobox(row_c, textvariable=self.client_platform_var,
                                        values=CLIENT_PLATFORMS["Happ"], state="readonly", width=14)
        self.cb_platform.pack(side="left", padx=(8, 10))
        self.cb_platform.bind("<<ComboboxSelected>>", lambda e: (self.update_identity_preview(), self.persist()))
        b_reid = ttk.Button(row_c, text="🎲", style="Soft.TButton", width=3,
                            command=self.regenerate_identity)
        b_reid.pack(side="left")
        tip(b_reid, "Сгенерировать новую личность: другая платформа/версия/модель/HWID.")
        self.identity_preview = ttk.Label(c3, style="Card.TLabel", foreground=MUTED, text="")
        self.identity_preview.pack(anchor="w", pady=(0, 2))

        ttk.Label(c3, text="Устройство (если маскировка выключена / для списка серверов)",
                  style="Head.TLabel").pack(anchor="w", pady=ROW_GAP)
        self.device_combo = ttk.Combobox(c3, values=list(DEVICES.keys()), state="readonly")
        self.device_combo.pack(fill="x", pady=(2, 8))
        self.device_combo.bind("<<ComboboxSelected>>", lambda e: self.on_device_change())
        row1 = ttk.Frame(c3, style="Card.TFrame")
        row1.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row1, text="Имя:", style="Card.TLabel").pack(side="left")
        self.name_var = tk.StringVar()
        e_name = ttk.Entry(row1, textvariable=self.name_var, font=("Consolas", 10))
        e_name.pack(side="left", fill="x", expand=True, padx=(8, 6))
        b_dn = ttk.Button(row1, text="🎲", style="Soft.TButton", width=3, command=self.random_name)
        b_dn.pack(side="left", padx=(0, 10))
        self.manual_name_var = tk.BooleanVar(value=False)
        cb_man = ttk.Checkbutton(row1, text="✏️ вручную", variable=self.manual_name_var,
                                 command=self.on_anon_toggle)
        cb_man.pack(side="left")
        row2 = ttk.Frame(c3, style="Card.TFrame")
        row2.pack(fill="x", pady=(0, 2))
        ttk.Label(row2, text="HWID:", style="Card.TLabel").pack(side="left")
        self.hwid_entry_var = tk.StringVar()
        e_hw = ttk.Entry(row2, textvariable=self.hwid_entry_var, font=("Consolas", 10))
        e_hw.pack(side="left", fill="x", expand=True, padx=(8, 6))
        b_dh = ttk.Button(row2, text="🎲", style="Soft.TButton", width=3, command=self.random_hwid)
        b_dh.pack(side="left")

        c4 = self.card(tab1)
        self.run_btn = ttk.Button(c4, text="▶  ПОЛУЧИТЬ ССЫЛКИ", command=self.start_fetch)
        self.run_btn.pack(side="left", padx=(0, 10))
        self.paste_btn = ttk.Button(c4, text="📥  Вставить JSON", style="Soft.TButton", command=self.paste_json)
        self.paste_btn.pack(side="left", padx=(0, 10))
        self.reset_btn = ttk.Button(c4, text="🔄  Сброс", style="Soft.TButton", command=self.reset_all)
        self.reset_btn.pack(side="left")
        self.output = scrolledtext.ScrolledText(
            tab1, font=("Consolas", 9), height=10, bg="white", fg=TEXT,
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER, insertbackground=TEXT
        )
        self.output.pack(fill="both", expand=True, padx=PAD, pady=(10, 6))

        t2a = self.card(tab2)
        self.check_btn = ttk.Button(t2a, text="⚡ Проверить доступность", style="Orange.TButton",
                                    command=self.start_check, state="disabled")
        self.check_btn.pack(side="left", padx=(0, 12))
        self.only_alive_var = tk.BooleanVar(value=False)
        cb_alive = ttk.Checkbutton(t2a, text="показывать только живые", variable=self.only_alive_var,
                                   command=self.rebuild_tree)
        cb_alive.pack(side="left", padx=(0, 12))
        self.group_by_country_var = tk.BooleanVar(value=False)
        cb_group = ttk.Checkbutton(t2a, text="🗺️ группировать по странам",
                                   variable=self.group_by_country_var, command=self.rebuild_tree)
        cb_group.pack(side="left")

        t2b = self.card(tab2)
        self.copy_btn = ttk.Button(t2b, text="📋 Копировать все", style="Green.TButton",
                                   command=self.copy_links, state="disabled")
        self.copy_btn.pack(side="left", padx=(0, 10))
        self.copy_alive_btn = ttk.Button(t2b, text="📋 Копировать живые", style="Green.TButton",
                                         command=self.copy_alive, state="disabled")
        self.copy_alive_btn.pack(side="left", padx=(0, 10))
        self.save_btn = ttk.Button(t2b, text="💾 Сохранить файл", style="Soft.TButton",
                                   command=self.save_links, state="disabled")
        self.save_btn.pack(side="left", padx=(0, 16))
        self.exp_sbox_btn = ttk.Button(t2b, text="📦 sing-box", style="Soft.TButton",
                                       command=self.do_export_singbox)
        self.exp_sbox_btn.pack(side="left", padx=(0, 6))
        self.exp_clash_btn = ttk.Button(t2b, text="⚔️ Clash", style="Soft.TButton",
                                        command=self.do_export_clash)
        self.exp_clash_btn.pack(side="left", padx=(0, 6))
        self.exp_qr_btn = ttk.Button(t2b, text="📱 QR-коды", style="Soft.TButton",
                                     command=self.do_export_qr)
        self.exp_qr_btn.pack(side="left")

        self.progress_var = tk.StringVar(value="Ссылок пока нет — получите их на вкладке «Декодер».")
        lbl_prog = ttk.Label(tab2, textvariable=self.progress_var, style="Sub.TLabel")
        lbl_prog.pack(anchor="w", padx=PAD + 2, pady=(8, 4))

        tree_wrap = ttk.Frame(tab2)
        tree_wrap.pack(fill="both", expand=True, padx=PAD, pady=(2, 14))
        cols = ("status", "ms", "name", "endpoint", "proto")
        self.tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical")
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for cid, ctext, cw, ca in (
                ("status", "Статус", 110, "w"),
                ("ms", "Пинг", 90, "center"),
                ("name", "Имя сервера", 420, "w"),
                ("endpoint", "Адрес:порт", 300, "w"),
                ("proto", "Протокол / защита", 240, "w")):
            self.tree.heading(cid, text=ctext)
            self.tree.column(cid, width=cw, anchor=ca, stretch=False)
        self.tree.tag_configure("alive", background="#e9f7ef", foreground="#1d7a46")
        self.tree.tag_configure("dead", background="#fdecea", foreground="#a33a32")
        self.tree.tag_configure("unknown", background="#fff6e0", foreground="#8a6414")
        self.tree.tag_configure("pending", background="#ffffff", foreground="#5a6472")
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        c_r1 = self.card(tab3)
        ttk.Label(c_r1, text="Подключение к роутеру (OpenWrt: Podkop / NetShift, sing-box extended)",
                  style="Head.TLabel").pack(anchor="w", pady=ROW_GAP)
        row_r1 = ttk.Frame(c_r1, style="Card.TFrame")
        row_r1.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row_r1, text="Сервис:", style="Card.TLabel").pack(side="left")
        self.router_service_var = tk.StringVar(value="Netshift")
        cb_service = ttk.Combobox(row_r1, textvariable=self.router_service_var,
                                  values=["Podkop", "Netshift"], state="readonly", width=10)
        cb_service.pack(side="left", padx=(8, 14))
        cb_service.bind("<<ComboboxSelected>>", lambda e: self.refresh_mode_list())
        ttk.Label(row_r1, text="IP роутера:", style="Card.TLabel").pack(side="left")
        self.router_ip_var = tk.StringVar(value="192.168.1.1")
        e_rip = ttk.Entry(row_r1, textvariable=self.router_ip_var, width=16)
        e_rip.pack(side="left", padx=(6, 14))
        ttk.Label(row_r1, text="SSH-порт:", style="Card.TLabel").pack(side="left")
        self.router_port_var = tk.StringVar(value="22")
        e_rport = ttk.Entry(row_r1, textvariable=self.router_port_var, width=6)
        e_rport.pack(side="left", padx=(6, 0))
        row_r2 = ttk.Frame(c_r1, style="Card.TFrame")
        row_r2.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row_r2, text="Логин:", style="Card.TLabel").pack(side="left")
        self.router_user_var = tk.StringVar(value="root")
        e_ruser = ttk.Entry(row_r2, textvariable=self.router_user_var, width=12)
        e_ruser.pack(side="left", padx=(6, 14))
        ttk.Label(row_r2, text="Пароль:", style="Card.TLabel").pack(side="left")
        self.router_pass_var = tk.StringVar(value="")
        e_rpass = ttk.Entry(row_r2, textvariable=self.router_pass_var, show="*")
        e_rpass.pack(side="left", fill="x", expand=True, padx=(6, 10))
        self.router_save_var = tk.BooleanVar(value=True)
        cb_save = ttk.Checkbutton(row_r2, text="💾 запомнить настройки", variable=self.router_save_var)
        cb_save.pack(side="left")
        row_r3 = ttk.Frame(c_r1, style="Card.TFrame")
        row_r3.pack(fill="x", pady=ROW_GAP)
        self.router_test_btn = ttk.Button(row_r3, text="🔌 Подключиться и прочитать секции",
                                          command=self.test_router_connection)
        self.router_test_btn.pack(side="left", padx=(0, 10))
        if not HAS_PARAMIKO:
            ttk.Label(row_r3, text="⚠️ нет paramiko: pip install paramiko",
                      style="Card.TLabel", foreground=RED).pack(side="left")

        c_r2 = self.card(tab3)
        ttk.Label(c_r2, text="Заливка ссылок в роутер", style="Head.TLabel").pack(anchor="w", pady=ROW_GAP)
        row_m = ttk.Frame(c_r2, style="Card.TFrame")
        row_m.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row_m, text="Режим записи:", style="Card.TLabel").pack(side="left")
        self.upload_mode_var = tk.StringVar()
        self.cb_mode = ttk.Combobox(row_m, textvariable=self.upload_mode_var,
                                    values=MODE_LABELS_NETSHIFT, state="readonly")
        self.cb_mode.pack(side="left", fill="x", expand=True, padx=(8, 12))
        self.router_delete_old_var = tk.BooleanVar(value=True)
        cb_del = ttk.Checkbutton(row_m, text="🗑️ удалить старые ссылки", variable=self.router_delete_old_var)
        cb_del.pack(side="left")
        self.cb_mode.bind("<<ComboboxSelected>>", lambda e: self.on_upload_mode_change())
        row_ns = ttk.Frame(c_r2, style="Card.TFrame")
        row_ns.pack(fill="x", pady=ROW_GAP)
        self.failover_direct_var = tk.BooleanVar(value=False)
        cb_fail = ttk.Checkbutton(row_ns, text="🛟 аварийный переход напрямую (failover_direct)",
                                  variable=self.failover_direct_var,
                                  command=lambda: self.on_upload_mode_change())
        cb_fail.pack(side="left")
        tip(cb_fail, "NetShift 0.9.12: пока ни один сервер секции не отвечает, её трафик\n"
                     "идёт напрямую (например, в zapret) и возвращается, как только сервер ожил.\n"
                     "Для Podkop опция не применяется.")
        ttk.Label(row_ns, text="   Обновление подписки:", style="Card.TLabel").pack(side="left")
        self.sub_interval_var = tk.StringVar(value="1h")
        cb_int = ttk.Combobox(row_ns, textvariable=self.sub_interval_var,
                              values=SUBSCRIPTION_INTERVALS, state="readonly", width=6)
        cb_int.pack(side="left", padx=(6, 0))
        tip(cb_int, "Как часто роутер перезапрашивает подписку в режиме «🔐 Подписка».\n"
                    "NetShift 0.9.12 хранит расписание у каждой секции отдельно.")
        self.sub_hint = ttk.Label(c_r2, style="Card.TLabel", foreground=MUTED, text="")
        self.sub_hint.pack(anchor="w", pady=(0, 2))
        self.refresh_mode_list()
        row_s = ttk.Frame(c_r2, style="Card.TFrame")
        row_s.pack(fill="x", pady=ROW_GAP)
        ttk.Label(row_s, text="Сколько ссылок:", style="Card.TLabel").pack(side="left")
        self.upload_source_var = tk.StringVar(value=UPLOAD_SOURCES[0])
        cb_src = ttk.Combobox(row_s, textvariable=self.upload_source_var,
                              values=UPLOAD_SOURCES, state="readonly", width=38)
        cb_src.pack(side="left", padx=(8, 10))
        cb_src.bind("<<ComboboxSelected>>", lambda e: self.on_source_change())
        ttk.Label(row_s, text="N =", style="Card.TLabel").pack(side="left")
        self.topn_var = tk.StringVar(value="10")
        self.sp_topn = ttk.Spinbox(row_s, textvariable=self.topn_var, from_=1, to=200,
                                   increment=1, width=5, state="disabled")
        self.sp_topn.pack(side="left", padx=(4, 0))
        sec_head = ttk.Frame(c_r2, style="Card.TFrame")
        sec_head.pack(fill="x", pady=(4, 2))
        ttk.Label(sec_head, text="Секции роутера (куда залить ссылки):",
                  style="Card.TLabel").pack(side="left")
        b_all = ttk.Button(sec_head, text="✅ выбрать все", style="Soft.TButton",
                           command=lambda: self.set_all_sections(True))
        b_all.pack(side="left", padx=(12, 4))
        b_none = ttk.Button(sec_head, text="⬜ снять все", style="Soft.TButton",
                            command=lambda: self.set_all_sections(False))
        b_none.pack(side="left")
        self.sections_box = tk.Frame(c_r2, bg="white", highlightbackground=BORDER, highlightthickness=1)
        self.sections_box.pack(fill="x", pady=(2, 8))
        self.sections_inner = ttk.Frame(self.sections_box, style="Card.TFrame", padding=8)
        self.sections_inner.pack(fill="x")
        ttk.Label(self.sections_inner,
                  text="Секции не загружены. Нажмите «🔌 Подключиться и прочитать секции».",
                  style="Card.TLabel", foreground=MUTED).pack(anchor="w")
        self.router_upload_btn = ttk.Button(c_r2, text="🚀 ЗАЛИТЬ В РОУТЕР", style="Green.TButton",
                                            command=self.upload_to_router, state="disabled")
        self.router_upload_btn.pack(anchor="w", pady=(4, 0))
        self.router_log = scrolledtext.ScrolledText(
            tab3, font=("Consolas", 9), height=10, bg="white", fg=TEXT,
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER, insertbackground=TEXT
        )
        self.router_log.pack(fill="both", expand=True, padx=PAD, pady=(10, 6))

        self.load_or_create_profile()
        self.load_router_config_ui()
        self.on_anon_toggle()
        self.apply_geometry()

    def busy(self, on, text=None):
        def _b():
            try:
                if on:
                    self.progress_bar.start(12)
                else:
                    self.progress_bar.stop()
            except Exception:
                pass
            if text:
                self.status_var.set(text)
        self.root.after(0, _b)

    def apply_geometry(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        try:
            scale = float(self.root.tk.call("tk", "scaling")) / 96.0
        except Exception:
            scale = 1.0
        eff_w = int(sw / max(scale, 1.0))
        eff_h = int(sh / max(scale, 1.0))
        w = max(1280, min(1520, eff_w - 60))
        h = max(860, min(1000, eff_h - 60))
        self.root.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")
        self.root.minsize(1180, 820)

    def card(self, parent):
        f = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        f.pack(fill="x", padx=PAD, pady=GAP)
        inner = ttk.Frame(f, style="Card.TFrame", padding=14)
        inner.pack(fill="x")
        return inner

    def log(self, text):
        self.root.after(0, lambda: (self.output.insert("end", text + "\n"), self.output.see("end")))

    def router_log_text(self, text):
        self.root.after(0, lambda: (self.router_log.insert("end", text + "\n"), self.router_log.see("end")))

    def set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def paste_link(self):
        try:
            self.link_var.set(self.root.clipboard_get().strip())
        except tk.TclError:
            messagebox.showerror("Ошибка", "Буфер обмена недоступен.")

    def reset_all(self):
        self.links_result = []
        self.rows = []
        self.iid2link = {}
        self.manual_selected_links = []
        self.sub_url = None
        self.link_var.set("")
        self.output.delete("1.0", "end")
        self.rebuild_tree()
        self.progress_var.set("Ссылок пока нет — получите их на вкладке «Декодер».")
        self.run_btn.config(state="normal")
        self.check_btn.config(state="disabled")
        self.copy_btn.config(state="disabled")
        self.copy_alive_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.router_upload_btn.config(state="disabled")
        self.busy(False, "Сброшено. Готов к новой ссылке")
        self.nb.select(0)
        self.output.insert("end", "🔄 Вставьте новую ссылку (📋 Вставить) и нажмите «▶ ПОЛУЧИТЬ ССЫЛКИ».\n")

    def on_source_change(self):
        src = self.upload_source_var.get()
        if src == UPLOAD_SOURCES[1]:
            self.sp_topn.config(state="normal")
        else:
            self.sp_topn.config(state="disabled")
        if "Выбрать вручную" in src:
            self.root.after(100, self.open_manual_selector)

    def open_manual_selector(self):
        if not self.rows:
            messagebox.showinfo("Нет ссылок", "Сначала получите ссылки на вкладке «Декодер».")
            return
        only_alive = self.upload_source_var.get() == UPLOAD_SOURCES[3]
        rows = [r for r in self.rows if not only_alive or r["status"] == "alive"]
        if not rows:
            messagebox.showinfo("Нет ссылок", "Нет подходящих ссылок для выбранного режима.")
            return
        rows.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9),
                                 r["ms"] if r["ms"] is not None else 10 ** 6))
        win = tk.Toplevel(self.root)
        win.title("Выберите ссылки для заливки в роутер")
        win.geometry("1020x640")
        win.transient(self.root)
        win.grab_set()
        hdr = ttk.Frame(win, padding=10)
        hdr.pack(fill="x")
        count_lbl = ttk.Label(hdr, text=f"Отмечено: 0 / {len(rows)}", font=("Segoe UI", 10, "bold"))
        count_lbl.pack(side="left")
        btns = ttk.Frame(hdr)
        btns.pack(side="right")
        container = ttk.Frame(win)
        container.pack(fill="both", expand=True, padx=10, pady=6)
        canvas = tk.Canvas(container, bg="white", highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        vars_list = []
        current_set = set(self.manual_selected_links)
        for r in rows:
            var = tk.BooleanVar(value=r["link"] in current_set)
            vars_list.append((var, r))
            row_f = tk.Frame(inner, bg="white")
            row_f.pack(fill="x", pady=1)
            bgc = {"alive": "#e9f7ef", "dead": "#fdecea", "unknown": "#fff6e0"}.get(r["status"], "#ffffff")
            row_f.configure(bg=bgc)
            ttk.Checkbutton(row_f, variable=var).pack(side="left", padx=(4, 8))
            stt = STATUS_ICON.get(r["status"], r["status"])
            ms = f"{r['ms']} ms" if r["ms"] is not None else "—"
            lbl = tk.Label(row_f, bg=bgc, anchor="w", font=("Segoe UI", 9),
                           text=f"{stt}   {ms:>7}   {pretty_name(r['name']) or '(без имени)':<60}   "
                                f"{r['addr']}:{r['port']:<26}   {r['proto']}/{r['security']}")
            lbl.pack(side="left", fill="x", expand=True)
            lbl.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))

        def update_count():
            n = sum(1 for v, _ in vars_list if v.get())
            count_lbl.config(text=f"Отмечено: {n} / {len(rows)}")

        for v, _ in vars_list:
            v.trace_add("write", lambda *a: update_count())
        update_count()

        def set_all(val):
            for v, _ in vars_list:
                v.set(val)

        def set_only_alive():
            for v, r in vars_list:
                v.set(r["status"] == "alive")

        ttk.Button(btns, text="✅ все", command=lambda: set_all(True)).pack(side="left", padx=2)
        ttk.Button(btns, text="⚡ только живые", command=set_only_alive).pack(side="left", padx=2)
        ttk.Button(btns, text="⬜ снять", command=lambda: set_all(False)).pack(side="left", padx=2)

        def on_ok():
            self.manual_selected_links = [r["link"] for v, r in vars_list if v.get()]
            canvas.unbind_all("<MouseWheel>")
            win.destroy()
            self.set_status(f"Выбрано вручную: {len(self.manual_selected_links)} ссылок")
            self.nb.select(2)

        def on_cancel():
            canvas.unbind_all("<MouseWheel>")
            win.destroy()

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bottom, text="✅ OK — использовать выбранные",
                   style="Green.TButton", command=on_ok).pack(side="left", padx=(0, 8))
        ttk.Button(bottom, text="Отмена", command=on_cancel).pack(side="left")
        self.root.wait_window(win)

    def refresh_mode_list(self):
        if self.router_service_var.get() == "Netshift":
            vals, default = MODE_LABELS_NETSHIFT, MODE_LABELS_NETSHIFT[0]
        else:
            vals, default = MODE_LABELS_PODKOP, MODE_LABELS_PODKOP[0]
        self.cb_mode.config(values=vals)
        if self.upload_mode_var.get() not in vals:
            self.upload_mode_var.set(default)
        self.on_upload_mode_change()

    def on_upload_mode_change(self):
        """Показать/скрыть опции, зависящие от режима записи."""
        if not hasattr(self, "sub_hint"):
            return
        kind = mode_kind(self.upload_mode_var.get())
        netshift = self.router_service_var.get() == "Netshift"
        if kind == "subscription":
            url = self.sub_url or "—"
            self.sub_hint.config(
                text=f"🔐 Роутер сам скачает подписку и подставит HWID/UA клиента.\n"
                     f"URL: {url if url == '—' else url[:90] + ('…' if len(url) > 90 else '')}\n"
                     "Ссылки из таблицы в этом режиме не заливаются.",
                foreground=MUTED)
        elif netshift and self.failover_direct_var.get():
            self.sub_hint.config(
                text="🛟 failover_direct: пока серверы не отвечают, трафик секции идёт напрямую.",
                foreground=MUTED)
        else:
            self.sub_hint.config(text="", foreground=MUTED)

    def on_anon_toggle(self):
        if self.anon_var.get():
            self.anon_hint.config(text=(
                "Анонимный режим: HWID по схеме, имя НЕ отправляется. Устройство = выбранное ниже "
                "(🎭 ротация переключает на случайное из пула). ✏️ вручную отправляет вашу модель серверу."
            ))
        else:
            self.anon_hint.config(text=(
                "Обычный режим: выбранное устройство + постоянный HWID + имя (видно в ЛК VPN). "
                "✏️ вручную: имя из поля уходит как модель устройства."
            ))

    def on_client_change(self):
        app = self.client_var.get()
        masked = app in CLIENT_PLATFORMS
        if masked:
            self.cb_platform.config(values=CLIENT_PLATFORMS[app], state="readonly")
            if self.client_platform_var.get() not in CLIENT_PLATFORMS[app]:
                self.client_platform_var.set(CLIENT_PLATFORMS[app][0])
            self.device_combo.config(state="disabled")
        else:
            self.cb_platform.config(state="disabled")
            self.device_combo.config(state="readonly")
        self.update_identity_preview()
        self.persist()

    def regenerate_identity(self):
        app = self.client_var.get()
        if app in CLIENT_PLATFORMS:
            self.client_platform_var.set(random.choice(CLIENT_PLATFORMS[app]))
        self._session_hwids.clear()
        self.update_identity_preview()
        self.persist()

    def update_identity_preview(self):
        if not hasattr(self, "identity_preview"):
            return
        try:
            ident = self.make_identity()
            d = ident["dev"]
        except Exception:
            return
        name = d.get("client") or d.get("os", "?")
        self.identity_preview.config(
            text=f"👤 {name} · {d.get('os', '')} {d.get('ver', '')} · {d.get('model', '')}"
                 f"   ·   HWID {ident['hwid'][:18]}…   ·   UA: {ident.get('ua', '')[:52]}")

    def on_device_change(self):
        if not self.manual_name_var.get():
            self.random_name(silent=True)
        self.persist()

    def random_name(self, silent=False):
        dev = DEVICES.get(self.device_combo.get(), {})
        base = random.choice(dev.get("names", ["My Device"]))
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        self.name_var.set(f"{base} {suffix}")
        if not silent:
            self.persist()

    def random_hwid(self):
        self.hwid_entry_var.set(str(uuid.uuid4()))
        self.persist()

    def persist(self):
        if self.anon_var.get() and self.no_disk_var.get():
            return
        save_profile(self.device_combo.get(), self.name_var.get(), self.hwid_entry_var.get(),
                     self.client_var.get(), self.client_platform_var.get())

    def load_or_create_profile(self):
        p = load_profile()
        if p:
            self.device_combo.set(p["device"])
            self.name_var.set(p["name"])
            self.hwid_entry_var.set(p["hwid"])
            if p.get("client") in CLIENT_CHOICES:
                self.client_var.set(p["client"])
            if p.get("platform"):
                self.client_platform_var.set(p["platform"])
        else:
            self.device_combo.current(0)
            self.random_name(silent=True)
            self.hwid_entry_var.set(str(uuid.uuid4()))
        self.on_client_change()

    def load_router_config_ui(self):
        cfg = load_router_config()
        if not cfg:
            return
        if cfg.get("service") in ("Podkop", "Netshift"):
            self.router_service_var.set(cfg["service"])
        self.router_ip_var.set(cfg.get("ip", "192.168.1.1"))
        self.router_port_var.set(str(cfg.get("port", 22)))
        self.router_user_var.set(cfg.get("user", "root"))
        self.router_save_var.set(bool(cfg.get("save_password", True)))
        if cfg.get("save_password"):
            self.router_pass_var.set(cfg.get("password", ""))
        self.refresh_mode_list()

    def save_router_config_from_ui(self):
        if not self.router_save_var.get():
            return
        save_router_config({
            "service": self.router_service_var.get(),
            "ip": self.router_ip_var.get(),
            "port": int(self.router_port_var.get() or 22),
            "user": self.router_user_var.get(),
            "password": self.router_pass_var.get(),
            "save_password": True,
        })

    def make_identity(self):
        anon = self.anon_var.get()
        manual_name = self.name_var.get().strip() if self.manual_name_var.get() else ""
        mode = self.hwid_mode_var.get()
        client = self.client_var.get()
        platform = self.client_platform_var.get()

        if client in CLIENT_IDENTITY_PROFILES:
            app = client
            platforms = CLIENT_PLATFORMS[app]
            plat = platform if platform in platforms else platforms[0]
            if anon and self.rotate_ident_var.get() and not manual_name:
                plat = random.choice(platforms)
            ident = generate_client_identity(app, plat, model_override=manual_name or None)
            if not ident:
                ident = generate_client_identity(app, platforms[0], model_override=manual_name or None)
            if mode == HWID_MODES[2]:
                ident["hwid"] = self.hwid_entry_var.get().strip() or ident["hwid"]
            elif mode == HWID_MODES[1]:
                key = (app, plat)
                if key not in self._session_hwids:
                    self._session_hwids[key] = ident["hwid"]
                ident["hwid"] = self._session_hwids[key]
            dev = dev_from_identity(ident)
            locale = random.choice(LOCALES) if (anon and self.rotate_ident_var.get() and not manual_name) else "ru-RU"
            return {
                "dev": dev,
                "hwid": ident["hwid"],
                "locale": locale,
                "name": manual_name or None,
                "ua": ident["ua"],
                "client": app,
                "platform": plat,
                "impersonate": random.choice(IMPERSONATE_POOL) if anon else dev["impersonate"],
            }

        # No client masking: the classic device list.
        if not anon:
            dev = dict(DEVICES[self.device_combo.get()])
            dev["os_header"] = dev.get("os_header") or dev["os"]
            if manual_name:
                dev["model"] = manual_name
            return {
                "dev": dev,
                "hwid": self.hwid_entry_var.get().strip() or str(uuid.uuid4()),
                "locale": "ru-RU",
                "name": manual_name or self.name_var.get().strip(),
                "ua": dev["ua"],
                "impersonate": dev["impersonate"],
            }
        if mode == HWID_MODES[0]:
            hwid = str(uuid.uuid4())
        elif mode == HWID_MODES[1]:
            hwid = self.session_hwid
        else:
            hwid = self.hwid_entry_var.get().strip() or str(uuid.uuid4())
        if self.rotate_ident_var.get() and not manual_name:
            pool = [d for d in DEVICES.values() if d.get("mobile", True)]
            dev = dict(random.choice(pool))
            locale = random.choice(LOCALES)
        else:
            dev = dict(DEVICES[self.device_combo.get()])
            locale = None
        dev["os_header"] = dev.get("os_header") or dev["os"]
        name = None
        if manual_name:
            dev["model"] = manual_name
            name = manual_name
        return {
            "dev": dev,
            "hwid": hwid,
            "locale": locale,
            "name": name,
            "ua": dev["ua"],
            "impersonate": random.choice(IMPERSONATE_POOL)
        }

    def start_fetch(self):
        link = self.link_var.get().strip()
        if not link:
            messagebox.showwarning("Внимание", "Вставьте ссылку на подписку!")
            return
        self.rows = []
        self.iid2link = {}
        self.manual_selected_links = []
        self.run_btn.config(state="disabled")
        self.output.delete("1.0", "end")
        if not self.anon_var.get():
            self.persist()
        self.busy(True, "Запуск получения ссылок...")
        threading.Thread(target=self.fetch_worker, args=(link,), daemon=True).start()

    def fetch_worker(self, link):
        final_url = None
        try:
            ident = self.make_identity()
            proxy = None
            if self.tor_var.get():
                proxy = self.proxy_var.get().strip() or None
                if proxy:
                    self.busy(True, "🧅 Проверка Tor/SOCKS5 прокси (смена IP)...")
                    ok, msg = check_tor_proxy(proxy)
                    self.log(f"🧅 {msg}")
                    if not ok:
                        self.log(" Запрос отменён (fail-closed), чтобы не раскрыть реальный IP.")
                        self.busy(False, "Прокси не работает — отменено")
                        return
            self.busy(True, "Дешифровка ссылки...")
            self.log("🔎 Локальная дешифровка ссылки...")
            final_url = decrypt_link(link)
            if not final_url.startswith("http"):
                self.log("ℹ️ Это готовая ссылка, а не URL подписки:")
                self.log(final_url)
                self.sub_url = None
                self.finish([final_url])
                return
            self.sub_url = final_url
            self.root.after(0, self.on_upload_mode_change)
            d = ident["dev"]
            manual_mark = " (вручную)" if self.manual_name_var.get() else ""
            rotate_mark = " [ротация]" if (self.anon_var.get() and self.rotate_ident_var.get()
                                           and not self.manual_name_var.get()) else ""
            self.log(f"🎭 Идентичность: {d['os']} {d['ver']} · {d['model']}{manual_mark}{rotate_mark}")
            self.log(f"🔑 HWID: {ident['hwid'][:8]}…  регион: {ident['locale'] or '—'}  "
                     f"имя: {ident['name'] or 'не отправляется'}")
            self.log(f"🌐 URL подписки: {final_url}\n")
            links = []
            try:
                self.busy(True, "Канал A: серверный прокси happy-decoder...")
                links = fetch_via_public_proxy(final_url, ident, self.log,
                                               proxy=proxy, anon=self.anon_var.get())
            except Exception as e:
                self.log(f"⚠️  Канал A не удался: {str(e)[:80]}")
            if not links:
                self.busy(True, "Канал B: прямое скачивание с TLS-маскировкой...")
                self.log("🔁 Пробую напрямую...")
                try:
                    body = fetch_direct(final_url, ident, self.log,
                                        proxy=proxy, anon=self.anon_var.get())
                    links = parse_subscription_text(body)
                except Exception as e:
                    self.log(f"⚠️  Канал B не удался: {str(e)[:80]}")
            if not links:
                self.log("\n🧱 Оба канала отбиты сервером.")
                self.log(f"💡 Откройте URL в браузере и используйте «📥 Вставить JSON»:\n👉 {final_url}")
                self.busy(False, "Сервер отбил запрос — используйте «Вставить JSON»")
                return
            raw = PARSE_STATS.get("raw", len(links))
            dup = raw - len(links)
            stats = {}
            for l in links:
                p = l.split("://", 1)[0]
                stats[p] = stats.get(p, 0) + 1
            self.log(f"\n✅ ГОТОВО! Уникальных серверов: {len(links)}")
            self.log(f"🧮 В подписке было записей: {raw}, дублей отброшено: {dup}")
            self.log(f"   Протоколы: {', '.join(f'{k}={v}' for k, v in sorted(stats.items()))}")
            self.log("💡 Вкладка «Ссылки и проверка»: ⚡ Проверить. Вкладка «Роутер»: 🚀 Залить.")
            self.finish(links)
        except Exception as e:
            self.log(f"\n❌ ОШИБКА: {e}")
            if final_url:
                self.log(f"💡 Откройте в браузере и используйте «📥 Вставить JSON»: {final_url}")
            self.busy(False, f"Ошибка: {str(e)[:60]}")
        finally:
            self.root.after(0, lambda: self.run_btn.config(state="normal"))

    def paste_json(self):
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showerror("Ошибка", "Буфер обмена недоступен.")
            return
        if not raw.strip():
            messagebox.showwarning("Внимание", "Буфер обмена пуст!")
            return
        self.rows = []
        self.iid2link = {}
        self.manual_selected_links = []
        self.output.delete("1.0", "end")
        self.log("📥 Канал C: разбор данных из буфера обмена...")
        links = parse_subscription_text(raw)
        if not links:
            self.log("❌ В буфере нет JSON/base64/списка ссылок.")
            return
        self.log(f"✅ ГОТОВО! Уникальных серверов: {len(links)} "
                 f"(записей было: {PARSE_STATS.get('raw', len(links))})")
        self.finish(links)

    def finish(self, links):
        self.links_result = links
        self.rows = []
        for l in links:
            info = parse_proxy_link(l)
            info.update({"link": l, "status": "pending", "ms": None, "note": "ещё не проверен"})
            self.rows.append(info)

        def _en():
            self.run_btn.config(state="normal")
            self.copy_btn.config(state="normal")
            self.save_btn.config(state="normal")
            self.check_btn.config(state="normal")
            self.copy_alive_btn.config(state="disabled")
            self.router_upload_btn.config(state="normal" if self.router_sections else "disabled")
            self.progress_var.set(f"Получено ссылок: {len(links)}. Нажмите ⚡ Проверить доступность.")
            self.rebuild_tree()
            self.nb.select(1)

        self.busy(False, f"Готово: {len(links)} ссылок")
        self.root.after(0, _en)

    def start_check(self):
        if not self.links_result:
            return
        self.check_btn.config(state="disabled")
        self.copy_alive_btn.config(state="disabled")
        for r in self.rows:
            r["status"], r["ms"], r["note"] = "pending", None, "проверка..."
        self.rebuild_tree()
        self.busy(True, "Проверка доступности серверов...")
        threading.Thread(target=self.check_worker, daemon=True).start()

    def check_worker(self):
        total = len(self.rows)
        with ThreadPoolExecutor(max_workers=16) as ex:
            futs = {ex.submit(check_link, r["link"]): r for r in self.rows}
            done = 0
            for fut in as_completed(futs):
                rec = futs[fut]
                try:
                    stt, ms, note = fut.result()
                except Exception as e:
                    stt, ms, note = "dead", None, str(e)[:40]
                rec["status"], rec["ms"], rec["note"] = stt, ms, note
                done += 1
                d = done
                self.root.after(0, lambda d=d: self.progress_var.set(f"Проверено {d}/{total}..."))
                self.root.after(0, lambda d=d: self.status_var.set(f"Проверка серверов: {d}/{total}"))
                self.root.after(0, self.rebuild_tree)
        alive = sum(1 for r in self.rows if r["status"] == "alive")
        dead = sum(1 for r in self.rows if r["status"] == "dead")
        unk = sum(1 for r in self.rows if r["status"] == "unknown")

        def _fin():
            self.check_btn.config(state="normal")
            self.copy_alive_btn.config(state="normal" if alive else "disabled")
            self.progress_var.set(f"Итог: ✅ живых {alive} · ❓ UDP {unk} · ❌ мёртвых {dead} (всего {total})")
            self.rebuild_tree()

        self.busy(False, f"Проверка завершена: живых {alive} из {total}")
        self.root.after(0, _fin)
        self.log(f"⚡ Проверка: живых {alive}, UDP-неопределённых {unk}, мёртвых {dead} из {total}")

    def _all_iids(self):
        out = []
        stack = list(self.tree.get_children())
        while stack:
            i = stack.pop()
            out.append(i)
            stack.extend(self.tree.get_children(i))
        return out

    def autofit_tree(self):
        f = self._tree_font
        cols = ("status", "ms", "name", "endpoint", "proto")
        widths = {cid: f.measure(self.tree.heading(cid, "text")) + 26 for cid in cols}
        for iid in self._all_iids():
            vals = self.tree.item(iid, "values")
            for cid, v in zip(cols, vals):
                w = f.measure(str(v)) + 26
                if w > widths[cid]:
                    widths[cid] = w
        widths["status"] = max(90, min(widths["status"], 150))
        widths["ms"] = max(70, min(widths["ms"], 110))
        widths["name"] = max(220, min(widths["name"], 760))
        widths["endpoint"] = max(170, min(widths["endpoint"], 460))
        widths["proto"] = max(150, min(widths["proto"], 340))
        total = sum(widths.values())
        try:
            avail = self.tree.winfo_width()
            if avail > 60 and total < avail - 30:
                widths["name"] += (avail - 30) - total
        except Exception:
            pass
        for cid in cols:
            self.tree.column(cid, width=widths[cid], stretch=False,
                             anchor=("center" if cid == "ms" else "w"))

    def rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.iid2link = {}
        rows = sorted(self.rows, key=lambda r: (STATUS_ORDER.get(r["status"], 9),
                                                r["ms"] if r["ms"] is not None else 10 ** 6))
        if self.only_alive_var.get():
            rows = [r for r in rows if r["status"] == "alive"]

        def _insert(parent, r):
            ms = f"{r['ms']} ms" if r["ms"] is not None else "—"
            name_display = pretty_name(r["name"])
            if r.get("description"):
                name_display += f" ({r['description']})"
            iid = self.tree.insert(parent, "end", tags=(r["status"],),
                                   values=(STATUS_ICON.get(r["status"], r["status"]), ms,
                                           name_display,
                                           f"{r['addr']}:{r['port']}",
                                           f"{r['proto']} / {r['security']}"))
            self.iid2link[iid] = r["link"]

        if self.group_by_country_var.get():
            groups = defaultdict(list)
            for r in rows:
                groups[extract_country(pretty_name(r["name"]))].append(r)
            for cc in sorted(groups):
                gr = groups[cc]
                alive_n = sum(1 for x in gr if x["status"] == "alive")
                parent = self.tree.insert("", "end", open=True,
                                          values=(f"🌐 [{cc}]", f"{alive_n}/{len(gr)}",
                                                  f"Группа {cc} — серверов: {len(gr)}", "", ""))
                for r in gr:
                    _insert(parent, r)
        else:
            for r in rows:
                _insert("", r)
        self.autofit_tree()

    def _on_tree_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        link = self.iid2link.get(sel[0])
        if not link:
            return
        info = parse_proxy_link(link)
        self._show_qr_popup(link, pretty_name(info.get("name") or "") or "Сервер")

    def _show_qr_popup(self, link, name=""):
        if not HAS_QRCODE:
            messagebox.showerror("Ошибка", "Нужен qrcode: pip install qrcode")
            return
        import io
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        win = tk.Toplevel(self.root)
        win.title(f"QR: {name}")
        win.resizable(False, False)
        photo = tk.PhotoImage(data=buf.getvalue())
        tk.Label(win, image=photo, bg="white").pack(padx=20, pady=20)
        win._photo_ref = photo
        tk.Label(win, text=name, font=("Segoe UI", 10)).pack(pady=(0, 6))

        def save():
            path = filedialog.asksaveasfilename(defaultextension=".png",
                                                initialfile=f"qr_{name[:20]}.png",
                                                filetypes=[("PNG", "*.png")])
            if path:
                img.save(path)

        ttk.Button(win, text="💾 Сохранить PNG", command=save).pack(pady=(0, 12))

    def get_upload_links(self):
        src = self.upload_source_var.get()
        if src == UPLOAD_SOURCES[0]:
            links = [r["link"] for r in self.rows if r["status"] == "alive"]
            return links if links else list(self.links_result)
        if src == UPLOAD_SOURCES[1]:
            alive = [r for r in self.rows if r["status"] == "alive"]
            alive.sort(key=lambda r: r["ms"] if r["ms"] is not None else 10 ** 6)
            try:
                n = max(1, int(self.topn_var.get()))
            except ValueError:
                n = 10
            links = [r["link"] for r in alive[:n]]
            return links if links else list(self.links_result)[:n]
        if src in (UPLOAD_SOURCES[2], UPLOAD_SOURCES[3]):
            if not self.manual_selected_links:
                self.open_manual_selector()
                if not self.manual_selected_links:
                    return []
            available = set(self.links_result)
            return [l for l in self.manual_selected_links if l in available]
        return list(self.links_result)

    def copy_links(self):
        if not self.links_result:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(self.links_result))
        self.set_status(f"📋 Скопировано ссылок: {len(self.links_result)}")

    def copy_alive(self):
        alive = [r["link"] for r in self.rows if r["status"] == "alive"]
        if not alive:
            messagebox.showinfo("Инфо", "Нет живых серверов — сначала выполните проверку.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(alive))
        self.set_status(f"📋 Скопировано живых ссылок: {len(alive)}")

    def save_links(self):
        if not self.links_result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="links.txt",
                                            filetypes=[("Текстовый файл", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.links_result))
            self.set_status(f"💾 Сохранено: {path}")

    def _export_links(self):
        alive = [r["link"] for r in self.rows if r["status"] == "alive"]
        return alive or list(self.links_result)

    def do_export_singbox(self):
        if not self.links_result:
            messagebox.showwarning("Нет ссылок", "Сначала получите ссылки!")
            return
        links = self._export_links()
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="sing-box.json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            try:
                export_singbox(links, path)
                self.set_status(f"📦 sing-box: {len(links)} серверов → {path}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def do_export_clash(self):
        if not HAS_YAML:
            messagebox.showerror("Нет PyYAML", "Установите: pip install pyyaml")
            return
        if not self.links_result:
            messagebox.showwarning("Нет ссылок", "Сначала получите ссылки!")
            return
        links = self._export_links()
        path = filedialog.asksaveasfilename(defaultextension=".yaml", initialfile="clash.yaml",
                                            filetypes=[("YAML", "*.yaml")])
        if path:
            try:
                export_clash(links, path)
                self.set_status(f"⚔️ Clash: {len(links)} серверов → {path}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def do_export_qr(self):
        if not HAS_QRCODE:
            messagebox.showerror("Нет qrcode", "Установите: pip install qrcode")
            return
        if not self.links_result:
            messagebox.showwarning("Нет ссылок", "Сначала получите ссылки!")
            return
        links = self._export_links()
        folder = filedialog.askdirectory(title="Выбери папку для QR-кодов")
        if folder:
            try:
                files = export_qr_codes(links, folder)
                self.set_status(f"📱 QR-кодов создано: {len(files)}")
                messagebox.showinfo("Готово", f"Создано {len(files)} QR-кодов в:\n{folder}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def test_router_connection(self):
        if not HAS_PARAMIKO:
            messagebox.showerror("paramiko не установлена",
                                 "Выполните:\npip install paramiko\n\n"
                                 "Для .exe пересоберите с --include-package=paramiko")
            return
        self.save_router_config_from_ui()
        self.refresh_mode_list()
        self.router_test_btn.config(state="disabled")
        self.router_log.delete("1.0", "end")
        self.busy(True, "Подключение к роутеру по SSH...")
        threading.Thread(target=self._router_connect_worker, daemon=True).start()

    def _router_connect_worker(self):
        ssh = RouterSSH(self.router_ip_var.get().strip(),
                        int(self.router_port_var.get() or 22),
                        self.router_user_var.get().strip(),
                        self.router_pass_var.get(),
                        self.router_service_var.get())
        try:
            self.router_log_text(f"🔌 Подключение к {ssh.host}:{ssh.port} "
                                 f"(выбран сервис: {ssh.service})...")
            ssh.connect()
            host_out, _, _ = ssh.exec_cmd("uname -n 2>/dev/null || hostname")
            self.router_log_text(f"✅ SSH подключён. Роутер: {host_out.strip()}")
            self.busy(True, "Чтение UCI-конфига роутера...")
            detected = ssh.detect_config()
            if not detected:
                raise Exception("На роутере не найдены конфиги ни podkop, ни netshift.")
            if detected != ssh.cfg_name():
                self.router_log_text(f"⚠️ Выбран '{ssh.service}', но на роутере стоит '{detected}'. Переключаюсь.")

                def _switch(det=detected):
                    self.router_service_var.set("Netshift" if det == "netshift" else "Podkop")
                    self.refresh_mode_list()

                self.root.after(0, _switch)
            self.router_log_text(f"📖 Читаю секции из конфига '{detected}'...")
            sections = ssh.get_sections()
            self.router_sections = sections
            self.router_log_text(f"📋 Найдено proxy-секций: {len(sections)}")
            for s in sections:
                self.router_log_text(f"   • {s['id']}  (текущий режим: {s['pctype']})")
            if not sections:
                self.router_log_text("⚠️ Proxy-секций нет. Создайте секцию в LuCI и повторите.")
            ssh.disconnect()

            def _ui():
                self.router_test_btn.config(state="normal")
                self.router_upload_btn.config(state="normal" if self.links_result else "disabled")
                self.update_sections_ui()

            self.busy(False, f"Роутер подключён: секций {len(sections)}")
            self.root.after(0, _ui)
        except Exception as e:
            self.router_log_text(f"❌ Ошибка: {str(e)[:220]}")
            self.busy(False, f"Ошибка роутера: {str(e)[:60]}")
            self.root.after(0, lambda: self.router_test_btn.config(state="normal"))

    def update_sections_ui(self):
        for w in self.sections_inner.winfo_children():
            w.destroy()
        self.section_vars = {}
        if not self.router_sections:
            lbl = ttk.Label(self.sections_inner, text="Секции не загружены или их нет.", foreground=MUTED)
            lbl.pack(anchor="w")
            return
        for i, sec in enumerate(self.router_sections):
            var = tk.BooleanVar(value=False)
            self.section_vars[sec["id"]] = var
            extra = ""
            if sec.get("links"):
                extra += f" · {sec['links']} ссылок"
            if sec.get("pctype") == "subscription":
                extra += " · подписка"
            if sec.get("failover"):
                extra += " · failover"
            cb = ttk.Checkbutton(self.sections_inner,
                                 text=f"{sec['name']}   ·   {sec.get('pctype', '?')}{extra}",
                                 variable=var)
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=3)
            sub_line = (f"\nПодписка: {sec['sub_url']}" if sec.get("sub_url") else "")
            tip(cb, f"Секция UCI: {sec['id']}\nИмя: {sec['name']}\n"
                    f"Сейчас записана как: {sec.get('pctype', '?')}\n"
                    f"Ссылок в секции: {sec.get('links', 0)}\n"
                    f"failover_direct: {'вкл' if sec.get('failover') else 'выкл'}{sub_line}\n"
                    f"Поставьте галку, чтобы залить ссылки сюда.")

    def set_all_sections(self, value):
        for var in self.section_vars.values():
            var.set(value)

    def upload_to_router(self):
        kind = mode_kind(self.upload_mode_var.get())
        subscription = kind == "subscription"
        if subscription and self.router_service_var.get() != "Netshift":
            messagebox.showwarning("Внимание",
                                   "Режим «подписка» поддерживает только NetShift 0.9.12+.")
            return
        if subscription and not self.sub_url:
            messagebox.showwarning("Внимание",
                                   "Нет URL подписки — получите ссылки заново на вкладке «Декодер».")
            return
        if not subscription and not self.links_result:
            messagebox.showwarning("Внимание", "Сначала получите ссылки на вкладке «Декодер»!")
            return
        selected = [sid for sid, var in self.section_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("Внимание", "Отметьте галками хотя бы одну секцию!")
            return
        links = [] if subscription else self.get_upload_links()
        if not subscription and not links:
            messagebox.showwarning("Внимание",
                                   "Нет ссылок для заливки при выбранном источнике.\n"
                                   "Выделите строки в таблице или смените источник.")
            return
        target = mode_target(self.router_service_var.get(), self.upload_mode_var.get())
        identity = self.make_identity()
        if subscription:
            summary = (f"URL подписки: {self.sub_url[:80]}\n"
                       f"Клиент: {identity['dev'].get('client') or identity['dev'].get('os')} "
                       f"{identity['dev'].get('ver', '')} · {identity['dev'].get('model', '')}\n"
                       f"HWID: {identity['hwid'][:16]}…\n"
                       f"Обновление: {self.sub_interval_var.get()}\n")
        else:
            preview = "\n".join(f"  • {pretty_name(urllib.parse.unquote(l.split('#')[-1])) if '#' in l else l[:60]}"
                                for l in links[:8])
            more = f"\n  … и ещё {len(links) - 8}" if len(links) > 8 else ""
            summary = (f"Источник: {self.upload_source_var.get()}\n"
                       f"Ссылок к заливке: {len(links)}\n{preview}{more}\n")
        failover = (self.failover_direct_var.get()
                    and self.router_service_var.get() == "Netshift")
        if not messagebox.askyesno("Подтверждение заливки",
                                   f"{summary}\n"
                                   f"Секции: {', '.join(selected)}\n"
                                   f"Режим записи: {self.upload_mode_var.get()}\n"
                                   f"Удалить старые: {'да' if self.router_delete_old_var.get() else 'нет'}\n"
                                   f"failover_direct: {'да' if failover else 'нет'}\n\n"
                                   f"Продолжить?"):
            return
        self.router_upload_btn.config(state="disabled")
        self.busy(True, "Заливка в роутер...")
        threading.Thread(target=self._upload_worker,
                         args=(selected, links, target, self.router_delete_old_var.get(),
                               identity, self.sub_url if subscription else None,
                               failover, self.sub_interval_var.get()),
                         daemon=True).start()

    def _upload_worker(self, section_ids, links, target, delete_old,
                       identity=None, sub_url=None, failover_direct=False,
                       update_interval="1h"):
        ssh = RouterSSH(self.router_ip_var.get().strip(),
                        int(self.router_port_var.get() or 22),
                        self.router_user_var.get().strip(),
                        self.router_pass_var.get(),
                        self.router_service_var.get())
        try:
            if sub_url:
                self.router_log_text(f"\n🚀 Запись подписки в {len(section_ids)} секций "
                                     f"(обновление {update_interval})...")
            else:
                self.router_log_text(f"\n🚀 Заливка {len(links)} ссылок в {len(section_ids)} секций "
                                     f"(режим: {target[0]} → опция {target[1]})...")
            ssh.connect()
            detected = ssh.detect_config()
            if not detected:
                raise Exception("Конфиг podkop/netshift не найден на роутере")
            self.busy(True, "Запись UCI и перезапуск сервиса...")
            results = ssh.upload_links(section_ids, links, delete_old, target,
                                       self.router_log_text,
                                       identity=identity, sub_url=sub_url,
                                       failover_direct=failover_direct,
                                       update_interval=update_interval)
            ok = sum(1 for _, good, _ in results if good)
            self.router_log_text(f"\n🎉 Готово: успешно {ok} из {len(results)}.")
            done = "подписка" if sub_url else f"{len(links)} ссылок"
            self.busy(False, f"Залито в {ok} секций: {done}")
            self.root.after(0, self.update_sections_ui)
        except Exception as e:
            self.router_log_text(f"❌ Ошибка заливки: {str(e)[:220]}")
            self.busy(False, f"Ошибка заливки: {str(e)[:60]}")
        finally:
            ssh.disconnect()
            self.root.after(0, lambda: self.router_upload_btn.config(state="normal"))

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title("О программе")
        win.geometry("560x420")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        f = ttk.Frame(win, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="🔓 Декодер подписок",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(f, text=f"© Алексей Мармеладов, 2026 г.   ·   v{APP_VERSION}",
                  font=("Segoe UI", 10, "italic"), foreground="#7a869a").pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=12)
        desc = (
            "Программа для анонимного получения, проверки и экспорта VPN-подписок.\n\n"
            "🔑 Основные возможности:\n"
            "  • Дешифровка ссылок happ://crypt…crypt5 (RSA-4096)\n"
            "  • Протоколы: VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC,\n"
            "    AnyTLS, ShadowTLS, NaïveProxy, Socks4/4a/5\n"
            "  • Маскировка клиента как Happ / INCY (UA, X-HWID, X-Device-*)\n"
            "  • Разбор ответов панелей: Xray JSON, sing-box JSON, Clash YAML, Base64\n"
            "  • Проверка доступности серверов (TCP/TLS/QUIC)\n"
            "  • Экспорт в sing-box 1.12+/1.14 и Clash (Mihomo), QR-коды\n"
            "  • Заливка на OpenWrt: Podkop 0.7.24, NetShift 0.9.12\n"
            "  • NetShift: режим «подписка» с HWID-подменой и failover_direct\n\n"
            "📚 Подробная инструкция: Справка → «Как пользоваться»"
        )
        ttk.Label(f, text=desc, font=("Segoe UI", 10),
                  justify="left", wraplength=520).pack(anchor="w")
        ttk.Button(f, text="Закрыть", command=win.destroy).pack(pady=(16, 0))

    def show_guide(self):
        win = tk.Toplevel(self.root)
        win.title("📖 Как пользоваться программой")
        win.geometry("820x680")
        win.transient(self.root)
        win.grab_set()
        container = ttk.Frame(win)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        canvas = tk.Canvas(container, bg="white", highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def h(text):
            ttk.Label(inner, text=text, font=("Segoe UI", 13, "bold"),
                      foreground="#3b7ddd").pack(anchor="w", pady=(12, 4))

        def p(text):
            ttk.Label(inner, text=text, font=("Segoe UI", 10),
                      justify="left", wraplength=780).pack(anchor="w", pady=2)

        h("🔓 Декодер подписок — краткое руководство")
        p("Программа предназначена для безопасного получения и работы с VPN-подписками. "
          "Ниже — пошаговое описание каждой вкладки.")
        h("Вкладка 1: ⚙️ Декодер")
        p("1. Вставьте зашифрованную ссылку вида happ://crypt… или happ://crypt5/… в поле «Ссылка на подписку».")
        p("2. Включите «Анонимный режим», если не хотите привязываться к HWID (рекомендуется).")
        p("3. «Клиент подписки»: Happ или INCY — программа отправляет точные User-Agent и "
          "X-HWID / X-Device-OS / X-Ver-OS / X-Device-Model, как реальное приложение "
          "(так же делает NetShift 0.9.12). «не маскировать» — старое поведение по списку устройств.")
        p("4. При необходимости задайте собственный HWID или сгенерируйте случайный кнопкой 🎲.")
        p("5. Нажмите «▶ ПОЛУЧИТЬ ССЫЛКИ». Программа расшифрует подписку и выведет список серверов. "
          "Если панель отдаёт разный ответ на разные клиенты, она автоматически переберёт "
          "User-Agent'ы (Happ, v2rayN, Hiddify, Clash.Meta, v2rayNG).")
        p("6. Кнопка «📋 Вставить JSON» разбирает буфер обмена (Xray JSON / sing-box JSON / "
          "Clash YAML / Base64 / список ссылок).")
        p("7. Кнопка «🔄 Сброс» полностью очищает состояние — удобно для новой подписки.")
        h("Вкладка 2: 🔗 Ссылки и проверка")
        p("1. Нажмите «⚡ Проверить доступность» — программа параллельно (16 потоков) проверит "
          "каждый сервер: TCP/TLS-хендшейк для VLESS/Trojan/VMess/AnyTLS, QUIC Initial для "
          "Hysteria2/TUIC, обычный TCP для Shadowsocks/Socks/NaïveProxy.")
        p("2. Результаты: ✅ жив / ❓ UDP-неопределён / ❌ мёртв.")
        p("3. Поставьте галочку «Только живые», чтобы скрыть недоступные серверы.")
        p("4. Выделите нужные серверы (Ctrl/Shift) и экспортируйте через кнопки внизу:")
        p("   • 📦 sing-box 1.12+/1.14 (TUN address, sniff/hijack-dns, reality/utls, "
          "AnyTLS, Hysteria2 server_ports + hop_interval, fragment/noises)")
        p("   • 📜 Clash YAML (Mihomo: ws/grpc/http, reality, AnyTLS, TUIC, Hysteria2)"
          )
        p("   • 🔳 QR-коды (двойной клик по строке — мгновенный QR)")
        h("Вкладка 3: 🌐 Роутер")
        p("1. Введите IP роутера, логин и пароль (по умолчанию 192.168.1.1 / root).")
        p("2. Выберите сервис: Podkop 0.7.24 или NetShift 0.9.12 (OpenWrt).")
        p("3. Нажмите «🔌 Подключиться и прочитать секции» — программа определит установленный "
          "пакет по SSH и прочитает UCI-секции (тип конфигурации, число ссылок, подписку, failover).")
        p("4. Выберите целевой режим записи. Неподдерживаемые сервисом протоколы отбрасываются "
          "автоматически: Podkop принимает только vless/trojan/ss/socks4/5/hy2, "
          "NetShift дополнительно vmess/tuic/anytls/naive.")
        p("5. «🔐 Подписка с HWID-подменой» (только NetShift) — роутер сам скачивает подписку "
          "и отправляет User-Agent/HWID/OS/модель выбранного клиента; интервал обновления "
          "задаётся рядом. «🛟 failover_direct» — пока серверы не отвечают, трафик идёт напрямую.")
        p("6. Нажмите «🚀 ЗАЛИТЬ В РОУТЕР» — конфигурация улетит на роутер, сервис "
          "перезапустится, а программа проверит журнал и процесс sing-box.")
        h("💡 Подсказки")
        p("• Наведите курсор на любой элемент — появится всплывающая подсказка.")
        p("• Настройки (роутер, HWID, геометрия окна) сохраняются в %APPDATA%\\HappDecoder "
          "и переживают перезапуск и любую сборку (.exe, onefile).")
        p("• Для Windows 10/11 программа автоматически учитывает масштабирование 125%/150%, "
          "чтобы интерфейс не был размытым или обрезанным.")
        ttk.Separator(inner).pack(fill="x", pady=16)
        ttk.Button(inner, text="Закрыть", command=win.destroy).pack(pady=(0, 10))


def _find_icon_file():
    candidates = []
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
    except Exception:
        pass
    candidates.append(os.path.join(os.getcwd(), "icon.ico"))
    try:
        candidates.append(os.path.join(os.path.dirname(sys.executable), "icon.ico"))
    except Exception:
        pass
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


if __name__ == "__main__":
    import ctypes as _ctypes
    try:
        _ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    if getattr(sys, "frozen", False) or "compiled" in globals():
        try:
            _ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass
    root = tk.Tk()
    root.withdraw()
    _icon_kept = None
    try:
        ico = _find_icon_file()
        if ico:
            root.iconbitmap(ico)
        else:
            import app_icon
            _icon_kept = tk.PhotoImage(data=app_icon.ICON_PNG_B64)
            root.iconphoto(True, _icon_kept)
    except Exception:
        pass
    root._decoder_icon_ref = _icon_kept
    app = DecoderApp(root)
    root.update_idletasks()
    app.apply_geometry()
    root.update_idletasks()
    root.deiconify()
    root.mainloop()