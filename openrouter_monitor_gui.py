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
import queue
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
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

if TOAST_AVAILABLE:
    class SafeToastNotifier(ToastNotifier):
        """Local win10toast shim to avoid the known None-return WNDPROC bug."""

        def on_destroy(self, hwnd, msg, wparam, lparam):
            nid = (self.hwnd, 0)
            try:
                from win32gui import Shell_NotifyIcon, NIM_DELETE
                from win32api import PostQuitMessage
                Shell_NotifyIcon(NIM_DELETE, nid)
                PostQuitMessage(0)
            except Exception:
                pass
            return 0
else:
    SafeToastNotifier = None

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
from model_catalog import MODEL_CATEGORIES, SORT_COLUMNS, enrich_model, fetch_catalog, filter_models, sort_models, finite_number
from monitor_theme import BACKGROUND, SURFACE, SURFACE_RAISED, BORDER, MUTED, TEXT, AMBER, GOLD, GREEN, make_icon, HoverTip

load_dotenv()

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

APP_NAME = "OpenRouter Monitor"
APP_VERSION = "1.1.0"
APP_AUTHOR = "Arthur Reboul Salze"
BASE_URL = 'https://openrouter.ai/api/v1'
MAX_PRICE = 5000.0
REQUEST_TIMEOUT_SECONDS = 12
VISIBLE_ROWS = 120

HERMES_ORANGE = AMBER
HERMES_GOLD = GOLD
HERMES_DARK_ORANGE = '#CC7000'
HERMES_DARK_BG = BACKGROUND
CONTEXT_TEXT_COLOR = AMBER
INPUT_PRICE_COLOR = '#FFE082'
OUTPUT_PRICE_COLOR = '#FFB74D'
NEUTRAL_PRICE_COLOR = MUTED
HEADER_BUTTON_GROUP_WIDTH = 424
HEADER_BUTTON_NORMAL_COLOR = SURFACE
HEADER_BUTTON_HOVER_COLOR = '#25231b'
HEADER_BUTTON_DISABLED_COLOR = SURFACE_RAISED
REFRESH_LIST_BUTTON_TEXT = 'Refresh\nlist'
REFRESH_LIST_LOADING_TEXT = 'Loading\nlist…'
REFRESH_CREDITS_BUTTON_TEXT = 'Refresh\ncredits'
REFRESH_CREDITS_LOADING_TEXT = 'Loading\ncredits…'
BRAND_LOGO = 'MEDIAS/Emblème néon doré sur badge sombre.png'
BRAND_BANNER = 'MEDIAS/Baniere OpenRouter Monitor avec planète orbitale lumineuse.png'

APP_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
CONFIG_DIR = Path(os.environ.get('OPENROUTER_MONITOR_DATA_DIR') or (Path.home() / f".{APP_NAME.lower().replace(' ', '_')}"))
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "app.log"
CACHE_FILE = CONFIG_DIR / "models_cache.json"
FAVORITES_FILE = CONFIG_DIR / "favorites.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

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
        "window_geometry": "1380x940",
        "last_sort_column": "output",
        "last_sort_reverse": False,
        "last_category": "all",
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
    # A key explicitly saved in Settings takes precedence over the .env default.
    if 'api_key' in config.config:
        return (config.get('api_key') or '').strip() or None
    return (os.getenv('OPENROUTER_API_KEY') or '').strip() or None

API_KEY = None

def format_price(val):
    try:
        if val is None:
            return None
        v = float(val)
        if v < 0 or finite_number(v) is None:
            return None
        return 0.0 if v == 0 else v * 1_000_000
    except (ValueError, TypeError):
        return None

def normalize_model(model):
    name = model.get('name') or ''
    inp = finite_number(model.get('input_price'))
    out = finite_number(model.get('output_price'))
    ctx = int(finite_number(model.get('context_length'), 0) or 0)
    normalized = enrich_model(model)
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
    pricing = model.get('pricing') or {}
    if finite_number(pricing.get('prompt'), 0) < 0:
        normalized['input_text'] = 'Varies'
    if finite_number(pricing.get('completion'), 0) < 0:
        normalized['output_text'] = 'Varies'
    if 'video' in normalized['output_modalities']:
        # Video is billed by duration/resolution, not by prompt/completion tokens.
        normalized['input_text'] = '—'
        normalized['output_text'] = 'See rates'
        normalized['input_color'] = normalized['output_color'] = MUTED
        normalized['input_price'] = normalized['output_price'] = None
    elif set(normalized['output_modalities']).intersection({'transcription', 'rerank'}) and 'text' not in normalized['output_modalities']:
        normalized['input_text'] = 'See rates'
        normalized['output_text'] = '—'
        normalized['input_color'] = normalized['output_color'] = MUTED
        normalized['input_price'] = normalized['output_price'] = None
    return normalized

def _model_within_price_limit(input_price, output_price):
    def _valid(price):
        return price is None or (finite_number(price) is not None and price >= 0)
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
    try:
        return fetch_catalog()
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
        models.append(normalize_model({
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
            'architecture': m.get('architecture') or {},
            'created': m.get('created'),
            'canonical_slug': m.get('canonical_slug'),
            'description': m.get('description') or '',
            'pricing': pricing,
            'popularity_rank': m.get('popularity_rank'),
            'is_promoted': m.get('is_promoted'),
            'discount_percent': m.get('discount_percent'),
            'promotion_known': m.get('promotion_known'),
            'promotion_checked_at': m.get('promotion_checked_at'),
        }))
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
            toaster = SafeToastNotifier() if SafeToastNotifier else ToastNotifier()
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
            icon_path = APP_DIR / BRAND_LOGO
            if icon_path.exists():
                with Image.open(icon_path) as source:
                    image = source.convert('RGBA')
                    bounds = image.getchannel('A').getbbox()
                    if bounds:
                        image = image.crop(bounds)
                    image.thumbnail((64, 64), Image.Resampling.LANCZOS)
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
        if sys.platform == 'win32':
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ArthurReboulSalze.OpenRouterMonitor')
            except Exception:
                pass

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        window_scale = self.root._get_window_scaling()
        screen_width = int(self.root.winfo_screenwidth() / window_scale)
        screen_height = int(self.root.winfo_screenheight() / window_scale)
        width = min(1380, max(1000, screen_width - 100))
        height = min(940, max(640, screen_height - 100))
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(min(1080, width), min(700, height))
        self.root.resizable(True, True)
        try:
            icon_path = APP_DIR / 'MEDIAS/openrouter-monitor.ico'
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
        if self.sort_col not in SORT_COLUMNS:
            self.sort_col = 'output'
        self.sort_rev = config.get('last_sort_reverse', False)
        self.is_loading = False
        self._pending_query = ''
        self.favorites = set(load_favorites())
        self.show_only_favorites = False
        self.show_only_promotions = False
        self.selected_category = config.get('last_category', 'all')
        if self.selected_category not in MODEL_CATEGORIES:
            self.selected_category = 'all'
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
        self._ui_queue = queue.Queue()
        self._ui_poll_id = None
        self._hovered_row = None
        self._selected_model_id = None
        self._column_bounds = {}
        self._icons = {}
        self._tooltips = []
        self._window_icon = None
        self._connection_state = 'Cached data'
        self._catalog_live = False

        self._logo_image = None
        self._brand_image = None

        self._build_ui()
        self._ui_poll_id = self.root.after(40, self._drain_ui_queue)
        self.root.bind('/', self._focus_search)
        self.root.bind('<Control-f>', self._focus_search)
        self.root.bind('<F5>', lambda _event: self.refresh())
        self._apply_window_branding()
        # CustomTkinter sets its default Windows icon after 200 ms.
        self.root.after(300, self._apply_window_branding)

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
        self._build_status_bar()
        self._build_main_area()

    def _apply_window_branding(self):
        if self._is_closing:
            return
        try:
            from PIL import Image, ImageTk
            path = APP_DIR / BRAND_LOGO
            if path.exists():
                with Image.open(path) as source:
                    image = self._trim_transparent_padding(source.convert('RGBA'))
                    image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                    self._window_icon = ImageTk.PhotoImage(image)
                self.root.iconphoto(True, self._window_icon)
            icon_path = APP_DIR / 'MEDIAS/openrouter-monitor.ico'
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
            if sys.platform == 'win32':
                self.root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                dark_mode = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        except Exception as error:
            logger.debug(f'Window branding unavailable: {error}')

    def _build_header(self):
        hdr = ctk.CTkFrame(self.root, height=200, fg_color=BACKGROUND, corner_radius=0)
        hdr.pack(side='top', fill='x', padx=18, pady=(8, 4))
        hdr.pack_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)
        hdr.grid_columnconfigure(1, weight=0, minsize=HEADER_BUTTON_GROUP_WIDTH)
        hdr.grid_columnconfigure(2, weight=0, minsize=300)
        hdr.grid_rowconfigure(0, weight=1)

        banner_shell = ctk.CTkFrame(hdr, fg_color=BACKGROUND, corner_radius=0)
        banner_shell.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        banner_shell.pack_propagate(False)
        self._logo_image = self._load_brand_asset([BRAND_BANNER, 'OPR_ban_2.png'], max_width=480, max_height=154)
        if self._logo_image:
            self.banner_label = ctk.CTkLabel(banner_shell, text='', image=self._logo_image)
            self.banner_label.pack(fill='both', expand=True)
            banner_shell.bind('<Configure>', self._resize_banner)
        else:
            ctk.CTkLabel(banner_shell, text='OPENROUTER MONITOR', font=ctk.CTkFont(size=20, weight='bold'), text_color=GOLD).pack(expand=True)
        ctk.CTkLabel(banner_shell, text='Track. Explore. Build Faster.', font=ctk.CTkFont(size=13), text_color=MUTED).pack(pady=(0, 12))

        btns_frame = ctk.CTkFrame(hdr, fg_color='transparent', width=HEADER_BUTTON_GROUP_WIDTH)
        btns_frame.grid(row=0, column=1, sticky='ew', padx=(0, 18))
        btns_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        for index, (attribute, label, icon_kind, command) in enumerate([
            ('settings_btn', 'Settings', 'settings', self.show_settings),
            ('clear_cache_btn', 'Clear\ncache', 'trash', self.clear_cache),
            ('refresh_credits_btn', REFRESH_CREDITS_BUTTON_TEXT, 'refresh', self.refresh_credits),
            ('refresh_btn', REFRESH_LIST_BUTTON_TEXT, 'list', self.refresh),
        ]):
            self._icons[icon_kind] = make_icon(icon_kind, 28)
            button = ctk.CTkButton(btns_frame, text=label, image=self._icons[icon_kind], compound='top', command=command,
                width=98, height=94, fg_color=SURFACE, hover_color=HEADER_BUTTON_HOVER_COLOR,
                border_width=1, border_color=BORDER, text_color=TEXT, font=ctk.CTkFont(size=12, weight='bold'), corner_radius=10)
            button.grid(row=0, column=index, sticky='ew', padx=(0, 8 if index < 3 else 0))
            setattr(self, attribute, button)
            self._tooltips.append(HoverTip(button, {'settings_btn': 'API key, startup and tray options.',
                'clear_cache_btn': 'Clear the local model cache and download a fresh catalog.',
                'refresh_credits_btn': 'Refresh your OpenRouter credit balance.',
                'refresh_btn': 'Refresh models, popularity rankings and offers. Shortcut: F5.'}[attribute]))

        category_shell = ctk.CTkFrame(btns_frame, fg_color=SURFACE, border_width=1, border_color=AMBER, corner_radius=10, height=50)
        category_shell.grid(row=1, column=0, columnspan=4, sticky='ew', pady=(12, 0))
        category_shell.grid_columnconfigure(1, weight=1)
        self._icons['category'] = make_icon('cube', 25)
        ctk.CTkLabel(category_shell, text='', image=self._icons['category']).grid(row=0, column=0, padx=(15, 8), pady=10)
        self._category_labels = {label: key for key, label in MODEL_CATEGORIES.items()}
        self.category_var = ctk.StringVar(value=MODEL_CATEGORIES[self.selected_category])
        self.category_menu = ctk.CTkOptionMenu(category_shell, values=list(MODEL_CATEGORIES.values()), variable=self.category_var,
            command=self._on_category_changed, width=330, height=40, fg_color=SURFACE, button_color=SURFACE,
            button_hover_color=HEADER_BUTTON_HOVER_COLOR, dropdown_fg_color=SURFACE_RAISED,
            dropdown_hover_color=HEADER_BUTTON_HOVER_COLOR, text_color=TEXT, dropdown_text_color=TEXT,
            font=ctk.CTkFont(size=14), anchor='w', corner_radius=8)
        self.category_menu.grid(row=0, column=1, sticky='ew', padx=(0, 8), pady=5)

        metrics = ctk.CTkFrame(hdr, fg_color='transparent', width=300)
        metrics.grid(row=0, column=2, sticky='ew')
        for index, (label, attribute, icon_kind, color) in enumerate([
            ('Models', 'models_count_lbl', 'cube', AMBER),
            ('Credits used', 'credits_lbl', 'credits', GOLD),
            ('Credits remaining', 'credits_available_lbl', 'ring', GREEN),
        ]):
            card = ctk.CTkFrame(metrics, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=10, height=52)
            card.pack(fill='x', pady=(0, 9 if index < 2 else 0))
            card.pack_propagate(False)
            self._icons[f'metric_{index}'] = make_icon(icon_kind, 26, color)
            ctk.CTkLabel(card, text='', image=self._icons[f'metric_{index}']).pack(side='left', padx=(15, 10))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=12), text_color=MUTED).pack(side='left')
            value = ctk.CTkLabel(card, text='—', font=ctk.CTkFont(size=20 if index == 0 else 13, weight='bold'), text_color=color if index == 0 else TEXT)
            value.pack(side='right', padx=(8, 14))
            setattr(self, attribute, value)

    def _resize_banner(self, event):
        if self._logo_image:
            original = self._logo_image.cget('dark_image')
            scale = min(max(1, event.width / self.banner_label._get_widget_scaling() - 4) / original.width, 154 / original.height)
            size = (max(1, int(original.width * scale)), max(1, int(original.height * scale)))
            if self._logo_image.cget('size') != size:
                self._logo_image.configure(size=size)

    def _build_search_bar(self):
        search_frame = ctk.CTkFrame(self.root, height=58, fg_color='transparent')
        search_frame.pack(side='top', fill='x', padx=18, pady=(8, 10))
        search_frame.pack_propagate(False)
        self.search_var = ctk.StringVar()
        self._search_debounce_id = None
        self.search_var.trace_add('write', lambda *_: self._on_search_changed())
        self.star_filter_btn = ctk.CTkButton(search_frame, text='★  Favorites', width=142, height=52,
            fg_color=SURFACE, hover_color=HEADER_BUTTON_HOVER_COLOR, text_color=GOLD, border_width=1, border_color=BORDER,
            font=ctk.CTkFont(size=13), command=self.toggle_star_filter, corner_radius=10)
        self.star_filter_btn.pack(side='right', padx=(10, 0), pady=3)
        self.promotion_filter_btn = ctk.CTkButton(search_frame, text='*  Offers', width=105, height=52,
            fg_color=SURFACE, hover_color=HEADER_BUTTON_HOVER_COLOR, text_color=GREEN, border_width=1, border_color=BORDER,
            font=ctk.CTkFont(size=13), command=self.toggle_promotion_filter, corner_radius=10)
        self.promotion_filter_btn.pack(side='right', padx=(10, 0), pady=3)

        self.search_shell = ctk.CTkFrame(search_frame, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=10)
        self.search_shell.pack(side='left', fill='both', expand=True, pady=3)
        self._icons['search'] = make_icon('search', 23, TEXT)
        ctk.CTkLabel(self.search_shell, text='', image=self._icons['search']).pack(side='left', padx=(16, 8))
        self.search_hint = ctk.CTkLabel(self.search_shell, text='Press  /  to focus', text_color=MUTED, font=ctk.CTkFont(size=11))
        self.search_hint.pack(side='right', padx=(8, 16))
        self.clear_search_btn = ctk.CTkButton(self.search_shell, text='×', width=30, height=32,
            command=self.clear_search, fg_color=SURFACE, hover_color=HEADER_BUTTON_HOVER_COLOR,
            text_color=MUTED, font=ctk.CTkFont(size=22), corner_radius=6, state='disabled')
        self.clear_search_btn.pack(side='right', padx=(4, 0))
        self._tooltips.append(HoverTip(self.clear_search_btn, 'Clear search. Shortcut: Escape.'))
        self.search_entry = ctk.CTkEntry(self.search_shell, textvariable=self.search_var,
            font=ctk.CTkFont(size=14), fg_color=SURFACE, border_width=0, text_color=TEXT, corner_radius=0)
        self.search_entry.pack(side='left', fill='both', expand=True, pady=6)
        self.search_placeholder = ctk.CTkLabel(self.search_entry, text='Search models, providers, or keywords…',
            text_color=MUTED, font=ctk.CTkFont(size=14), anchor='w', fg_color=SURFACE)
        self.search_placeholder.place(x=6, rely=0.5, anchor='w')
        self.search_placeholder.bind('<Button-1>', self._focus_search)
        self.search_entry.bind('<Return>', lambda _event: self._trigger_search())
        self.search_entry.bind('<Escape>', lambda _event: self.clear_search())
        self.search_entry.bind('<FocusIn>', self._search_focus_in)
        self.search_entry.bind('<FocusOut>', self._search_focus_out)

    def _focus_search(self, event=None):
        if event and getattr(event, 'keysym', None) == 'slash' and isinstance(self.root.focus_get(), (tk.Entry, tk.Text)):
            return None
        self.search_entry.focus_set()
        return 'break'

    def _search_focus_in(self, _event=None):
        self.search_shell.configure(border_color=AMBER)
        self.search_placeholder.place_forget()

    def _search_focus_out(self, _event=None):
        self.search_shell.configure(border_color=BORDER)
        if not self.search_var.get():
            self.search_placeholder.place(x=6, rely=0.5, anchor='w')

    def _on_category_changed(self, label):
        self.selected_category = self._category_labels.get(label, 'all')
        config.set('last_category', self.selected_category)
        self.apply_filter()

    def _update_category_menu(self):
        self._category_labels = {}
        for key, name in MODEL_CATEGORIES.items():
            count = len(self.all_models) if key == 'all' else sum(key in model['output_modalities'] for model in self.all_models)
            self._category_labels[f'{name}  ({count})'] = key
        self.category_menu.configure(values=list(self._category_labels))
        self.category_var.set(next(label for label, key in self._category_labels.items() if key == self.selected_category))

    def _build_main_area(self):
        """Build main area with a single-pass canvas renderer."""
        main = ctk.CTkFrame(self.root, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=12)
        main.pack(side='top', fill='both', expand=True, padx=18, pady=(0, 6))
        self.table_header = ctk.CTkFrame(main, height=42, fg_color=SURFACE_RAISED, corner_radius=8)
        self.table_header.pack(side='top', fill='x', padx=2, pady=(2, 0))
        self.table_header.pack_propagate(False)
        self._column_labels = {
            'star': '★', 'idx': '#', 'name': 'Model', 'provider': 'Provider / ID',
            'context': 'Tokens', 'input': 'Input / 1M', 'output': 'Output / 1M',
            'popularity': 'Popularity', 'created': 'Added', 'promotion': 'Offer *',
        }
        self.header_btns = []
        for key, label in self._column_labels.items():
            btn = ctk.CTkButton(self.table_header, text=label,
                command=lambda k=key: self.sort_by(k),
                width=60, height=36, fg_color=SURFACE_RAISED, hover_color=HEADER_BUTTON_HOVER_COLOR,
                text_color=GOLD if key == self.sort_col else TEXT, corner_radius=6,
                font=ctk.CTkFont(size=11, weight='bold'), anchor='w' if key in ('name', 'provider') else 'center')
            self.header_btns.append((btn, key))
            help_text = {
                'popularity': 'Official OpenRouter popularity rank. Click to change the sort direction.',
                'created': 'Date added to OpenRouter (UTC). The first click shows the newest models.',
                'promotion': 'Offers listed by OpenRouter. The first click shows the largest discounts.\n* marks a promotional price.',
                'input': 'Price per million input tokens, or characters for speech models.\nFor video, transcription and reranking, open › for the full rates.',
                'output': 'Price per million output tokens. Open › to see media prices and provider details.',
            }.get(key)
            if help_text:
                self._tooltips.append(HoverTip(btn, help_text))
        self._update_header_sort_state()
        list_frame = tk.Frame(main, bg=SURFACE)
        list_frame.pack(side='top', fill='both', expand=True, padx=3, pady=(0, 5))

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('CanvasList.Vertical.TScrollbar',
            background=BORDER, troughcolor=SURFACE,
            arrowcolor=MUTED, bordercolor=SURFACE, width=12)

        self.list_canvas = tk.Canvas(
            list_frame,
            bg=SURFACE,
            highlightthickness=0,
            bd=0,
            yscrollincrement=34,
            cursor='hand2'
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
        self.list_canvas.bind('<Motion>', self._on_canvas_motion)
        self.list_canvas.bind('<Leave>', self._on_canvas_leave)
        self._row_tooltip = HoverTip(self.list_canvas)
        self._tooltips.append(self._row_tooltip)

    def _build_status_bar(self):
        ctk.CTkFrame(self.root, height=1, fg_color='#594022', corner_radius=0).pack(side='bottom', fill='x')
        self.status_bar = ctk.CTkFrame(self.root, fg_color='transparent', height=44)
        self.status_bar.pack(side='bottom', fill='x', padx=22)
        self.status_bar.pack_propagate(False)
        self.status_lbl = ctk.CTkLabel(self.status_bar, text='Loading catalog…', font=ctk.CTkFont(size=12), text_color=MUTED)
        self.status_lbl.pack(side='left')
        self.author_lbl = ctk.CTkLabel(self.status_bar, text=f'{APP_NAME} v{APP_VERSION}', font=ctk.CTkFont(size=11), text_color=MUTED)
        self.author_lbl.pack(side='right')
        self.connection_lbl = ctk.CTkLabel(self.status_bar, text='●  Cached data    │', font=ctk.CTkFont(size=11), text_color=MUTED)
        self.connection_lbl.pack(side='right', padx=14)

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
            self._models_version += 1
            self._sort_cache_key = None
            self._sort_cache = None
            self._last_render_signature = None
            self._update_header_models_count(len(self.all_models))
            self._update_category_menu()
            self.apply_filter()
        else:
            self.all_models = []
            self._sort_cache_key = None
            self._sort_cache = None
            self._last_render_signature = None
            self._update_header_models_count(None)
            self._update_category_menu()
            self._draw_empty_state('Loading the OpenRouter catalog…')
        self.update_credits_display()
        self._refresh_tray_tooltip()

        if API_KEY:
            self._submit_background(self._fetch_credits)
        # Catalog and modality metadata are public; the key is only needed for credits.
        self.refresh()
        self._schedule_credits_refresh()

    def _fetch_credits(self):
        if not API_KEY:
            self._queue_ui(lambda: (
                self.credits_lbl.configure(text='—'),
                self.credits_available_lbl.configure(text='—'),
                self._refresh_tray_tooltip()
            ))
            return
        credits = get_generation_cost()
        self._queue_ui(lambda: self._on_credits_loaded(credits))

    def _on_credits_loaded(self, credits):
        self.credits_info = credits
        self.update_credits_display()

    def _fetch_models_and_cache(self):
        self._do_refresh()

    def _on_models_loaded(self, models):
        self.all_models = models
        self._models_version += 1
        self._sort_cache_key = None
        self._sort_cache = None
        self._last_render_signature = None
        self._update_header_models_count(len(models))
        self._update_category_menu()
        self.is_loading = False
        self._catalog_live = True
        if not self.credits_info.get('data'):
            self._set_connection_state('Catalog live', GREEN)
        self.apply_filter()
        self.refresh_btn.configure(
            state='normal',
            text=REFRESH_LIST_BUTTON_TEXT,
            fg_color=HEADER_BUTTON_NORMAL_COLOR,
            hover_color=HEADER_BUTTON_HOVER_COLOR,
            text_color=TEXT,
        )

    def refresh(self):
        if self.is_loading:
            return
        self.is_loading = True
        self.refresh_btn.configure(
            state='disabled',
            text=REFRESH_LIST_LOADING_TEXT,
            fg_color=HEADER_BUTTON_DISABLED_COLOR,
            hover_color=HEADER_BUTTON_HOVER_COLOR,
            text_color=TEXT,
        )
        self.status_lbl.configure(text='Loading...')
        self._submit_background(self._do_refresh)

    def _do_refresh(self):
        try:
            raw = get_models_from_api()
        except Exception as e:
            logger.error(f"Refresh failed: {e}")
            raw = []
        if raw:
            models = process_models(raw)
            if not self._is_closing:
                save_cache(models)
            self._queue_ui(lambda: self._on_models_loaded(models))
        else:
            self._queue_ui(self._on_catalog_error)

    def _on_catalog_error(self):
        self.is_loading = False
        self._catalog_live = False
        self.refresh_btn.configure(state='normal', text=REFRESH_LIST_BUTTON_TEXT, text_color=TEXT)
        self._set_connection_state('Offline · cached data', MUTED)
        self.status_lbl.configure(text='Refresh failed · cached models are still available', text_color=MUTED)
        if not self.all_models:
            self._draw_empty_state('Unable to load models. Check your connection and refresh the list.')

    def _on_all_loaded(self, models, credits):
        self.credits_info = credits
        self.update_credits_display()
        self._on_models_loaded(models)

    def refresh_data(self):
        self.refresh()

    def refresh_credits(self):
        if self.is_loading:
            return
        if not API_KEY:
            self.status_lbl.configure(text='API key not configured.')
            return
        self.refresh_credits_btn.configure(
            state='disabled',
            text=REFRESH_CREDITS_LOADING_TEXT,
            fg_color=HEADER_BUTTON_DISABLED_COLOR,
            hover_color=HEADER_BUTTON_HOVER_COLOR,
            text_color=TEXT,
        )
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
        self.refresh_credits_btn.configure(
            state='normal',
            text=REFRESH_CREDITS_BUTTON_TEXT,
            fg_color=HEADER_BUTTON_NORMAL_COLOR,
            hover_color=HEADER_BUTTON_HOVER_COLOR,
            text_color=TEXT,
        )

    # ========================================================================
    # UI HELPERS
    # ========================================================================

    def _queue_ui(self, callback):
        if self._is_closing:
            return
        self._ui_queue.put(callback)

    def _drain_ui_queue(self):
        if self._is_closing:
            return
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                logger.exception('UI callback failed')
        self._ui_poll_id = self.root.after(40, self._drain_ui_queue)

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
                self.models_count_lbl.configure(text='—')
            else:
                self.models_count_lbl.configure(text=f'{total_models:,}')

    def _set_connection_state(self, text, color):
        self._connection_state = text
        self.connection_lbl.configure(text=f'●  {text}    │', text_color=color)

    def update_credits_display(self):
        if not self.credits_info or 'data' not in self.credits_info:
            self.credits_lbl.configure(text='—')
            self.credits_available_lbl.configure(text='—')
            if API_KEY:
                self._set_connection_state('API unavailable', MUTED)
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
            self.credits_lbl.configure(text=f'${usage:.2f}')
            if remaining is None:
                self.credits_available_lbl.configure(text='Unlimited')
            else:
                self.credits_available_lbl.configure(text=f'${float(remaining):.2f}')
        else:
            self.credits_lbl.configure(text=f'${usage:.2f} / ${float(limit):.2f}')
            if remaining is None:
                self.credits_available_lbl.configure(text='—')
            else:
                self.credits_available_lbl.configure(text=f'${float(remaining):.2f}')
        self._set_connection_state('API Connected', GREEN)
        self._refresh_tray_tooltip()

    # ========================================================================
    # SORTING AND FILTERING
    # ========================================================================

    def sort_by(self, col):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col = col
            self.sort_rev = col in ('created', 'promotion')
        self._update_header_sort_state()
        config.set('last_sort_column', col)
        config.set('last_sort_reverse', self.sort_rev)
        self.apply_filter()

    def _update_header_sort_state(self):
        for btn, key in self.header_btns:
            suffix = ('  ↓' if self.sort_rev else '  ↑') if key == self.sort_col else ''
            btn.configure(text=f'{self._column_labels[key]}{suffix}', text_color=AMBER if key == self.sort_col else TEXT)

    def get_sorted(self, models):
        return sort_models(models, self.sort_col, self.sort_rev, self.favorites)

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
        self.star_filter_btn.configure(fg_color='#302619' if self.show_only_favorites else SURFACE,
            border_color=AMBER if self.show_only_favorites else BORDER)
        self._last_render_signature = None
        self.apply_filter()

    def toggle_promotion_filter(self):
        self.show_only_promotions = not self.show_only_promotions
        self.promotion_filter_btn.configure(fg_color='#102d23' if self.show_only_promotions else SURFACE,
            border_color=GREEN if self.show_only_promotions else BORDER)
        self._last_render_signature = None
        self.apply_filter()

    def _on_search_changed(self):
        if self._is_closing:
            return
        has_query = bool(self.search_var.get())
        self.clear_search_btn.configure(state='normal' if has_query else 'disabled', text_color=TEXT if has_query else MUTED)
        if has_query:
            self.search_placeholder.place_forget()
        elif self.root.focus_get() is not self.search_entry._entry:
            self.search_placeholder.place(x=6, rely=0.5, anchor='w')
        if self._search_debounce_id:
            self.root.after_cancel(self._search_debounce_id)
        self._search_debounce_id = self.root.after(180, self._debounced_search)

    def _debounced_search(self):
        self._search_debounce_id = None
        self.apply_filter()

    def _trigger_search(self):
        if self._search_debounce_id:
            self.root.after_cancel(self._search_debounce_id)
            self._search_debounce_id = None
        self._last_render_signature = None
        self.apply_filter()

    def clear_search(self):
        self.search_var.set('')
        if self._search_debounce_id:
            self.root.after_cancel(self._search_debounce_id)
            self._search_debounce_id = None
        self._pending_query = ''
        self._last_render_signature = None
        self.apply_filter()
        self.search_entry.focus_set()

    def apply_filter(self):
        query = self.search_var.get().lower().strip()
        filtered = filter_models(self._get_sorted_all(), query, self.selected_category, self.favorites,
            self.show_only_favorites, self.show_only_promotions)

        filter_state_key = (
            self._models_version,
            self._favorites_version if (self.show_only_favorites or self.sort_col == 'star') else 0,
            self.sort_col,
            self.sort_rev,
            self.show_only_favorites,
            self.show_only_promotions,
            self.selected_category,
            query,
        )
        self._filter_state_key = filter_state_key

        signature = self._build_render_signature(filtered, query)
        if signature == self._last_render_signature:
            return
        self._last_render_signature = signature

        self._clear_scroll()

        if not filtered:
            label = 'No matching offers' if self.show_only_promotions else 'No matching favorites' if self.show_only_favorites else 'No models match your filters'
            self._draw_empty_state(label)
            self._set_filter_status(0, len(self.all_models), query, 0)
            return

        total = len(filtered)
        total_all = len(self.all_models)
        self._visible_models = filtered
        self._render_rows_chunk(filtered, 0, 0, 0)
        self._set_filter_status(total, total_all, query, total)

    def _build_render_signature(self, filtered, query):
        favorites_state = self._favorites_version
        return (
            self._models_version,
            favorites_state,
            len(filtered),
            tuple(m['id'] for m in filtered),
            self.sort_col,
            self.sort_rev,
            self.show_only_favorites,
            self.show_only_promotions,
            self.selected_category,
            query,
        )

    def _set_filter_status(self, total, total_all, query, visible_count):
        if self.show_only_favorites:
            text = f'{total} favorites / {total_all} models'
        elif query or self.selected_category != 'all' or self.show_only_promotions:
            text = f'{total} / {total_all} models'
        else:
            text = f'{total_all} models total'
        if self.selected_category != 'all':
            text += f'  ·  {MODEL_CATEGORIES[self.selected_category]}'
        if self.show_only_promotions:
            text += '  ·  Offers'
        if any(model.get('is_promoted') for model in self._visible_models):
            text += '  ·  * Promotional price'
        if self.all_models and not any(model.get('promotion_known') for model in self.all_models):
            text += '  ·  Offers unavailable'
        self.status_lbl.configure(text=text, text_color=MUTED)

    def _clear_scroll(self):
        self._row_tooltip.hide()
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
        self._hovered_row = None
        self._visible_models = rows
        self._layout_columns()
        for row_idx, model in enumerate(rows):
            self._create_model_row(row_idx, model)
        total_height = max(self.list_canvas.winfo_height(), len(rows) * self._canvas_row_height)
        self.list_canvas.configure(scrollregion=(0, 0, self._canvas_table_width, total_height))

    def _create_model_row(self, row_idx, model):
        bg = '#141a1f' if row_idx % 2 == 0 else '#101519'
        y0 = row_idx * self._canvas_row_height
        y1 = y0 + self._canvas_row_height
        cy = y0 + (self._canvas_row_height / 2)
        row_tags = ('row', f"model::{model['id']}")
        selected = self._selected_model_id == model['id']
        background = self.list_canvas.create_rectangle(2, y0 + 1, self._canvas_table_width - 2, y1 - 1,
            fill='#302215' if selected else bg, outline='#ad6b1b' if selected else '', width=1, tags=row_tags)
        self.list_canvas.create_line(3, y1, self._canvas_table_width - 3, y1, fill='#242c32', tags=row_tags)
        is_fav = model['id'] in self.favorites
        center = lambda key: sum(self._column_bounds[key]) / 2
        star_item = self.list_canvas.create_text(
            center('star'),
            cy,
            text='★' if is_fav else '☆',
            fill=AMBER if is_fav else MUTED,
            font=self._table_fonts['star'],
            tags=('row', 'star', f"model::{model['id']}")
        )
        self.list_canvas.create_text(center('idx'), cy, text=str(row_idx + 1), fill=MUTED, font=self._table_fonts['normal'], tags=row_tags)
        for key, text, font_key in [('name', model.get('name') or '—', 'name'), ('provider', model['id'], 'id')]:
            left, right = self._column_bounds[key]
            self.list_canvas.create_text(left + 6, cy, text=self._ellipsize(text + (' *' if key == 'name' and model.get('is_promoted') else ''),
                right - left - 12, self._table_fonts[font_key]), fill=TEXT if key == 'name' else MUTED,
                font=self._table_fonts[font_key], anchor='w', tags=row_tags)
        for key, text, color, font_key in [
            ('context', model.get('context_text') or '—', model.get('context_color') or MUTED, 'normal'),
            ('input', model.get('input_text') or '—', GOLD if model.get('input_price') == 0 else model.get('input_color', MUTED), 'price'),
            ('output', model.get('output_text') or '—', GOLD if model.get('output_price') == 0 else model.get('output_color', MUTED), 'price'),
            ('popularity', model.get('popularity_text') or '—', AMBER if model.get('popularity_rank') else MUTED, 'normal'),
            ('created', model.get('created_text') or '—', TEXT if model.get('created') else MUTED, 'date'),
            ('promotion', model.get('promotion_text') or '—', GREEN if model.get('is_promoted') else MUTED, 'price'),
        ]:
            self.list_canvas.create_text(center(key), cy, text=text, fill=color, font=self._table_fonts[font_key], tags=row_tags)
        arrow = self.list_canvas.create_text(center('details'), cy, text='›', fill=AMBER if selected else MUTED,
            font=self._table_fonts['star'], tags=row_tags)
        self._row_widgets[model['id']] = {'star': star_item, 'background': background, 'bg': bg, 'arrow': arrow}

    def _layout_columns(self):
        scale = self.table_header._get_widget_scaling()
        width = max(1, self.list_canvas.winfo_width())
        if width <= 1:
            width = int(1300 * scale)
        self._canvas_table_width = width
        self._canvas_row_height = max(24, int(34 * scale))
        self.list_canvas.configure(yscrollincrement=self._canvas_row_height)
        widths = {'star': 36, 'idx': 32, 'context': 92, 'input': 96, 'output': 96,
                  'popularity': 108, 'created': 104, 'promotion': 92, 'details': 24}
        available = max(120, width / scale - sum(widths.values()))
        widths['name'] = available * 0.55
        widths['provider'] = available * 0.45
        self._column_bounds = {}
        position = 0
        for key in ('star', 'idx', 'name', 'provider', 'context', 'input', 'output', 'popularity', 'created', 'promotion', 'details'):
            right = position + widths[key] * scale
            self._column_bounds[key] = (position, right)
            position = right
        for button, key in self.header_btns:
            left, right = self._column_bounds[key]
            button.configure(width=max(1, (right - left) / scale - 2))
            button.place(x=left / scale, y=3)
        if getattr(self, '_font_scale', None) != scale:
            self._font_scale = scale
            self._table_fonts = {
                'normal': tkfont.Font(family='Segoe UI', size=-round(13 * scale)),
                'name': tkfont.Font(family='Segoe UI', size=-round(14 * scale), weight='bold'),
                'id': tkfont.Font(family='Consolas', size=-round(12 * scale)),
                'price': tkfont.Font(family='Segoe UI', size=-round(12 * scale), weight='bold'),
                'date': tkfont.Font(family='Segoe UI', size=-round(12 * scale)),
                'star': tkfont.Font(family='Segoe UI Symbol', size=-round(24 * scale)),
            }

    def _ellipsize(self, text, max_width, font):
        if font.measure(text) <= max_width:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.measure(text[:middle] + '…') <= max_width:
                low = middle
            else:
                high = middle - 1
        return text[:low] + '…'

    def _show_more_rows(self):
        return

    def _draw_empty_state(self, text):
        width = max(self.list_canvas.winfo_width(), self._canvas_table_width)
        height = max(self.list_canvas.winfo_height(), 120)
        self.list_canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            fill=MUTED,
            font=('Segoe UI', 12)
        )
        self.list_canvas.configure(scrollregion=(0, 0, width, height))

    def _redraw_if_needed(self):
        if self._visible_models:
            self._render_rows_chunk(self._visible_models, 0, 0, 0)
        else:
            self._layout_columns()

    def _row_at_event(self, event):
        index = int(self.list_canvas.canvasy(event.y) // self._canvas_row_height)
        return index if 0 <= index < len(self._visible_models) else None

    def _paint_row_state(self, index):
        if index is None or index >= len(self._visible_models):
            return
        model = self._visible_models[index]
        row = self._row_widgets.get(model['id'])
        if not row:
            return
        active = index == self._hovered_row or model['id'] == self._selected_model_id
        self.list_canvas.itemconfigure(row['background'], fill='#302215' if active else row['bg'], outline='#ad6b1b' if active else '')
        self.list_canvas.itemconfigure(row['arrow'], fill=AMBER if active else MUTED)

    def _on_canvas_motion(self, event):
        index = self._row_at_event(event)
        if index is not None and event.x < self._column_bounds['provider'][1]:
            model = self._visible_models[index]
            category_text = ', '.join(MODEL_CATEGORIES.get(key, key.title()) for key in model['output_modalities'])
            self._row_tooltip.schedule(f"{model['name']}\n{model['id']}\n{category_text}\nClick the row to copy the ID. Use › to open details.", event.x_root, event.y_root)
        else:
            self._row_tooltip.hide()
        if index == self._hovered_row:
            return
        previous = self._hovered_row
        self._hovered_row = index
        self._paint_row_state(previous)
        self._paint_row_state(index)

    def _on_canvas_leave(self, _event=None):
        self._row_tooltip.hide()
        previous = self._hovered_row
        self._hovered_row = None
        self._paint_row_state(previous)

    def _on_canvas_click(self, event):
        self._row_tooltip.hide()
        index = self._row_at_event(event)
        if index is None:
            return
        model_id = self._visible_models[index]['id']
        if event.x < self._column_bounds['star'][1]:
            self.toggle_favorite(model_id)
            return
        if event.x >= self._column_bounds['details'][0]:
            from urllib.parse import quote
            webbrowser.open(f'https://openrouter.ai/{quote(model_id, safe="/:")}')
            return
        previous = next((i for i, model in enumerate(self._visible_models) if model['id'] == self._selected_model_id), None)
        self._selected_model_id = model_id
        self._paint_row_state(previous)
        self._paint_row_state(index)
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
        self._status_color_reset_id = self.root.after(2800, lambda: self.status_lbl.configure(text_color=MUTED))

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
        if self.root.state() == 'iconic' and self._system_tray:
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
        key = prompt_for_api_key(self.root)
        if not key:
            return
        self._set_api_key_value(key)

    def _set_api_key_value(self, key):
        global API_KEY
        API_KEY = key.strip() or None
        config.set('api_key', API_KEY or '')
        self.credits_info = {}
        self.update_credits_display()
        if API_KEY:
            self._submit_background(self._fetch_credits)
        else:
            self._set_connection_state('Catalog live' if self._catalog_live else 'Cached data', GREEN if self._catalog_live else MUTED)
        self._refresh_tray_tooltip()

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
        for tooltip in self._tooltips:
            tooltip.hide()

        if self._ui_poll_id:
            self.root.after_cancel(self._ui_poll_id)
            self._ui_poll_id = None

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
        self.top.geometry("500x560")
        self.top.resizable(False, False)
        self.top.transient(self.parent)
        self.top.grab_set()
        self.top.protocol('WM_DELETE_WINDOW', self._on_close_dialog)
        try:
            icon_path = APP_DIR / 'MEDIAS/openrouter-monitor.ico'
            if icon_path.exists():
                self.top.iconbitmap(str(icon_path))
        except Exception as e:
            logger.debug(f"Failed to set settings icon: {e}")
        self._settings_icon = None
        try:
            if self.app._window_icon:
                self.top.iconphoto(False, self.app._window_icon)
        except Exception as e:
            logger.debug(f"Failed to set settings iconphoto: {e}")

        self._build_ui()

        self.top.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - self.top.winfo_width()) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - self.top.winfo_height()) // 2
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
        shell = ctk.CTkFrame(self.top, fg_color=BACKGROUND, corner_radius=0)
        shell.pack(fill='both', expand=True)

        ctk.CTkFrame(shell, height=4, fg_color=HERMES_ORANGE).pack(fill='x')

        header = ctk.CTkFrame(shell, fg_color='transparent')
        header.pack(fill='x', padx=22, pady=(14, 6))
        ctk.CTkLabel(header, text='Settings', font=ctk.CTkFont(size=22, weight='bold'), text_color='white').pack(anchor='w')
        ctk.CTkLabel(
            header,
            text='API key, tray, startup and automatic credit refresh.',
            font=ctk.CTkFont(size=12),
            text_color='#9A9A9A'
        ).pack(anchor='w', pady=(2, 0))

        panel = ctk.CTkFrame(shell, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        panel.pack(fill='both', expand=True, padx=18, pady=(2, 8))

        self.auto_start_var = ctk.BooleanVar(value=self.config.get('auto_start', False))
        self.minimize_var = ctk.BooleanVar(value=self.config.get('minimize_to_tray', True))
        self.interval_var = ctk.StringVar(value=str(self.config.get('refresh_interval_minutes', 5)))
        self.api_key_var = ctk.StringVar(value=API_KEY or '')

        key_card = ctk.CTkFrame(panel, fg_color=SURFACE_RAISED, corner_radius=10)
        key_card.pack(fill='x', padx=18, pady=(14, 6))
        ctk.CTkLabel(key_card, text='OpenRouter API key', font=ctk.CTkFont(size=14, weight='bold'), text_color=GOLD).pack(anchor='w', padx=14, pady=(10, 4))
        self.api_key_entry = ctk.CTkEntry(key_card, textvariable=self.api_key_var, show='•', height=36,
            fg_color=SURFACE, border_color=BORDER, text_color=TEXT)
        self.api_key_entry.pack(fill='x', padx=14, pady=(0, 6))
        ctk.CTkLabel(key_card, text='Used for account credits. Model browsing works without a key.',
            font=ctk.CTkFont(size=11), text_color=MUTED).pack(anchor='w', padx=14, pady=(0, 10))

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

        timer_card = ctk.CTkFrame(panel, fg_color=SURFACE_RAISED, corner_radius=12)
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
            if (self.api_key_var.get().strip() or None) != API_KEY:
                self.app._set_api_key_value(self.api_key_var.get())

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
            logger.info("No API key configured; public catalog browsing is available")

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
