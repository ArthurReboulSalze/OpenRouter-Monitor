# OpenRouter Monitor

<p align="center">
  <img src="OPR_ban_2.png" alt="OpenRouter Monitor Banner" width="760">
</p>

A Windows desktop app for browsing OpenRouter models, comparing token prices, tracking credits, and copying the exact model identifier with one click.

## Features

- Fast model listing with search, sorting, and favorites
- Color-coded `Tokens`, `Input / 1M`, and `Output / 1M`
- One-click copy of the exact OpenRouter model id
- Credit usage and remaining credit display
- Local cache for fast startup
- System tray integration with credit summary tooltip
- Simple settings dialog for startup, tray behavior, and credit refresh timer

## Requirements

- Windows 10 or Windows 11
- Python 3.10+ to run from source
- An OpenRouter API key for live credit data and live refresh

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your local environment file:

```bash
copy .env.example .env
```

Add your OpenRouter API key to `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
```

## Run From Source

```bash
python run.py
```

## Build the Windows Executable

```bash
pip install pyinstaller
python build.py
```

Output:

```text
dist/OpenRouter Monitor.exe
```

## Main Files

- `openrouter_monitor_gui.py` - main application
- `run.py` - local launcher
- `build.py` - PyInstaller build script
- `OpenRouter Monitor.spec` - PyInstaller spec file
- `installer.iss` - Inno Setup installer script

## How To Use

- Click the star to add or remove a favorite
- Click a column header to sort
- Type in the search bar to filter models
- Click a model row to copy the exact OpenRouter model id
- Use `Refresh credits` and `Refresh list` to update data manually

## Local App Data

User data is stored in:

```text
%USERPROFILE%\.openrouter_monitor\
```

Important files:

- `config.json`
- `favorites.json`
- `models_cache.json`
- `app.log`

## Notes

- Without an API key, the app can still run from cached model data
- Live credit information depends on the OpenRouter endpoints available for your key
- The project is designed for Windows and the UI is optimized for that environment
