import re

with open('printing.py', 'r') as f:
    content = f.read()

# Replace db query for user and settings in print_bill
# Find:
"""
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
"""
# Replace with:
content = re.sub(
    r'    db = SessionLocal\(\)\n    \n    # We pass the active user_id inside payload from frontend to find out who printed it\n    active_user_id = payload\.get\(\'user_id\', 1\)\n    user = db\.query\(User\)\.filter\(User\.id == active_user_id\)\.first\(\)\n    settings = db\.query\(SystemSettings\)\.first\(\)\n    db\.close\(\)\n    \n    # Retrieve correct protocol\n    protocol = "escpos"\n    if user:\n        protocol = user\.printer_protocol\n        printer_ip = user\.printer_ip',
    r'    # We pass the active user_id inside payload from frontend to find out who printed it\n    active_user_id = payload.get(\'user_id\', 1)\n    user_settings = get_user_settings(active_user_id)\n    \n    # Retrieve correct protocol\n    protocol = "escpos"\n    printer_ip = None\n    if user_settings:\n        protocol = user_settings.get("printer_protocol", "escpos")\n        printer_ip = user_settings.get("printer_ip")',
    content
)

with open('printing.py', 'w') as f:
    f.write(content)
