"""Unit tests for network host selection helpers."""

from __future__ import annotations

import config
import net_utils


class TestLocalHostSelection:
    def test_get_local_ips_prefers_wifi_before_ethernet(self, monkeypatch):
        monkeypatch.setattr(net_utils, "_load_network_settings", lambda: (None, None))
        monkeypatch.setattr(
            net_utils,
            "list_active_ipv4_interfaces",
            lambda: [
                {"name": "Ethernet", "ip": "10.0.0.20"},
                {"name": "Wi-Fi", "ip": "192.168.1.30"},
            ],
        )

        assert net_utils.get_local_ips() == ["192.168.1.30", "10.0.0.20"]

    def test_get_local_ips_respects_saved_preferred_ip(self, monkeypatch):
        monkeypatch.setattr(net_utils, "_load_network_settings", lambda: (None, "10.0.0.20"))
        monkeypatch.setattr(
            net_utils,
            "list_active_ipv4_interfaces",
            lambda: [
                {"name": "Ethernet", "ip": "10.0.0.20"},
                {"name": "Wi-Fi", "ip": "192.168.1.30"},
            ],
        )

        assert net_utils.get_local_ips()[0] == "10.0.0.20"

    def test_get_public_hosts_prepends_normalized_override(self, monkeypatch):
        monkeypatch.setattr(config, "PUBLIC_HOST", "https://pc-remote.local:8080")
        monkeypatch.setattr(net_utils, "get_local_ip", lambda: "192.168.1.30")

        assert net_utils.get_public_hosts() == ["pc-remote.local", "192.168.1.30"]

    def test_get_local_ips_prefers_wifi_when_vpn_exists(self, monkeypatch):
        monkeypatch.setattr(net_utils, "_load_network_settings", lambda: (None, None))
        monkeypatch.setattr(
            net_utils,
            "list_active_ipv4_interfaces",
            lambda: [
                {"name": "Windscribe IKEv2", "ip": "10.10.10.20"},
                {"name": "Wi-Fi", "ip": "192.168.1.30"},
            ],
        )

        assert net_utils.get_local_ips()[0] == "192.168.1.30"
