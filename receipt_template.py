import datetime
from zoneinfo import ZoneInfo

ROME_TZ = ZoneInfo("Europe/Rome")

# ==============================================================================
# CONFIGURAZIONE INTESTAZIONE E PIÈ DI PAGINA DELLO SCONTRINO (BILL RECEIPT)
# ==============================================================================
# Modificare liberamente i testi qui sotto per personalizzare le informazioni
# stampate in testa e in coda sullo scontrino non fiscale cliente.
# ==============================================================================

RECEIPT_HEADER = {
    "title_bold": "Restaurant\nAND ITS NAME",
    "subtitle": "Location\nRest of location",
}

RECEIPT_FOOTER = {
    "disclaimer": "SCONTRINO NON FISCALE",
    "custom_message": "",  # Messaggio opzionale (es. ringraziamenti, P.IVA, social)
}


def build_bill_header(order_id: int, paper_width: str = "80mm") -> bytes:
    """
    Genera la sequenza di byte ESC/POS per l'intestazione dello scontrino.
    Include titolo locale, sottotitolo/indirizzo e numero ordine ben evidenziato.
    """
    buf = bytearray()
    
    # Intestazione Locale
    buf.extend(b'\x1ba\x01')  # Centrato
    buf.extend(b'\x1b!\x08')  # Grassetto
    buf.extend(f"{RECEIPT_HEADER['title_bold']}\n".encode('cp858', errors='replace'))
    buf.extend(b'\x1b!\x00')  # Normale
    buf.extend(f"{RECEIPT_HEADER['subtitle']}\n\n".encode('cp858', errors='replace'))

    # Numero Ordine
    buf.extend(b'\x1b!\x38')  # Doppia altezza + doppia larghezza + grassetto
    buf.extend(f"ORDINE {order_id:03d}\n\n".encode('cp858', errors='replace'))
    
    return bytes(buf)


def build_column_header(width: int = 48) -> bytes:
    """
    Genera l'intestazione delle colonne DESCRIZIONE / Prezzo (€).
    Adatta la spaziatura per 80mm (48 col) o 58mm (32 col).
    """
    buf = bytearray()
    buf.extend(b'\x1ba\x00')  # Allineamento a sinistra
    if width >= 48:
        buf.extend(b'\x1b!\x10')  # Doppia altezza
        buf.extend(b'DESCRIZIONE                           Prezzo (\xd5)\n\n')
    else:
        buf.extend(b'\x1b!\x08')  # Grassetto
        buf.extend(b'DESCRIZIONE          Prezzo (\xd5)\n')
        buf.extend(("-" * width + "\n").encode('cp858', errors='replace'))
    buf.extend(b'\x1b!\x00')  # Normale
    return bytes(buf)


def build_bill_footer(order_id: int, now: datetime.datetime = None, paper_width: str = "80mm") -> bytes:
    """
    Genera la sequenza di byte ESC/POS per il piè di pagina dello scontrino.
    Include data/ora, numero progressivo documento e dicitura scontrino non fiscale.
    """
    if now is None:
        now = datetime.datetime.now(ROME_TZ)

    buf = bytearray()
    buf.extend(b'\x1ba\x01')  # Centrato
    buf.extend(f"\n{now.strftime('%d-%m-%Y  %H:%M')}\n".encode('cp858', errors='replace'))
    buf.extend(f"DOCUMENTO N. {order_id:03d}\n\n".encode('cp858', errors='replace'))
    buf.extend(f"{RECEIPT_FOOTER['disclaimer']}\n".encode('cp858', errors='replace'))
    
    custom_msg = RECEIPT_FOOTER.get('custom_message')
    if custom_msg:
        buf.extend(f"\n{custom_msg}\n".encode('cp858', errors='replace'))

    buf.extend(b"\n\n\n\n")
    return bytes(buf)
