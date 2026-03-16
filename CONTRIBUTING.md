# Contributing

Thanks for helping improve PC Remote.

## Development Setup

```powershell
py -3.13 -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Before Opening A Pull Request

- Run `python -m pytest` from the repository root
- Keep changes focused and easy to review
- Update docs when behavior, setup, or developer workflow changes
- Add or adjust tests when you change app behavior

## Project Conventions

- The app targets Windows 10/11 first
- The web controller should stay lightweight and LAN-friendly
- Platform-specific integrations should be wrapped so they can be mocked in tests
- Temporary local analysis files should stay out of Git history

## Pull Request Notes

- Include a short summary of the user-facing change
- Mention how you tested it
- Call out any Windows-only limitations or follow-up work
