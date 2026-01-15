import os
import time
import math
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

load_dotenv(override=True)

class MatchingEngine:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or os.getenv("MONGO_PUBLIC_URL")
        self.db_name = os.getenv("DB_NAME") or os.getenv("MONGODB_DB")
        
        if not self.uri or not self.db_name:
            raise ValueError("MONGODB_URI or DB_NAME missing")
            
        self.client = MongoClient(self.uri)
        self.db = self.client[self.db_name]
        self.influencers = self.db["influencers"]
        self.products = self.db["products"]

    def calculate_similarity(self, vec_a, vec_b):
        """
        Calculates Cosine Similarity between two vectors.
        """
        if not vec_a or not vec_b:
            return 0.0
        
        # Reshape for sklearn
        a = np.array(vec_a).reshape(1, -1)
        b = np.array(vec_b).reshape(1, -1)
        
        return cosine_similarity(a, b)[0][0]

    def find_influencers_for_product(self, product_doc, limit=10):
        """
        Recommend influencers for a given product document.
        """
        product_name = product_doc.get("title") or product_doc.get("name", "Unknown")
        print(f"Match: Analyzing matching for '{product_name}'...")
        
        prod_embed = product_doc.get("embedding")
        prod_tags = set(product_doc.get("tags", []))
        prod_cat = product_doc.get("structured_tags", {}).get("category", "")
        
        # --- Normalization Logic ---
        CATEGORY_SYNONYMS = {
            "요가": "운동",
            "러닝": "운동",
            "헬스": "운동",
            "피트니스": "운동",
            "필라테스": "운동",
            "운동": "운동",
            "등산": "아웃도어",
            "캠핑": "아웃도어",
            "여행": "여행",
            "패션": "패션",
            "뷰티": "뷰티",
            "육아": "육아",
            "게임": "게임",
            "IT": "테크",
            "전자기기": "테크",
            "자동차": "자동차",
            "차": "자동차",
            "시승": "자동차",
            "모빌리티": "자동차"
        }

        def normalize(text):
            if not text: return "N/A"
            text_str = str(text) # Handle list if passed accidently, though expected str
            for key, value in CATEGORY_SYNONYMS.items():
                if key in text_str: return value
            return text_str

        norm_prod_cat = normalize(prod_cat)
        
        if not prod_embed:
            print("Warning: Product has no embedding. Results will be poor.")

        # --- Step 1: Candidate Generation ---
        candidates = list(self.influencers.find({}))
        scored_candidates = []
        
        for inf in candidates:
            inf_industry = inf.get("structured_tags", {}).get("industry", "")
            
            # --- Step 2: Semantic Similarity ---
            sim_score = 0.0
            inf_embed = inf.get("embedding")
            if prod_embed and inf_embed:
                sim_score = self.calculate_similarity(prod_embed, inf_embed)
            
            # --- Step 3: Keyword Overlap ---
            inf_tags = set(inf.get("tags", []))
            overlap = prod_tags.intersection(inf_tags)
            keyword_score = len(overlap) / max(len(prod_tags), 1)

            # Strict Filter: Require at least 1 keyword match
            if len(overlap) == 0:
                continue

            # --- Step 4: Engagement Rate ---
            stats = inf.get("stats", {})
            subs = stats.get("subscribers", 1) or 1
            avg_likes = stats.get("avg_likes", 0) or 0
            er = avg_likes / subs if subs > 0 else 0
            er_score = min(er * 20, 1.0)
            
            # --- Step 5: Multi-Category Matching ---
            cat_score = 0.0
            norm_inf_cat = normalize(inf_industry)
            
            # 1. Identify ALL valid categories for this product
            #    (Primary Category + Tags that are actually categories)
            valid_product_categories = set()
            if norm_prod_cat != "N/A":
                valid_product_categories.add(norm_prod_cat)
                
            for tag in prod_tags:
                norm_tag = normalize(tag)
                if norm_tag != "N/A" and norm_tag != tag: # If tag maps to a known category synonym
                    valid_product_categories.add(norm_tag)
                # Also check direct mapping if tag IS a standard category key (e.g., '게임')
                if tag in CATEGORY_SYNONYMS.values(): 
                     valid_product_categories.add(tag)

            # 2. Check for Match or Mismatch
            is_match = False
            
            # A. Direct overlap
            if norm_inf_cat in valid_product_categories:
                is_match = True
            
            # B. Substring Overlap (fallback)
            if not is_match and inf_industry:
                for vcat in valid_product_categories:
                    if (vcat in inf_industry) or (inf_industry in vcat):
                        is_match = True
                        break
            
            if is_match:
                cat_score = 0.3 # Boost for matching ANY valid category
            elif (len(valid_product_categories) > 0) and (norm_inf_cat != "N/A"):
                # Mismatch Penalty
                # Only penalize if influencer category is completely disjoint from ALL product categories
                cat_score = -0.5 
            
            final_score = (sim_score * 0.4) + (keyword_score * 0.3) + (er_score * 0.1) + cat_score
            
            # Ensure score doesn't go below 0
            final_score = max(final_score, 0.0)
            
            scored_candidates.append({
                "influencer": inf,
                "score": final_score,
                "details": {
                    "similarity": round(sim_score, 2),
                    "keyword_overlap": len(overlap),
                    "er_score": round(er_score, 2),
                    "industry": inf_industry,
                    "matched_category": is_match
                }
            })
        
        # Sort by score DESC
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        
        return scored_candidates[:limit]

if __name__ == "__main__":
    # Test run
    engine = MatchingEngine()
    print("Engine initialized.")
