"""Tiny tray GUI for status + logs.

Uses:
- tkinter (hidden root window for message loop)
- pystray for the tray icon and context menu
"""
import tkinter as tk
try:
    from pystray import Icon, MenuItem, Menu
    _PYSTRAY_AVAILABLE = True
except ImportError:
    Icon = MenuItem = Menu = None  # type: ignore[assignment]
    _PYSTRAY_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageTk
    _PIL_AVAILABLE = True
except ImportError:
    Image = ImageDraw = ImageTk = None  # type: ignore[assignment]
    _PIL_AVAILABLE = False
import threading
import queue
from typing import Callable
import json
import urllib.request
import urllib.error
import urllib.parse
import autostart
import net_utils
try:
    import qrcode
    _QRCODE_AVAILABLE = True
except ImportError:
    qrcode = None  # type: ignore[assignment]
    _QRCODE_AVAILABLE = False

phone_connected = False
logs = []
gui_icon = None
WEB_PORT = 8080
API_PORT = 8000
_tk_root = None
_tk_queue: queue.Queue[Callable] = queue.Queue()


def _tray_support_error() -> str | None:
    if not _PYSTRAY_AVAILABLE:
        return "pystray is not installed; tray UI disabled"
    if not _PIL_AVAILABLE:
        return "Pillow is not installed; tray UI disabled"
    return None

def add_log(message: str):
    """Append a log line for the tray "Logs" window (and print to console)."""
    logs.append(message)
    # Prevent unbounded growth (API/web can also display logs).
    if len(logs) > 500:
        del logs[:-500]
    print(message)  # для дебага в консоли

def set_phone_status(connected: bool):
    """Update tray title with the current phone connection state."""
    global phone_connected
    phone_connected = connected
    if gui_icon and gui_icon.visible:
        gui_icon.title = f"Ассистент - Телефон {'Подключен' if connected else 'Отключен'}"

def _process_tk_queue():
    while True:
        try:
            fn = _tk_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception as exc:
            add_log(f"Ошибка GUI: {exc}")
    if _tk_root and _tk_root.winfo_exists():
        _tk_root.after(80, _process_tk_queue)

def _enqueue_tk(fn):
    _tk_queue.put(fn)

def _ensure_root() -> tk.Tk:
    if _tk_root and _tk_root.winfo_exists():
        return _tk_root
    raise RuntimeError("Tk root is not ready")

def _open_logs():
    """Open a simple window showing accumulated logs."""
    root = _ensure_root()
    win = tk.Toplevel(root)
    win.title("Логи ассистента")
    text = tk.Text(win, width=80, height=20)
    text.pack()
    for line in logs:
        text.insert(tk.END, line + "\n")

def show_logs(icon, item):
    _enqueue_tk(_open_logs)

def create_image():
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow is required for tray icon rendering")
    image = Image.new('RGB', (64, 64), color='green')
    d = ImageDraw.Draw(image)
    d.rectangle((16, 16, 48, 48), fill='lightgreen')
    return image

def _web_url() -> str:
    ip = net_utils.get_local_ip()
    return f"http://{ip}:{WEB_PORT}"

def _api_url() -> str:
    ip = net_utils.get_local_ip()
    return f"http://{ip}:{API_PORT}"

def _copy_to_clipboard(root: tk.Tk, value: str) -> None:
    root.clipboard_clear()
    root.clipboard_append(value)
    root.update()

def _api_post(path: str, payload: dict) -> tuple[int | None, str]:
    return _api_post_local(path, payload)

def _api_post_local(path: str, payload: dict) -> tuple[int | None, str]:
    url = f"http://127.0.0.1:{API_PORT}" + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        return exc.code, body
    except Exception as exc:
        return None, str(exc)

def _get_pair_payload() -> tuple[str | None, bool]:
    code, body = _api_post_local("/pair", {})
    if code != 200:
        return None, False
    try:
        data = json.loads(body)
        token = str(data.get("token") or "")
        return token or None, bool(data.get("requires_password_setup", False))
    except Exception:
        return None, False


def _get_pair_status(token: str) -> tuple[bool, bool]:
    code, body = _api_post_local("/pair_status", {"token": token})
    if code != 200:
        return False, False
    try:
        data = json.loads(body)
        return bool(data.get("opened")), bool(data.get("completed"))
    except Exception:
        return False, False

def _open_qr():
    if not _PIL_AVAILABLE or not _QRCODE_AVAILABLE:
        add_log("QR окно недоступно: установите Pillow и qrcode")
        return
    token, requires_setup = _get_pair_payload()
    url = _web_url()
    if token:
        query = urllib.parse.urlencode({"token": token})
        url = f"{url}/?{query}"
    root = _ensure_root()
    win = tk.Toplevel(root)
    win.title("QR код")
    win.resizable(False, False)

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)  # type: ignore
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")  # type: ignore
    img = img.resize((260, 260), Image.NEAREST)  # type: ignore
    tk_img = ImageTk.PhotoImage(img, master=win)

    label = tk.Label(win, image=tk_img)
    label.image = tk_img  # type: ignore
    label.pack(padx=12, pady=(12, 6))

    tk.Label(win, text=url).pack(pady=(0, 6))
    if requires_setup:
        tk.Label(
            win,
            text="Первый запуск: открой QR и задай пароль из 4 цифр.",
            wraplength=260,
            justify="center",
        ).pack(padx=12, pady=(0, 6))
    else:
        tk.Label(
            win,
            text="QR подключает сразу, без ввода пароля на телефоне.",
            wraplength=260,
            justify="center",
        ).pack(padx=12, pady=(0, 6))
    tk.Button(win, text="Скопировать ссылку", command=lambda: _copy_to_clipboard(win, url)).pack(pady=(0, 12))  # type: ignore

    if token:
        def poll_pair_status() -> None:
            if not win.winfo_exists():
                return
            _, completed = _get_pair_status(token)
            if completed:
                win.destroy()
                return
            win.after(700, poll_pair_status)

        win.after(700, poll_pair_status)

def show_qr(icon, item):
    _enqueue_tk(_open_qr)

def _open_settings():
    root = _ensure_root()
    win = tk.Toplevel(root)
    win.title("Настройки")
    win.resizable(False, False)

    web_url = _web_url()
    api_url = _api_url()

    tk.Label(win, text="Web:").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
    tk.Label(win, text=web_url).grid(row=0, column=1, sticky="w", padx=6, pady=(12, 4))
    tk.Button(win, text="Скопировать", command=lambda: _copy_to_clipboard(win, web_url)).grid(row=0, column=2, padx=12, pady=(12, 4))  # type: ignore

    tk.Label(win, text="API:").grid(row=1, column=0, sticky="w", padx=12, pady=4)
    tk.Label(win, text=api_url).grid(row=1, column=1, sticky="w", padx=6, pady=4)
    tk.Button(win, text="Скопировать", command=lambda: _copy_to_clipboard(win, api_url)).grid(row=1, column=2, padx=12, pady=4)  # type: ignore

    status_var = tk.StringVar()

    def update_autostart_ui():
        enabled = autostart.is_enabled()
        status_var.set("Включен" if enabled else "Выключен")
        enable_btn.configure(state=tk.DISABLED if enabled else tk.NORMAL)
        disable_btn.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def enable():
        try:
            path = autostart.install()
            add_log(f"Автозапуск включен: {path}")
        except Exception as exc:
            add_log(f"Не удалось включить автозапуск: {exc}")
        update_autostart_ui()

    def disable():
        try:
            removed = autostart.remove()
            if removed:
                add_log("Автозапуск выключен")
            else:
                add_log("Автозапуск и так не был включен")
        except Exception as exc:
            add_log(f"Не удалось выключить автозапуск: {exc}")
        update_autostart_ui()

    tk.Label(win, text="Автозапуск:").grid(row=2, column=0, sticky="w", padx=12, pady=(10, 4))
    tk.Label(win, textvariable=status_var).grid(row=2, column=1, sticky="w", padx=6, pady=(10, 4))
    enable_btn = tk.Button(win, text="Включить", command=enable)
    disable_btn = tk.Button(win, text="Выключить", command=disable)
    enable_btn.grid(row=3, column=1, sticky="w", padx=6, pady=(0, 8))
    disable_btn.grid(row=3, column=2, sticky="w", padx=6, pady=(0, 8))

    tk.Button(win, text="Открыть логи", command=_open_logs).grid(row=3, column=0, sticky="w", padx=12, pady=(0, 8))

    tk.Label(win, text="Смена пароля:").grid(row=4, column=0, sticky="w", padx=12, pady=(8, 4))
    tk.Label(win, text="Текущий").grid(row=5, column=0, sticky="w", padx=12, pady=2)
    current_entry = tk.Entry(win, show="*")
    current_entry.grid(row=5, column=1, columnspan=2, sticky="we", padx=6, pady=2)

    tk.Label(win, text="Новый").grid(row=6, column=0, sticky="w", padx=12, pady=2)
    new_entry = tk.Entry(win)
    new_entry.grid(row=6, column=1, columnspan=2, sticky="we", padx=6, pady=2)

    pw_status = tk.StringVar(value="")
    pw_status_label = tk.Label(win, textvariable=pw_status)
    pw_status_label.grid(row=7, column=0, columnspan=3, sticky="w", padx=12, pady=(4, 4))

    def change_password():
        current_pw = current_entry.get().strip()
        new_pw = new_entry.get().strip()
        if not current_pw or not new_pw:
            pw_status.set("Заполни оба поля")
            return
        if len(new_pw) != 4 or not new_pw.isdigit():
            pw_status.set("Новый пароль: 4 цифры")
            return
        code, _ = _api_post("/change_password", {
            "current_password": current_pw,
            "new_password": new_pw,
        })
        if code == 200:
            pw_status.set("Пароль изменён")
            current_entry.delete(0, tk.END)
            new_entry.delete(0, tk.END)
        elif code == 403:
            pw_status.set("Неверный текущий пароль")
        elif code == 400:
            pw_status.set("Новый пароль должен быть 4 цифры")
        elif code is None:
            pw_status.set("Нет связи с сервером")
        else:
            pw_status.set("Ошибка смены пароля")

    tk.Button(win, text="Сменить пароль", command=change_password).grid(row=8, column=1, sticky="w", padx=6, pady=(0, 12))

    update_autostart_ui()

def show_settings(icon, item):
    _enqueue_tk(_open_settings)

def quit_app(icon, item):
    """Exit the tray icon loop."""
    icon.stop()
    print("Выход из трея")

def start_tray():
    global gui_icon
    if not _PYSTRAY_AVAILABLE:
        add_log("pystray не установлен, tray GUI отключен")
        return
    menu = Menu(
        MenuItem('QR код', show_qr),
        MenuItem('Настройки', show_settings),
        MenuItem('Выход', quit_app)
    )
    gui_icon = Icon("PC Remote", create_image(),
                    f"Ассистент - Телефон {'Подключен' if phone_connected else 'Отключен'}", menu)
    gui_icon.run()

def start_gui():
    global _tk_root
    root = tk.Tk()
    root.withdraw()
    _tk_root = root
    root.after(80, _process_tk_queue)
    root.mainloop()

def run():
    """Start tkinter loop + tray icon."""
    support_error = _tray_support_error()
    if support_error:
        add_log(support_error)
        add_log("Running without tray UI; API and web servers stay active.")
        start_gui()
        return

    threading.Thread(target=start_gui, daemon=True).start()
    start_tray()
