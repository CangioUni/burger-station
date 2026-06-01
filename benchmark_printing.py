import time
from unittest.mock import patch, MagicMock
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.abspath('.'))

import main
import printing
from sqlalchemy.orm import Session

# Setup mock data if not exists
db = main.SessionLocal()
if not db.query(main.SystemSettings).first():
    db.add(main.SystemSettings(id=1, kitchen_printer_protocol="escpos", kitchen_printer_ip="127.0.0.1"))
    db.commit()

# Add a bunch of bibite to make query heavier
existing_bibite = db.query(main.MenuItem).filter(main.MenuItem.category == "bibite").count()
if existing_bibite < 50:
    for i in range(50):
        db.add(main.MenuItem(description=f"Bibite Test {i}", category="bibite", is_active=True))
    db.commit()

payload = {
    "items": [
        {"description": "Menu Classico", "category": "menu", "combo_choices": "Bibite Test 1,Bibite Test 2"},
        {"description": "Bibite Test 3", "category": "bibite"},
        {"description": "Panino Classico", "category": "panini"}
    ],
    "table_number": "5",
    "takeaway": False
}
db.close()

def run_benchmark():
    # Mock Network
    with patch('printing.Network') as mock_network:
        mock_p = MagicMock()
        mock_network.return_value = mock_p
        mock_p.paper_status.return_value = 2 # Has paper

        start = time.time()
        for i in range(200):
            printing.print_kitchen_receipt(i, payload)
        end = time.time()

    print(f"Time taken for 200 kitchen receipts: {end - start:.4f} seconds")

if __name__ == "__main__":
    run_benchmark()
