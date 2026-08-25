# Testing Guide

**English** · [Русский](testing_RU.md)

## Overview

The automated test suite lives in the `tests/` directory and is configured
through `pytest.ini`. Tests are designed to run locally and in GitHub Actions
without requiring real audio devices, GUI interaction, or external services.

## Setup

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run The Full Suite

```powershell
python -m pytest
```

## Run A Specific File

```powershell
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_main.py -v
python -m pytest tests/test_audio.py -v
```

## Run A Specific Test

```powershell
python -m pytest tests/test_auth.py::TestPasswordHash::test_password_hash_creation -v
```

## Run With Coverage

```powershell
python -m pip install pytest-cov
python -m pytest --cov=. --cov-report=html
```

## Test Layout

- `tests/test_auth.py`: password hashing, tokens, setup, and auth lifecycle
- `tests/test_main.py`: API startup, health checks, restart flow, app endpoints, and caching
- `tests/test_audio.py`: audio helpers, device selection, volume control, and failure handling
- `tests/test_gui.py`: tray fallbacks, pairing helpers, and Tk safety checks
- `tests/test_apps.py`: app discovery, quick launch, pinned apps, and window actions
- `tests/test_net_utils.py`: local IP selection and public host resolution

## Writing New Tests

Use small, focused tests that isolate platform-specific behavior with mocks.
The existing suite follows a straightforward `pytest` + `unittest.mock` style.

```python
from unittest.mock import patch


class TestNewFeature:
    def test_example(self):
        with patch("module.function"):
            assert True
```

## CI Notes

- The GitHub Actions workflow runs on `windows-latest`
- The CI entry point is `python -m pytest`
- New features should ship with tests or a short justification for missing coverage

## Troubleshooting

- Run commands from the repository root so imports resolve normally
- If a dependency is missing, reinstall from `requirements.txt`
- Audio and GUI tests rely on mocks, so local hardware state should not matter
- If packaging tests are added later, keep them separate from the fast default suite
