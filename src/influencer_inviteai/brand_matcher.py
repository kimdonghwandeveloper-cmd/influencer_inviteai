import os
import requests
from bs4 import BeautifulSoup
from collections import Counter
import re
from typing import List, Optional, Tuple
import concurrent.futures

# 기존 Collector 재사용
# (상대 경로 import 문제 방지를 위해 sys.path 조작하거나 같은 패키지 내라면 .으로 import)
try:
    from influencer_inviteai.collector import YouTubeCollector
except ImportError:
    # 스크립트 직접 실행 시 경로 문제 해결용
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from influencer_inviteai.collector import YouTubeCollector

class BrandAnalyzer:
    """
    브랜드 웹사이트를 분석하여 핵심 키워드를 추출하고, 
    YouTubeCollector를 구동하여 적합한 인플루언서를 찾습니다.
    """
    
    def __init__(self):
        self.collector = YouTubeCollector()
        
    def fetch_page_content(self, url: str) -> str:
        """웹사이트 HTML 텍스트 수집"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding # 한글 깨짐 방지
            return response.text
        except Exception as e:
            print(f"웹사이트 접속 실패: {e}")
            return ""

    def extract_keywords(self, html_content: str) -> Tuple[str, List[str]]:
        """
        HTML에서 [주 키워드(Brand/Category), 부 키워드(Related)] 추출
        """
        if not html_content:
            return "", []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Title & Meta Description
        title = soup.title.string if soup.title else ""
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")
            
        print(f"  [분석] Title: {title}")
        
        # 2. 본문 텍스트 추출 및 정제
        # 2. 본문 텍스트 추출 및 정제
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator=" ")
        
        # [수정] 한글+영어+숫자 포함하여 2글자 이상 (슬림9 같은 브랜드명 캐치)
        words = re.findall(r'[가-힣0-9a-zA-Z]{2,}', text + " " + title + " " + meta_desc)
        
        stopwords = {
            "로그인", "회원가입", "장바구니", "검색", "메뉴", "보기", "바로가기", "배송", "상품", "고객센터",
            "브랜드", "신상", "쇼핑", "스토어", "공지사항", "리뷰", "이벤트", "마이페이지", "전체", "베스트",
            "느껴지는", "테크놀로지", "있는", "하는", "입니다", "으로", "에서"
        }
        words = [w for w in words if w not in stopwords]
        
        counter = Counter(words)
        common_words = [word for word, count in counter.most_common(20)]
        
        # 3. 주 키워드 (Primary) 선정: Title 단어 중 본문 빈도수가 가장 높은 단어 (Brand Name 유추)
        primary_keyword = ""
        title_words = re.findall(r'[가-힣0-9a-zA-Z]+', title)
        
        # 의미 있는 Title 단어만 필터링
        candidates = [w for w in title_words if len(w) > 1 and w not in stopwords]
        
        if candidates:
            # 빈도수 대결
            best_candidate = candidates[0]
            max_freq = 0
            
            for cand in candidates:
                freq = counter[cand]
                if freq > max_freq:
                    max_freq = freq
                    best_candidate = cand
            
            primary_keyword = best_candidate
        
        # 만약 Title에서 못 찾으면 빈도수 1등을 주 키워드로
        if not primary_keyword and common_words:
            primary_keyword = common_words[0]

        # 4. 부 키워드 (Secondary) 선정: 빈도 상위 3개 (주 키워드 제외)
        secondary_keywords = []
        for w in common_words:
            if w != primary_keyword and w not in secondary_keywords:
                secondary_keywords.append(w)
            if len(secondary_keywords) >= 3:
                break
        
        return primary_keyword, secondary_keywords

    def run_brand_matching(self, brand_url: str):
        print(f"=== 브랜드 매칭 시스템 가동: {brand_url} ===")
        
        # 1. 웹사이트 분석
        html = self.fetch_page_content(brand_url)
        primary_kw, secondary_kws = self.extract_keywords(html)
        
        if not primary_kw:
            print("키워드 추출 실패. 종료합니다.")
            return

        print(f"=== 분석 결과 ===")
        print(f"  [의류] (필수 포함): {primary_kw}")
        print(f"  [패션 운동 육아]] (탐색 대상): {secondary_kws}")
        
        # 2. YouTube 수집기 연동 (Parallel Execution)
        print(f"\n=== 인플루언서 병렬 탐색 시작 ({len(secondary_kws)} threads) ===")
        
        MAX_WORKERS = 3
        all_results = []
        
        def process_keyword(sub_kw):
            """스레드별 개별 수집기 인스턴스 사용"""
            local_collector = YouTubeCollector()
            print(f"\n[Thread-Start] 탐색: '{sub_kw}' (필수: '{primary_kw}')")
            return local_collector.search_channels(sub_kw, context_keyword=primary_kw, limit=3)

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_kw = {executor.submit(process_keyword, kw): kw for kw in secondary_kws}
            
            for future in concurrent.futures.as_completed(future_to_kw):
                kw = future_to_kw[future]
                try:
                    data = future.result()
                    all_results.extend(data)
                    print(f"[Thread-End] '{kw}' 탐색 완료 ({len(data)}개 발견)")
                except Exception as exc:
                    print(f"'{kw}' 처리 중 예외 발생: {exc}")
                    
        print(f"\n=== 총 {len(all_results)}개의 유효 채널 확보 ===")

if __name__ == "__main__":
    matcher = BrandAnalyzer()
    TARGET_URL = "https://slim9.co.kr/?srsltid=AfmBOoo5i3gwH7dtaTc5SzjJcsd97u7LfS-lMfuqOcibGaNhrwmehdfJ"
    matcher.run_brand_matching(TARGET_URL)
