"""Network helpers."""

from __future__ import annotations

import ipaddress
import json
import logging
import shutil
import socket
import sys
import urllib.parse
from pathlib import Path

import config

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    _PSUTIL_AVAILABLE = False

logger = logging.getLogger(config.LOGGER_NAME)

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

_ETH_TOKENS = ("ethernet", "eth")
_WIFI_TOKENS = ("wi-fi", "wifi", "wlan", "wireless", "беспровод")


def _is_bad_iface(name: str) -> bool:
    return any(token in name.casefold() for token in _BAD_IFACE_TOKENS)


def _is_virtualbox_hostonly_ip(ip: ipaddress.IPv4Address) -> bool:
    return ip in ipaddress.IPv4Network("192.168.56.0/24")


def _legacy_runtime_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _legacy_runtime_settings_path() -> Path:
    return _legacy_runtime_app_dir() / config.SETTINGS_FILENAME


def _legacy_appdata_settings_paths() -> list[Path]:
    base = config.appdata_base_dir()
    if base is None:
        return []
    return [base / name / config.SETTINGS_FILENAME for name in config.LEGACY_APP_NAMES]


def _migrate_from_source(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    try:
        if source.resolve() == target.resolve():
            return False
    except Exception as exc:
        logger.warning("Failed to resolve legacy network settings path %s: %s", source, exc)

    if target.exists():
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(source), str(target))
        return True
    except Exception as exc:
        logger.warning("Failed to move legacy network settings %s -> %s: %s", source, target, exc)
        try:
            shutil.copy2(source, target)
            source.unlink(missing_ok=True)
            return True
        except Exception as copy_exc:
            logger.exception("Failed to migrate network settings %s -> %s: %s", source, target, copy_exc)
            return False


def _migrate_legacy_settings(target: Path) -> None:
    candidates = _legacy_appdata_settings_paths()
    candidates.append(_legacy_runtime_settings_path())
    for source in candidates:
        if _migrate_from_source(source, target):
            break


def _settings_path() -> Path:
    path = config.app_dir() / config.SETTINGS_FILENAME
    _migrate_legacy_settings(path)
    return path


def _load_network_settings() -> tuple[str | None, str | None]:
    try:
        raw = json.loads(_settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except Exception as exc:
        logger.warning("Failed to read network settings: %s", exc)
        return None, None

    if not isinstance(raw, dict):
        logger.warning("Ignoring non-object network settings payload")
        return None, None

    net = raw.get("network", {})
    if not isinstance(net, dict):
        return None, None

    preferred_iface = net.get("preferred_interface")
    preferred_ip = net.get("preferred_ip")
    if preferred_iface is not None:
        preferred_iface = str(preferred_iface)
    if preferred_ip is not None:
        preferred_ip = str(preferred_ip)
    return preferred_iface, preferred_ip


def _score_iface(name: str, ip: ipaddress.IPv4Address) -> int:
    score = 0
    lowered = name.casefold()
    if ip.is_private:
        score += 50
    if any(token in lowered for token in _GOOD_IFACE_TOKENS):
        score += 20
    if any(token in lowered for token in _BAD_IFACE_TOKENS):
        score -= 100
    if _is_virtualbox_hostonly_ip(ip):
        score -= 150
    if ip.is_link_local:
        score -= 50
    if ip.is_loopback:
        score -= 200
    return score


def _interface_kind(name: str) -> str:
    lowered = name.casefold()
    if any(token in lowered for token in _ETH_TOKENS):
        return "ethernet"
    if any(token in lowered for token in _WIFI_TOKENS):
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
    items.sort(key=lambda item: (str(item["name"]).lower(), str(item["ip"])))
    return items


def _fallback_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception as exc:
        logger.warning("Falling back to loopback IP: %s", exc)
        return "127.0.0.1"
    finally:
        sock.close()


def _active_ipv4_candidates() -> list[tuple[str, ipaddress.IPv4Address]]:
    candidates: list[tuple[str, ipaddress.IPv4Address]] = []
    for item in list_active_ipv4_interfaces():
        try:
            name = str(item.get("name") or "")
            ip = ipaddress.IPv4Address(str(item.get("ip") or ""))
        except Exception:
            continue
        if ip.is_loopback or ip.is_link_local:
            continue
        candidates.append((name, ip))
    return candidates


def get_local_ips() -> list[str]:
    """Ordered local IPv4 candidates for URLs shown to phone clients."""
    preferred_iface, preferred_ip = _load_network_settings()
    candidates = _active_ipv4_candidates()
    ordered: list[str] = []

    def push(value: str | None) -> None:
        if value and value not in ordered:
            ordered.append(value)

    if preferred_ip:
        for if_name, ip in candidates:
            if str(ip) == preferred_ip:
                push(str(ip))

    if preferred_iface:
        for if_name, ip in candidates:
            if if_name.casefold() == preferred_iface.casefold():
                push(str(ip))

    def pick_by_tokens(tokens: tuple[str, ...]) -> str | None:
        for if_name, ip in candidates:
            lowered = if_name.casefold()
            if _is_bad_iface(if_name):
                continue
            if _is_virtualbox_hostonly_ip(ip):
                continue
            if any(token in lowered for token in tokens):
                return str(ip)
        return None

    wifi_ip = pick_by_tokens(_WIFI_TOKENS)
    if wifi_ip:
        push(wifi_ip)

    eth_ip = pick_by_tokens(_ETH_TOKENS)
    if eth_ip:
        push(eth_ip)

    if candidates:
        scored = [(_score_iface(name, ip), name, str(ip), ip) for name, ip in candidates]
        scored.sort(key=lambda item: item[0], reverse=True)
        for _, name, ip, parsed_ip in scored:
            if _is_bad_iface(name) or _is_virtualbox_hostonly_ip(parsed_ip):
                continue
            push(ip)

    if ordered:
        return ordered

    if candidates:
        scored = [(_score_iface(name, ip), str(ip)) for name, ip in candidates]
        scored.sort(key=lambda item: item[0], reverse=True)
        for _, ip in scored:
            push(ip)

    if ordered:
        return ordered

    fallback = _fallback_ip()
    return [fallback] if fallback else []


def get_local_ip() -> str:
    """Best-effort local IP for printing the URL in console/UI."""
    items = get_local_ips()
    return items[0] if items else _fallback_ip()


def _normalize_host(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = raw if "://" in raw else f"//{raw}"
    parsed = urllib.parse.urlsplit(candidate)
    host = parsed.hostname
    return str(host).strip() if host else None


def get_public_hosts() -> list[str]:
    """Ordered public hosts for QR and browser entry points."""
    hosts: list[str] = []
    override = _normalize_host(config.PUBLIC_HOST)
    if override:
        hosts.append(override)
    primary = get_local_ip()
    if primary not in hosts:
        hosts.append(primary)
    return hosts
