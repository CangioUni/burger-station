import re

with open('printing.py', 'r') as f:
    content = f.read()

cache_code = """
# --- Performance Caching ---
_menu_cache_lock = threading.Lock()
_bibite_names_cache = None

_settings_cache_lock = threading.Lock()
_system_settings_cache = None

_user_cache_lock = threading.Lock()
_user_settings_cache = {}

def invalidate_menu_cache():
    global _bibite_names_cache
    with _menu_cache_lock:
        _bibite_names_cache = None

def invalidate_settings_cache():
    global _system_settings_cache
    with _settings_cache_lock:
        _system_settings_cache = None

def invalidate_user_cache(user_id=None):
    global _user_settings_cache
    with _user_cache_lock:
        if user_id is None:
            _user_settings_cache.clear()
        elif user_id in _user_settings_cache:
            del _user_settings_cache[user_id]

def get_bibite_names():
    global _bibite_names_cache
    with _menu_cache_lock:
        if _bibite_names_cache is None:
            db = SessionLocal()
            try:
                items = db.query(MenuItem).filter(MenuItem.category == 'bibite', MenuItem.is_active == True).all()
                _bibite_names_cache = {bi.description for bi in items}
            finally:
                db.close()
        return _bibite_names_cache

def get_system_settings():
    global _system_settings_cache
    with _settings_cache_lock:
        if _system_settings_cache is None:
            db = SessionLocal()
            try:
                settings = db.query(SystemSettings).first()
                if settings:
                    _system_settings_cache = {
                        "kitchen_printer_protocol": settings.kitchen_printer_protocol,
                        "kitchen_printer_ip": settings.kitchen_printer_ip
                    }
                else:
                    _system_settings_cache = {}
            finally:
                db.close()
        return _system_settings_cache

def get_user_settings(user_id):
    global _user_settings_cache
    with _user_cache_lock:
        if user_id not in _user_settings_cache:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    _user_settings_cache[user_id] = {
                        "printer_protocol": user.printer_protocol,
                        "printer_ip": user.printer_ip
                    }
                else:
                    _user_settings_cache[user_id] = None
            finally:
                db.close()
        return _user_settings_cache[user_id]
# ---------------------------
"""

# Insert cache code after init function
content = re.sub(
    r'(def init\(.*?:\n.*?MenuItem = menu_item_model\n)',
    r'\1\n' + cache_code,
    content,
    flags=re.DOTALL
)

with open('printing.py', 'w') as f:
    f.write(content)
