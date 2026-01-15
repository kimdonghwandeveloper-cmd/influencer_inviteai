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

print(f"Checking DB: {db_name}.products")
count = coll.count_documents({"brand": "Logitech"})
print(f"Total Logitech items: {count}")

for doc in coll.find({"brand": "Logitech"}).limit(10):
    print(f"- {doc.get('title')} | {doc.get('price')} | {doc.get('url')}")
