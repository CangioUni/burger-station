# Burger Station POS

## Introduction
Burger Station POS is a lightweight, fully localized web-based Point of Sale (POS) system built using a Python backend (`FastAPI`/`SQLAlchemy`) and a touch-responsive vanilla JavaScript/TailwindCSS frontend. It operates on a decoupled ledger architecture, ensuring that historical orders accurately preserve item prices, ingredients, and modifiers regardless of future modifications to the live menu. 

## How to Run
The software requires Python 3.x and relies on pip packages defined in `requirements.txt`.

**1. Configure the Virtual Environment:**
```bash
python -m venv .venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Dependencies:**
Sending data to ESC/POS printer makes use of https://github.com/python-escpos library. For printer profile, look at (available-profiles)[https://python-escpos.readthedocs.io/en/latest/printer_profiles/available-profiles.html]

**3. Start the Application Server:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
*The POS interface will now be accessible locally at `http://localhost:8000` via your web browser.*

## Main Functions
- **Dynamic Cart Interface**: Tablet-optimized layout featuring visual item grids, rapid discount integrations via touch-numpads, and dynamic takeaway/table configurations.
- **Persistent Order State**: Employs real-time `localStorage` tracking preventing total data loss during abrupt network disconnections or hardware crashes.
- **Menu & Category Editor**: Accessible via the `Editor Menu` button, granting live Create/Read/Update/Delete (CRUD) capabilities mapping directly to the SQLite backend.
- **Historical Order Ledger**: Dedicated `Ultimi Ordini` dashboard unpacking chronological data streams of previous checkouts dynamically.
- **PDF Export Generator**: Native hook natively converting transaction history directly into structured `.pdf` reports via `fpdf2`.
- **Decoupled Architecture**: Old transactions log raw textual strings and precise monetary values at the point-of-sale, preventing historical distortions.

## Roadmap
- **Kitchen Display Screen (KDS)**: Direct web-socket routing to a dedicated `kitchen.html` dashboard for cook-line tracking.
- **Direct Receipt Printing**: Advanced ESP/POS integrations seamlessly pushing payloads natively to standard thermal network printers (Epson, Star Micronics).
- **Employee Hierarchy Pins**: Administrative login checks locking the ledger delete queries behind manager passwords.
- **Advanced Graphical Reports**: Injecting lightweight Chart.js dashboards inside the Orders ledger rendering heatmap charts for peak sales times.
