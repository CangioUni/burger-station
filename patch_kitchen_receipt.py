import re

with open('printing.py', 'r') as f:
    content = f.read()

# 1. Replace db query for settings
# Find:
"""
    db = SessionLocal()
    settings = db.query(SystemSettings).first()
    db.close()

    if settings and settings.kitchen_printer_protocol == "xon/xoff":
"""
# Replace with get_system_settings()
content = re.sub(
    r'    db = SessionLocal\(\)\n    settings = db.query\(SystemSettings\).first\(\)\n    db.close\(\)\n\n    if settings and settings.kitchen_printer_protocol == "xon/xoff":',
    r'    settings = get_system_settings()\n\n    if settings and settings.get("kitchen_printer_protocol") == "xon/xoff":',
    content
)

content = re.sub(
    r'printer_ip = settings.kitchen_printer_ip if settings and settings.kitchen_printer_ip else "10.0.0.200"',
    r'printer_ip = settings.get("kitchen_printer_ip") if settings and settings.get("kitchen_printer_ip") else "10.0.0.200"',
    content
)

# 2. Replace db query for bibite
# Find:
"""
            # Build a set of all bibite item names from the DB
            db2 = SessionLocal()
            bibite_names = set()
            try:
                bibite_items = db2.query(MenuItem).filter(MenuItem.category == 'bibite', MenuItem.is_active == True).all()
                for bi in bibite_items:
                    bibite_names.add(bi.description)
            finally:
                db2.close()
"""
# Replace with get_bibite_names()
content = re.sub(
    r'            # Build a set of all bibite item names from the DB\n            db2 = SessionLocal\(\)\n            bibite_names = set\(\)\n            try:\n                bibite_items = db2.query\(MenuItem\).filter\(MenuItem.category == \'bibite\', MenuItem.is_active == True\).all\(\)\n                for bi in bibite_items:\n                    bibite_names.add\(bi.description\)\n            finally:\n                db2.close\(\)',
    r'            # Fetch bibite names from cache\n            bibite_names = get_bibite_names()',
    content
)

with open('printing.py', 'w') as f:
    f.write(content)
