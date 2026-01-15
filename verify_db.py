from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
mongo_uri = os.getenv("MONGO_URI")
db_name = os.getenv("MONGO_DB_NAME", "inma_db")

if not mongo_uri:
    print("MONGO_URI not found")
    exit(1)

client = MongoClient(mongo_uri)
db = client[db_name]
coll = db["products"]

print(f"=== Checking DB: {db_name}.products ===")

# Count by Brand
pipeline = [
    {"$group": {"_id": "$brand", "count": {"$sum": 1}}}
]
results = list(coll.aggregate(pipeline))

if not results:
    print("No products found.")
else:
    for res in results:
        print(f"Brand: {res['_id']} | Count: {res['count']}")

print("\n=== Sample Data (Latest 5) ===")
for doc in coll.find().sort("last_updated", -1).limit(5):
    print(f"[{doc.get('brand')}] {doc.get('title')} ({doc.get('price')} KRW)")

print("\n=== Checking DB: {db_name}.influencers ===")
inf_coll = db["influencers"]
inf_count = inf_coll.count_documents({})
print(f"Total Influencers: {inf_count}")

# Count by Category/Keyword (Approximate via 'keywords' or just total)
# Since category field might be empty, just showing total for now.
pipeline = [
    {"$unwind": "$keywords"},
    {"$group": {"_id": "$keywords", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 5}
]
print("Top 5 Keywords:")
for res in inf_coll.aggregate(pipeline):
    print(f"- {res['_id']}: {res['count']}")
