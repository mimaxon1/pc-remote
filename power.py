"""Windows power actions used by the API endpoints.

This module intentionally keeps the implementation tiny and dependency-free.
All endpoints that call these functions are protected by the shared password
(`config.PASSWORD`).
"""

import os


def shutdown() -> None:
    """Shutdown the PC immediately."""
    os.system("shutdown /s /t 0")


def reboot() -> None:
    """Reboot the PC immediately."""
    os.system("shutdown /r /t 0")
