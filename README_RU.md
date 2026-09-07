<p align="center">
  <img src="web/icons/icon-192.png" alt="Иконка PC Remote" width="96">
</p>

<h1 align="center">PC Remote</h1>

<p align="center">
  <strong>Управляйте Windows-компьютером из браузера любого телефона.</strong><br>
  Без мобильного приложения, аккаунта и облака. Запустили, отсканировали QR-код — готово.
</p>

<p align="center">
  <a href="README.md">English</a> · <strong>Русский</strong>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/releases/latest"><strong>Скачать для Windows</strong></a>
  ·
  <a href="docs/faq_RU.md">FAQ</a>
</p>

<p align="center">
  <a href="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml"><img src="https://github.com/mimaxon1/pc-remote/actions/workflows/tests.yml/badge.svg?branch=main" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6" alt="Windows 10/11">
  <img src="https://img.shields.io/github/license/mimaxon1/pc-remote" alt="License">
  <img src="https://img.shields.io/github/v/release/mimaxon1/pc-remote" alt="Latest release">
</p>

PC Remote — лёгкий open-source пульт для Windows, который превращает браузер Android или iPhone в локальную панель управления компьютером. Проект рассчитан на тех, кому нужен простой local-first вариант без облачного сервиса и обязательного приложения на телефоне.

Подходит для дивана и ТВ, презентаций, демонстрационных ПК, стриминга, домашней сети и других сценариев в одном Wi-Fi/LAN.

## Почему PC Remote

- **На телефон ничего ставить не нужно** — достаточно современного браузера.
- **Нет аккаунта и облака** — управление остаётся внутри локальной сети.
- **Быстрое подключение** — запуск приложения и QR-код.
- **Есть готовая Windows-сборка** — Python обычному пользователю не нужен.
- **Полезные повседневные функции** — приложения, окна, громкость, мультимедиа, аудиовыход и питание.
- **Открытый исходный код** — можно проверить, изменить или собрать проект самостоятельно.

Если вы ищете open-source Windows remote, браузерный пульт для ПК или лёгкую локальную альтернативу решениям вроде Unified Remote, PC Remote сделан именно под этот сценарий.

## Быстрый старт

1. Откройте [последний релиз](https://github.com/mimaxon1/pc-remote/releases/latest).
2. Скачайте Windows-сборку.
3. Запустите `PC Remote.exe`.
4. Откройте окно QR-подключения через иконку в трее.
5. Отсканируйте QR-код телефоном в той же локальной сети.
6. Управляйте компьютером из браузера.

Старые релизы могут содержать только portable ZIP. Новые релизы по тегам настроены на автоматическую публикацию и установщика Windows, и portable ZIP.

## Что можно управлять

- Системной громкостью и mute
- Мультимедиа
- Выбором аудиовыхода
- Недавними и закреплёнными приложениями
- Запуском desktop-приложений
- Открытием, сворачиванием и закрытием окон
- Действиями питания Windows
- Автозапуском и поведением приложения в трее
- Светлой и тёмной темой
- Русским и английским web-интерфейсом

## Где это удобно

- Диван / HTPC
- ПК, подключённый к телевизору
- Презентации и демонстрационные компьютеры
- Игровые и стриминговые сетапы
- Второй экран как панель управления
- Домашняя лаборатория и self-hosted Windows

## Local-first архитектура

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

Внешний аккаунт и облачный backend для работы не нужны.

## Безопасность

PC Remote рассчитан на доверенную локальную сеть. **Не публикуйте его порты напрямую в интернет.**

- PIN-коды хранятся как salted PBKDF2-HMAC-SHA256 хеши
- Сессионные токены создаются через Python `secrets` и хранятся в памяти
- CORS ограничен локальными origin-адресами
- Попытки входа ограничиваются rate limit
- Runtime-настройки хранятся в `%APPDATA%\PC Remote`

По умолчанию используется HTTP, потому что приложение предназначено для локальной сети. Для доступа извне используйте аутентифицированный VPN или другой защищённый транспорт вместо прямого проброса портов.

Сообщение об уязвимостях: [SECURITY.md](SECURITY.md).

## Windows-сборки

Проект поддерживает два формата релиза:

- **Installer** — обычная установка для текущего пользователя, ярлык в меню «Пуск» и опциональный ярлык на рабочем столе.
- **Portable ZIP** — распаковать и запустить без установки.

Релизы по тегам `v*` собираются автоматически через GitHub Actions: запускаются тесты, PyInstaller-сборка, Inno Setup installer, portable ZIP и SHA-256 checksums.

## Запуск из исходников

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

## Сборка из исходников

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pyinstaller tzdata
python build_release.py
```

Portable-результат:

```text
dist\PC Remote\PC Remote.exe
```

Для чистой first-run сборки без сохранённых локальных настроек:

```powershell
python build_release.py --reset-settings
```

Для создания установщика после portable-сборки скомпилируйте [`installer/PC-Remote.iss`](installer/PC-Remote.iss) через Inno Setup 6.

## Тесты

```powershell
.venv\Scripts\python.exe -m pytest
```

Тесты также запускаются через GitHub Actions.

## Структура проекта

```text
.
|- main.py                 точка входа FastAPI и запуск приложения
|- auth.py                 PIN, pairing и сессионные токены
|- gui.py                  приложение в трее и окна настройки
|- apps.py                 поиск и запуск приложений
|- audio.py                интеграция с аудио Windows
|- web/                    web-интерфейс для телефона
|- tests/                  автоматические тесты
|- installer/              описание Windows-установщика
|- docs/                   документация и материалы для публикации
|- build_release.py        сборка portable-версии
```

## Документация

- [FAQ и сценарии](docs/faq_RU.md) · [English](docs/faq.md)
- [Тестирование](docs/testing_RU.md) · [English](docs/testing.md)
- [Материалы для публикации](docs/PROMOTION.md)
- [История изменений](CHANGELOG_RU.md) · [English](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Лицензия

Apache License 2.0. См. [LICENSE](LICENSE) и [NOTICE](NOTICE).
