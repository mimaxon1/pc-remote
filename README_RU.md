<p align="center">
  <img src="web/icons/icon-192.png" alt="Иконка PC Remote" width="96">
</p>

<h1 align="center">PC Remote</h1>

<p align="center">
  Управление Windows-компьютером с телефона в одной локальной сети.
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>Русский</strong>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml">
    <img src="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml/badge.svg?branch=main" alt="Tests">
  </a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.13%2B-3776AB" alt="Python">
</p>

PC Remote — лёгкий локальный пульт управления Windows. На компьютере работает приложение в системном трее, а с телефона можно подключиться через обычный браузер без установки отдельного мобильного приложения.

Текущая версия: `v1.4.1`

## Возможности

- Первичное подключение по QR-коду
- Вход по PIN-коду и короткоживущие сессионные токены
- Управление громкостью, mute, мультимедиа и аудиовыходом
- Запуск недавних и закреплённых приложений
- Открытие, сворачивание и закрытие окон приложений
- Управление питанием Windows
- Русский и английский интерфейс
- Светлая и тёмная темы
- Приложение в трее, автозапуск и защита от нескольких экземпляров
- Portable-сборка для Windows, не требующая установленного Python

## Архитектура

```text
Браузер телефона
       |
       | локальный Wi-Fi / LAN
       v
Web-контроллер :8080
       |
       v
FastAPI API :8000
       |
       +-- аудио / мультимедиа
       +-- приложения и окна
       +-- управление питанием
       +-- аутентификация
       |
Приложение в системном трее Windows
```

Проект изначально сделан как local-first: облачный сервис и внешний аккаунт для работы не нужны.

## Безопасность

PC Remote рассчитан на доверенную локальную сеть и не должен напрямую публиковаться в интернет.

- PIN-коды хранятся в виде salted PBKDF2-HMAC-SHA256 хешей
- Сессионные токены создаются через модуль Python `secrets` и хранятся только в памяти
- CORS ограничен локальными origin-адресами
- Попытки входа ограничиваются rate limit
- Runtime-настройки хранятся в `%APPDATA%\PC Remote` и не входят в репозиторий

По умолчанию используется HTTP, поскольку приложение предназначено для локальной сети. Для доступа через недоверенную сеть лучше использовать защищённый VPN или другой безопасный транспорт, а не пробрасывать порты приложения напрямую в интернет.

Информация о сообщении уязвимостей: [SECURITY.md](SECURITY.md).

## Быстрый запуск

Требования:

- Windows 10 или Windows 11
- Python 3.13+
- Компьютер и телефон в одной локальной сети

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

После запуска приложение в трее поднимет API и web-контроллер. Для подключения телефона используйте QR-код из меню приложения.

## Portable-сборка

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pyinstaller tzdata
python build_release.py
```

Результат:

```text
dist\PC Remote\PC Remote.exe
```

Чтобы специально собрать чистую версию без сохранённых локальных настроек:

```powershell
python build_release.py --reset-settings
```

## Тесты

```powershell
.venv\Scripts\python.exe -m pytest
```

Тесты покрывают аутентификацию, запуск приложения, API-сценарии, Windows-интеграции, безопасность GUI и управление приложениями. Они также запускаются через GitHub Actions.

## Структура проекта

```text
.
|- main.py             точка входа FastAPI и запуск приложения
|- auth.py             PIN, pairing и сессионные токены
|- gui.py              приложение в трее и окна настройки
|- apps.py             поиск и запуск приложений
|- audio.py            интеграция с аудио Windows
|- web/                web-интерфейс для телефона
|- tests/              автоматические тесты
|- docs/               дополнительная документация
|- build_release.py    сборка portable-версии
```

## Документация

- [Тестирование](docs/testing_RU.md) · [English](docs/testing.md)
- [История изменений](CHANGELOG_RU.md) · [English](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Лицензия

Проект распространяется по лицензии Apache License 2.0. См. [LICENSE](LICENSE) и [NOTICE](NOTICE).
