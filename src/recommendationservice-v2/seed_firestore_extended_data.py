import os
from datetime import datetime, timezone

from google.cloud import firestore

project_id = os.environ.get("GCP_PROJECT_ID", "cloud-chasers-microservices")
database_id = "cloudchasersdb"

db = firestore.Client(project=project_id, database=database_id)

sample_users = {
    "user-concordia-99": {
        "user_id": "user-concordia-99",
        "category_affinity": "vintage photography, travel & portable electronics",
        "past_purchased_skus": ["OLJCESPC7Z", "CAMERA001"],
        "price_sensitivity": "medium",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "user-kitchen-pro": {
        "user_id": "user-kitchen-pro",
        "category_affinity": "home barista, specialty coffee & kitchenware",
        "past_purchased_skus": ["6E92ZMYYFZ", "KITCH001"],
        "price_sensitivity": "low",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "user-beauty-traveler": {
        "user_id": "user-beauty-traveler",
        "category_affinity": "hair styling, beauty & compact travel accessories",
        "past_purchased_skus": ["2ZYFJ3GM2N"],
        "price_sensitivity": "medium",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "user-summer-runner": {
        "user_id": "user-summer-runner",
        "category_affinity": "running, outdoor fitness, eyewear & summer sportswear",
        "past_purchased_skus": ["66VCHSJNUP"],
        "price_sensitivity": "high",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
}

for uid, data in sample_users.items():
    db.collection("user_sessions").document(uid).set(data)
    print(f"Seeded Firestore document: user_sessions/{uid}")

print("Firestore extended seeding complete!")
