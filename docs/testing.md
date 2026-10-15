# Testing Guide

**English** · [Русский](testing_RU.md)

The Rust test suite runs on Windows, Apple Silicon macOS, and Intel macOS in GitHub Actions. It uses temporary directories for settings tests and does not require a live audio device or a real phone.

## Run locally

Install stable Rust, then run these commands from the repository root:

```sh
cargo fmt --all -- --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
```

The PIN protection tests exercise both directions across `/login`, protected API routes, and valid session tokens. Persisted-settings tests use a temporary directory.

## Build the desktop app

```sh
cargo build --release --locked
```

Release artifacts are assembled in GitHub Actions: a Windows installer and portable ZIP, plus a universal macOS app for Apple Silicon and Intel.
