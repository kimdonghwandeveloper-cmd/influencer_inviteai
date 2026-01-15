@app.get("/stats")
def get_stats():
    if not MONGODB_URI:
        raise HTTPException(500, "MONGODB_URI missing")
    
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]
    
    inf_col = db[MONGODB_INFLUENCER_COLLECTION]
    prod_col = db["products"]
    
    total_influencers = inf_col.count_documents({})
    total_products = prod_col.count_documents({})
    
    # Top segments (simple aggregation on keywords or category field if exists)
    # Here we simulate segments based on keywords/industries for the dashboard chart
    pipeline = [
        {"$project": {"keywords": 1}},
        {"$unwind": "$keywords"},
        {"$group": {"_id": "$keywords", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    top_keywords = list(inf_col.aggregate(pipeline))
    
    return {
        "total_influencers": total_influencers,
        "total_products": total_products,
        "active_campaigns": 3, # Mock data for now
        "emails_sent": 128,    # Mock data for now
        "segments": [{"name": k["_id"], "value": k["count"]} for k in top_keywords]
    }
