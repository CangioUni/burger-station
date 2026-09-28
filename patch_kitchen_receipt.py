import requests

payload = {
    "items": [
        {
            "description": "Test Item",
            "price": 10.0,
            "_is_sent_to_kitchen": False,
            "notes": "",
            "ingredients": "",
            "combo_choices": ""
        }
    ],
    "total": 10.0,
    "discount": 0.0,
    "payment_method": "Cash",
    "payment_status": True,
    "takeaway": False,
    "table_number": "Nessuno",
    "user_id": 1,
    "notes": ""
}

try:
    response = requests.post("http://localhost:8000/order", json=payload)
    print(response.json())
except Exception as e:
    print(e)
