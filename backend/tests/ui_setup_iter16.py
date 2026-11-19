# Helper for iteration 16 UI tests: create/delete TEST_ apps, flip Hubtel live window. Usage:
#   python ui_setup_iter16.py paid | pending_live | restore | delete <trk...>
import json, sys, time, requests
from pymongo import MongoClient

BASE = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL=")][0].rstrip("/")
ENV = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
db = MongoClient(ENV["MONGO_URL"].strip('"'))[ENV["DB_NAME"].strip('"')]
BACKUP = "/tmp/hubtel_backup.json"


def create():
    p = {"visa_code": "tourist_evisa", "passport_country": "France", "passport_number": "TEST12345",
         "passport_type": "Ordinary", "passport_expiry": "2030-01-01", "travelling_from": "France",
         "arrival_date": "2027-02-01", "departure_date": "2027-02-15", "full_name": "TEST_Iter16 UI",
         "email": "delivered@resend.dev", "phone": "+33600000000", "profession": "Engineer",
         "processing": "regular", "lang": "en"}
    return requests.post(f"{BASE}/api/applications", json=p, timeout=30).json()["tracking_no"]


cmd = sys.argv[1]
if cmd == "paid":
    t = create()
    requests.post(f"{BASE}/api/payments/confirm", json={"tracking_no": t, "success": True}, timeout=30)
    print(t)
elif cmd == "pending_live":
    t = create()
    requests.post(f"{BASE}/api/payments/initiate", json={"tracking_no": t}, timeout=30)
    orig = db.settings.find_one({"id": "singleton"})["hubtel"]
    assert orig.get("sandbox") is True
    json.dump(orig, open(BACKUP, "w"))
    db.settings.update_one({"id": "singleton"}, {"$set": {"hubtel": dict(orig, sandbox=False, api_id="TEST_fake_id",
                                                                      api_key="TEST_fake_key", merchant_account_id="1234567")}})
    body = {"ResponseCode": "0000", "Status": "Success", "Data": {"ClientReference": t, "Status": "Success", "CheckoutId": "FORGED"}}
    requests.post(f"{BASE}/api/webhooks/hubtel", json=body, timeout=30)
    time.sleep(20)
    d = db.applications.find_one({"tracking_no": t}, {"_id": 0, "payment_status": 1, "payment_verification": 1})
    print(t, d)
elif cmd == "restore":
    orig = json.load(open(BACKUP))
    db.settings.update_one({"id": "singleton"}, {"$set": {"hubtel": orig}})
    print("restored", db.settings.find_one({"id": "singleton"})["hubtel"])
elif cmd == "delete":
    tok = requests.post(f"{BASE}/api/admin/login", json={"email": "admin@eghanavisa.com", "password": "Admin@2026"}, timeout=30).json()["token"]
    for t in sys.argv[2:]:
        print(t, requests.delete(f"{BASE}/api/admin/applications/{t}", headers={"Authorization": f"Bearer {tok}"}, timeout=30).status_code)
