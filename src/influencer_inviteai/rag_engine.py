import os
import pymongo
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Optional
import time

# 환경 변수 로드
load_dotenv()

class RAGEngine:
    """
    RAG (Retrieval-Augmented Generation) 엔진
    - MongoDB에 저장된 인플루언서 데이터를 벡터화(Embedding)
    - 사용자 쿼리에 맞는 최적의 인플루언서를 벡터 검색(Vector Search)
    """

    def __init__(self):
        # 1. MongoDB 연결
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_name = os.getenv("MONGO_DB_NAME", "inma_db")
        
        if not self.mongo_uri:
            raise ValueError("MONGO_URI가 설정되지 않았습니다.")
            
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.db_name]
        self.collection = self.db["influencers"]
        
        # 2. OpenAI 연결
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("Warning: OPENAI_API_KEY가 설정되지 않았습니다. 임베딩 기능을 사용할 수 없습니다.")
        
        self.openai_client = OpenAI(api_key=self.api_key)

    def generate_embedding(self, text: str) -> List[float]:
        """텍스트를 벡터(Embedding)로 변환 (OpenAI text-embedding-3-small)"""
        text = text.replace("\n", " ")
        if not text:
            return []
            
        try:
            response = self.openai_client.embeddings.create(
                input=[text],
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"임베딩 생성 실패: {e}")
            return []

    def index_influencers(self):
        """
        DB에 있는 모든 인플루언서 데이터를 순회하며,
        아직 임베딩이 없는 문서에 대해 벡터를 생성하고 저장합니다.
        """
        print("=== 인플루언서 데이터 임베딩 작업 시작 ===")
        
        # 임베딩이 없는 문서 찾기
        cursor = self.collection.find({"embedding": {"$exists": False}})
        count = self.collection.count_documents({"embedding": {"$exists": False}})
        
        print(f"총 {count}개의 미처리 문서를 발견했습니다.")
        
        processed = 0
        for doc in cursor:
            # 1. 임베딩할 텍스트 조합 (Title + Description + Keywords + Recent Titles)
            # RAG가 잘 찾을 수 있도록 풍부한 문맥을 만들어줍니다.
            
            # 키워드와 타이틀 가져오기 (없으면 빈 리스트)
            keywords = doc.get("keywords", [])
            recent_titles = []
            if "content_summary" in doc and "recent_titles" in doc["content_summary"]:
                recent_titles = doc["content_summary"]["recent_titles"]
            
            # 텍스트 조합
            context_text = f"채널명: {doc['title']}\n"
            context_text += f"설명: {doc.get('description', '')}\n"
            context_text += f"주요 키워드: {', '.join(keywords)}\n"
            context_text += f"최근 영상: {', '.join(recent_titles)}"
            
            # 2. 임베딩 생성
            embedding = self.generate_embedding(context_text)
            
            if embedding:
                # 3. DB 업데이트
                self.collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": embedding, "last_embedded": time.time()}}
                )
                processed += 1
                print(f"[{processed}/{count}] 임베딩 완료: {doc['title']}")
                
            # Rate Limit 방지
            time.sleep(0.1)
            
        print("=== 임베딩 작업 완료 ===")

    def search_similar_influencers(self, query: str, limit: int = 5) -> List[Dict]:
        """
        사용자 질문(Query)과 유사한 인플루언서를 벡터 검색합니다.
        (MongoDB Atlas Vector Search 필요)
        """
        query_embedding = self.generate_embedding(query)
        
        if not query_embedding:
            return []
            
        print(f"검색어 임베딩 생성 완료. Vector Search 실행... (Query: {query})")
        
        # MongoDB Atlas Vector Search Aggregation Pipeline
        # (사전에 Atlas UI에서 'vector_index'라는 Search Index를 생성해야 함)
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,
                    "limit": limit
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "title": 1,
                    "description": 1,
                    "keywords": 1,
                    "inma_score": 1,
                    "email": 1,
                    "score": {"$meta": "vectorSearchScore"} # 유사도 점수
                }
            }
        ]
        
        try:
            results = list(self.collection.aggregate(pipeline))
            return results
        except Exception as e:
            print(f"Vector Search 실패 (Index가 설정되었는지 확인하세요): {e}")
            return list(self.collection.find(regex_query).limit(limit))

    def index_products(self):
        """MongoDB에 저장된 상품 데이터를 벡터화하여 저장"""
        print("=== 상품 데이터 임베딩 작업 시작 ===")
        collection = self.db["products"]
        
        # 임베딩이 없는 문서 찾기
        cursor = collection.find({"embedding": {"$exists": False}})
        count = collection.count_documents({"embedding": {"$exists": False}})
        
        print(f"총 {count}개의 미처리 상품을 발견했습니다.")
        
        processed = 0
        for doc in cursor:
            # 텍스트 조합 (제목 + 설명 + 가격)
            context_text = f"브랜드: {doc.get('brand', 'Slim9')}\n"
            context_text += f"상품명: {doc.get('title', '')}\n"
            context_text += f"가격: {doc.get('price', '0')}원\n"
            context_text += f"설명: {doc.get('description', '')}"
            
            # 임베딩 생성
            embedding = self.generate_embedding(context_text)
            
            if embedding:
                product_collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": embedding, "last_embedded": time.time()}}
                )
                processed += 1
                print(f"[{processed}/{count}] 상품 임베딩 완료: {doc.get('title')}")
            
            time.sleep(0.1)
        print("=== 상품 임베딩 작업 완료 ===")

    def search_products(self, query: str, limit: int = 5) -> List[Dict]:
        """
        사용자 질문과 유사한 상품을 검색합니다.
        """
        query_embedding = self.generate_embedding(query)
        if not query_embedding:
            return []
            
        print(f"상품 검색 실행 (Query: {query})")
        product_collection = self.db["brands"]
        
        # Vector Search Pipeline
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,
                    "limit": limit
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "title": 1,
                    "price": 1,
                    "description": 1,
                    "url": 1,
                    "image": 1,
                    "brand": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]
        
        try:
            results = list(product_collection.aggregate(pipeline))
            return results
        except Exception as e:
            print(f"Vector Search 실패: {e}")
            # Fallback
            regex_query = {"title": {"$regex": query, "$options": "i"}}
            return list(product_collection.find(regex_query).limit(limit))

if __name__ == "__main__":
    # 테스트 실행
    engine = RAGEngine()
    
    # 1. 데이터 인덱싱 (임베딩 생성)
    engine.index_influencers()
    
    # 2. 테스트 검색
    test_query = "패션 하울 영상을 주로 올리는 유튜버"
    results = engine.search_similar_influencers(test_query)
    
    print(f"\n[검색 결과: '{test_query}']")
    for res in results:
        print(f"- {res['title']} (Score: {res.get('score', 0):.4f})")
