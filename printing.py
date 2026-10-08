import datetime
import threading
import base64
from zoneinfo import ZoneInfo
from escpos.printer import Network
import receipt_template

printer_locks = {}
printer_locks_mutex = threading.Lock()

def get_printer_lock(ip):
    with printer_locks_mutex:
        if ip not in printer_locks:
            printer_locks[ip] = threading.Lock()
        return printer_locks[ip]

ROME_TZ = ZoneInfo("Europe/Rome")

# Injected by main.py at startup
SessionLocal = None
User = None
SystemSettings = None
MenuItem = None
Category = None

def init(session_local, user_model, settings_model, menu_item_model, category_model=None):
    """Called once from main.py to inject DB dependencies."""
    global SessionLocal, User, SystemSettings, MenuItem, Category
    SessionLocal = session_local
    User = user_model
    SystemSettings = settings_model
    MenuItem = menu_item_model
    Category = category_model


# --- Performance Caching ---
_cache_lock = threading.RLock()
_system_settings_cache = None
_user_settings_cache = {}
_category_printer_cache = None
_menu_item_lookup_cache = None

def invalidate_menu_cache():
    global _menu_item_lookup_cache
    with _cache_lock:
        _menu_item_lookup_cache = None

def invalidate_category_cache():
    global _category_printer_cache, _menu_item_lookup_cache
    with _cache_lock:
        _category_printer_cache = None
        _menu_item_lookup_cache = None

def invalidate_settings_cache():
    global _system_settings_cache
    with _cache_lock:
        _system_settings_cache = None

def invalidate_user_cache(user_id=None):
    global _user_settings_cache
    with _cache_lock:
        if user_id is None:
            _user_settings_cache.clear()
        elif user_id in _user_settings_cache:
            del _user_settings_cache[user_id]

def get_system_settings():
    global _system_settings_cache
    with _cache_lock:
        if _system_settings_cache is None:
            db = SessionLocal()
            try:
                settings = db.query(SystemSettings).first()
                if settings:
                    _system_settings_cache = {
                        "kitchen_printer_protocol": getattr(settings, "kitchen_printer_protocol", "escpos") or "escpos",
                        "kitchen_printer_ip": getattr(settings, "kitchen_printer_ip", "10.0.0.200") or "10.0.0.200",
                        "auto_print_kitchen": getattr(settings, "auto_print_kitchen", True) if getattr(settings, "auto_print_kitchen", True) is not None else True,
                        "bar_printer_protocol": getattr(settings, "bar_printer_protocol", "escpos") or "escpos",
                        "bar_printer_ip": getattr(settings, "bar_printer_ip", "10.0.0.200") or "10.0.0.200",
                        "auto_print_bar": getattr(settings, "auto_print_bar", True) if getattr(settings, "auto_print_bar", True) is not None else True
                    }
                else:
                    _system_settings_cache = {
                        "kitchen_printer_protocol": "escpos",
                        "kitchen_printer_ip": "10.0.0.200",
                        "auto_print_kitchen": True,
                        "bar_printer_protocol": "escpos",
                        "bar_printer_ip": "10.0.0.200",
                        "auto_print_bar": True
                    }
            finally:
                db.close()
        return _system_settings_cache

def get_user_settings(user_id):
    global _user_settings_cache
    with _cache_lock:
        if user_id not in _user_settings_cache:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    _user_settings_cache[user_id] = {
                        "printer_protocol": user.printer_protocol or "escpos",
                        "printer_ip": user.printer_ip or "10.0.0.200",
                        "auto_print_main": user.auto_print_main if user.auto_print_main is not None else True,
                        "printer_connection_type": getattr(user, "printer_connection_type", "network") or "network",
                        "printer_paper_width": getattr(user, "printer_paper_width", "80mm") or "80mm"
                    }
                else:
                    _user_settings_cache[user_id] = None
            finally:
                db.close()
        return _user_settings_cache[user_id]

def get_category_printer_map():
    global _category_printer_cache
    with _cache_lock:
        if _category_printer_cache is None:
            db = SessionLocal()
            try:
                if Category:
                    cats = db.query(Category).all()
                    _category_printer_cache = {
                        c.name.strip().lower(): (getattr(c, 'printer_target', 'cucina') or 'cucina').lower()
                        for c in cats if c.name
                    }
                else:
                    _category_printer_cache = {}
            finally:
                db.close()
        return _category_printer_cache

def get_menu_item_lookup():
    global _menu_item_lookup_cache
    with _cache_lock:
        if _menu_item_lookup_cache is None:
            db = SessionLocal()
            try:
                cat_map = get_category_printer_map()
                items = db.query(MenuItem).filter(MenuItem.is_active == True).all()
                lookup = {}
                for mi in items:
                    cat_name = (mi.category or '').strip().lower()
                    target = cat_map.get(cat_name, 'cucina')
                    lookup[mi.description.strip().lower()] = {
                        'category': cat_name,
                        'printer_target': target
                    }
                _menu_item_lookup_cache = lookup
            finally:
                db.close()
        return _menu_item_lookup_cache

def categorize_order_items(payload):
    """
    Categorizes the items of an order into:
    - kitchen_items: items to be printed on Kitchen printer
    - bar_items: items to be printed on Bevande/Bar printer
    """
    cat_map = get_category_printer_map()
    menu_lookup = get_menu_item_lookup()

    kitchen_items = []
    bar_items = []

    for item in payload.get('items', []):
        desc = item.get('description', '')
        category = (item.get('category') or '').strip().lower()
        combo_choices = item.get('combo_choices', '')

        # Fallback category lookup if not present on item dict
        if not category:
            item_info = menu_lookup.get(desc.strip().lower())
            if item_info:
                category = item_info['category']

        target = cat_map.get(category, 'cucina')

        if target == 'cucina':
            kitchen_items.append(item)
        elif target == 'bevande':
            bar_items.append(item)

        # Handle combo choices: if any sub-item belongs to 'bevande', extract for the bar ticket
        if combo_choices:
            for sub in combo_choices.split(','):
                sub_clean = sub.strip()
                if not sub_clean or sub_clean == 'Nessuna Scelta':
                    continue
                base_desc = sub_clean.split('[')[0].strip()
                sub_info = menu_lookup.get(base_desc.lower())
                if sub_info and sub_info.get('printer_target') == 'bevande':
                    # Only add to bar_items if parent wasn't already assigned to bevande
                    if target != 'bevande':
                        bar_items.append({
                            'description': base_desc,
                            'combo_choices': '',
                            'notes': '',
                            'ingredients': '',
                            'category': sub_info.get('category', 'bibite')
                        })

    return kitchen_items, bar_items

def get_required_printers(payload, auto_print_main=True, auto_print_kitchen=True, auto_print_bar=True):
    printers = set()
    if auto_print_main:
        active_user_id = payload.get('user_id', 1)
        user_settings = get_user_settings(active_user_id)
        conn_type = user_settings.get("printer_connection_type", "network") if user_settings else "network"
        if conn_type == "network":
            printer_ip = user_settings.get("printer_ip") if user_settings else None
            printers.add(printer_ip or "10.0.0.200")

    settings = get_system_settings()
    kitchen_items, bar_items = categorize_order_items(payload)

    if auto_print_kitchen and len(kitchen_items) > 0:
        k_ip = settings.get("kitchen_printer_ip") if settings else None
        printers.add(k_ip or "10.0.0.200")

    if auto_print_bar and len(bar_items) > 0:
        b_ip = settings.get("bar_printer_ip") if settings else None
        printers.add(b_ip or "10.0.0.200")

    return list(printers)

def row_left_right(label: str, value: str, width: int = 48) -> str:
    """Return a left/right aligned string padded to `width` characters."""
    spaces = width - len(label) - len(value)
    if spaces < 1:
        max_label = max(1, width - len(value) - 1)
        label = label[:max_label]
        spaces = 1
    return label + " " * max(spaces, 1) + value

def generate_bill_escpos(order_id: int, payload: dict, paper_width: str = "80mm") -> bytes:
    """
    Generates the complete binary ESC/POS byte sequence for a customer receipt.
    Adapts column layout automatically for 80mm (48 columns) or 58mm (32 columns).
    """
    width = 32 if paper_width == "58mm" else 48
    buf = bytearray()

    # Reset printer & select code table 19 (CP858)
    buf.extend(b'\x1b@') # Initialize
    buf.extend(b'\x1b\x74\x13') # Select table 19 (CP858)

    # 1. Header (modular from receipt_template.py)
    buf.extend(receipt_template.build_bill_header(order_id, paper_width=paper_width))

    # 2. Column Header (modular from receipt_template.py)
    buf.extend(receipt_template.build_column_header(width=width))

    gross_total = 0.0

    grouped_items = []
    for item in payload.get('items', []):
        desc = item.get('description', '')
        price = float(item.get('price', 0))
        combo_choices = item.get('combo_choices', '')
        notes = item.get('notes', '')
        ingredients = item.get('ingredients', '')
        discount = float(item.get('item_discount', 0))
        discount_type = item.get('item_discount_type', '%')
        is_groupable = not combo_choices and not notes and not ingredients and discount == 0

        if is_groupable:
            found = False
            for g in grouped_items:
                if g['groupable'] and g['description'] == desc and g['price'] == price:
                    g['qty'] += 1
                    found = True
                    break
            if not found:
                grouped_items.append({
                    'groupable': True, 'description': desc, 'price': price,
                    'qty': 1, 'combo_choices': '', 'notes': '', 'ingredients': '',
                    'discount': 0, 'discount_type': '%'
                })
        else:
            grouped_items.append({
                'groupable': False, 'description': desc, 'price': price,
                'qty': 1, 'combo_choices': combo_choices, 'notes': notes, 'ingredients': ingredients,
                'discount': discount, 'discount_type': discount_type
            })

    for item in grouped_items:
        desc = item['description']
        price = item['price']
        qty = item['qty']
        item_discount = item.get('discount', 0)
        item_discount_type = item.get('discount_type', '%')

        base_item_total = price * qty
        discount_amount = 0
        if item_discount > 0:
            if item_discount_type == '%':
                discount_amount = base_item_total * (item_discount / 100)
            else:
                discount_amount = item_discount

        item_total = base_item_total - discount_amount
        if item_total < 0:
            item_total = 0

        gross_total += item_total

        if qty > 1:
            buf.extend((f"{qty} x {price:.2f}".replace('.', ',') + "\n").encode('cp858', errors='replace'))
            buf.extend((row_left_right(desc, f"{base_item_total:.2f}".replace('.', ','), width) + "\n").encode('cp858', errors='replace'))
        else:
            buf.extend((row_left_right(desc, f"{price:.2f}".replace('.', ','), width) + "\n").encode('cp858', errors='replace'))

        if item_discount > 0:
            if item_discount_type == '%':
                discount_label = f"SCONTO {int(item_discount)}%" if item_discount.is_integer() else f"SCONTO {item_discount:.2f}%"
            else:
                discount_label = "SCONTO"
            discount_val_str = f"-{discount_amount:.2f}".replace('.', ',')
            buf.extend((row_left_right("  " + discount_label, discount_val_str, width) + "\n").encode('cp858', errors='replace'))

        combo_choices = item['combo_choices']
        if combo_choices:
            for sub in combo_choices.split(','):
                sub_clean = sub.strip()
                if sub_clean:
                    buf.extend((" - " + sub_clean + "\n").encode('cp858', errors='replace'))

    # Separator
    buf.extend(("-" * width + "\n").encode('cp858', errors='replace'))

    # Totals
    overall_discount = payload.get('discount', 0)

    if overall_discount > 0:
        subtotal_str = f"{gross_total:.2f}".replace('.', ',')
        buf.extend((row_left_right("SUBTOTALE", subtotal_str, width) + "\n").encode('cp858', errors='replace'))

        discount_str = f"-{overall_discount:.2f}".replace('.', ',')
        buf.extend((row_left_right("SCONTO", discount_str, width) + "\n").encode('cp858', errors='replace'))
        buf.extend(("-" * width + "\n").encode('cp858', errors='replace'))

        net_total = gross_total - overall_discount
        if net_total < 0:
            net_total = 0
    else:
        net_total = gross_total

    buf.extend(b'\x1b!\x10') # Double height
    total_str = f"{net_total:.2f}".replace('.', ',')
    buf.extend((row_left_right("TOTALE COMPLESSIVO", total_str, width) + "\n").encode('cp858', errors='replace'))
    buf.extend(b'\x1b!\x00') # Normal

    payment_status = payload.get('payment_status', True)
    payment_method = payload.get('payment_method', '')

    buf.extend(b'\n')
    if payment_status:
        if payment_method:
            buf.extend((row_left_right("Metodo di pagamento:", f"{payment_method}", width) + "\n").encode('cp858', errors='replace'))
    else:
        buf.extend(b'\x1ba\x01') # Center
        buf.extend(b'\x1b!\x08') # Bold
        buf.extend(b'NON PAGATO\n')
        buf.extend(b'\x1b!\x00') # Normal
        buf.extend(b'\x1ba\x00') # Left

    # Footer (modular from receipt_template.py)
    now = datetime.datetime.now(ROME_TZ)
    buf.extend(receipt_template.build_bill_footer(order_id, now=now, paper_width=paper_width))

    # Feed and cut
    buf.extend(b'\x1dV\x41\x03') # GS V 65 3

    return bytes(buf)

def print_bill(order_id: int, payload: dict, lock_acquired: bool = False):
    active_user_id = payload.get('user_id', 1)
    user_settings = get_user_settings(active_user_id)

    conn_type = user_settings.get("printer_connection_type", "network") if user_settings else "network"
    paper_width = user_settings.get("printer_paper_width", "80mm") if user_settings else "80mm"

    raw_escpos_bytes = generate_bill_escpos(order_id, payload, paper_width=paper_width)
    raw_b64 = base64.b64encode(raw_escpos_bytes).decode('ascii')

    extra_meta = {
        "is_bluetooth": (conn_type == "bluetooth"),
        "escpos_base64": raw_b64,
        "paper_width": paper_width
    }

    if conn_type == "bluetooth":
        return True, "Scontrino pronto per invio Bluetooth", extra_meta

    protocol = "escpos"
    printer_ip = None
    if user_settings:
        protocol = user_settings.get("printer_protocol", "escpos")
        printer_ip = user_settings.get("printer_ip")

    if not printer_ip:
        printer_ip = "10.0.0.200"

    port = 9100

    if protocol == "xon/xoff":
        print("XON/XOFF protocol selected. Printing bypassed.")
        return False, "Protocollo XON/XOFF non supportato", extra_meta

    try:
        lock = None
        if not lock_acquired:
            lock = get_printer_lock(printer_ip)
            acquired = lock.acquire(timeout=5)
            if not acquired:
                return False, "Stampante occupata da troppo tempo. Riprova.", extra_meta

        try:
            p = Network(printer_ip, port, profile="KR-306", timeout=2.0)

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA", extra_meta
            except Exception:
                pass

            p._raw(raw_escpos_bytes)

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA", extra_meta
            except Exception:
                pass

            p.close()
            return True, "Scontrino stampato correttamente", extra_meta
        finally:
            if lock:
                lock.release()
    except Exception as e:
        print(f"Error printing bill: {e}")
        return False, f"Errore stampante scontrini: {str(e)}", extra_meta

def print_production_ticket(order_id: int, items: list, ticket_title: str, printer_ip: str, protocol: str, payload_meta: dict, lock_acquired: bool = False):
    """
    Prints a preparation ticket (e.g. Cucina or Bevande) to a specific network printer.
    All items assigned to this destination are grouped in a single bill.
    """
    if not items:
        return True, "Nessun articolo per questa stampante"

    if protocol == "xon/xoff":
        print(f"XON/XOFF protocol selected for {ticket_title}. Printing bypassed.")
        return False, "Protocollo XON/XOFF non supportato"

    if not printer_ip:
        printer_ip = "10.0.0.200"

    port = 9100

    try:
        lock = None
        if not lock_acquired:
            lock = get_printer_lock(printer_ip)
            acquired = lock.acquire(timeout=30)
            if not acquired:
                return False, f"Stampante {ticket_title} occupata da troppo tempo. Riprova."

        try:
            p = Network(printer_ip, port, profile="KR-306", timeout=2.0)

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA"
            except Exception:
                pass

            p._raw(b'\x1b\x74\x13') # CP 858

            # Group identical items
            grouped = []
            for item in items:
                desc = item.get('description', '')
                combo_choices = item.get('combo_choices', '')
                notes = item.get('notes', '')
                ingredients = item.get('ingredients', '')

                is_groupable = not combo_choices and not notes and not ingredients

                if is_groupable:
                    found = False
                    for g in grouped:
                        if g['groupable'] and g['description'] == desc:
                            g['qty'] += item.get('qty', 1)
                            found = True
                            break
                    if not found:
                        grouped.append({
                            'groupable': True,
                            'description': desc,
                            'qty': item.get('qty', 1),
                            'combo_choices': '',
                            'notes': '',
                            'ingredients': ''
                        })
                else:
                    grouped.append({
                        'groupable': False,
                        'description': desc,
                        'qty': item.get('qty', 1),
                        'combo_choices': combo_choices,
                        'notes': notes,
                        'ingredients': ingredients
                    })

            # Ticket Header
            p.set(align="center", bold=True, double_height=True, double_width=True)
            p.text(f"ORDINE {order_id:03d}\n")
            p.set(align="center", normal_textsize=True)
            now = datetime.datetime.now(ROME_TZ)
            p.text(f"{now.strftime('%d-%m-%Y %H:%M')}\n")
            p.text("-" * 48 + "\n")

            takeaway = payload_meta.get('takeaway', False)
            table = payload_meta.get('table_number', 'Nessuno')
            if takeaway:
                p.set(align="center", bold=True, double_height=True)
                p.text(">>> ASPORTO <<<\n")
                p.set(normal_textsize=True)
                p.text("-" * 48 + "\n")
            elif table and str(table).lower() != 'nessuno':
                p.set(align="center", bold=True, double_height=True)
                p.text(f"TAVOLO {table}\n")
                p.set(normal_textsize=True)
                p.text("-" * 48 + "\n")

            # Ticket Category Header
            if ticket_title:
                p.set(align="center", bold=True)
                p.text(f"*** {ticket_title.upper()} ***\n")
                p.set(normal_textsize=True, bold=False)
                p.text("-" * 48 + "\n")

            # Item Lines
            p.set(align="left")
            for item in grouped:
                desc = item['description'].upper()
                qty = item['qty']
                p.set(bold=True, double_height=True)
                p.text(f"{qty} {desc}\n")
                p.set(normal_textsize=True, bold=False)

                if item.get('combo_choices'):
                    for sub in item['combo_choices'].split(','):
                        sub_clean = sub.strip()
                        if sub_clean:
                            p.text("  - " + sub_clean + "\n")
                if item.get('ingredients'):
                    p.text("  [Ingr: " + item['ingredients'] + "]\n")
                if item.get('notes'):
                    p.text("  *Nota: " + item['notes'] + "\n")

            p.text("-" * 48 + "\n")

            order_notes = payload_meta.get('notes', '')
            if order_notes:
                p.set(bold=True)
                p.text("NOTE ORDINE:\n")
                p.set(bold=False)
                p.text(order_notes + "\n")
                p.text("-" * 48 + "\n")

            p.cut()

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA"
            except Exception:
                pass

            p.close()
            return True, f"Comanda {ticket_title} stampata correttamente"
        finally:
            if lock:
                lock.release()
    except Exception as e:
        print(f"Error printing {ticket_title} receipt: {e}")
        return False, f"Errore stampante {ticket_title}: {str(e)}"

def print_kitchen_receipt(order_id: int, payload: dict, lock_acquired: bool = False):
    settings = get_system_settings()
    k_ip = settings.get("kitchen_printer_ip", "10.0.0.200") if settings else "10.0.0.200"
    k_proto = settings.get("kitchen_printer_protocol", "escpos") if settings else "escpos"

    kitchen_items, _ = categorize_order_items(payload)
    if not kitchen_items:
        return True, "Nessun articolo per cucina"

    return print_production_ticket(
        order_id=order_id,
        items=kitchen_items,
        ticket_title="CUCINA",
        printer_ip=k_ip,
        protocol=k_proto,
        payload_meta=payload,
        lock_acquired=lock_acquired
    )

def print_bar_receipt(order_id: int, payload: dict, lock_acquired: bool = False):
    settings = get_system_settings()
    b_ip = settings.get("bar_printer_ip", "10.0.0.200") if settings else "10.0.0.200"
    b_proto = settings.get("bar_printer_protocol", "escpos") if settings else "escpos"

    _, bar_items = categorize_order_items(payload)
    if not bar_items:
        return True, "Nessun articolo per bevande"

    return print_production_ticket(
        order_id=order_id,
        items=bar_items,
        ticket_title="BEVANDE",
        printer_ip=b_ip,
        protocol=b_proto,
        payload_meta=payload,
        lock_acquired=lock_acquired
    )
