"""Tiny tray GUI for status + logs."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import logging
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

import autostart
import config
import net_utils

Icon = Menu = MenuItem = None  # type: ignore[assignment]
Image = ImageDraw = ImageTk = None  # type: ignore[assignment]
qrcode = None  # type: ignore[assignment]
_PYSTRAY_AVAILABLE: bool | None = None
_PIL_AVAILABLE: bool | None = None
_QRCODE_AVAILABLE: bool | None = None

logger = logging.getLogger(config.LOGGER_NAME)


@dataclass(frozen=True)
class LogEntry:
    id: int
    message: str


phone_connected = False
logs: deque[LogEntry] = deque(maxlen=config.LOG_BUFFER_LIMIT)
gui_icon = None
_tk_root = None
_tk_queue: queue.Queue[Callable[[], None]] = queue.Queue()
_logs_lock = threading.Lock()
_next_log_id = 0
_pair_waiters: dict[str, threading.Event] = {}
_pair_waiters_lock = threading.Lock()


def _ensure_pystray() -> bool:
    global Icon, Menu, MenuItem, _PYSTRAY_AVAILABLE
    if _PYSTRAY_AVAILABLE is not None:
        return _PYSTRAY_AVAILABLE
    try:
        from pystray import Icon as _Icon, Menu as _Menu, MenuItem as _MenuItem

        Icon = _Icon
        Menu = _Menu
        MenuItem = _MenuItem
        _PYSTRAY_AVAILABLE = True
    except ImportError:
        _PYSTRAY_AVAILABLE = False
    return _PYSTRAY_AVAILABLE


def _ensure_pillow() -> bool:
    global Image, ImageDraw, ImageTk, _PIL_AVAILABLE
    if _PIL_AVAILABLE is not None:
        return _PIL_AVAILABLE
    try:
        from PIL import Image as _Image, ImageDraw as _ImageDraw, ImageTk as _ImageTk

        Image = _Image
        ImageDraw = _ImageDraw
        ImageTk = _ImageTk
        _PIL_AVAILABLE = True
    except ImportError:
        _PIL_AVAILABLE = False
    return _PIL_AVAILABLE


def _ensure_qrcode() -> bool:
    global qrcode, _QRCODE_AVAILABLE
    if _QRCODE_AVAILABLE is not None:
        return _QRCODE_AVAILABLE
    try:
        import qrcode as _qrcode

        qrcode = _qrcode
        _QRCODE_AVAILABLE = True
    except ImportError:
        _QRCODE_AVAILABLE = False
    return _QRCODE_AVAILABLE


def _tray_support_error() -> str | None:
    if not _ensure_pystray():
        return "pystray is not installed; tray UI disabled"
    if not _ensure_pillow():
        return "Pillow is not installed; tray UI disabled"
    return None


def add_log(message: str) -> None:
    """Append a log line for the tray "Logs" window."""
    global _next_log_id
    with _logs_lock:
        _next_log_id += 1
        logs.append(LogEntry(id=_next_log_id, message=message))
    print(message)


def get_logs(since: int | None, limit: int) -> tuple[list[LogEntry], int, bool]:
    """Return log entries and whether the caller should replace local state."""
    requested_limit = max(1, int(limit))
    with _logs_lock:
        entries = list(logs)
        last_id = entries[-1].id if entries else _next_log_id
        if since is None:
            selected = entries[-requested_limit:]
            next_since = selected[-1].id if selected else last_id
            return selected, next_since, True
        if not entries:
            return [], since, False
        oldest_id = entries[0].id
        if since < oldest_id - 1:
            selected = entries[-requested_limit:]
            next_since = selected[-1].id if selected else last_id
            return selected, next_since, True
        selected = [entry for entry in entries if entry.id > since]
        if len(selected) > requested_limit:
            selected = selected[-requested_limit:]
            return selected, selected[-1].id, True
        next_since = selected[-1].id if selected else since
        return selected, next_since, False


def _log_messages(limit: int | None = None) -> list[str]:
    with _logs_lock:
        entries = list(logs)
    if limit is not None:
        entries = entries[-max(1, int(limit)) :]
    return [entry.message for entry in entries]


def register_pair_waiter(token: str) -> threading.Event | None:
    if not token:
        return None
    waiter = threading.Event()
    with _pair_waiters_lock:
        _pair_waiters[token] = waiter
    return waiter


def clear_pair_waiter(token: str) -> None:
    if not token:
        return
    with _pair_waiters_lock:
        _pair_waiters.pop(token, None)


def notify_pair_completed(token: str) -> None:
    if not token:
        return
    with _pair_waiters_lock:
        waiter = _pair_waiters.get(token)
    if waiter is not None:
        waiter.set()


def set_phone_status(connected: bool) -> None:
    """Update tray title with the current phone connection state."""
    global phone_connected
    phone_connected = connected
    if gui_icon and gui_icon.visible:
        gui_icon.title = f"Ассистент - Телефон {'Подключен' if connected else 'Отключен'}"


def _process_tk_queue() -> None:
    while True:
        try:
            fn = _tk_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception as exc:
            logger.exception("GUI queue action failed: %s", exc)
            add_log(f"Ошибка GUI: {exc}")
    if _tk_root and _tk_root.winfo_exists():
        _tk_root.after(config.TK_QUEUE_POLL_MS, _process_tk_queue)


def _enqueue_tk(fn: Callable[[], None]) -> None:
    _tk_queue.put(fn)


def _ensure_root() -> tk.Tk:
    if _tk_root and _tk_root.winfo_exists():
        return _tk_root
    raise RuntimeError("Tk root is not ready")


def _open_logs() -> None:
    root = _ensure_root()
    win = tk.Toplevel(root)
    win.title("Логи ассистента")
    text = tk.Text(win, width=80, height=20)
    text.pack()
    for line in _log_messages():
        text.insert(tk.END, line + "\n")


def show_logs(icon, item) -> None:
    _enqueue_tk(_open_logs)


def create_image():
    if not _ensure_pillow():
        raise RuntimeError("Pillow is required for tray icon rendering")
    image = Image.new("RGB", (64, 64), color="green")
    d = ImageDraw.Draw(image)
    d.rectangle((16, 16, 48, 48), fill="lightgreen")
    return image


def _web_url() -> str:
    host = net_utils.get_public_hosts()[0]
    return f"http://{host}:{config.WEB_PORT}"


def _api_url() -> str:
    host = net_utils.get_public_hosts()[0]
    return f"http://{host}:{config.API_PORT}"


def _copy_to_clipboard(root: tk.Tk, value: str) -> None:
    root.clipboard_clear()
    root.clipboard_append(value)
    root.update()


def _api_post_local(path: str, payload: dict[str, object]) -> tuple[int | None, str]:
    url = f"http://127.0.0.1:{config.API_PORT}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.HTTP_CLIENT_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        return exc.code, body
    except Exception as exc:
        logger.warning("Local API request to %s failed: %s", path, exc)
        return None, str(exc)


def _api_post(path: str, payload: dict[str, object]) -> tuple[int | None, str]:
    return _api_post_local(path, payload)


def _get_pair_payload() -> tuple[str | None, bool]:
    code, body = _api_post_local("/pair", {})
    if code != 200:
        logger.warning("Failed to request QR pair token, status=%s", code)
        return None, False
    try:
        data = json.loads(body)
        token = str(data.get("token") or "")
        return token or None, bool(data.get("requires_password_setup", False))
    except Exception as exc:
        logger.warning("Failed to parse QR pair token response: %s", exc)
        return None, False

def _pair_url(base_url: str, token: str | None) -> str:
    if not token:
        return base_url
    query = urllib.parse.urlencode({"token": token})
    return f"{base_url}/?{query}"


def _alternative_pair_urls(token: str | None) -> list[str]:
    urls: list[str] = []
    for host in net_utils.get_public_hosts()[1:]:
        url = _pair_url(f"http://{host}:{config.WEB_PORT}", token)
        if url not in urls:
            urls.append(url)
    return urls


def _open_qr() -> None:
    if not _ensure_pillow() or not _ensure_qrcode():
        add_log("QR окно недоступно: установите Pillow и qrcode")
        return

    token, requires_setup = _get_pair_payload()
    base_url = _web_url()
    pair_url = _pair_url(base_url, token)
    if not token:
        logger.warning("QR token was not issued; showing base web address only")

    root = _ensure_root()
    win = tk.Toplevel(root)
    win.title("QR код")
    win.resizable(False, False)

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )  # type: ignore[attr-defined]
    qr.add_data(pair_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")  # type: ignore[union-attr]
    img = img.resize((260, 260), Image.NEAREST)  # type: ignore[attr-defined]
    tk_img = ImageTk.PhotoImage(img, master=win)

    label = tk.Label(win, image=tk_img)
    label.image = tk_img  # type: ignore[attr-defined]
    label.pack(padx=12, pady=(12, 6))

    tk.Label(win, text=pair_url, wraplength=260, justify="center").pack(pady=(0, 6))
    alternative_urls = _alternative_pair_urls(token)
    if alternative_urls:
        tk.Label(
            win,
            text="If this QR URL times out, try:\n" + "\n".join(alternative_urls[:3]),
            wraplength=260,
            justify="center",
        ).pack(padx=12, pady=(0, 6))
    if requires_setup:
        tk.Label(
            win,
            text="Первый запуск: открой QR и задай PIN из 4 цифр.",
            wraplength=260,
            justify="center",
        ).pack(padx=12, pady=(0, 6))
    else:
        tk.Label(
            win,
            text="QR подключает сразу, без ввода PIN на телефоне.",
            wraplength=260,
            justify="center",
        ).pack(padx=12, pady=(0, 6))
    tk.Button(
        win,
        text="Скопировать адрес",
        command=lambda: _copy_to_clipboard(win, pair_url),
    ).pack(pady=(0, 12))

    if token:
        pair_waiter = register_pair_waiter(token)

        def close_qr_window() -> None:
            if win.winfo_exists():
                win.destroy()

        def wait_for_pair_completion() -> None:
            if pair_waiter is None:
                return
            pair_waiter.wait()
            _enqueue_tk(close_qr_window)

        def on_destroy(event) -> None:
            if event.widget is win:
                clear_pair_waiter(token)
                if pair_waiter is not None:
                    pair_waiter.set()

        win.bind("<Destroy>", on_destroy)
        threading.Thread(target=wait_for_pair_completion, daemon=True).start()


def show_qr(icon, item) -> None:
    _enqueue_tk(_open_qr)


def _open_settings() -> None:
    root = _ensure_root()
    win = tk.Toplevel(root)
    win.title("Настройки")
    win.resizable(False, False)

    web_url = _web_url()
    api_url = _api_url()

    tk.Label(win, text="Web:").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
    tk.Label(win, text=web_url).grid(row=0, column=1, sticky="w", padx=6, pady=(12, 4))
    tk.Button(win, text="Скопировать", command=lambda: _copy_to_clipboard(win, web_url)).grid(row=0, column=2, padx=12, pady=(12, 4))

    tk.Label(win, text="API:").grid(row=1, column=0, sticky="w", padx=12, pady=4)
    tk.Label(win, text=api_url).grid(row=1, column=1, sticky="w", padx=6, pady=4)
    tk.Button(win, text="Скопировать", command=lambda: _copy_to_clipboard(win, api_url)).grid(row=1, column=2, padx=12, pady=4)

    status_var = tk.StringVar()

    def update_autostart_ui() -> None:
        enabled = autostart.is_enabled()
        status_var.set("Включен" if enabled else "Выключен")
        enable_btn.configure(state=tk.DISABLED if enabled else tk.NORMAL)
        disable_btn.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def enable() -> None:
        try:
            path = autostart.install()
            add_log(f"Автозапуск включен: {path}")
        except Exception as exc:
            logger.exception("Failed to enable autostart: %s", exc)
            add_log(f"Не удалось включить автозапуск: {exc}")
        update_autostart_ui()

    def disable() -> None:
        try:
            removed = autostart.remove()
            if removed:
                add_log("Автозапуск выключен")
            else:
                add_log("Автозапуск и так не был включен")
        except Exception as exc:
            logger.exception("Failed to disable autostart: %s", exc)
            add_log(f"Не удалось выключить автозапуск: {exc}")
        update_autostart_ui()

    tk.Label(win, text="Автозапуск:").grid(row=2, column=0, sticky="w", padx=12, pady=(10, 4))
    tk.Label(win, textvariable=status_var).grid(row=2, column=1, sticky="w", padx=6, pady=(10, 4))
    enable_btn = tk.Button(win, text="Включить", command=enable)
    disable_btn = tk.Button(win, text="Выключить", command=disable)
    enable_btn.grid(row=3, column=1, sticky="w", padx=6, pady=(0, 8))
    disable_btn.grid(row=3, column=2, sticky="w", padx=6, pady=(0, 8))

    tk.Button(win, text="Открыть логи", command=_open_logs).grid(row=3, column=0, sticky="w", padx=12, pady=(0, 8))

    tk.Label(win, text="Смена PIN:").grid(row=4, column=0, sticky="w", padx=12, pady=(8, 4))
    tk.Label(win, text="Текущий").grid(row=5, column=0, sticky="w", padx=12, pady=2)
    current_entry = tk.Entry(win, show="*")
    current_entry.grid(row=5, column=1, columnspan=2, sticky="we", padx=6, pady=2)

    tk.Label(win, text="Новый").grid(row=6, column=0, sticky="w", padx=12, pady=2)
    new_entry = tk.Entry(win, show="*")
    new_entry.grid(row=6, column=1, columnspan=2, sticky="we", padx=6, pady=2)

    pw_status = tk.StringVar(value="")
    tk.Label(win, textvariable=pw_status).grid(row=7, column=0, columnspan=3, sticky="w", padx=12, pady=(4, 4))

    def change_password() -> None:
        current_pw = current_entry.get().strip()
        new_pw = new_entry.get().strip()
        if not current_pw or not new_pw:
            pw_status.set("Заполни оба поля")
            return
        if len(new_pw) != config.PIN_LENGTH or not new_pw.isdigit():
            pw_status.set(f"Новый PIN: {config.PIN_LENGTH} цифры")
            return
        code, _ = _api_post(
            "/change_password",
            {
                "current_password": current_pw,
                "new_password": new_pw,
            },
        )
        if code == 200:
            pw_status.set("PIN изменен")
            current_entry.delete(0, tk.END)
            new_entry.delete(0, tk.END)
        elif code == 403:
            pw_status.set("Неверный текущий PIN")
        elif code == 400:
            pw_status.set(f"Новый PIN должен быть из {config.PIN_LENGTH} цифр")
        elif code is None:
            pw_status.set("Нет связи с сервером")
        else:
            pw_status.set("Ошибка смены PIN")

    tk.Button(win, text="Сменить PIN", command=change_password).grid(row=8, column=1, sticky="w", padx=6, pady=(0, 12))

    update_autostart_ui()


def show_settings(icon, item) -> None:
    _enqueue_tk(_open_settings)


def quit_app(icon, item) -> None:
    icon.stop()
    logger.info("Tray exit requested")


def start_tray() -> None:
    global gui_icon
    if not _ensure_pystray():
        add_log("pystray не установлен, tray GUI отключен")
        return
    menu = Menu(
        MenuItem("QR код", show_qr),
        MenuItem("Настройки", show_settings),
        MenuItem("Выход", quit_app),
    )
    gui_icon = Icon(
        "PC Remote",
        create_image(),
        f"Ассистент - Телефон {'Подключен' if phone_connected else 'Отключен'}",
        menu,
    )
    gui_icon.run()


def start_gui() -> None:
    global _tk_root
    root = tk.Tk()
    root.withdraw()
    _tk_root = root
    root.after(config.TK_QUEUE_POLL_MS, _process_tk_queue)
    root.mainloop()


def run() -> None:
    """Start tkinter loop + tray icon."""
    support_error = _tray_support_error()
    if support_error:
        add_log(support_error)
        add_log("Running without tray UI; API and web servers stay active.")
        start_gui()
        return

    threading.Thread(target=start_gui, daemon=True).start()
    start_tray()
