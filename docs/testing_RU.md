# Тестирование

[English](testing.md) · **Русский**

## Обзор

Автоматические тесты находятся в каталоге `tests/` и настраиваются через `pytest.ini`. Они рассчитаны на локальный запуск и GitHub Actions без реальных аудиоустройств, ручного взаимодействия с GUI и внешних сервисов.

## Подготовка окружения

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Запуск всех тестов

```powershell
python -m pytest
```

## Запуск отдельного файла

```powershell
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_main.py -v
python -m pytest tests/test_audio.py -v
```

## Запуск отдельного теста

```powershell
python -m pytest tests/test_auth.py::TestPasswordHash::test_password_hash_creation -v
```

## Покрытие кода

```powershell
python -m pip install pytest-cov
python -m pytest --cov=. --cov-report=html
```

## Структура тестов

- `tests/test_auth.py` — хеширование PIN, токены, первичная настройка и жизненный цикл аутентификации
- `tests/test_main.py` — запуск API, health-check, перезапуск, endpoints приложений и кэширование
- `tests/test_audio.py` — работа с аудио, выбор устройства, громкость и обработка ошибок
- `tests/test_gui.py` — fallback-логика трея, pairing helpers и безопасная работа Tk
- `tests/test_apps.py` — поиск приложений, быстрый запуск, закреплённые приложения и действия с окнами
- `tests/test_net_utils.py` — выбор локального IP и определение доступных LAN-адресов

## Добавление новых тестов

Предпочтительны небольшие изолированные тесты. Windows-зависимое поведение лучше закрывать моками, чтобы результат не зависел от конкретного компьютера.

```python
from unittest.mock import patch


class TestNewFeature:
    def test_example(self):
        with patch("module.function"):
            assert True
```

## CI

- GitHub Actions запускается на `windows-latest`
- основная команда CI: `python -m pytest`
- новые функции желательно сопровождать тестами

## Если тесты не запускаются

- запускайте команды из корня репозитория
- при ошибках импорта заново установите зависимости из `requirements.txt`
- тесты аудио и GUI используют моки, поэтому наличие конкретного оборудования не требуется
- будущие тесты упаковки лучше держать отдельно от быстрого основного набора
