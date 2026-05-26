import datetime
import threading
from zoneinfo import ZoneInfo
from escpos.printer import Network

printer_lock = threading.Lock()

ROME_TZ = ZoneInfo("Europe/Rome")

# These will be injected by main.py at startup to avoid circular imports
SessionLocal = None
User = None
SystemSettings = None
MenuItem = None

def init(session_local, user_model, settings_model, menu_item_model):
    """Called once from main.py to inject DB dependencies."""
    global SessionLocal, User, SystemSettings, MenuItem
    SessionLocal = session_local
    User = user_model
    SystemSettings = settings_model
    MenuItem = menu_item_model

# Build line with splitted text aligned left and right
def row_left_right(label: str, value: str, width: int = 48) -> str:
    """Return a left/right aligned string padded to `width` characters."""
    spaces = width - len(label) - len(value)
    return label + " " * max(spaces, 1) + value


def print_bill(order_id: int, payload: dict):
    db = SessionLocal()
    
    # We pass the active user_id inside payload from frontend to find out who printed it
    active_user_id = payload.get('user_id', 1)
    user = db.query(User).filter(User.id == active_user_id).first()
    settings = db.query(SystemSettings).first()
    db.close()
    
    # Retrieve correct protocol
    protocol = "escpos"
    if user:
        protocol = user.printer_protocol
        printer_ip = user.printer_ip

    if not printer_ip:
        printer_ip = "10.0.0.200"

    port = 9100

    if protocol == "xon/xoff":
        # TODO: Implement XON/XOFF printing
        print("XON/XOFF protocol selected. Printing bypassed.")
        return False, "Protocollo XON/XOFF non supportato"

    
    try:
        with printer_lock:
            p = Network(printer_ip, port, profile="KR-306", timeout=2.0)

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA"
            except Exception as e:
                pass

            #p._raw(b'\x1b\x74\x13') # CP 858
            p.charcode('CP858')

            # Add optional logo to start of receipt if available - make sure it's a 384px wide monochrome PNG for best results
            # try:
            #     p.image("rblogo.png", center=True)
            # except Exception as e:
            #     print(f"Logo print error: {e}")
            #     pass

            # Group header
            p.set(align="center", bold=True, normal_textsize=True)
            p.text("Restaurant\nAND ITS NAME\n")
            p.set(align="center", bold=False)
            p.text("Location\nRest of location\n\n")

            p.set(align="center", bold=True, double_height=True, double_width=True)
            p.text(f"ORDINE {order_id:03d}\n\n")

            # Column header
            p._raw(b'\x1b\x74\x13') # Select table 19 (CP858)
            p.set(align="left", double_height=True)
            # header = row_left_right("DESCRIZIONE", "Prezzo (€)", 48)
            # p.text(header + "\n\n")
            p._raw(b'DESCRIZIONE                           Prezzo (\xd5)\n\n')
            p.set(align="left", normal_textsize=True)
            
            # Line items
            # p.set(align="left")

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
                print(f"Description: {desc}, Discount: {discount}")
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
                print(f"Description: {desc}, Discount: {item_discount}")

                base_item_total = price * qty
                discount_amount = 0
                if item_discount > 0:
                    if item_discount_type == '%':
                        discount_amount = base_item_total * (item_discount / 100)
                    else:
                        discount_amount = item_discount

                # The net total for the item
                item_total = base_item_total - discount_amount
                if item_total < 0:
                    item_total = 0

                gross_total += item_total

                if qty > 1:
                    p.text(f"{qty} x {price:.2f}".replace('.', ',') + "\n")
                    p.text(row_left_right(desc, f"{base_item_total:.2f}".replace('.', ','), 48) + "\n")
                else:
                    p.text(row_left_right(desc, f"{price:.2f}".replace('.', ','), 48) + "\n")

                if item_discount > 0:
                    if item_discount_type == '%':
                        discount_label = f"SCONTO {int(item_discount)}%" if item_discount.is_integer() else f"SCONTO {item_discount:.2f}%"
                    else:
                        discount_label = "SCONTO"
                    discount_val_str = f"-{discount_amount:.2f}".replace('.', ',')
                    p.text(row_left_right("  " + discount_label, discount_val_str, 48) + "\n")

                combo_choices = item['combo_choices']
                if combo_choices:
                    for sub in combo_choices.split(','):
                        sub_clean = sub.strip()
                        if sub_clean:
                            p.text(" - " + sub_clean + "\n")

            # Separator
            p.text("-" * 48 + "\n")

            # Totals
            overall_discount = payload.get('discount', 0)

            if overall_discount > 0:
                p.set(align="left", double_height=False)
                subtotal_str = f"{gross_total:.2f}".replace('.', ',')
                p.text(row_left_right("SUBTOTALE", subtotal_str, 48) + "\n")

                discount_str = f"-{overall_discount:.2f}".replace('.', ',')
                p.text(row_left_right("SCONTO", discount_str, 48) + "\n")
                p.text("-" * 48 + "\n")

                net_total = gross_total - overall_discount
                if net_total < 0:
                    net_total = 0
            else:
                net_total = gross_total

            p.set(align="left", double_height=True)
            total_str = f"{net_total:.2f}".replace('.', ',')
            p.text(row_left_right("TOTALE COMPLESSIVO", total_str, 48) + "\n")
            p.set(normal_textsize=True)

            payment_status = payload.get('payment_status', True)
            payment_method = payload.get('payment_method', '')

            p.text("\n")
            if payment_status:
                # p.set(align="center", bold=True, double_height=True)
                # p.text("PAGATO\n")
                # p.set(normal_textsize=True)
                if payment_method:
                    p.text(row_left_right("Metodo di pagamento:", f"{payment_method}", 48) + "\n")
            else:
                p.set(align="center", bold=True, double_height=False)
                p.text("NON PAGATO\n")
                p.set(normal_textsize=True)


            # Footer
            p.set(align="center")
            now = datetime.datetime.now(ROME_TZ)
            p.text(f"\n{now.strftime('%d-%m-%Y  %H:%M')}\n")
            p.text(f"DOCUMENTO N. {order_id:03d}\n\nSCONTRINO NON FISCALE\n\n")

            p.cut()

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA"
            except Exception as e:
                pass

            p.close()
            return True, "Scontrino stampato correttamente"
    except Exception as e:
        print(f"Error printing bill: {e}")
        return False, f"Errore stampante scontrini: {str(e)}"


def print_kitchen_receipt(order_id: int, payload: dict):
    db = SessionLocal()
    settings = db.query(SystemSettings).first()
    db.close()

    if settings and settings.kitchen_printer_protocol == "xon/xoff":
        print("XON/XOFF protocol selected. Kitchen printing bypassed.")
        return False, "Protocollo XON/XOFF non supportato"

    printer_ip = settings.kitchen_printer_ip if settings and settings.kitchen_printer_ip else "10.0.0.200"
    port = 9100

    try:
        with printer_lock:
            p = Network(printer_ip, port, profile="KR-306", timeout=2.0)

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA"
            except Exception as e:
                pass

            p._raw(b'\x1b\x74\x13') # CP 858

            # Group similar items (excluding bibite)
            grouped_items = []
            for item in payload.get('items', []):
                desc = item.get('description', '')
                combo_choices = item.get('combo_choices', '')
                notes = item.get('notes', '')
                ingredients = item.get('ingredients', '')

                category = item.get('category', '')
                if category == 'bibite':
                    continue

                is_groupable = not combo_choices and not notes and not ingredients

                if is_groupable:
                    found = False
                    for g in grouped_items:
                        if g['groupable'] and g['description'] == desc:
                            g['qty'] += 1
                            found = True
                            break
                    if not found:
                        grouped_items.append({
                            'groupable': True, 'description': desc,
                            'qty': 1, 'combo_choices': '', 'notes': '', 'ingredients': ''
                        })
                else:
                    grouped_items.append({
                        'groupable': False, 'description': desc,
                        'qty': 1, 'combo_choices': combo_choices, 'notes': notes, 'ingredients': ingredients
                    })

            # Only print the first kitchen bill if there are non-bibite items
            if grouped_items:
                p.set(align="center", bold=True, double_height=True, double_width=True)
                p.text(f"ORDINE {order_id:03d}\n")
                p.set(align="center", normal_textsize=True)
                now = datetime.datetime.now(ROME_TZ)
                p.text(f"{now.strftime('%d-%m-%Y %H:%M')}\n")
                p.text("-" * 48 + "\n")

                takeaway = payload.get('takeaway', False)
                table = payload.get('table_number', 'Nessuno')
                if takeaway:
                    p.set(align="center", bold=True, double_height=True)
                    p.text(">>> ASPORTO <<<\n")
                    p.set(normal_textsize=True)
                    p.text("-" * 48 + "\n")
                elif table and table.lower() != 'nessuno':
                    p.set(align="center", bold=True, double_height=True)
                    p.text(f"TAVOLO {table}\n")
                    p.set(normal_textsize=True)
                    p.text("-" * 48 + "\n")

                p.set(align="left")

                for item in grouped_items:
                    desc = item['description'].upper()
                    qty = item['qty']
                    p.set(bold=True, double_height=True)
                    p.text(f"{qty} {desc}\n")
                    p.set(normal_textsize=True, bold=False)

                    if item['combo_choices']:
                        for sub in item['combo_choices'].split(','):
                            sub_clean = sub.strip()
                            if sub_clean:
                                p.text("  - " + sub_clean + "\n")
                    if item['ingredients']:
                        p.text("  [Ingr: " + item['ingredients'] + "]\n")
                    if item['notes']:
                        p.text("  *Nota: " + item['notes'] + "\n")

                p.text("-" * 48 + "\n")
                notes = payload.get('notes', '')
                if notes:
                    p.set(bold=True)
                    p.text("NOTE ORDINE:\n")
                    p.set(bold=False)
                    p.text(notes + "\n")
                    p.text("-" * 48 + "\n")

                p.cut()


            # ===============================================
            # Print second bill with "bibite" only
            # This includes standalone bibite AND bibite extracted from combo_choices

            # Build a set of all bibite item names from the DB
            db2 = SessionLocal()
            bibite_names = set()
            try:
                bibite_items = db2.query(MenuItem).filter(MenuItem.category == 'bibite', MenuItem.is_active == True).all()
                for bi in bibite_items:
                    bibite_names.add(bi.description)
            finally:
                db2.close()

            # Collect all bibite: standalone items + extracted from combo_choices
            bibite_list = []
            for item in payload.get('items', []):
                category = item.get('category', '')
                desc = item.get('description', '')
                combo_choices = item.get('combo_choices', '')

                # Case 1: standalone bibite item
                if category == 'bibite':
                    bibite_list.append(desc)

                # Case 2: combo item with choices that might be bibite
                if combo_choices:
                    for choice in combo_choices.split(','):
                        choice_clean = choice.strip()
                        if choice_clean and choice_clean in bibite_names:
                            bibite_list.append(choice_clean)

            # Group identical bibite
            grouped_bibite = {}
            for name in bibite_list:
                grouped_bibite[name] = grouped_bibite.get(name, 0) + 1

            # Only print this bill if there are actually bibite items
            if grouped_bibite:
                p.set(align="center", bold=True, double_height=True, double_width=True)
                p.text(f"ORDINE {order_id:03d}\n")
                p.set(align="center", normal_textsize=True)
                now = datetime.datetime.now(ROME_TZ)
                p.text(f"{now.strftime('%d-%m-%Y %H:%M')}\n")
                p.text("-" * 48 + "\n")

                takeaway = payload.get('takeaway', False)
                table = payload.get('table_number', 'Nessuno')
                if takeaway:
                    p.set(align="center", bold=True, double_height=True)
                    p.text(">>> ASPORTO <<<\n")
                    p.set(normal_textsize=True)
                    p.text("-" * 48 + "\n")
                elif table and table.lower() != 'nessuno':
                    p.set(align="center", bold=True, double_height=True)
                    p.text(f"TAVOLO {table}\n")
                    p.set(normal_textsize=True)
                    p.text("-" * 48 + "\n")

                p.set(align="left")

                for name, qty in grouped_bibite.items():
                    p.set(bold=True, double_height=True)
                    p.text(f"{qty} {name.upper()}\n")
                    p.set(normal_textsize=True, bold=False)

                p.cut()

            try:
                if p.paper_status() == 0:
                    p.close()
                    return False, "CARTA ESAURITA"
            except Exception as e:
                pass

            p.close()
            return True, "Comanda cucina stampata correttamente"

    except Exception as e:
        print(f"Error printing kitchen receipt: {e}")
        return False, f"Errore stampante cucina: {str(e)}"
