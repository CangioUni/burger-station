import re

with open('main.py', 'r') as f:
    content = f.read()

# 1. Menu manipulations: invalidate_menu_cache()
content = re.sub(
    r'(def update_menu_item.*?\n.*?db\.commit\(\))',
    r'\1\n    printing.invalidate_menu_cache()',
    content,
    flags=re.DOTALL
)
content = re.sub(
    r'(def delete_menu_item.*?\n.*?db\.commit\(\))',
    r'\1\n        printing.invalidate_menu_cache()',
    content,
    flags=re.DOTALL
)
content = re.sub(
    r'(def create_menu_item.*?\n.*?db\.commit\(\))',
    r'\1\n    printing.invalidate_menu_cache()',
    content,
    flags=re.DOTALL
)
content = re.sub(
    r'(def import_menu_json.*?\n.*?db\.commit\(\))',
    r'\1\n        printing.invalidate_menu_cache()',
    content,
    flags=re.DOTALL
)

# 2. Settings manipulations: invalidate_settings_cache()
content = re.sub(
    r'(def update_settings.*?\n.*?db\.commit\(\))',
    r'\1\n        printing.invalidate_settings_cache()',
    content,
    flags=re.DOTALL
)

# 3. User manipulations: invalidate_user_cache()
content = re.sub(
    r'(def update_user_cart.*?user = db\.query.*?if user:.*?db\.commit\(\))',
    r'\1\n        printing.invalidate_user_cache(user_id)',
    content,
    flags=re.DOTALL
)

with open('main.py', 'w') as f:
    f.write(content)
