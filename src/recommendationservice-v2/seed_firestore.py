import os
from datetime import datetime, timezone

from google.cloud import firestore

project_id = os.environ.get("GCP_PROJECT_ID", "cloud-chasers-microservices")
database_id = "cloudchasersdb"

db = firestore.Client(project=project_id, database=database_id)

sample_users = {
    "user-concordia-99": {
        "user_id": "user-concordia-99",
        "category_affinity": "vintage photography & retro electronics",
        "past_purchased_skus": ["OLJCESPC7Z"],
        "price_sensitivity": "medium",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "user-kitchen-pro": {
        "user_id": "user-kitchen-pro",
        "category_affinity": "home barista, coffee & kitchenware",
        "past_purchased_skus": ["6E92ZMYYFZ", "2ZYFJ3GM2N"],
        "price_sensitivity": "low",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
}

for uid, data in sample_users.items():
    db.collection("user_sessions").document(uid).set(data)
    print(f"Seeded Firestore document: user_sessions/{uid}")

print("Firestore seeding complete!")
