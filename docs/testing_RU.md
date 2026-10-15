# Тестирование

[English](testing.md) · **Русский**

Набор Rust-тестов запускается в GitHub Actions на Windows, Apple Silicon и Intel Mac. Тесты настроек используют временные каталоги; настоящее аудиоустройство и телефон не нужны.

macOS CI также собирает arm64 и x86_64, затем проверяет universal-приложение и DMG. CI не может выдать разрешения Automation и Accessibility, поэтому Apple Events, управление окнами и Login Item нужно отдельно принять на настоящем Mac.

## Локальный запуск

Установите stable Rust и запустите из корня репозитория:

```sh
cargo fmt --all -- --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
```

Тесты защиты PIN проверяют оба направления между `/login`, защищёнными API-маршрутами и действующими токенами. Тесты сохранения настроек используют временный каталог.

## Сборка приложения

```sh
cargo build --release --locked
```

GitHub Actions собирает установщик и portable ZIP для Windows, а также универсальное приложение macOS для Apple Silicon и Intel.
