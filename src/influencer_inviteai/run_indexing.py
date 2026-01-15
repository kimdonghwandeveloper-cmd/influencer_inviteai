from influencer_inviteai.rag_engine import RAGEngine

def main():
    try:
        engine = RAGEngine()
        engine.index_products()
    except Exception as e:
        print(f"Indexing failed: {e}")

if __name__ == "__main__":
    main()
