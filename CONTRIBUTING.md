# Contributing to Zentrix

Thanks for taking the time to improve Zentrix. The project is a Windows-first
PySide6 desktop application, so please keep changes focused, small and covered
by tests where practical.

## Development setup

```powershell
git clone https://github.com/w1kscc/Zentrix.git
cd zentrix
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Populate the local engines (never commit them):

```powershell
python scripts/fetch_engines.py --zapret
python scripts/fetch_engines.py --cores
```

Run the app:

```powershell
python -m src.main
```

Run the tests:

```powershell
python -m pytest -q
```

## Ground rules

1. **One window, no consoles.** Child processes must be launched with
   `winapi.create_no_window_flag()` / `subprocess.CREATE_NO_WINDOW`. Never call
   `cmd.exe`, `start`, or an upstream `.bat` directly from the UI.
2. **Never hardcode local paths.** Engine locations come from settings,
   `paths.ENGINES_DIR`, or the git-ignored `settings.local.json`.
3. **Never commit engines or binaries.** `engines/` is ignored on purpose.
   Download them with `scripts/fetch_engines.py`.
4. **All sounds are synthesized.** Do not add audio files to `assets/`.
   Extend `src/sound_generator.py` instead.
5. **Keep the UI responsive.** Blocking I/O, subprocess work and network calls
   belong in a `Task` (`src/ui/workers.py`) or a daemon thread. Charts and logs
   refresh at 1 Hz at most.
6. **Lazy pages stay lazy.** Pages are loaded through `PAGE_MODULES`; do not
   import page modules eagerly in `main_window.py`.

## Code style

- Python 3.12, `from __future__ import annotations`, type hints on public
  functions.
- 4 spaces, max line length ~100, double quotes.
- UI strings are Russian; code comments and docstrings are English.
- Use `theme.qcolor()` for `QColor` construction so palette values, alpha and
  `#rrggbbaa` strings keep working.
- New icons: put an SVG in `assets/icons/`, keep the root
  `stroke="#EAF0FF"` + `fill="none"` convention so runtime retinting works.

## Tests

Add tests under `tests/` for parsers, settings migrations, engines, and other
pure logic. Qt-dependent tests should not require a visible window; use the
`QT_QPA_PLATFORM=offscreen` fallback already configured in `tests/conftest.py`.

```powershell
python -m pytest -q
```

## Commits and pull requests

- Keep commits scoped: one feature or fix per commit.
- Describe user-visible changes and mention any new settings keys.
- Include a screenshot for visual changes (`docs/screenshots/`).
- Do not include build output, `dist/`, `build/`, logs, or engine archives.

By contributing you agree that your changes are licensed under the MIT license.
