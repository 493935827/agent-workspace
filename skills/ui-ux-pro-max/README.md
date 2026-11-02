# ui-ux-pro-max

Searchable local UI/UX design intelligence for web, mobile, and desktop: styles, product palettes and reasoning profiles, font pairings, UX guidelines, icons, GSAP presets, chart recommendations, and stack-specific guidance. See `SKILL.md` for when and how to apply it.

## Requirements

- Python 3.x. `search.py` and its helpers use only the standard library — no external dependencies, no `pip install` needed.

## Installing Python if it is missing

Verify first:

```bash
python --version    # or: python3 --version / py -3 --version
```

If no interpreter is available:

- **Windows**: install from [python.org/downloads](https://www.python.org/downloads/) (tick "Add python.exe to PATH"), or run `winget install Python.Python.3.12`. The `py -3` launcher ships with the python.org installer.
- **macOS**: install from [python.org/downloads](https://www.python.org/downloads/) or run `brew install python`.
- **Linux**: use the distribution package manager, e.g. `sudo apt install python3` (Debian/Ubuntu) or `sudo dnf install python3` (Fedora).

Any Python 3.8+ interpreter works; the scripts need only the standard library.

## Running the search tool

All commands resolve `scripts/search.py` relative to this skill's own root directory (the folder containing this README and `SKILL.md`), written below as `<skill-root>`:

```bash
python "<skill-root>/scripts/search.py" "<query>" --domain <domain>
```

Common invocations:

```bash
# Product-wide design direction
python "<skill-root>/scripts/search.py" "beauty spa wellness" --design-system -p "Serenity Spa"

# Focused concern in one domain
python "<skill-root>/scripts/search.py" "error summary validation" --domain ux

# Stack-specific implementation guidance
python "<skill-root>/scripts/search.py" "suspense streaming bundle" --stack nextjs
```

Useful flags (full contract in `SKILL.md`): `--domain <domain>`, `--stack <stack>`, `--design-system`, `-n <max_results>`, `-f ascii|markdown`, `--json`, `--persist` with `--output-dir "<project-root>"` (plus `--page` and `--force`), and the `--variance` / `--motion` / `--density` dials.

## Directory structure

- `SKILL.md` — trigger conditions, workflow, query contract, and command reference.
- `scripts/` — `search.py` (the search entry point), `core.py`, `design_system.py`, `reasoning_contract.py`, `validate_data.py`, and `tests/`.
- `data/` — the local searchable catalogs (CSV) and their provenance metadata.
- `references/` — `quick-reference.md` (full rule text for every category) and `pro-rules.md` (app-polish rules and the pre-delivery checklist).
