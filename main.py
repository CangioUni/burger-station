from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, or_, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import text
from sqlalchemy import inspect
from escpos.printer import Network
from stats_exporter import StatsExporter
from fpdf import FPDF
import datetime
from zoneinfo import ZoneInfo
import socket
import asyncio
import time
import json
import threading
import os

ROME_TZ = ZoneInfo("Europe/Rome")
import printing
from printing import print_bill, print_kitchen_receipt, row_left_right

DATABASE_URL = "sqlite:///./orders.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 15})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    printer_ip = Column(String)
    active_cart = Column(String, default="[]")
    active_state = Column(String, default="{}")
    auto_print_main = Column(Boolean, default=True)
    printer_protocol = Column(String, default="escpos")
    printer_connection_type = Column(String, default="network")
    printer_paper_width = Column(String, default="80mm")

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    sort_order = Column(Integer, default=0)
    printer_target = Column(String, default="cucina")

class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True)
    description = Column(String)
    price = Column(Float)
    image_url = Column(String)
    category = Column(String, default="burgers")
    components = Column(String, default="")
    additions = Column(String, default="")
    is_combo = Column(Boolean, default=False)
    combo_items = Column(String, default="[]")
    is_active = Column(Boolean, default=True)
    max_items = Column(Integer, nullable=True)
    ordered_count = Column(Integer, default=0)
    sort_order = Column(Integer, default=0)

class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True)
    bill_printer_ip = Column(String)
    kitchen_printer_ip = Column(String)
    auto_print = Column(Boolean, default=True)
    next_order_number = Column(Integer, default=1)
    auto_print_kitchen = Column(Boolean, default=True)
    kitchen_printer_protocol = Column(String, default="escpos")
    bar_printer_ip = Column(String, default="10.0.0.200")
    bar_printer_protocol = Column(String, default="escpos")
    auto_print_bar = Column(Boolean, default=True)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_number = Column(String, default="")
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(ROME_TZ))
    total = Column(Float)
    discount = Column(Float)
    payment_method = Column(String)
    payment_status = Column(Boolean, default=False)
    payment_datetime = Column(DateTime, nullable=True)
    takeaway = Column(Boolean)
    table_number = Column(String)
    user_id = Column(Integer, ForeignKey('users.id'))
    notes = Column(String, default="")
    items = relationship("OrderItem", backref="order")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    description = Column(String)
    quantity = Column(Integer)
    price_at_sale = Column(Float)
    notes = Column(String)
    ingredients = Column(String)
    combo_choices = Column(String, default="")
    discount = Column(Float, default=0.0)
    discount_type = Column(String, default="%")

Base.metadata.create_all(bind=engine)

# Add is_active column if it doesn't exist
db = SessionLocal()
try:
    db.execute(text("ALTER TABLE menu_items ADD COLUMN is_active BOOLEAN DEFAULT 1"))
    db.commit()
except Exception:
    db.rollback()
finally:
    db.close()


try:
    db = SessionLocal()
    db.execute(text("ALTER TABLE order_items ADD COLUMN discount FLOAT DEFAULT 0.0"))
    db.commit()
except Exception:
    db.rollback()
finally:
    db.close()

try:
    db = SessionLocal()
    db.execute(text("ALTER TABLE order_items ADD COLUMN discount_type VARCHAR DEFAULT '%'"))
    db.commit()
except Exception:
    db.rollback()
finally:
    db.close()

# Add column 'additions' if missing
inspector = inspect(engine)
if "menu_items" in inspector.get_table_names():
    columns = [c["name"] for c in inspector.get_columns("menu_items")]
    if "additions" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE menu_items ADD COLUMN additions VARCHAR DEFAULT ''"))
    if "max_items" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE menu_items ADD COLUMN max_items INTEGER"))
    if "ordered_count" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE menu_items ADD COLUMN ordered_count INTEGER DEFAULT 0"))
    if "sort_order" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE menu_items ADD COLUMN sort_order INTEGER DEFAULT 0"))

if "categories" in inspector.get_table_names():
    cat_columns = [c["name"] for c in inspector.get_columns("categories")]
    with engine.begin() as conn:
        if "sort_order" not in cat_columns:
            conn.execute(text("ALTER TABLE categories ADD COLUMN sort_order INTEGER DEFAULT 0"))
        if "printer_target" not in cat_columns:
            conn.execute(text("ALTER TABLE categories ADD COLUMN printer_target VARCHAR DEFAULT 'cucina'"))
            conn.execute(text("UPDATE categories SET printer_target = 'bevande' WHERE LOWER(name) IN ('bibite', 'bevande', 'bar', 'drink', 'drinks')"))

if "system_settings" in inspector.get_table_names():
    ss_columns = [c["name"] for c in inspector.get_columns("system_settings")]
    with engine.begin() as conn:
        if "next_order_number" not in ss_columns:
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN next_order_number INTEGER DEFAULT 1"))
        if "auto_print_kitchen" not in ss_columns:
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN auto_print_kitchen BOOLEAN DEFAULT 1"))
        if "kitchen_printer_protocol" not in ss_columns:
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN kitchen_printer_protocol VARCHAR DEFAULT 'escpos'"))
        if "bar_printer_ip" not in ss_columns:
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN bar_printer_ip VARCHAR DEFAULT '10.0.0.200'"))
        if "bar_printer_protocol" not in ss_columns:
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN bar_printer_protocol VARCHAR DEFAULT 'escpos'"))
        if "auto_print_bar" not in ss_columns:
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN auto_print_bar BOOLEAN DEFAULT 1"))

if "users" in inspector.get_table_names():
    user_columns = [c["name"] for c in inspector.get_columns("users")]
    with engine.begin() as conn:
        if "active_cart" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN active_cart VARCHAR DEFAULT '[]'"))
        if "active_state" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN active_state VARCHAR DEFAULT '{}'"))
        if "auto_print_main" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN auto_print_main BOOLEAN DEFAULT 1"))
        if "printer_protocol" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN printer_protocol VARCHAR DEFAULT 'escpos'"))
        if "printer_connection_type" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN printer_connection_type VARCHAR DEFAULT 'network'"))
        if "printer_paper_width" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN printer_paper_width VARCHAR DEFAULT '80mm'"))

if "orders" in inspector.get_table_names():
    order_columns = [c["name"] for c in inspector.get_columns("orders")]
    with engine.begin() as conn:
        if "order_number" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN order_number VARCHAR DEFAULT ''"))
            conn.execute(text("UPDATE orders SET order_number = CAST(id AS VARCHAR) WHERE order_number = ''"))
        if "payment_status" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN payment_status BOOLEAN DEFAULT 1"))
        if "payment_datetime" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN payment_datetime DATETIME"))



# --- Initial Seeding ---
db = SessionLocal()
if not db.query(User).first():
    db.add_all([User(id=i, name=f"Staff {i}", printer_ip=f"192.168.1.10{i}") for i in range(1, 6)])
    db.add_all([
        Category(name="menu"),
        Category(name="panini"),
        Category(name="contorni"),
        Category(name="bibite"),
        Category(name="dolci")
    ])
    # For local images, replace 'https://placehold.co/...' with '/static/images/your_file.jpg'
    db.add_all([
        MenuItem(description="Panino Classico", price=9.00, image_url="/static/images/burger_classico.png", category="panini", components="Pane,Hamburger,Pomodoro,Insalata"),
        MenuItem(description="Panino Sportivo", price=9.00, image_url="https://placehold.co/400x300?text=Panino+Sportivo", category="panini", components="Pane,Cotoletta,Pomodoro,Insalata"),
        MenuItem(description="Panino Leggero", price=7.00, image_url="https://placehold.co/400x300?text=Panino+Leggero", category="panini", components="Pane,Hamburger Vegetale,Pomodoro,Insalata"),
        MenuItem(description="Menu Classico", price=14.00, image_url="https://placehold.co/400x300?text=Menu+Classico", category="menu", is_combo=True, combo_items='[["Panino Classico"], ["Patatine"], ["Coca Cola", "Birra", "Acqua"]]'),
        MenuItem(description="Menu Sportivo", price=14.00, image_url="https://placehold.co/400x300?text=Menu+Sportivo", category="menu", is_combo=True, combo_items='[["Panino Sportivo"], ["Patatine"], ["Coca Cola", "Birra", "Acqua"]]'),
        MenuItem(description="Menu Leggero", price=12.00, image_url="https://placehold.co/400x300?text=Menu+Supereroe", category="menu", is_combo=True, combo_items='[["Panino Leggero"], ["Patatine"], ["Coca Cola", "Birra", "Acqua"]]'),
        MenuItem(description="Patatine", price=4.00, image_url="https://placehold.co/400x300?text=Patatine", category="contorni", components=""),
        MenuItem(description="Acqua Nat", price=1.00, image_url="/static/images/acqua.png", category="bibite", components=""),
        MenuItem(description="Acqua Gas", price=1.00, image_url="/static/images/acqua.png", category="bibite", components=""),
        MenuItem(description="Coca Cola", price=3.00, image_url="/static/images/cola.png", category="bibite", components=""),
        MenuItem(description="Birra", price=4.00, image_url="/static/images/birra.png", category="bibite", components=""),
        MenuItem(description="Donut", price=5.00, image_url="/static/images/donut.png", category="dolci", components="")
    ])
    settings = SystemSettings(id=1, bill_printer_ip="10.0.0.200", kitchen_printer_ip="10.0.0.200")
    db.add(settings)
    db.commit()
db.close()

# Initialize printing module (must be after models + DB setup)
printing.init(SessionLocal, User, SystemSettings, MenuItem, Category)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

main_loop = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

# In-memory dictionary to hold display states
display_states = {}
display_states_lock = asyncio.Lock()

async def get_or_create_display_state(user_id: int, db=None) -> dict:
    async with display_states_lock:
        if user_id not in display_states:
            cart_items = []
            subtotal = 0.0
            total = 0.0
            if db:
                user = db.query(User).filter(User.id == user_id).first()
                if user and user.active_cart:
                    try:
                        cart_data = json.loads(user.active_cart)
                        for item in cart_data:
                            desc = item.get("description", "")
                            price = item.get("current_price", item.get("price", 0.0))
                            cart_items.append({"description": desc, "price": price})
                            subtotal += price
                        if user.active_state:
                            state_data = json.loads(user.active_state)
                            disc = state_data.get("discount", 0.0)
                            disc_type = state_data.get("discount_type", "%")
                            if disc_type == '%':
                                discount_amount = subtotal * (disc / 100.0)
                            else:
                                discount_amount = disc
                            total = max(0.0, subtotal - discount_amount)
                        else:
                            total = subtotal
                    except Exception:
                        pass
            display_states[user_id] = {
                "cart": cart_items,
                "subtotal": round(subtotal, 2),
                "total": round(total, 2),
                "order_completed_message": "",
                "version": int(time.time() * 1000),
                "event": asyncio.Event()
            }
        return display_states[user_id]

async def trigger_display_state_change(user_id: int, cart_items: list, subtotal: float, total: float, order_completed_message: str = ""):
    async with display_states_lock:
        if user_id not in display_states:
            display_states[user_id] = {
                "cart": [],
                "subtotal": 0.0,
                "total": 0.0,
                "order_completed_message": "",
                "version": int(time.time() * 1000),
                "event": asyncio.Event()
            }
        
        state = display_states[user_id]
        state["cart"] = cart_items
        state["subtotal"] = round(subtotal, 2)
        state["total"] = round(total, 2)
        state["order_completed_message"] = order_completed_message
        state["version"] = int(time.time() * 1000)
        
        # Notify waiting long pollers
        old_event = state["event"]
        state["event"] = asyncio.Event()
        old_event.set()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

class SettingsUpdate(BaseModel):
    bill_printer_ip: str
    kitchen_printer_ip: str
    auto_print_kitchen: bool
    kitchen_printer_protocol: str
    bar_printer_ip: Optional[str] = "10.0.0.200"
    auto_print_bar: Optional[bool] = True
    bar_printer_protocol: Optional[str] = "escpos"
    next_order_number: int

bancomat_lock = threading.Lock()

@app.post("/pay/bancomat")
def pay_bancomat():
    # Use non-blocking acquire to check if another terminal is already waiting
    acquired = bancomat_lock.acquire(blocking=False)
    if not acquired:
        return {"status": "locked"}

    try:
        # Placeholder for actual bancomat logic. Wait a short time to simulate.
        time.sleep(2)
        return {"status": "success"}
    finally:
        bancomat_lock.release()

@app.get("/settings")
def get_settings():
    db = SessionLocal()
    settings = db.query(SystemSettings).first()
    db.close()
    if settings:
        return {
            "bill_printer_ip": settings.bill_printer_ip or "", 
            "kitchen_printer_ip": settings.kitchen_printer_ip or "", 
            "auto_print_kitchen": settings.auto_print_kitchen if settings.auto_print_kitchen is not None else True, 
            "kitchen_printer_protocol": settings.kitchen_printer_protocol or "escpos",
            "bar_printer_ip": getattr(settings, "bar_printer_ip", "10.0.0.200") or "10.0.0.200",
            "auto_print_bar": getattr(settings, "auto_print_bar", True) if getattr(settings, "auto_print_bar", True) is not None else True,
            "bar_printer_protocol": getattr(settings, "bar_printer_protocol", "escpos") or "escpos",
            "next_order_number": settings.next_order_number or 1
        }
    return {
        "bill_printer_ip": "", 
        "kitchen_printer_ip": "10.0.0.200", 
        "auto_print_kitchen": True, 
        "kitchen_printer_protocol": "escpos",
        "bar_printer_ip": "10.0.0.200",
        "auto_print_bar": True,
        "bar_printer_protocol": "escpos",
        "next_order_number": 1
    }

@app.post("/settings")
def update_settings(payload: SettingsUpdate):
    db = SessionLocal()
    try:
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings(id=1)
            db.add(settings)
        settings.bill_printer_ip = payload.bill_printer_ip
        settings.kitchen_printer_ip = payload.kitchen_printer_ip
        settings.auto_print_kitchen = payload.auto_print_kitchen
        settings.kitchen_printer_protocol = payload.kitchen_printer_protocol
        settings.bar_printer_ip = payload.bar_printer_ip or "10.0.0.200"
        settings.auto_print_bar = payload.auto_print_bar if payload.auto_print_bar is not None else True
        settings.bar_printer_protocol = payload.bar_printer_protocol or "escpos"
        settings.next_order_number = payload.next_order_number
        db.commit()
        printing.invalidate_settings_cache()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/test-printer")
def test_printer(ip: str, port: int = 9100):
    try:
        p = Network(ip, int(port), timeout=3.0)
        try:
            status = p.paper_status()
            p.close()
            if status == 2:
                return {"status": "success", "message": f"Stampante raggiungibile su {ip}:{port}. Carta adeguata."}
            elif status == 1:
                return {"status": "success", "message": f"Stampante raggiungibile su {ip}:{port}. Carta in esaurimento."}
            elif status == 0:
                return {"status": "error", "message": f"Stampante raggiungibile su {ip}:{port}. CARTA ESAURITA!"}
            else:
                return {"status": "success", "message": f"Stampante raggiungibile su {ip}:{port}. Stato carta sconosciuto ({status})."}
        except Exception as e:
            try: p.close()
            except: pass
            return {"status": "error", "message": f"Stampante raggiunta, ma errore lettura stato: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Impossibile connettersi a {ip}:{port}. Errore: {str(e)}"}

@app.get("/users")
def get_users():
    db = SessionLocal()
    users = db.query(User).all()
    db.close()
    return users

class UserUpdate(BaseModel):
    name: Optional[str] = None
    printer_ip: Optional[str] = None
    auto_print_main: Optional[bool] = None
    printer_protocol: Optional[str] = None
    printer_connection_type: Optional[str] = None
    printer_paper_width: Optional[str] = None

@app.put("/users/{user_id}")
@app.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        raise HTTPException(status_code=404, detail="Operatore non trovato")
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.printer_ip is not None:
        user.printer_ip = payload.printer_ip.strip()
    if payload.auto_print_main is not None:
        user.auto_print_main = payload.auto_print_main
    if payload.printer_protocol is not None:
        user.printer_protocol = payload.printer_protocol
    if payload.printer_connection_type is not None:
        user.printer_connection_type = payload.printer_connection_type
    if payload.printer_paper_width is not None:
        user.printer_paper_width = payload.printer_paper_width
    db.commit()
    printing.invalidate_user_cache(user_id)
    db.close()
    return {"status": "success"}

class UserStateUpdate(BaseModel):
    active_cart: str
    active_state: str
    auto_print_main: bool
    printer_ip: str
    printer_protocol: str
    printer_connection_type: Optional[str] = "network"
    printer_paper_width: Optional[str] = "80mm"

@app.get("/users/{user_id}/cart")
def get_user_cart(user_id: int):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    if user:
        return {
            "active_cart": user.active_cart or "[]", 
            "active_state": user.active_state or "{}", 
            "auto_print_main": user.auto_print_main,
            "printer_ip": user.printer_ip or "",
            "printer_protocol": user.printer_protocol or "escpos",
            "printer_connection_type": getattr(user, "printer_connection_type", "network") or "network",
            "printer_paper_width": getattr(user, "printer_paper_width", "80mm") or "80mm"
        }
    return {
        "active_cart": "[]",
        "active_state": "{}",
        "auto_print_main": True,
        "printer_ip": "",
        "printer_protocol": "escpos",
        "printer_connection_type": "network",
        "printer_paper_width": "80mm"
    }

@app.post("/users/{user_id}/cart")
def update_user_cart(user_id: int, payload: UserStateUpdate):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.active_cart = payload.active_cart
        user.active_state = payload.active_state
        user.auto_print_main = payload.auto_print_main
        user.printer_ip = payload.printer_ip
        user.printer_protocol = payload.printer_protocol
        if payload.printer_connection_type is not None:
            user.printer_connection_type = payload.printer_connection_type
        if payload.printer_paper_width is not None:
            user.printer_paper_width = payload.printer_paper_width
        db.commit()
        printing.invalidate_user_cache(user_id)

        # Trigger customer display update asynchronously
        try:
            cart_data = json.loads(payload.active_cart)
            cart_items = []
            subtotal = 0.0
            for item in cart_data:
                desc = item.get("description", "")
                price = item.get("current_price", item.get("price", 0.0))
                cart_items.append({"description": desc, "price": price})
                subtotal += price
            
            state_data = json.loads(payload.active_state)
            disc = state_data.get("discount", 0.0)
            disc_type = state_data.get("discount_type", "%")
            if disc_type == '%':
                discount_amount = subtotal * (disc / 100.0)
            else:
                discount_amount = disc
            total = max(0.0, subtotal - discount_amount)
            
            if main_loop and main_loop.is_running():
                main_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(trigger_display_state_change(user_id, cart_items, subtotal, total, ""))
                )
        except Exception as e:
            print("Error triggering display update:", e)

    db.close()
    return {"status": "success"}

@app.get("/customer-display/{user_id}")
async def get_customer_display(user_id: int, version: Optional[int] = None, timeout: int = 20):
    db = SessionLocal()
    state = await get_or_create_display_state(user_id, db)
    db.close()
    
    if version is not None and state["version"] == version:
        # Long poll: wait for the event to be set or timeout
        event = state["event"]
        try:
            await asyncio.wait_for(event.wait(), timeout=float(timeout))
        except asyncio.TimeoutError:
            pass
        # Reload current state (it might have changed, or we timed out)
        state = await get_or_create_display_state(user_id)
        
    return {
        "cart": state["cart"],
        "subtotal": state["subtotal"],
        "total": state["total"],
        "order_completed_message": state["order_completed_message"],
        "version": state["version"]
    }

@app.get("/menu")
def get_menu():
    db = SessionLocal()
    items = (
        db.query(MenuItem)
        .filter(MenuItem.is_active == True)
        .order_by(MenuItem.sort_order.asc(), MenuItem.description.asc())
        .all()
    )
    db.close()
    return items

class CategoryCreate(BaseModel):
    name: str
    sort_order: Optional[int] = None
    printer_target: Optional[str] = "cucina"

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    printer_target: Optional[str] = None

class ReorderCategoriesPayload(BaseModel):
    ordered_ids: list[int]

class MenuItemCreate(BaseModel):
    description: str
    price: float
    image_url: str
    category: str
    components: str = ""
    additions: str = ""
    is_combo: bool = False
    combo_items: str = "[]"
    is_active: bool = True
    max_items: Optional[int] = None
    sort_order: int = 0

@app.get("/categories")
def get_categories():
    db = SessionLocal()
    cats = db.query(Category).order_by(Category.sort_order.asc(), Category.id.asc()).all()
    db.close()
    return cats

@app.post("/categories")
def create_category(payload: CategoryCreate):
    db = SessionLocal()
    if payload.sort_order is None:
        max_order = db.query(func.max(Category.sort_order)).scalar()
        sort_val = (max_order + 1) if max_order is not None else 0
    else:
        sort_val = payload.sort_order
    cat = Category(
        name=payload.name,
        sort_order=sort_val,
        printer_target=payload.printer_target or "cucina"
    )
    db.add(cat)
    db.commit()
    printing.invalidate_category_cache()
    db.close()
    return {"status": "success"}

@app.patch("/categories/{cat_id}")
@app.put("/categories/{cat_id}")
def update_category(cat_id: int, payload: CategoryUpdate):
    db = SessionLocal()
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        db.close()
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    if payload.name is not None:
        cat.name = payload.name
    if payload.sort_order is not None:
        cat.sort_order = payload.sort_order
    if payload.printer_target is not None:
        cat.printer_target = payload.printer_target
    db.commit()
    printing.invalidate_category_cache()
    db.close()
    return {"status": "success"}

@app.post("/categories/reorder")
def reorder_categories(payload: ReorderCategoriesPayload):
    db = SessionLocal()
    try:
        for index, cat_id in enumerate(payload.ordered_ids):
            db.query(Category).filter(Category.id == cat_id).update({"sort_order": index})
        db.commit()
        printing.invalidate_category_cache()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()

@app.delete("/categories/{cat_id}")
def delete_category(cat_id: int):
    db = SessionLocal()
    db.query(Category).filter(Category.id == cat_id).delete()
    db.commit()
    printing.invalidate_category_cache()
    db.close()
    return {"status": "success"}

@app.post("/menu")
def create_menu_item(payload: MenuItemCreate):
    db = SessionLocal()
    item = MenuItem(**payload.dict())
    db.add(item)
    db.commit()
    printing.invalidate_menu_cache()
    db.close()
    return {"status": "success"}

@app.delete("/menu/{item_id}")
def delete_menu_item(item_id: int):
    db = SessionLocal()
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item:
        item.is_active = False
        db.commit()
        printing.invalidate_menu_cache()
    db.close()
    return {"status": "success"}

@app.put("/menu/{item_id}")
def update_menu_item(item_id: int, payload: MenuItemCreate):
    db = SessionLocal()
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item:
        item.description = payload.description
        item.price = payload.price
        item.image_url = payload.image_url
        item.category = payload.category
        item.components = payload.components
        item.additions = payload.additions
        item.is_combo = payload.is_combo
        item.combo_items = payload.combo_items
        item.is_active = payload.is_active
        item.max_items = payload.max_items
        item.sort_order = payload.sort_order
        db.commit()
    printing.invalidate_menu_cache()
    db.close()
    return {"status": "success"}

# Thread-safe lock for atomic order number sequence generation
order_creation_lock = threading.Lock()

@app.post("/order")
def create_order(payload: dict = Body(...)):
    db = SessionLocal()
    try:
        settings = db.query(SystemSettings).first()
        auto_print_kitchen = settings.auto_print_kitchen if settings else True

        user = db.query(User).filter(User.id == payload.get('user_id')).first()
        auto_print_main = user.auto_print_main if user else True
        auto_print_bar = settings.auto_print_bar if settings and settings.auto_print_bar is not None else True

        # Pre-acquire printer locks before starting the DB transaction to avoid committing if printer is busy
        required_printers = printing.get_required_printers(payload, auto_print_main, auto_print_kitchen, auto_print_bar)
        acquired_locks = []
        try:
            for ip in required_printers:
                lock = printing.get_printer_lock(ip)
                if lock.acquire(timeout=30):
                    acquired_locks.append(lock)
                else:
                    raise HTTPException(status_code=409, detail="Stampante occupata da troppo tempo. Riprova.")

            with order_creation_lock:
                kwargs = {
                    'total': payload['total'],
                'discount': payload['discount'],
                'payment_method': payload['payment_method'],
                'payment_status': payload.get('payment_status', True),
                'takeaway': payload['takeaway'],
                'table_number': payload['table_number'],
                'user_id': payload['user_id'],
                'notes': payload.get('notes', '')
            }

            if kwargs['payment_status']:
                kwargs['payment_datetime'] = datetime.datetime.now(ROME_TZ)
            else:
                kwargs['payment_datetime'] = None

            if not settings:
                settings = SystemSettings(id=1, auto_print=True, next_order_number=1)
                db.add(settings)
                db.flush()

            custom_id = payload.get('order_id')

            existing_order = None
            if custom_id:
                existing_order = db.query(Order).filter(Order.order_number == str(custom_id)).first()

            if existing_order:
                existing_order.total = kwargs['total']
                existing_order.discount = kwargs['discount']
                existing_order.payment_method = kwargs['payment_method']
                existing_order.payment_status = kwargs['payment_status']
                existing_order.payment_datetime = kwargs['payment_datetime']
                existing_order.takeaway = kwargs['takeaway']
                existing_order.table_number = kwargs['table_number']
                existing_order.user_id = kwargs['user_id']
                existing_order.notes = kwargs['notes']

                # Remove old items and replace
                db.query(OrderItem).filter(OrderItem.order_id == existing_order.id).delete()

                order_id_to_use = existing_order.id
                order_number_str = existing_order.order_number
                is_new_order = False
            else:
                if custom_id:
                    kwargs['order_number'] = str(custom_id)
                else:
                    kwargs['order_number'] = str(settings.next_order_number)
                    settings.next_order_number += 1

                new_order = Order(**kwargs)
                db.add(new_order)
                db.flush()
                order_id_to_use = new_order.id
                order_number_str = new_order.order_number
                is_new_order = True

            new_items_for_kitchen = []

            # --- Bulk Load Menu Items to Avoid N+1 ---
            item_ids_to_fetch = set()
            item_descs_to_fetch = set()

            for item in payload['items']:
                if item.get('id'):
                    item_ids_to_fetch.add(item['id'])
                if item.get('description'):
                    item_descs_to_fetch.add(item['description'])

                combo_choices_str = item.get('combo_choices', '')
                if combo_choices_str:
                    for choice in combo_choices_str.split(','):
                        choice = choice.strip()
                        if not choice:
                            continue
                        base_desc = choice.split('[')[0].strip()
                        if base_desc and base_desc != 'Nessuna Scelta':
                            item_descs_to_fetch.add(base_desc)

            menu_items_by_id = {}
            menu_items_by_desc = {}
            if item_ids_to_fetch or item_descs_to_fetch:
                filters = []
                if item_ids_to_fetch:
                    filters.append(MenuItem.id.in_(list(item_ids_to_fetch)))
                if item_descs_to_fetch:
                    filters.append(MenuItem.description.in_(list(item_descs_to_fetch)))

                bulk_items = db.query(MenuItem).filter(or_(*filters)).all()
                for mi in bulk_items:
                    menu_items_by_id[mi.id] = mi
                    menu_items_by_desc[mi.description] = mi
            # -----------------------------------------

            for item in payload['items']:
                is_sent = item.get('_is_sent_to_kitchen', False)
                if not is_sent:
                    new_items_for_kitchen.append(item)
                order_item = OrderItem(
                    order_id=order_id_to_use,
                    description=item['description'],
                    quantity=1,
                    price_at_sale=item['price'],
                    notes=item.get('notes', ''),
                    ingredients=item.get('ingredients', ''),
                    combo_choices=item.get('combo_choices', ''),
                    discount=item.get('item_discount', 0.0),
                    discount_type=item.get('item_discount_type', '%')
                )
                db.add(order_item)

                # Update max items ordered counter for the ordered item itself
                menu_item = None
                if item.get('id') and item['id'] in menu_items_by_id:
                    menu_item = menu_items_by_id[item['id']]
                elif item.get('description') in menu_items_by_desc:
                    menu_item = menu_items_by_desc[item['description']]

                if menu_item and menu_item.max_items is not None:
                    if menu_item.max_items - menu_item.ordered_count > 0:
                        menu_item.ordered_count += 1

                # Also update ordered_count for each sub-item chosen inside a combo
                combo_choices_str = item.get('combo_choices', '')
                if combo_choices_str:
                    for choice in combo_choices_str.split(','):
                        choice = choice.strip()
                        if not choice:
                            continue
                        # Strip optional ingredient customisation suffix: "Name [Senza X, Con Y]"
                        base_desc = choice.split('[')[0].strip()
                        if not base_desc or base_desc == 'Nessuna Scelta':
                            continue

                        sub_menu_item = menu_items_by_desc.get(base_desc)
                        if sub_menu_item and sub_menu_item.max_items is not None:
                            if sub_menu_item.max_items - sub_menu_item.ordered_count > 0:
                                sub_menu_item.ordered_count += 1

            # Clear the user's active cart after successfully placing the order
            if user:
                user.active_cart = "[]"
                user.active_state = "{}"

            db.commit()
            
            # Trigger customer display update for completed order (can be outside the lock)
            try:
                if main_loop and main_loop.is_running():
                    msg = f"Ordine #{order_number_str} completato!"
                    main_loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(trigger_display_state_change(kwargs['user_id'], [], 0.0, 0.0, msg))
                    )
            except Exception as e:
                print("Error triggering order completion display update:", e)

            bill_status = {"printed": False, "message": "Autostampa disabilitata"}
            kitchen_status = {"printed": False, "message": "Non necessaria / disabilitata"}
            bar_status = {"printed": False, "message": "Non necessaria / disabilitata"}

            order_num_int = int(order_number_str) if order_number_str.isdigit() else order_id_to_use

            # 1. Print Customer Bill
            if auto_print_main:
                b_res = print_bill(order_num_int, payload, lock_acquired=True)
                if len(b_res) == 3:
                    b_ok, b_msg, b_extra = b_res
                else:
                    b_ok, b_msg = b_res
                    b_extra = {}
                bill_status = {"printed": b_ok, "message": b_msg, **b_extra}
                if not b_ok and b_msg == "CARTA ESAURITA":
                    bill_status["paper_out"] = True

            prod_payload = {
                "items": new_items_for_kitchen,
                "table_number": payload.get("table_number", "Nessuno"),
                "takeaway": payload.get("takeaway", False),
                "notes": payload.get("notes", "")
            }

            # 2. Print to Kitchen (Cucina)
            if auto_print_kitchen:
                k_ok, k_msg = printing.print_kitchen_receipt(order_num_int, prod_payload, lock_acquired=True)
                kitchen_status = {"printed": k_ok, "message": k_msg}
                if not k_ok and k_msg == "CARTA ESAURITA":
                    kitchen_status["paper_out"] = True

            # 3. Print to Bar (Bevande)
            if auto_print_bar:
                bar_ok, bar_msg = printing.print_bar_receipt(order_num_int, prod_payload, lock_acquired=True)
                bar_status = {"printed": bar_ok, "message": bar_msg}
                if not bar_ok and bar_msg == "CARTA ESAURITA":
                    bar_status["paper_out"] = True

            return {
                "status": "success",
                "order_id": order_number_str,
                "auto_print": auto_print_main or auto_print_kitchen or auto_print_bar,
                "bill_status": bill_status,
                "kitchen_status": kitchen_status,
                "bar_status": bar_status
            }
        finally:
            # Always release acquired printer locks
            for lock in acquired_locks:
                try:
                    lock.release()
                except Exception:
                    pass
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/order/{order_id}/print-bill")
def reprint_bill(order_id: str, payload: dict = Body(...)):
    try:
        b_res = print_bill(int(order_id) if order_id.isdigit() else 0, payload)
        if len(b_res) == 3:
            b_ok, b_msg, b_extra = b_res
        else:
            b_ok, b_msg = b_res
            b_extra = {}
        status_dict = {"printed": b_ok, "message": b_msg, **b_extra}
        if not b_ok and b_msg == "CARTA ESAURITA":
            status_dict["paper_out"] = True
        return {"status": "success", "bill_status": status_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/order/{order_id}/escpos-bill")
@app.post("/order/{order_id}/escpos-bill")
def get_order_escpos_bill(order_id: str, user_id: Optional[int] = 1, paper_width: Optional[str] = None):
    """
    Generates and returns ESC/POS Base64 binary directly for Web Bluetooth printing on tablets.
    """
    db = SessionLocal()
    try:
        order = db.query(Order).filter((Order.order_number == str(order_id)) | (Order.id == (int(order_id) if str(order_id).isdigit() else 0))).first()
        if not order:
            raise HTTPException(status_code=404, detail="Ordine non trovato")
        
        items_payload = []
        for i in order.items:
            items_payload.append({
                "description": i.description,
                "price": i.price_at_sale,
                "notes": i.notes or "",
                "ingredients": i.ingredients or "",
                "combo_choices": i.combo_choices or "",
                "item_discount": i.discount or 0.0,
                "item_discount_type": i.discount_type or "%"
            })
        
        payload = {
            "items": items_payload,
            "total": order.total,
            "discount": order.discount,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "takeaway": order.takeaway,
            "table_number": order.table_number,
            "user_id": user_id or order.user_id,
            "notes": order.notes or ""
        }
        
        target_width = paper_width
        if not target_width:
            u_settings = printing.get_user_settings(user_id or order.user_id)
            target_width = u_settings.get("printer_paper_width", "80mm") if u_settings else "80mm"
        
        order_num_int = int(order.order_number) if (order.order_number and order.order_number.isdigit()) else order.id
        raw_bytes = printing.generate_bill_escpos(order_num_int, payload, paper_width=target_width)
        b64 = base64.b64encode(raw_bytes).decode('ascii')
        
        return {
            "status": "success",
            "order_id": order.order_number or str(order.id),
            "paper_width": target_width,
            "escpos_base64": b64
        }
    finally:
        db.close()

@app.post("/order/{order_id}/print-kitchen")
def reprint_kitchen(order_id: str, payload: dict = Body(...)):
    try:
        new_items_for_kitchen = []
        for item in payload.get('items', []):
            # Same filtering logic as create_order
            is_sent = item.get('_is_sent_to_kitchen', False)
            if not is_sent:
                new_items_for_kitchen.append(item)

        kitchen_payload = {
            "items": new_items_for_kitchen,
            "table_number": payload.get("table_number", "Nessuno"),
            "takeaway": payload.get("takeaway", False),
            "notes": payload.get("notes", "")
        }

        k_ok, k_msg = printing.print_kitchen_receipt(int(order_id) if order_id.isdigit() else 0, kitchen_payload)
        status_dict = {"printed": k_ok, "message": k_msg}
        if not k_ok and k_msg == "CARTA ESAURITA":
            status_dict["paper_out"] = True
        return {"status": "success", "kitchen_status": status_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/order/{order_id}/print-bar")
@app.post("/order/{order_id}/print-bevande")
def reprint_bar(order_id: str, payload: dict = Body(...)):
    try:
        new_items = []
        for item in payload.get('items', []):
            is_sent = item.get('_is_sent_to_kitchen', False)
            if not is_sent:
                new_items.append(item)

        bar_payload = {
            "items": new_items,
            "table_number": payload.get("table_number", "Nessuno"),
            "takeaway": payload.get("takeaway", False),
            "notes": payload.get("notes", "")
        }

        b_ok, b_msg = printing.print_bar_receipt(int(order_id) if order_id.isdigit() else 0, bar_payload)
        status_dict = {"printed": b_ok, "message": b_msg}
        if not b_ok and b_msg == "CARTA ESAURITA":
            status_dict["paper_out"] = True
        return {"status": "success", "bar_status": status_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders")
def get_orders():
    db = SessionLocal()
    orders = db.query(Order).order_by(Order.id.desc()).all()
    res = []
    for o in orders:
        items = [{"description": i.description, "price_at_sale": i.price_at_sale, "notes": i.notes, "ingredients": i.ingredients, "combo_choices": i.combo_choices or ""} for i in o.items]
        res.append({
            "id": o.order_number or str(o.id),
            "total": o.total,
            "discount": o.discount,
            "timestamp": o.timestamp,
            "payment_method": o.payment_method,
            "payment_status": o.payment_status,
            "payment_datetime": o.payment_datetime,
            "items": items,
            "takeaway": o.takeaway,
            "table_number": o.table_number,
            "notes": o.notes
        })
    db.close()
    return res

@app.get("/export/menu_json")
def export_menu_json():
    db = SessionLocal()
    categories = db.query(Category).order_by(Category.sort_order.asc(), Category.id.asc()).all()
    items = db.query(MenuItem).order_by(MenuItem.sort_order.asc(), MenuItem.description.asc()).all()
    db.close()
    return {
        "categories": [
            {
                "name": c.name,
                "sort_order": c.sort_order if c.sort_order is not None else 0,
                "printer_target": c.printer_target or "cucina"
            } for c in categories
        ],
        "items": [
            {
                "description": i.description,
                "price": i.price,
                "image_url": i.image_url,
                "category": i.category,
                "components": i.components,
                "additions": i.additions,
                "is_combo": i.is_combo,
                "combo_items": i.combo_items,
                "is_active": i.is_active,
                "max_items": i.max_items,
                "sort_order": i.sort_order if i.sort_order is not None else 0
            } for i in items
        ]
    }

class ImportMenuPayload(BaseModel):
    mode: str
    data: dict

@app.post("/import/menu_json")
def import_menu_json(payload: ImportMenuPayload):
    db = SessionLocal()
    try:
        data = payload.data
        if not isinstance(data, dict):
             raise Exception("Invalid JSON format: root is not an object")
             
        cats = data.get("categories", [])
        items = data.get("items", [])
        
        if payload.mode == "replace":
            db.execute(text("DELETE FROM menu_items"))
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='menu_items'"))
            db.execute(text("DELETE FROM categories"))
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='categories'"))
            db.commit()
        printing.invalidate_menu_cache()
        printing.invalidate_category_cache()

        existing_names = {name for (name,) in db.query(Category.name).all()}
            
        for idx, c in enumerate(cats):
            c_name = c.get("name")
            c_order = c.get("sort_order", idx)
            c_target = c.get("printer_target", "cucina")
            if c_name and c_name not in existing_names:
                db.add(Category(name=c_name, sort_order=c_order, printer_target=c_target))
                existing_names.add(c_name)
                
        for i in items:
            new_item = MenuItem(
                description=i.get("description", ""),
                price=i.get("price", 0.0),
                image_url=i.get("image_url", ""),
                category=i.get("category", ""),
                components=i.get("components", ""),
                additions=i.get("additions", ""),
                is_combo=i.get("is_combo", False),
                combo_items=i.get("combo_items", "[]"),
                is_active=i.get("is_active", True),
                max_items=i.get("max_items", None),
                ordered_count=0,
                sort_order=i.get("sort_order", 0)
            )
            db.add(new_item)
            
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@app.delete("/orders")
def delete_all_orders():
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM order_items"))
        db.execute(text("DELETE FROM orders"))
        try:
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='order_items'"))
            db.execute(text("DELETE FROM sqlite_sequence WHERE name='orders'"))
        except Exception:
            pass
        db.execute(text("UPDATE system_settings SET next_order_number = 1"))
        db.execute(text("UPDATE menu_items SET ordered_count = 0"))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
    return {"status": "success"}

@app.get("/api/stats/days")
def get_stats_days():
    exporter = StatsExporter(session_factory=SessionLocal)
    days = exporter.get_available_days()
    return {"days": days}

@app.get("/api/stats/data")
def get_stats_data(day: str):
    if not isinstance(day, str):
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD")

    try:
        datetime.datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD")

    exporter = StatsExporter(session_factory=SessionLocal)
    stats = exporter.generate_stats(day)
    return stats

@app.post("/api/stats/export/excel")
def export_stats_excel(payload: dict = Body(...)):
    day = payload.get('day')
    if not day:
        raise HTTPException(status_code=400, detail="Day is required")

    if not isinstance(day, str):
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD")

    try:
        datetime.datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD")

    exporter = StatsExporter(session_factory=SessionLocal)
    stats = exporter.generate_stats(day)

    os.makedirs("static/export", exist_ok=True)
    excel_path = f"static/export/stats_{day}.xlsx"
    exporter.export_to_excel(stats, excel_path)

    return {"status": "success", "url": f"/{excel_path}"}

@app.post("/api/stats/export/pdf")
def export_stats_pdf(payload: dict = Body(...)):
    day = payload.get('day')
    if not day:
        raise HTTPException(status_code=400, detail="Day is required")

    if not isinstance(day, str):
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD")

    try:
        datetime.datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD")

    exporter = StatsExporter(session_factory=SessionLocal)
    stats = exporter.generate_stats(day)

    os.makedirs("static/export", exist_ok=True)
    pdf_path = f"static/export/stats_{day}.pdf"
    exporter.export_to_pdf(stats, pdf_path)

    return {"status": "success", "url": f"/{pdf_path}"}


@app.get("/export/orders")
def export_orders():
    db = SessionLocal()
    orders = db.query(Order).order_by(Order.id.asc()).all()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16)
    
    pdf.cell(200, 10, txt="Orders Report", ln=True, align='C')
    pdf.ln(5)
    
    for o in orders:
        pdf.set_font("Arial", 'B', 11)
        table_str = f" - Tavolo: {o.table_number}" if o.table_number and o.table_number.lower() != "nessuno" else ""
        pdf.cell(200, 10, txt=f"Order #{o.id} - Date: {o.timestamp} - Total: EUR {o.total:.2f} (Discount: EUR {o.discount:.2f}){table_str}", ln=True)
        pdf.set_font("Arial", '', 10)
        for i in o.items:
            ingr_str = f" [{i.ingredients}]" if i.ingredients else ""
            notes_str = f" (Note: {i.notes})" if i.notes else ""
            pdf.cell(200, 8, txt=f"    - {i.description}{ingr_str}{notes_str} : EUR {i.price_at_sale:.2f}", ln=True)
            if i.combo_choices:
                for choice in i.combo_choices.split(','):
                    pdf.cell(200, 6, txt=f"        > {choice.strip()}", ln=True)
        if hasattr(o, 'notes') and o.notes:
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(200, 8, txt=f"    * Note Ordine: {o.notes}", ln=True)
        pdf.ln(3)
        
    db.close()
    pdf_path = "static/orders_export.pdf"
    pdf.output(pdf_path)
    return FileResponse(pdf_path, filename="orders_export.pdf", media_type='application/pdf')