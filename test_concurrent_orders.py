import requests
import concurrent.futures
import time

URL = "http://localhost:8000/order"

def submit_order(i):
    payload = {
        "items": [
            {
                "description": f"Test Item {i}",
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

    start = time.time()
    try:
        response = requests.post(URL, json=payload)
        return response.status_code, response.json(), time.time() - start
    except Exception as e:
        return 500, str(e), time.time() - start

if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(submit_order, i) for i in range(5)]

        for future in concurrent.futures.as_completed(futures):
            print(future.result())
