from influencer_inviteai.rag_engine import RAGEngine

def main():
    engine = RAGEngine()
    query = "편안한 네모팬티 추천해줘"
    print(f"Query: {query}")
    
    # Check data count
    count = engine.db["brands"].count_documents({})
    print(f"Total products in DB (brands): {count}")
    
    print("--- First 10 Product Titles ---")
    titles = []
    for doc in engine.db["brands"].find({}, {"title": 1}).limit(10):
        t = doc.get('title')
        titles.append(t)
        print(f" - {t}")
    print("----------------------")

    # Manual regex check
    regex_count = engine.db["brands"].count_documents({"title": {"$regex": "네모팬티", "$options": "i"}})
    print(f"Manual Regex Check Count for '네모팬티': {regex_count}")

    # Try creating index (simplified attempt)
    try:
        engine.db["brands"].create_search_index(
            model={"definition": {
                "mappings": {
                    "dynamic": True,
                    "fields": {
                        "embedding": {
                            "dimensions": 1536,
                            "similarity": "cosine",
                            "type": "knnVector"
                        }
                    }
                }
            },
            "name": "vector_index"}
        )
        print("Attempted to create search index 'vector_index'.")
    except Exception as e:
        print(f"Index creation skipped/failed: {e}")

    results = engine.search_products("네모팬티", limit=3)
    
    print(f"Found {len(results)} results for '네모팬티':")
    for res in results:
        print(f"- {res.get('title')} ({res.get('price')}원)")
        print(f"  Score: {res.get('score')}")

if __name__ == "__main__":
    main()
