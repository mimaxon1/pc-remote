"""Default password (used only on first run).

On the first start the app creates `settings.json` next to the exe/script and
stores the password as a hash there. After that, change the password via the
web UI or `/change_password` endpoint (no rebuild needed).
"""

PASSWORD = "1234"
