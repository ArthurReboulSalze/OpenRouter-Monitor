# -*- coding: utf-8 -*-
"""
OpenRouter Monitor - Performance-Optimized Edition
Uses a lightweight canvas table for fast rendering with per-column colors.
"""
# fmt: off

import sys
import io
import os
import json
import logging
import webbrowser
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Windows-specific imports
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    import winreg
    import winsound
    try:
        from win10toast import ToastNotifier
        TOAST_AVAILABLE = True
    except ImportError:
        TOAST_AVAILABLE = False
    try:
        import pystray
        from pystray import MenuItem as item, Menu
        from PIL import Image
        TRAY_AVAILABLE = True
    except ImportError:
        TRAY_AVAILABLE = False
else:
    TOAST_AVAILABLE = False
    TRAY_AVAILABLE = False

if sys.platform == 'win32':
    try:
        if getattr(sys.stdout, 'buffer', None):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if getattr(sys.stderr, 'buffer', None):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

import requests
import tkinter.messagebox as mb
from tkinter import simpledialog
import customtkinter as ctk
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

APP_NAME = "OpenRouter Monitor"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Arthur Reboul Salze"
BASE_URL = 'https://openrouter.ai/api/v1'
MAX_PRICE = 5000.0
REQUEST_TIMEOUT_SECONDS = 12
VISIBLE_ROWS = 120

HERMES_ORANGE = '#FF8C00'
HERMES_GOLD = '#FFD700'
HERMES_DARK_ORANGE = '#CC7000'
HERMES_DARK_BG = '#1a1a1a'
CONTEXT_TEXT_COLOR = '#FF8A65'
INPUT_PRICE_COLOR = '#FFE082'
OUTPUT_PRICE_COLOR = '#FFB74D'
NEUTRAL_PRICE_COLOR = '#555555'

APP_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
CONFIG_DIR = Path.home() / f".{APP_NAME.lower().replace(' ', '_')}"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "app.log"
CACHE_FILE = CONFIG_DIR / "models_cache.json"
FAVORITES_FILE = CONFIG_DIR / "favorites.json"
CONFIG_DIR.mkdir(exist_ok=True)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

def setup_logging():
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logging()

# ============================================================================
# CONFIGURATION MANAGER
# ============================================================================

class ConfigManager:
    DEFAULTS = {
        "auto_start": False,
        "minimize_to_tray": True,
        "start_with_windows": False,
        "start_minimized": False,
        "check_updates_on_startup": True,
        "notifications_enabled": True,
        "window_geometry": "1000x750",
        "last_sort_column": "output",
        "last_sort_reverse": False,
        "accent_color": "dark-blue",
        "refresh_interval_minutes": 5,
        "max_visible_rows": 99999,
    }

    def __init__(self):
        self.config = {}
        self.load()

    def load(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.config = {**self.DEFAULTS, **loaded}
            else:
                self.config = self.DEFAULTS.copy()
                self.save()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = self.DEFAULTS.copy()

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

config = ConfigManager()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_api_key():
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        api_key = config.get('api_key')
    return api_key

API_KEY = None

def format_price(val):
    try:
        if val is None:
            return None
        v = float(val)
        return 0.0 if v == 0 else v * 1_000_000
    except (ValueError, TypeError):
        return None

def normalize_model(model):
    name = model.get('name') or ''
    inp = model.get('input_price')
    out = model.get('output_price')
    ctx = model.get('context_length', 0) or 0
    normalized = dict(model)
    normalized['id'] = normalized.get('id', '')
    normalized['name'] = name
    normalized['name_lower'] = normalized.get('name_lower') or name.lower()
    normalized['input_price'] = inp
    normalized['output_price'] = out
    normalized['context_length'] = ctx
    normalized['context_text'] = normalized.get('context_text') or (f'{ctx:,}' if ctx else '-')
    normalized['context_color'] = CONTEXT_TEXT_COLOR if ctx else NEUTRAL_PRICE_COLOR
    normalized['input_text'] = 'Free' if inp == 0 else '-' if inp is None else f'${inp:.4f}'
    normalized['input_color'] = NEUTRAL_PRICE_COLOR if inp is None else INPUT_PRICE_COLOR
    normalized['output_text'] = 'Free' if out == 0 else '-' if out is None else f'${out:.4f}'
    normalized['output_color'] = NEUTRAL_PRICE_COLOR if out is None else OUTPUT_PRICE_COLOR
    return normalized

def _model_within_price_limit(input_price, output_price):
    def _valid(price):
        return price is None or (0 <= price <= MAX_PRICE)
    return _valid(input_price) and _valid(output_price)

# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    models = []
                    for m in data:
                        if not isinstance(m, dict):
                            continue
                        normalized = normalize_model(m)
                        if _model_within_price_limit(normalized.get('input_price'), normalized.get('output_price')):
                            models.append(normalized)
                    return models
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
    return None

def save_cache(data):
    try:
        tmp_file = CACHE_FILE.with_suffix('.tmp')
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        tmp_file.replace(CACHE_FILE)
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

def load_favorites():
    if FAVORITES_FILE.exists():
        try:
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load favorites: {e}")
    return []

def save_favorites(favs):
    try:
        with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
            json.dump(favs, f, ensure_ascii=False, separators=(',', ':'))
    except Exception as e:
        logger.error(f"Failed to save favorites: {e}")

def clear_models_cache():
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        return True
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        return False

def prompt_for_api_key(parent=None):
    created_root = None
    try:
        root = parent
        if root is None:
            created_root = tk.Tk()
            created_root.withdraw()
            created_root.attributes('-topmost', True)
            root = created_root
        api_key = simpledialog.askstring(
            APP_NAME,
            "Enter your OpenRouter API key (optional):",
            parent=root,
            show='*'
        )
        if api_key:
            return api_key.strip()
    except Exception as e:
        logger.error(f"API key prompt failed: {e}")
    finally:
        if created_root is not None:
            try:
                created_root.destroy()
            except Exception:
                pass
    return None

# ============================================================================
# API FUNCTIONS
# ============================================================================

def get_models_from_api():
    if not API_KEY:
        return []
    try:
        headers = {'Authorization': f'Bearer {API_KEY}'}
        r = requests.get(f'{BASE_URL}/models', headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        r.raise_for_status()
        return r.json().get('data', [])
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        return []

def get_generation_cost():
    if not API_KEY:
        return {}
    headers = {'Authorization': f'Bearer {API_KEY}'}
    merged = {'data': {}}

    try:
        r = requests.get(f'{BASE_URL}/key', headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        r.raise_for_status()
        payload = r.json()
        payload = payload if isinstance(payload, dict) else {}
        merged['data'].update(payload.get('data', {}))
    except Exception as e:
        logger.error(f"Failed to fetch key credits: {e}")

    try:
        r = requests.get(f'{BASE_URL}/credits', headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        if r.ok:
            payload = r.json() if isinstance(r.json(), dict) else {}
            credits_data = payload.get('data', {})
            if isinstance(credits_data, dict):
                merged['data']['total_credits'] = credits_data.get('total_credits')
                merged['data']['total_usage'] = credits_data.get('total_usage')
        else:
            logger.debug(f"Credits endpoint returned status {r.status_code}")
    except Exception as e:
        logger.debug(f"Credits summary endpoint unavailable: {e}")

    if merged.get('data'):
        logger.debug(f"Credits payload keys: {list(merged['data'].keys())}")
        return merged
    return {}

def process_models(raw):
    models = []
    for m in raw:
        pricing = m.get('pricing', {})
        inp = format_price(pricing.get('prompt'))
        out = format_price(pricing.get('completion'))
        ctx = m.get('context_length', 0) or 0
        if not _model_within_price_limit(inp, out):
            continue
        name = m.get('name', '')
        models.append({
            'id': m.get('id', ''),
            'name': name,
            'name_lower': name.lower(),
            'input_price': inp,
            'output_price': out,
            'context_length': ctx,
            'context_text': f"{ctx:,}" if ctx else '-',
            'context_color': CONTEXT_TEXT_COLOR if ctx else NEUTRAL_PRICE_COLOR,
            'input_text': 'Free' if inp == 0 else '-' if inp is None else f'${inp:.4f}',
            'input_color': NEUTRAL_PRICE_COLOR if inp is None else INPUT_PRICE_COLOR,
            'output_text': 'Free' if out == 0 else '-' if out is None else f'${out:.4f}',
            'output_color': NEUTRAL_PRICE_COLOR if out is None else OUTPUT_PRICE_COLOR,
        })
    return models

# ============================================================================
# WINDOWS UTILITIES
# ============================================================================

class WindowsUtils:
    @staticmethod
    def add_to_startup():
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            exe_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
            winreg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Failed to add to startup: {e}")
            return False

    @staticmethod
    def remove_from_startup():
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Failed to remove from startup: {e}")
            return False

    @staticmethod
    def check_startup():
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, APP_NAME)
                winreg.CloseKey(key)
                return True
            except WindowsError:
                winreg.CloseKey(key)
                return False
        except Exception:
            return False

    @staticmethod
    def show_notification(title, message, icon_path=None):
        if not TOAST_AVAILABLE or not config.get('notifications_enabled', True):
            return False
        try:
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=3, threaded=True, icon_path=icon_path)
            return True
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False

    @staticmethod
    def play_sound(sound_type='info'):
        try:
            if sound_type == 'info':
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
            elif sound_type == 'error':
                winsound.MessageBeep(winsound.MB_ICONHAND)
            elif sound_type == 'warning':
                winsound.MessageBeep(winsound.MB_ICONWARNING)
        except Exception:
            pass

# ============================================================================
# UPDATE CHECKER
# ============================================================================

class UpdateChecker:
    UPDATE_URL = "https://api.github.com/repos/yourusername/openrouter-monitor/releases/latest"

    @staticmethod
    def check_for_update(current_version):
        if 'yourusername' in UpdateChecker.UPDATE_URL:
            return {'available': False}
        try:
            r = requests.get(UpdateChecker.UPDATE_URL, timeout=10)
            r.raise_for_status()
            latest = r.json().get('tag_name', '').lstrip('v')
            if latest and latest > current_version:
                return {'available': True, 'version': latest, 'url': r.json().get('html_url', '')}
        except Exception as e:
            logger.error(f"Update check failed: {e}")
        return {'available': False}

# ============================================================================
# SYSTEM TRAY
# ============================================================================

class SystemTray:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self.setup_icon()

    def setup_icon(self):
        if not TRAY_AVAILABLE:
            return
        try:
            icon_path = APP_DIR / 'opr.ico'
            if icon_path.exists():
                image = Image.open(icon_path)
            else:
                image = Image.new('RGB', (64, 64), color=HERMES_ORANGE)
            menu = pystray.Menu(
                item('Open', self.on_open),
                item('Show', self.on_show),
                item('Hide', self.on_hide),
                pystray.Menu.SEPARATOR,
                item('Refresh', self.on_refresh),
                pystray.Menu.SEPARATOR,
                item('Settings', self.on_settings),
                item('Auto-start: {}'.format(
                    '✓ On' if config.get('auto_start') else '✗ Off'
                ), self.on_toggle_startup),
                pystray.Menu.SEPARATOR,
                item('Exit', self.on_exit)
            )
            self.icon = pystray.Icon(APP_NAME, image, self.app.get_tray_tooltip(), menu)
        except Exception as e:
            logger.error(f"Failed to create system tray: {e}")

    def run(self):
        if self.icon and TRAY_AVAILABLE:
            threading.Thread(target=self.icon.run, daemon=True).start()

    def on_open(self, icon=None, item=None):
        self.app.run_on_ui(self.app.show_window)
    def on_show(self, icon=None, item=None):
        self.app.run_on_ui(self.app.show_window)
    def on_hide(self, icon=None, item=None):
        self.app.run_on_ui(self.app.hide_window)
    def on_refresh(self, icon=None, item=None):
        self.app.run_on_ui(self.app.refresh_data)
    def on_settings(self, icon=None, item=None):
        self.app.run_on_ui(self.app.show_settings)
    def on_toggle_startup(self, icon=None, item=None):
        self.app.run_on_ui(self.app.toggle_startup_setting)
    def on_exit(self, icon=None, item=None):
        self.app.run_on_ui(self.app.quit)
    def refresh_menu(self):
        if not self.icon:
            return
        self.icon.menu = pystray.Menu(
            item('Open', self.on_open),
            item('Show', self.on_show),
            item('Hide', self.on_hide),
            pystray.Menu.SEPARATOR,
            item('Refresh', self.on_refresh),
            pystray.Menu.SEPARATOR,
            item('Settings', self.on_settings),
            item('Auto-start: {}'.format(
                '✓ On' if config.get('auto_start', False) else '✗ Off'
            ), self.on_toggle_startup),
            pystray.Menu.SEPARATOR,
            item('Exit', self.on_exit)
        )
    def set_tooltip(self, text):
        if not self.icon:
            return
        try:
            self.icon.title = text
        except Exception as e:
            logger.debug(f"Failed to update tray tooltip: {e}")
    def stop(self):
        if self.icon:
            self.icon.stop()

# ============================================================================
# MAIN GUI APPLICATION
# ============================================================================

class OpenRouterGUI:
    """Main application window with a fast canvas-based listing."""

    def __init__(self):
        logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme(config.get('accent_color', 'dark-blue'))

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry('1000x750')
        self.root.resizable(False, False)
        try:
            icon_path = APP_DIR / 'opr.ico'
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception as e:
            logger.warning(f"Failed to set window icon: {e}")
        self.root.configure(fg_color=HERMES_DARK_BG)

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.bind('<Unmap>', self._on_unmap)

        # Application state
        self.all_models = []
        self.credits_info = {}
        self.sort_col = config.get('last_sort_column', 'output')
        self.sort_rev = config.get('last_sort_reverse', False)
        self.is_loading = False
        self._pending_query = ''
        self.favorites = set(load_favorites())
        self.show_only_favorites = False
        self._is_closing = False
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='openrouter-monitor-v2')
        self._row_widgets = {}
        self._last_render_signature = None
        self._favorites_save_id = None
        self._models_version = 0
        self._favorites_version = 0
        self._sort_cache_key = None
        self._sort_cache = None
        self._filter_state_key = None
        self._visible_models = []
        self._canvas_row_height = 30
        self._canvas_table_width = 930
        self._system_tray = None
        self._credits_timer_id = None
        self._settings_dialog = None
        self._status_color_reset_id = None

        self._logo_image = None
        self._brand_image = None

        self._build_ui()

        if config.get('start_minimized', False):
            self.hide_window()

        if TRAY_AVAILABLE and config.get('minimize_to_tray', True):
            self._system_tray = SystemTray(self)
            self._system_tray.run()

        if sys.platform == 'win32':
            config.set('auto_start', WindowsUtils.check_startup())
            if self._system_tray:
                self._system_tray.refresh_menu()

        self._refresh_tray_tooltip()

        self.root.after(100, self.load_data)
        if config.get('check_updates_on_startup', True):
            self.root.after(2000, self._check_updates_async)
        logger.info("Application initialized")

    # ========================================================================
    # UI CONSTRUCTION
    # ========================================================================

    def _build_ui(self):
        self._build_header()
        self._build_search_bar()
        self._build_main_area()
        self._build_status_bar()

    def _build_header(self):
        hdr = ctk.CTkFrame(self.root, height=126, fg_color='#1a1a1a')
        hdr.pack(side='top', fill='x', padx=0, pady=0)
        hdr.pack_propagate(False)
        ctk.CTkFrame(hdr, height=4, fg_color=HERMES_ORANGE).pack(side='top', fill='x')

        hdr_content = ctk.CTkFrame(hdr, fg_color='#1a1a1a')
        hdr_content.pack(side='top', fill='x', padx=14, pady=(6, 2))

        left_frame = ctk.CTkFrame(hdr_content, fg_color='#1a1a1a')
        left_frame.pack(side='left', fill='both', expand=True)

        banner_shell = ctk.CTkFrame(left_frame, fg_color='#1a1a1a', height=116)
        banner_shell.pack(side='left', fill='x', expand=True, padx=(6, 12), pady=(0, 0))
        banner_shell.pack_propagate(False)

        self._logo_image = self._load_brand_asset(['OPR_ban_2.png'], max_width=520, max_height=116)
        if self._logo_image:
            ctk.CTkLabel(banner_shell, text='', image=self._logo_image).place(relx=0.11, rely=0.50, anchor='w')
        else:
            ctk.CTkLabel(banner_shell, text='OPENROUTER MONITOR', font=ctk.CTkFont(size=18, weight='bold'), text_color=HERMES_GOLD).place(relx=0.11, rely=0.50, anchor='w')

        # Metrics
        metrics_frame = ctk.CTkFrame(hdr_content, fg_color='#1a1a1a')
        metrics_frame.pack(side='right', fill='y')

        models_container = ctk.CTkFrame(metrics_frame, fg_color='#252525', corner_radius=10, border_width=1, border_color='#333333')
        models_container.pack(side='top', fill='x', pady=(0, 4))
        ctk.CTkLabel(models_container, text='◉', font=ctk.CTkFont(size=11), text_color=HERMES_GOLD).pack(side='left', padx=(10, 4), pady=5)
        self.models_count_lbl = ctk.CTkLabel(models_container, text='Models: --', font=ctk.CTkFont(size=12, weight='bold'), text_color='white')
        self.models_count_lbl.pack(side='left', padx=(0, 10), pady=5)

        credits_used_container = ctk.CTkFrame(metrics_frame, fg_color='#252525', corner_radius=10, border_width=1, border_color='#333333')
        credits_used_container.pack(side='top', fill='x', pady=(0, 4))
        ctk.CTkLabel(credits_used_container, text='◈', font=ctk.CTkFont(size=12), text_color=HERMES_GOLD).pack(side='left', padx=(10, 4), pady=5)
        self.credits_lbl = ctk.CTkLabel(credits_used_container, text='', font=ctk.CTkFont(size=12, weight='bold'), text_color='white')
        self.credits_lbl.pack(side='left', padx=(0, 10), pady=5)

        credits_available_container = ctk.CTkFrame(metrics_frame, fg_color='#252525', corner_radius=10, border_width=1, border_color='#333333')
        credits_available_container.pack(side='top', fill='x')
        ctk.CTkLabel(credits_available_container, text='⬡', font=ctk.CTkFont(size=12), text_color='#00C853').pack(side='left', padx=(10, 4), pady=5)
        self.credits_available_lbl = ctk.CTkLabel(credits_available_container, text='', font=ctk.CTkFont(size=12, weight='bold'), text_color='white')
        self.credits_available_lbl.pack(side='left', padx=(0, 10), pady=5)

        # Buttons
        btns_frame = ctk.CTkFrame(hdr_content, fg_color='#1a1a1a')
        btns_frame.pack(side='left', fill='y', padx=(6, 0))

        btns_row = ctk.CTkFrame(btns_frame, fg_color='#1a1a1a')
        btns_row.pack(side='top', fill='x', pady=(2, 0))

        self.settings_btn = ctk.CTkButton(btns_row, text='⚙\nSettings', command=self.show_settings,
            width=62, height=50, fg_color='#2a2a2a', hover_color='#333333',
            text_color=HERMES_GOLD, font=ctk.CTkFont(size=11, weight='bold'), corner_radius=10)
        self.settings_btn.pack(side='left', padx=(0, 4))

        self.clear_cache_btn = ctk.CTkButton(btns_row, text='✕\nClear cache', command=self.clear_cache,
            width=62, height=50, fg_color='#2a2a2a', hover_color='#3a2a00',
            text_color=HERMES_GOLD, font=ctk.CTkFont(size=11, weight='bold'), corner_radius=10)
        self.clear_cache_btn.pack(side='left', padx=(0, 4))

        self.refresh_credits_btn = ctk.CTkButton(btns_row, text='Refresh credits', command=self.refresh_credits,
            width=102, height=50, fg_color='#2a2a2a', hover_color='#333333',
            text_color=HERMES_GOLD, font=ctk.CTkFont(size=12, weight='bold'), corner_radius=10)
        self.refresh_credits_btn.pack(side='left', padx=(0, 4))

        self.refresh_btn = ctk.CTkButton(btns_row, text='Refresh list', command=self.refresh,
            width=102, height=50, fg_color=HERMES_DARK_ORANGE, hover_color=HERMES_ORANGE,
            text_color='white', font=ctk.CTkFont(size=12, weight='bold'), corner_radius=10)
        self.refresh_btn.pack(side='left')

        self.api_key_btn = ctk.CTkButton(btns_frame, text='API Key', command=self.set_api_key,
            width=340, height=28, fg_color='#2a2a2a', hover_color='#333333',
            text_color=HERMES_GOLD, font=ctk.CTkFont(size=11, weight='bold'), corner_radius=8)
        self.api_key_btn.pack(side='top', pady=(8, 0))

        ctk.CTkFrame(hdr_content, width=8, fg_color='#1a1a1a').pack(side='left', fill='y')
        ctk.CTkFrame(hdr, height=2, fg_color='#2a2a2a').pack(side='bottom', fill='x')

    def _build_search_bar(self):
        search_frame = ctk.CTkFrame(self.root, height=50, fg_color='#1a1a1a')
        search_frame.pack(side='top', fill='x', padx=10, pady=(0, 5))
        search_frame.pack_propagate(False)

        ctk.CTkLabel(search_frame, text='Search:', font=ctk.CTkFont(size=13), text_color='#888888').pack(side='left', padx=(10, 5))

        self.search_var = ctk.StringVar()
        self._search_debounce_id = None
        self.search_var.trace_add('write', lambda *_: self._on_search_changed())

        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var,
            placeholder_text='Type to filter...', font=ctk.CTkFont(size=13),
            fg_color='#2a2a2a', border_color='#444444', text_color='white')
        search_entry.pack(side='left', fill='x', expand=True, padx=5, pady=8)
        search_entry.bind('<Return>', lambda e: self._trigger_search())

        self.star_filter_btn = ctk.CTkButton(search_frame, text='☆', width=32, height=32,
            fg_color='#2a2a2a', hover_color='#333333', text_color=HERMES_GOLD,
            font=ctk.CTkFont(size=16), command=self.toggle_star_filter)
        self.star_filter_btn.pack(side='left', padx=(0, 5), pady=8)

    def _build_main_area(self):
        """Build main area with a single-pass canvas renderer."""
        main = ctk.CTkFrame(self.root, fg_color='#1a1a1a')
        main.pack(side='top', fill='both', expand=True, padx=10, pady=(5, 10))

        hdr_row = ctk.CTkFrame(main, height=32, fg_color='#252525')
        hdr_row.pack(side='top', fill='x', pady=(0, 0))
        hdr_row.pack_propagate(False)

        cols = [
            ('★', 4, 32, 'star'),
            ('#', 44, 32, 'idx'),
            ('Model', 260, 230, 'name'),
            ('Tokens', 705, 80, 'context'),
            ('Input / 1M', 779, 92, 'input'),
            ('Output / 1M', 867, 96, 'output'),
        ]
        self.header_btns = []
        for txt, x, w, key in cols:
            btn = ctk.CTkButton(hdr_row, text=txt,
                command=lambda k=key: self.sort_by(k),
                width=w, height=28, fg_color='#252525', hover_color='#333333',
                text_color=HERMES_GOLD if key == self.sort_col else 'white',
                font=ctk.CTkFont(size=11, weight='bold'))
            btn.place(x=x, y=2)
            self.header_btns.append((btn, key))

        list_frame = tk.Frame(main, bg='#1a1a1a')
        list_frame.pack(side='top', fill='both', expand=True)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('CanvasList.Vertical.TScrollbar',
            background='#222222', troughcolor='#1a1a1a',
            arrowcolor='#888888', bordercolor='#1a1a1a')

        self.list_canvas = tk.Canvas(
            list_frame,
            bg='#1a1a1a',
            highlightthickness=0,
            bd=0,
            yscrollincrement=30
        )
        self.list_scrollbar = ttk.Scrollbar(
            list_frame,
            orient='vertical',
            command=self.list_canvas.yview,
            style='CanvasList.Vertical.TScrollbar'
        )
        self.list_canvas.configure(yscrollcommand=self.list_scrollbar.set)
        self.list_scrollbar.pack(side='right', fill='y')
        self.list_canvas.pack(side='left', fill='both', expand=True)

        self.list_canvas.bind('<Button-1>', self._on_canvas_click)
        self.list_canvas.bind('<MouseWheel>', self._on_canvas_mousewheel)
        self.list_canvas.bind('<Configure>', lambda _e: self._redraw_if_needed())

    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self.root, fg_color='transparent', height=18)
        self.status_bar.pack(side='bottom', fill='x', pady=(3, 0))
        self.status_bar.pack_propagate(False)

        self.status_lbl = ctk.CTkLabel(self.status_bar, text='', font=ctk.CTkFont(size=10), text_color='#666666')
        self.status_lbl.place(relx=0.5, rely=0.5, anchor='center')

        self.author_lbl = ctk.CTkLabel(self.status_bar, text=APP_AUTHOR, font=ctk.CTkFont(size=10), text_color='#777777')
        self.author_lbl.place(relx=0.995, rely=0.5, anchor='e')

    # ========================================================================
    # IMAGE LOADING
    # ========================================================================

    def _load_scaled_png(self, image_path, max_width, max_height):
        try:
            from PIL import Image
            with Image.open(image_path) as loaded:
                img = loaded.copy()
            img = self._trim_transparent_padding(img)
            w, h = img.size
            if w <= 0 or h <= 0:
                return None
            ratio = min(max_width / w, max_height / h)
            target_size = (max(1, int(round(w * ratio))), max(1, int(round(h * ratio))))
            return ctk.CTkImage(light_image=img, dark_image=img, size=target_size)
        except Exception as e:
            logger.error(f"Failed to load image {image_path}: {e}")
            return None

    def _trim_transparent_padding(self, image):
        if not image or image.mode not in ('RGBA', 'LA'):
            return image
        try:
            alpha = image.getchannel('A')
            bounds = alpha.getbbox()
            return image.crop(bounds) if bounds else image
        except Exception:
            return image

    def _load_brand_asset(self, preferred_names, max_width, max_height):
        for name in preferred_names:
            candidate = APP_DIR / name
            if candidate.exists():
                image = self._load_scaled_png(str(candidate), max_width=max_width, max_height=max_height)
                if image:
                    return image
        return None

    # ========================================================================
    # DATA MANAGEMENT
    # ========================================================================

    def load_data(self):
        cached = load_cache()
        if cached:
            self.all_models = cached
            self._sort_cache_key = None
            self._sort_cache = None
            self._last_render_signature = None
            self._update_header_models_count(len(self.all_models))
            self.status_lbl.configure(text=f'Cache loaded: {len(self.all_models)} models')
            self.apply_filter()
            if not API_KEY:
                self.credits_lbl.configure(text='Credits used: N/A (API key optional)')
                self.credits_available_lbl.configure(text='Credits remaining: N/A')
        else:
            self.all_models = []
            self._sort_cache_key = None
            self._sort_cache = None
            self._last_render_signature = None
            self._update_header_models_count(None)
            if API_KEY:
                self.status_lbl.configure(text='No cache - click Refresh list')
            else:
                self.status_lbl.configure(text='No local cache. API key optional for live data.')
                self.credits_lbl.configure(text='Credits used: N/A (API key optional)')
                self.credits_available_lbl.configure(text='Credits remaining: N/A')
        self._refresh_tray_tooltip()

        if API_KEY:
            self._submit_background(self._fetch_credits)
        if API_KEY and not cached:
            self._submit_background(self._fetch_models_and_cache)
        self._schedule_credits_refresh()

    def _fetch_credits(self):
        if not API_KEY:
            self._queue_ui(lambda: (
                self.credits_lbl.configure(text='Credits used: N/A (API key optional)'),
                self.credits_available_lbl.configure(text='Credits remaining: N/A'),
                self._refresh_tray_tooltip()
            ))
            return
        credits = get_generation_cost()
        self._queue_ui(lambda: self._on_credits_loaded(credits))

    def _on_credits_loaded(self, credits):
        self.credits_info = credits
        self.update_credits_display()

    def _fetch_models_and_cache(self):
        if not API_KEY:
            self._queue_ui(lambda: self.status_lbl.configure(text='API key not configured. Showing cached data only.'))
            return
        self._queue_ui(lambda: self.status_lbl.configure(text='Loading models...'))
        raw = get_models_from_api()
        if raw:
            models = process_models(raw)
            if not self._is_closing:
                save_cache(models)
            self._queue_ui(lambda: self._on_models_loaded(models))
        else:
            self._queue_ui(lambda: self.status_lbl.configure(text='Model loading error'))

    def _on_models_loaded(self, models):
        self.all_models = models
        self._models_version += 1
        self._sort_cache_key = None
        self._sort_cache = None
        self._last_render_signature = None
        self._update_header_models_count(len(models))
        now = datetime.now().strftime('%H:%M:%S')
        self.status_lbl.configure(text=f'Updated: {now} ({len(models)} models)')
        self.apply_filter()
        self.refresh_btn.configure(state='normal', text='Refresh list', fg_color='#444444')

    def refresh(self):
        if self.is_loading:
            return
        if not API_KEY:
            self.status_lbl.configure(text='API key not configured. Showing cached data only.')
            self.load_data()
            return
        self.is_loading = True
        self.refresh_btn.configure(state='disabled', text='Loading list...', fg_color='#333333')
        self.status_lbl.configure(text='Loading...')
        self._pending_query = self.search_var.get()
        self._submit_background(self._do_refresh)

    def _do_refresh(self):
        try:
            raw = get_models_from_api()
            credits = get_generation_cost()
        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            raw = []
            credits = {}
        if raw:
            models = process_models(raw)
            if not self._is_closing:
                save_cache(models)
            self._queue_ui(lambda: self._on_all_loaded(models, credits))
        else:
            self.is_loading = False
            self._queue_ui(lambda: self.refresh_btn.configure(state='normal', text='Refresh list', fg_color='#444444'))
            self._queue_ui(lambda: self.status_lbl.configure(text='Load error'))

    def _on_all_loaded(self, models, credits):
        self.all_models = models
        self.credits_info = credits
        self._models_version += 1
        self._sort_cache_key = None
        self._sort_cache = None
        self._last_render_signature = None
        self._update_header_models_count(len(models))
        self.update_credits_display()
        now = datetime.now().strftime('%H:%M:%S')
        self.status_lbl.configure(text=f'Updated: {now} ({len(models)} models)')
        self.apply_filter()
        self.is_loading = False
        self.refresh_btn.configure(state='normal', text='Refresh list', fg_color='#444444')
        self._pending_query = ''
        if config.get('notifications_enabled', True):
            WindowsUtils.show_notification(APP_NAME, f"Data refreshed: {len(models)} models")

    def refresh_data(self):
        self.refresh()

    def refresh_credits(self):
        if self.is_loading:
            return
        if not API_KEY:
            self.status_lbl.configure(text='API key not configured.')
            return
        self.refresh_credits_btn.configure(state='disabled', text='Loading...')
        self._submit_background(self._do_refresh_credits)

    def _do_refresh_credits(self):
        try:
            credits = get_generation_cost()
        except Exception as e:
            logger.error(f"Credits refresh failed: {e}")
            credits = {}
        self._queue_ui(lambda: self._on_credits_refreshed(credits))

    def _on_credits_refreshed(self, credits):
        self.credits_info = credits
        self.update_credits_display()
        now = datetime.now().strftime('%H:%M:%S')
        self.status_lbl.configure(text=f'Credits updated: {now}')
        self.refresh_credits_btn.configure(state='normal', text='Refresh credits')

    # ========================================================================
    # UI HELPERS
    # ========================================================================

    def _queue_ui(self, callback):
        if self._is_closing:
            return
        try:
            self.root.after(0, lambda: None if self._is_closing else callback())
        except Exception:
            pass

    def _submit_background(self, callback, *args):
        if self._is_closing:
            return None
        try:
            return self._executor.submit(callback, *args)
        except RuntimeError:
            return None

    def _schedule_credits_refresh(self):
        if self._credits_timer_id:
            try:
                self.root.after_cancel(self._credits_timer_id)
            except Exception:
                pass
            self._credits_timer_id = None
        if self._is_closing:
            return
        interval = max(1, int(config.get('refresh_interval_minutes', 5)))
        ms = interval * 60 * 1000
        self._credits_timer_id = self.root.after(ms, self._credits_timer_tick)

    def _credits_timer_tick(self):
        if self._is_closing:
            return
        self._credits_timer_id = None
        if API_KEY:
            self._submit_background(self._do_refresh_credits)
        self._schedule_credits_refresh()

    def _update_header_models_count(self, total_models=None):
        if hasattr(self, 'models_count_lbl'):
            if total_models is None:
                self.models_count_lbl.configure(text='Models: --')
            else:
                self.models_count_lbl.configure(text=f'Models: {total_models}')

    def update_credits_display(self):
        if not self.credits_info or 'data' not in self.credits_info:
            self.credits_lbl.configure(text='Credits used: --')
            self.credits_available_lbl.configure(text='Credits remaining: --')
            self._refresh_tray_tooltip()
            return
        d = self.credits_info.get('data', {})
        total_usage = d.get('total_usage')
        total_credits = d.get('total_credits')
        usage = float(total_usage if total_usage is not None else (d.get('usage') or 0))
        limit = total_credits if total_credits is not None else d.get('limit')
        remaining = d.get('limit_remaining')
        if remaining is None and total_credits is not None:
            remaining = float(total_credits) - float(total_usage or 0)
        if remaining is None and limit is not None:
            remaining = float(limit) - usage

        if limit in (None, 0):
            self.credits_lbl.configure(text=f'Credits used: ${usage:.2f}')
            if remaining is None:
                self.credits_available_lbl.configure(text='Credits remaining: Unlimited')
            else:
                self.credits_available_lbl.configure(text=f'Credits remaining: ${float(remaining):.2f}')
        else:
            self.credits_lbl.configure(text=f'Credits used: ${usage:.2f} / ${float(limit):.2f}')
            if remaining is None:
                self.credits_available_lbl.configure(text='Credits remaining: --')
            else:
                self.credits_available_lbl.configure(text=f'Credits remaining: ${float(remaining):.2f}')
        self._refresh_tray_tooltip()

    # ========================================================================
    # SORTING AND FILTERING
    # ========================================================================

    def sort_by(self, col):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col = col
            self.sort_rev = False
        self._update_header_sort_state()
        config.set('last_sort_column', col)
        config.set('last_sort_reverse', self.sort_rev)
        self.apply_filter()

    def _update_header_sort_state(self):
        for btn, key in self.header_btns:
            btn.configure(text_color=HERMES_GOLD if key == self.sort_col else 'white')

    def get_sorted(self, models):
        rev = self.sort_rev
        if self.sort_col == 'star':
            return sorted(models, key=lambda x: x['id'] not in self.favorites, reverse=rev)
        elif self.sort_col == 'name':
            return sorted(models, key=lambda x: x.get('name_lower') or (x['name'] or '').lower(), reverse=rev)
        elif self.sort_col == 'context':
            return sorted(models, key=lambda x: x['context_length'] or 0, reverse=rev)
        elif self.sort_col == 'input':
            return sorted(models, key=lambda x: x['input_price'] if x['input_price'] is not None else 999999, reverse=rev)
        elif self.sort_col == 'output':
            return sorted(models, key=lambda x: x['output_price'] if x['output_price'] is not None else 999999, reverse=rev)
        return models

    def _get_sorted_all(self):
        cache_key = (
            self._models_version,
            self.sort_col,
            self.sort_rev,
            self._favorites_version if self.sort_col == 'star' else 0,
        )
        if cache_key == self._sort_cache_key and self._sort_cache is not None:
            return self._sort_cache
        self._sort_cache = self.get_sorted(self.all_models)
        self._sort_cache_key = cache_key
        return self._sort_cache

    # ========================================================================
    # FILTERING
    # ========================================================================

    def toggle_star_filter(self):
        self.show_only_favorites = not self.show_only_favorites
        self.star_filter_btn.configure(text='★' if self.show_only_favorites else '☆')
        self._last_render_signature = None
        self.apply_filter()

    def _on_search_changed(self):
        if self._is_closing:
            return
        if self._search_debounce_id:
            self.root.after_cancel(self._search_debounce_id)
        self._search_debounce_id = self.root.after(300, lambda: self.apply_filter())

    def _trigger_search(self):
        if self._search_debounce_id:
            self.root.after_cancel(self._search_debounce_id)
            self._search_debounce_id = None
        self._last_render_signature = None
        self.apply_filter()

    def clear_search(self):
        if self._search_debounce_id:
            self.root.after_cancel(self._search_debounce_id)
            self._search_debounce_id = None
        self.search_var.set('')
        self._last_render_signature = None
        self.apply_filter()

    def apply_filter(self):
        query = self._pending_query if self._pending_query else self.search_var.get()
        self._pending_query = ''
        query = query.lower().strip()

        filtered = self._get_sorted_all()
        if self.show_only_favorites:
            filtered = [m for m in filtered if m['id'] in self.favorites]
        if query:
            filtered = [m for m in filtered if query in (m.get('name_lower') or (m['name'] or '').lower())]

        filter_state_key = (
            self._models_version,
            self._favorites_version if (self.show_only_favorites or self.sort_col == 'star') else 0,
            self.sort_col,
            self.sort_rev,
            self.show_only_favorites,
            query,
        )
        self._filter_state_key = filter_state_key

        signature = self._build_render_signature(filtered, query)
        if signature == self._last_render_signature:
            return
        self._last_render_signature = signature

        self._clear_scroll()

        if not filtered:
            self._draw_empty_state('No favorites' if self.show_only_favorites else 'No models match')
            self.status_lbl.configure(text='0 models')
            self.is_loading = False
            self.refresh_btn.configure(state='normal', text='Refresh list')
            return

        total = len(filtered)
        total_all = len(self.all_models)
        self._visible_models = filtered
        self._render_rows_chunk(filtered, 0, 0, 0)
        self._set_filter_status(total, total_all, query, total)
        self.is_loading = False
        self.refresh_btn.configure(state='normal', text='Refresh list')

    def _build_render_signature(self, filtered, query):
        favorites_state = self._favorites_version if (self.show_only_favorites or self.sort_col == 'star') else 0
        return (
            self._models_version,
            favorites_state,
            len(filtered),
            tuple(m['id'] for m in filtered),
            self.sort_col,
            self.sort_rev,
            self.show_only_favorites,
            query,
        )

    def _set_filter_status(self, total, total_all, query, visible_count):
        if self.show_only_favorites:
            text = f'{total} favorites / {total_all} models'
        elif query:
            text = f'{total} / {total_all} models'
        else:
            text = f'{total_all} models total'
        self.status_lbl.configure(text=text)

    def _clear_scroll(self):
        self._visible_models = []
        self.list_canvas.delete('all')
        self.list_canvas.configure(scrollregion=(0, 0, self._canvas_table_width, 0))
        self._row_widgets.clear()

    def _cancel_pending_render(self):
        return

    def _render_rows_chunk(self, rows, start, token, remaining=0):
        if self._is_closing:
            return
        self.list_canvas.delete('all')
        self._row_widgets.clear()
        self._visible_models = rows
        for row_idx, model in enumerate(rows):
            self._create_model_row(row_idx, model)
        total_height = max(self.list_canvas.winfo_height(), len(rows) * self._canvas_row_height)
        self.list_canvas.configure(scrollregion=(0, 0, self._canvas_table_width, total_height))

    def _create_model_row(self, row_idx, model):
        bg = '#1e1e1e' if row_idx % 2 == 0 else '#252525'
        y0 = row_idx * self._canvas_row_height
        y1 = y0 + self._canvas_row_height
        cy = y0 + (self._canvas_row_height / 2)
        row_tags = ('row', f"model::{model['id']}")
        self.list_canvas.create_rectangle(0, y0, self._canvas_table_width, y1, fill=bg, outline='', tags=row_tags)
        is_fav = model['id'] in self.favorites
        star_item = self.list_canvas.create_text(
            20,
            cy,
            text='★' if is_fav else '☆',
            fill=HERMES_GOLD if is_fav else '#555555',
            font=('Segoe UI Symbol', 14),
            tags=('row', 'star', f"model::{model['id']}")
        )
        self.list_canvas.create_text(52, cy, text=str(row_idx + 1), fill='#777777', font=('Segoe UI', 10), tags=row_tags)
        self.list_canvas.create_text(84, cy, text=model.get('name') or '-', fill='white', font=('Segoe UI', 10, 'bold'), anchor='w', tags=row_tags)
        self.list_canvas.create_text(670, cy, text=model.get('id') or '-', fill='#A8A8A8', font=('Consolas', 9), anchor='e', tags=row_tags)
        self.list_canvas.create_text(745, cy, text=model.get('context_text') or '-', fill=model.get('context_color') or NEUTRAL_PRICE_COLOR, font=('Segoe UI', 10), anchor='center', tags=row_tags)
        self.list_canvas.create_text(825, cy, text=model.get('input_text') or '-', fill=model.get('input_color') or NEUTRAL_PRICE_COLOR, font=('Segoe UI', 10, 'bold'), anchor='center', tags=row_tags)
        self.list_canvas.create_text(915, cy, text=model.get('output_text') or '-', fill=model.get('output_color') or NEUTRAL_PRICE_COLOR, font=('Segoe UI', 10, 'bold'), anchor='center', tags=row_tags)

        self._row_widgets[model['id']] = {'star': star_item}

    def _show_more_rows(self):
        return

    def _draw_empty_state(self, text):
        width = max(self.list_canvas.winfo_width(), self._canvas_table_width)
        height = max(self.list_canvas.winfo_height(), 120)
        self.list_canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            fill='#666666',
            font=('Segoe UI', 12)
        )
        self.list_canvas.configure(scrollregion=(0, 0, width, height))

    def _redraw_if_needed(self):
        if self._visible_models:
            self._render_rows_chunk(self._visible_models, 0, 0, 0)

    def _on_canvas_click(self, event):
        item = self.list_canvas.find_withtag('current')
        if not item:
            return
        tags = self.list_canvas.gettags(item[0])
        model_id = None
        for tag in tags:
            if tag.startswith('model::'):
                model_id = tag.split('::', 1)[1]
                break
        if not model_id:
            return
        if 'star' in tags:
            self.toggle_favorite(model_id)
            return
        self.copy_model_command(model_id)

    def _on_canvas_mousewheel(self, event):
        if self.list_canvas.winfo_height() <= 0:
            return
        self.list_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

    def _set_status_accent(self, text):
        self.status_lbl.configure(text=text, text_color=HERMES_GOLD)
        if self._status_color_reset_id:
            try:
                self.root.after_cancel(self._status_color_reset_id)
            except Exception:
                pass
        self._status_color_reset_id = self.root.after(2800, lambda: self.status_lbl.configure(text_color='#666666'))

    # ========================================================================
    # FAVORITES MANAGEMENT
    # ========================================================================

    def toggle_favorite(self, model_id):
        if model_id in self.favorites:
            self.favorites.discard(model_id)
        else:
            self.favorites.add(model_id)
        self._favorites_version += 1
        self._schedule_favorites_save()
        self._update_star_only_view(model_id)

    def _schedule_favorites_save(self):
        if self._favorites_save_id:
            try:
                self.root.after_cancel(self._favorites_save_id)
            except Exception:
                pass
        self._favorites_save_id = self.root.after(500, self._flush_favorites_save)

    def _flush_favorites_save(self):
        self._favorites_save_id = None
        favs = list(self.favorites)
        if self._is_closing:
            save_favorites(favs)
        else:
            self._submit_background(save_favorites, favs)

    def _update_star_only_view(self, model_id):
        self._last_render_signature = None
        self.apply_filter()

    def copy_model_command(self, model_id):
        if not model_id or self._is_closing:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(model_id)
            self.root.update_idletasks()
            self._set_status_accent(f'Copied model command: {model_id}')
        except Exception as e:
            logger.error(f"Failed to copy model command: {e}")
            self._set_status_accent('Unable to copy model command')

    # ========================================================================
    # WINDOW MANAGEMENT
    # ========================================================================

    def hide_window(self):
        self.root.withdraw()

    def _on_unmap(self, event=None):
        if self._is_closing:
            return
        if self.root.state() == 'iconic':
            self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def show_settings(self):
        if self._settings_dialog and self._settings_dialog.top.winfo_exists():
            self._settings_dialog.top.lift()
            self._settings_dialog.top.focus_force()
            return
        self._settings_dialog = SettingsDialog(self, config)

    def set_api_key(self):
        global API_KEY
        key = prompt_for_api_key(self.root)
        if not key:
            return
        API_KEY = key
        config.set('api_key', key)
        self.status_lbl.configure(text='API key saved. Live refresh is now enabled.')
        self._refresh_tray_tooltip()
        self.load_data()

    def clear_cache(self):
        if self._is_closing:
            return
        if not mb.askyesno("Clear cache",
            f"Delete the local models cache file?\n{CACHE_FILE}\n\nThis will force a fresh download."):
            return
        if clear_models_cache():
            self.all_models = []
            self._models_version += 1
            self._sort_cache_key = None
            self._sort_cache = None
            self._last_render_signature = None
            self.status_lbl.configure(text='Local cache deleted. Reloading fresh data...')
            self.load_data()
        else:
            mb.showerror('Cache error', 'Unable to delete the local cache file.')

    def run_on_ui(self, callback, *args, **kwargs):
        if self._is_closing:
            return
        try:
            self.root.after(0, lambda: None if self._is_closing else callback(*args, **kwargs))
        except Exception as e:
            logger.debug(f"UI dispatch skipped: {e}")

    def toggle_startup_setting(self):
        new_state = not config.get('auto_start', False)
        if sys.platform == 'win32':
            if new_state:
                WindowsUtils.add_to_startup()
            else:
                WindowsUtils.remove_from_startup()
        config.set('auto_start', new_state)
        config.set('start_with_windows', new_state)
        config.set('start_minimized', new_state)
        if self._system_tray:
            self._system_tray.refresh_menu()

    def get_tray_tooltip(self):
        if not self.credits_info or 'data' not in self.credits_info:
            return f'{APP_NAME} | Remaining: -- | Used: --'
        data = self.credits_info.get('data', {})
        total_usage = data.get('total_usage')
        total_credits = data.get('total_credits')
        usage = float(total_usage if total_usage is not None else (data.get('usage') or 0))
        remaining = data.get('limit_remaining')
        if remaining is None and total_credits is not None:
            remaining = float(total_credits) - float(total_usage or 0)
        if remaining is None and data.get('limit') not in (None, 0):
            remaining = float(data.get('limit')) - float(data.get('usage') or 0)
        remaining_text = 'Unlimited' if remaining is None and (total_credits if total_credits is not None else data.get('limit')) in (None, 0) else '--'
        if remaining is not None:
            remaining_text = f'${float(remaining):.2f}'
        return f'{APP_NAME} | Remaining: {remaining_text} | Used: ${usage:.2f}'

    def _refresh_tray_tooltip(self):
        if self._system_tray:
            self._system_tray.set_tooltip(self.get_tray_tooltip())

    def sync_tray_state(self):
        wants_tray = TRAY_AVAILABLE and config.get('minimize_to_tray', True)
        if wants_tray and not self._system_tray:
            self._system_tray = SystemTray(self)
            self._system_tray.run()
        elif not wants_tray and self._system_tray:
            try:
                self._system_tray.stop()
            except Exception:
                pass
            self._system_tray = None
        if self._system_tray:
            self._system_tray.refresh_menu()
            self._refresh_tray_tooltip()

    def on_settings_closed(self):
        self._settings_dialog = None

    def _check_updates_async(self):
        if self._is_closing:
            return
        threading.Thread(target=self._check_updates, daemon=True).start()

    def _check_updates(self):
        result = UpdateChecker.check_for_update(APP_VERSION)
        if result.get('available'):
            self._queue_ui(lambda: self._show_update_dialog(result))

    def _show_update_dialog(self, result):
        if self._is_closing:
            return
        response = mb.askquestion("Update available",
            f"Version {result['version']} is available.\nWould you like to open the download page?",
            icon='info')
        if response == 'yes':
            webbrowser.open(result['url'])

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def _on_close(self):
        if self._is_closing:
            return
        logger.info("Application closing")
        self._is_closing = True
        self.is_loading = False

        if self._settings_dialog and self._settings_dialog.top.winfo_exists():
            try:
                self._settings_dialog.top.destroy()
            except Exception:
                pass
            self._settings_dialog = None

        if self._search_debounce_id:
            try:
                self.root.after_cancel(self._search_debounce_id)
            except Exception:
                pass
            self._search_debounce_id = None

        if self._favorites_save_id:
            try:
                self.root.after_cancel(self._favorites_save_id)
            except Exception:
                pass
            self._favorites_save_id = None

        if self._status_color_reset_id:
            try:
                self.root.after_cancel(self._status_color_reset_id)
            except Exception:
                pass
            self._status_color_reset_id = None

        self._cancel_pending_render()

        if self._credits_timer_id:
            try:
                self.root.after_cancel(self._credits_timer_id)
            except Exception:
                pass
            self._credits_timer_id = None

        save_favorites(list(self.favorites))

        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

        if self._system_tray:
            try:
                self._system_tray.stop()
            except Exception:
                pass
            self._system_tray = None

        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            pass
        logger.info("Application closed cleanly")

    def quit(self):
        self._on_close()

    def run(self):
        self.root.mainloop()

# ============================================================================
# SETTINGS DIALOG
# ============================================================================

class SettingsDialog:
    def __init__(self, app, config_manager):
        self.app = app
        self.parent = app.root
        self.config = config_manager
        self.top = ctk.CTkToplevel(self.parent)
        self.top.title("Settings")
        self.top.geometry("470x360")
        self.top.resizable(False, False)
        self.top.transient(self.parent)
        self.top.grab_set()
        self.top.protocol('WM_DELETE_WINDOW', self._on_close_dialog)
        try:
            icon_path = APP_DIR / 'opr.ico'
            if icon_path.exists():
                self.top.iconbitmap(str(icon_path))
        except Exception as e:
            logger.debug(f"Failed to set settings icon: {e}")
        self._settings_icon = None
        try:
            png_icon_path = APP_DIR / 'OPR_ICO.png'
            if png_icon_path.exists():
                self._settings_icon = tk.PhotoImage(file=str(png_icon_path))
                self.top.iconphoto(False, self._settings_icon)
        except Exception as e:
            logger.debug(f"Failed to set settings iconphoto: {e}")

        self._build_ui()

        self.top.update_idletasks()
        x = (self.top.winfo_screenwidth() // 2) - (470 // 2)
        y = (self.top.winfo_screenheight() // 2) - (360 // 2)
        self.top.geometry(f'+{x}+{y}')
        self.top.focus_force()

    def _on_close_dialog(self):
        try:
            self.top.grab_release()
        except Exception:
            pass
        try:
            self.top.destroy()
        finally:
            self.app.on_settings_closed()

    def _build_ui(self):
        shell = ctk.CTkFrame(self.top, fg_color='#1a1a1a', corner_radius=0)
        shell.pack(fill='both', expand=True)

        ctk.CTkFrame(shell, height=4, fg_color=HERMES_ORANGE).pack(fill='x')

        header = ctk.CTkFrame(shell, fg_color='transparent')
        header.pack(fill='x', padx=22, pady=(14, 6))
        ctk.CTkLabel(header, text='Settings', font=ctk.CTkFont(size=22, weight='bold'), text_color='white').pack(anchor='w')
        ctk.CTkLabel(
            header,
            text='Tray, startup and automatic credit refresh.',
            font=ctk.CTkFont(size=12),
            text_color='#9A9A9A'
        ).pack(anchor='w', pady=(2, 0))

        panel = ctk.CTkFrame(shell, fg_color='#222222', corner_radius=14, border_width=1, border_color='#343434')
        panel.pack(fill='both', expand=True, padx=18, pady=(2, 8))

        self.auto_start_var = ctk.BooleanVar(value=self.config.get('auto_start', False))
        self.minimize_var = ctk.BooleanVar(value=self.config.get('minimize_to_tray', True))
        self.interval_var = ctk.StringVar(value=str(self.config.get('refresh_interval_minutes', 5)))

        toggles = ctk.CTkFrame(panel, fg_color='transparent')
        toggles.pack(fill='x', padx=18, pady=(14, 6))

        ctk.CTkCheckBox(
            toggles,
            text='Start with Windows and launch minimized',
            variable=self.auto_start_var,
            text_color='white',
            fg_color=HERMES_ORANGE,
            hover_color=HERMES_DARK_ORANGE
        ).pack(anchor='w', pady=(0, 10))

        ctk.CTkCheckBox(
            toggles,
            text='Minimize to system tray',
            variable=self.minimize_var,
            text_color='white',
            fg_color=HERMES_ORANGE,
            hover_color=HERMES_DARK_ORANGE
        ).pack(anchor='w')

        timer_card = ctk.CTkFrame(panel, fg_color='#262626', corner_radius=12)
        timer_card.pack(fill='x', padx=18, pady=(8, 8))
        ctk.CTkLabel(
            timer_card,
            text='Credits refresh timer',
            font=ctk.CTkFont(size=14, weight='bold'),
            text_color=HERMES_GOLD
        ).pack(anchor='w', padx=14, pady=(10, 2))
        ctk.CTkLabel(
            timer_card,
            text='Choose how often remaining credits are refreshed automatically.',
            font=ctk.CTkFont(size=11),
            text_color='#9A9A9A'
        ).pack(anchor='w', padx=14, pady=(0, 8))
        ctk.CTkOptionMenu(
            timer_card,
            values=['1', '5', '10', '15', '30', '60'],
            variable=self.interval_var,
            width=132,
            fg_color='#2F2F2F',
            button_color=HERMES_DARK_ORANGE,
            button_hover_color=HERMES_ORANGE,
            dropdown_fg_color='#2A2A2A'
        ).pack(anchor='w', padx=14, pady=(0, 10))

        footer = ctk.CTkFrame(shell, fg_color='transparent')
        footer.pack(fill='x', padx=18, pady=(0, 10))
        ctk.CTkButton(
            footer,
            text='Cancel',
            command=self._on_close_dialog,
            width=132,
            height=34,
            fg_color='#2A2A2A',
            hover_color='#333333',
            text_color='white'
        ).pack(side='right')
        ctk.CTkButton(
            footer,
            text='Save settings',
            command=self._save,
            width=160,
            height=34,
            fg_color=HERMES_DARK_ORANGE,
            hover_color=HERMES_ORANGE,
            text_color='white'
        ).pack(side='right', padx=(0, 10))

    def _save(self):
        try:
            old_auto_start = self.config.get('auto_start', False)
            new_auto_start = self.auto_start_var.get()
            if old_auto_start != new_auto_start and sys.platform == 'win32':
                if new_auto_start:
                    WindowsUtils.add_to_startup()
                else:
                    WindowsUtils.remove_from_startup()

            self.config.set('auto_start', new_auto_start)
            self.config.set('start_with_windows', new_auto_start)
            self.config.set('start_minimized', new_auto_start)
            self.config.set('minimize_to_tray', self.minimize_var.get())
            self.config.set('refresh_interval_minutes', int(self.interval_var.get()))

            self.app.sync_tray_state()
            self.app._schedule_credits_refresh()

            logger.info("Settings saved")
            self._on_close_dialog()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            mb.showerror("Error", f"Unable to save settings: {e}")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    try:
        global API_KEY
        API_KEY = get_api_key()
        if API_KEY:
            logger.info("OpenRouter API key loaded")
        else:
            logger.info("No API key configured; running in cache-only mode")

        def except_hook(exctype, value, traceback):
            logger.error("Uncaught exception", exc_info=(exctype, value, traceback))
            sys.__excepthook__(exctype, value, traceback)
        sys.excepthook = except_hook

        app = OpenRouterGUI()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        try:
            mb.showerror("Fatal error", f"An error occurred:\n{e}\n\nSee the log file for details.")
        except Exception:
            pass
        sys.exit(1)

if __name__ == '__main__':
    main()
