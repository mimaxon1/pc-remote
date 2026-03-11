"""Network helpers."""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
from pathlib import Path
import ipaddress
from typing import Optional
try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    _PSUTIL_AVAILABLE = False


_BAD_IFACE_TOKENS = (
    "vpn",
    "tun",
    "tap",
    "tunnel",
    "wireguard",
    "wg",
    "openvpn",
    "nord",
    "cisco",
    "anyconnect",
    "pulse",
    "forti",
    "virtual",
    "vmware",
    "vbox",
    "virtualbox",
    "hyper-v",
    "wsl",
    "docker",
    "loopback",
)

_GOOD_IFACE_TOKENS = (
    "wi-fi",
    "wifi",
    "wlan",
    "ethernet",
    "eth",
    "lan",
    "local",
    "беспровод",
    "ether",
)

_ETH_TOKENS = (
    "ethernet",
    "eth",
)

_WIFI_TOKENS = (
    "wi-fi",
    "wifi",
    "wlan",
    "wireless",
    "беспровод",
)
APP_DIR_NAME = "PC Remote"
LEGACY_APP_DIR_NAMES = ("PC-Android",)


def _is_bad_iface(name: str) -> bool:
    n = name.casefold()
    return any(t in n for t in _BAD_IFACE_TOKENS)


def _is_virtualbox_hostonly_ip(ip: ipaddress.IPv4Address) -> bool:
    # VirtualBox Host-Only default network: 192.168.56.0/24
    return ip in ipaddress.IPv4Network("192.168.56.0/24")


def _appdata_base_dir() -> Optional[Path]:
    if os.name != "nt":
        return None
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    return Path(base) if base else None


def _app_dir() -> Path:
    base = _appdata_base_dir()
    if base:
        return base / APP_DIR_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME


def _legacy_runtime_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _legacy_runtime_settings_path() -> Path:
    return _legacy_runtime_app_dir() / "settings.json"


def _legacy_appdata_settings_paths() -> list[Path]:
    base = _appdata_base_dir()
    if base is None:
        return []
    return [base / name / "settings.json" for name in LEGACY_APP_DIR_NAMES]


def _migrate_from_source(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    try:
        if source.resolve() == target.resolve():
            return False
    except Exception:
        pass

    if target.exists():
        try:
            source.unlink()
        except Exception:
            pass
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(source), str(target))
        return True
    except Exception:
        try:
            shutil.copy2(source, target)
            source.unlink(missing_ok=True)
            return True
        except Exception:
            return False


def _migrate_legacy_settings(target: Path) -> None:
    candidates = _legacy_appdata_settings_paths()
    candidates.append(_legacy_runtime_settings_path())
    for source in candidates:
        if _migrate_from_source(source, target):
            break


def _settings_path() -> Path:
    path = _app_dir() / "settings.json"
    _migrate_legacy_settings(path)
    return path


def _load_network_settings() -> tuple[str | None, str | None]:
    try:
        raw = json.loads(_settings_path().read_text(encoding="utf-8"))
        net = raw.get("network", {}) if isinstance(raw, dict) else {}
        preferred_iface = net.get("preferred_interface")
        preferred_ip = net.get("preferred_ip")
        if preferred_iface is not None:
            preferred_iface = str(preferred_iface)
        if preferred_ip is not None:
            preferred_ip = str(preferred_ip)
        return preferred_iface, preferred_ip
    except Exception:
        return None, None


def _score_iface(name: str, ip: ipaddress.IPv4Address) -> int:
    n = name.casefold()
    score = 0
    if ip.is_private:
        score += 50
    if any(t in n for t in _GOOD_IFACE_TOKENS):
        score += 20
    if any(t in n for t in _BAD_IFACE_TOKENS):
        score -= 100
    if _is_virtualbox_hostonly_ip(ip):
        score -= 150
    if ip.is_link_local:
        score -= 50
    if ip.is_loopback:
        score -= 200
    return score


def _interface_kind(name: str) -> str:
    n = name.casefold()
    if any(t in n for t in _ETH_TOKENS):
        return "ethernet"
    if any(t in n for t in _WIFI_TOKENS):
        return "wifi"
    if _is_bad_iface(name):
        return "virtual"
    return "other"


def list_active_ipv4_interfaces() -> list[dict[str, object]]:
    """Return active non-loopback IPv4 interfaces."""
    if not _PSUTIL_AVAILABLE:
        ip = _fallback_ip()
        return [] if ip == "127.0.0.1" else [{
            "name": "unknown",
            "ip": ip,
            "speed_mbps": 0,
            "kind": "other",
            "is_virtualbox_host_only": False,
            "is_preferred_candidate": True,
        }]
    items: list[dict[str, object]] = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for if_name, addr_list in addrs.items():
        st = stats.get(if_name)
        if st and not st.isup:
            continue
        for addr in addr_list:
            if addr.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.IPv4Address(addr.address)
            except Exception:
                continue
            if ip.is_loopback or ip.is_link_local:
                continue
            items.append(
                {
                    "name": if_name,
                    "ip": str(ip),
                    "speed_mbps": int(getattr(st, "speed", 0) or 0),
                    "kind": _interface_kind(if_name),
                    "is_virtualbox_host_only": _is_virtualbox_hostonly_ip(ip),
                    "is_preferred_candidate": not _is_bad_iface(if_name) and not _is_virtualbox_hostonly_ip(ip),
                }
            )
    items.sort(key=lambda item: (item["name"].lower(), item["ip"]))
    return items


def _fallback_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def get_local_ip() -> str:
    """Best-effort local IP for printing the URL in console/UI.

    Prefers LAN/Wi‑Fi over VPN by heuristics. Optional overrides in settings.json:
    {
      "network": { "preferred_interface": "...", "preferred_ip": "..." }
    }
    """
    preferred_iface, preferred_ip = _load_network_settings()

    if not _PSUTIL_AVAILABLE:
        return _fallback_ip()

    candidates: list[tuple[str, ipaddress.IPv4Address]] = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for if_name, addr_list in addrs.items():
        st = stats.get(if_name)
        if st and not st.isup:
            continue
        for addr in addr_list:
            if addr.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.IPv4Address(addr.address)
            except Exception:
                continue
            if ip.is_loopback or ip.is_link_local:
                continue
            candidates.append((if_name, ip))

    if preferred_ip:
        for if_name, ip in candidates:
            if str(ip) == preferred_ip:
                return str(ip)

    if preferred_iface:
        for if_name, ip in candidates:
            if if_name.casefold() == preferred_iface.casefold():
                return str(ip)

    # Explicit preference: Ethernet first, then Wi‑Fi (skip VPN/virtual/host-only if possible)
    def pick_by_tokens(tokens: tuple[str, ...]) -> str | None:
        for if_name, ip in candidates:
            n = if_name.casefold()
            if _is_bad_iface(if_name):
                continue
            if _is_virtualbox_hostonly_ip(ip):
                continue
            if any(t in n for t in tokens):
                return str(ip)
        return None

    eth_ip = pick_by_tokens(_ETH_TOKENS)
    if eth_ip:
        return eth_ip

    wifi_ip = pick_by_tokens(_WIFI_TOKENS)
    if wifi_ip:
        return wifi_ip

    if candidates:
        scored = [(_score_iface(n, ip), str(ip)) for n, ip in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    return _fallback_ip()
