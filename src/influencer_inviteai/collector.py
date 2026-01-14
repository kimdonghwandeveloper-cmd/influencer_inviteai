import os
import re
import pymongo
from pymongo import MongoClient
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from dotenv import load_dotenv
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
import concurrent.futures

# 환경 변수 로드 (.env 파일)
load_dotenv()

class YouTubeCollector:
    """
    YouTube API 비용 최적화(Playlist Hacking) 전략을 사용하여 데이터를 수집하는 클래스.
    MongoDB에 수집된 인플루언서 및 콘텐츠 정보를 저장합니다.
    """

    def __init__(self):
        """
        API 클라이언트 및 데이터베이스 연결을 초기화합니다.
        """
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        self.mongo_uri = os.getenv("MONGO_URI")

        if not self.youtube_api_key:
            raise ValueError("환경 변수 YOUTUBE_API_KEY가 설정되지 않았습니다.")
        
        # YouTube Data API 클라이언트 생성
        self.youtube = build("youtube", "v3", developerKey=self.youtube_api_key)

        # MongoDB 클라이언트 초기화 (Lazy Connection)
        self.db = None
        if self.mongo_uri:
            try:
                self.client = MongoClient(self.mongo_uri)
                self.db = self.client["inma_db"]
                print("MongoDB에 연결되었습니다.")
            except Exception as e:
                print(f"경고: MongoDB 연결 실패. 데이터가 저장되지 않습니다. 오류: {e}")
        else:
            print("경고: MONGO_URI가 설정되지 않았습니다. 데이터 저장이 비활성화됩니다.")

    def get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        채널의 기본 통계 및 'uploads' 플레이리스트 ID를 조회합니다.
        비용: 1 Unit (channels.list)
        
        Args:
            channel_id: 유튜브 채널 ID

        Returns:
            채널 정보 사전(Dictionary) 또는 실패 시 None
        """
        try:
            request = self.youtube.channels().list(
                part="snippet,contentDetails,statistics",
                id=channel_id
            )
            response = request.execute()

            if not response.get("items"):
                print(f"채널을 찾을 수 없습니다: {channel_id}")
                return None

            item = response["items"][0]
            
            # 이메일 추출 (설명란 정규식 검색)
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', item["snippet"]["description"])
            email_text = ", ".join(set(emails)) if emails else None
            
            # 정보 추출 및 구조화
            info = {
                "_id": item["id"], # 채널 ID를 문서 PK로 사용
                "platform": "youtube",
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "email": email_text,
                "custom_url": item["snippet"].get("customUrl"),
                "country": item["snippet"].get("country"),
                "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
                "stats": {
                    "subscribers": int(item["statistics"].get("subscriberCount", 0)),
                    "total_views": int(item["statistics"].get("viewCount", 0)),
                    "video_count": int(item["statistics"].get("videoCount", 0)),
                },
                "inma_score": 0.0, # 추후 계산될 자체 품질 점수
                "category": [], 
                "last_updated": datetime.utcnow()
            }
            return info

        except Exception as e:
            print(f"채널 정보 가져오기 실패 ({channel_id}): {e}")
            return None

    def get_recent_videos(self, playlist_id: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        채널의 'uploads' 플레이리스트에서 최신 동영상 목록을 가져옵니다.
        (검색 API 대신 사용하여 비용을 절약합니다.)
        비용: 1 Unit (playlistItems.list)

        Args:
            playlist_id: 채널의 'uploads' 플레이리스트 ID
            max_results: 가져올 영상 개수 (기본 10개)

        Returns:
            동영상 정보 리스트
        """
        videos = []
        try:
            request = self.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=max_results
            )
            response = request.execute()

            for item in response.get("items", []):
                video_id = item["contentDetails"]["videoId"]
                
                # 기본 메트릭 초기화 (나중에 videos.list로 업데이트 필요)
                metrics = {
                    "view_count": 0,
                    "like_count": 0,
                    "comment_count": 0
                }
                
                video_info = {
                    "_id": video_id,
                    "channel_id": item["snippet"]["channelId"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                    "transcript_summary": "", # 자막은 별도 수집
                    "visual_description": "", # AI 비전 분석용
                    "embedding": [], # RAG 벡터 데이터
                    "tags": [], 
                    "metrics": metrics,
                    "analysis": {
                        "mood": "",
                        "category": ""
                    }
                }
                videos.append(video_info)

        except Exception as e:
            print(f"플레이리스트 항목 가져오기 실패 ({playlist_id}): {e}")
        
        return videos

    def get_video_transcript(self, video_id: str) -> str:
        """
        youtube-transcript-api를 사용하여 동영상의 자막을 가져옵니다.
        (API 할당량을 사용하지 않음)
        
        Args:
            video_id: 동영상 ID

        Returns:
            자막 텍스트 전체 (실패 시 빈 문자열)
        """
        try:
            # 한국어 우선, 없으면 영어 시도
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            
            # 텍스트만 합침
            full_text = " ".join([t['text'] for t in transcript_list])
            return full_text

        except (TranscriptsDisabled, NoTranscriptFound):
            print(f"자막이 없거나 비활성화된 영상입니다: {video_id}")
            return ""
        except Exception as e:
            print(f"자막 가져오기 오류 ({video_id}): {e}")
            return ""

    def save_to_mongo(self, collection_name: str, data: Dict[str, Any]) -> bool:
        """
        MongoDB 컬렉션에 데이터를 저장(Upsert)합니다.
        
        Args:
            collection_name: 'influencers' 또는 'contents'
            data: 저장할 문서 데이터 ('_id' 필드 필수)

        Returns:
            성공 여부 (True/False)
        """
        if self.db is None:
            return False
        
        try:
            collection = self.db[collection_name]
            # _id를 기준으로 덮어쓰기 (Upsert)
            collection.update_one(
                {"_id": data["_id"]},
                {"$set": data},
                upsert=True
            )
            title = data.get('title', data['_id'])
            print(f"[{collection_name}] 저장 성공: {title}")
            return True
        except Exception as e:
            print(f"MongoDB 저장 실패: {e}")
            return False

    def _fetch_video_stats(self, video_ids: List[str]) -> Dict[str, Dict]:
        """
        [내부함수] 여러 동영상의 상세 통계(조회수, 좋아요 등)를 한 번에 조회합니다.
        비용: 1 Unit (videos.list) - 배치 조회로 효율성 증대
        """
        stats_map = {}
        if not video_ids:
            return stats_map
            
        try:
            request = self.youtube.videos().list(
                part="statistics",
                id=",".join(video_ids)
            )
            response = request.execute()
            for item in response.get("items", []):
                stats = item["statistics"]
                stats_map[item["id"]] = {
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0))
                }
        except Exception as e:
            print(f"비디오 통계 조회 실패: {e}")
        return stats_map

    def deep_analyze_channel(self, channel_info: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict]]:
        """
        [3차 필터] 채널 심층 분석
        최근 영상들의 활동성(Recency)과 참여도(Engagement)를 분석하여 합격 여부를 결정합니다.
        
        Returns:
            (업데이트된 채널정보, 분석에 사용된 영상리스트) 튜플
            * 실패 시 (None, []) 반환
        """
        uploads_id = channel_info.get("uploads_playlist_id")
        if not uploads_id:
            return None, []
            
        # 1. 최근 영상 5개 가져오기
        videos = self.get_recent_videos(uploads_id, max_results=5)
        if not videos:
            return None, []
            
        # 2. 활동성(Recency) 및 업로드 주기(Cycle) 분석
        video_dates = [datetime.strptime(v["published_at"], "%Y-%m-%dT%H:%M:%SZ") for v in videos]
        latest_date = video_dates[0]
        days_since_upload = (datetime.utcnow() - latest_date).days
        
        # [조건 변경] 6개월(180일) 이상 미업로드 시 패널티 부여 (완전 탈락은 1년 기준)
        recency_score = 1.0
        if days_since_upload > 365:
            print(f"  [탈락] 활동 중단: 마지막 업로드가 {days_since_upload}일 전입니다.")
            return None, []
        elif days_since_upload > 180:
            print(f"  [경고] 휴면 의심: 마지막 업로드가 {days_since_upload}일 전입니다. (점수 감점)")
            recency_score = 0.5 # 점수 50% 삭감
            
        # 업로드 주기 계산 (평균 간격)
        intervals = []
        for i in range(len(video_dates)-1):
            diff = (video_dates[i] - video_dates[i+1]).days
            intervals.append(diff)
            
        avg_interval = sum(intervals) / len(intervals) if intervals else 30 # 기본값 30일
        
        # 3. 참여도(Engagement) 계산을 위한 통계 조회
        video_ids = [v["_id"] for v in videos]
        stats_map = self._fetch_video_stats(video_ids) # 배치 조회 (최적화)
        
        total_views = 0
        valid_videos_count = 0
        
        for v in videos:
            stats = stats_map.get(v["_id"])
            if stats:
                total_views += stats["view_count"]
                valid_videos_count += 1
                v["metrics"] = stats # 영상 객체에 통계 정보 병합 (재사용)
        
        if valid_videos_count == 0:
            return None, []
            
        avg_views = total_views / valid_videos_count
        subscribers = channel_info["stats"]["subscribers"]
        
        # 참여도 계산 (평균 조회수 / 구독자 수)
        if subscribers == 0:
            engagement_rate = 0
        else:
            engagement_rate = (avg_views / subscribers) * 100
            
        # 4. 참여도 체크: 최소 2% 이상
        if engagement_rate < 2.0:
            print(f"  [탈락] 참여도 부족: {engagement_rate:.2f}% (평균 조회수: {avg_views:.0f})")
            return None, []
            
        # 5. INMA Score 계산 (랭킹용)
        # 기본 점수: 참여도(%) * 10
        # 주기 보너스: 주기가 짧을수록(자주 올릴수록) 가산점 (최대 2배)
        # 최신성 페널티: recency_score 적용
        
        consistency_multiplier = 1.0
        if avg_interval <= 7: consistency_multiplier = 1.5 # 주 1회 이상
        elif avg_interval <= 14: consistency_multiplier = 1.2 # 격주 1회 이상
        
        final_score = (engagement_rate * 10) * consistency_multiplier * recency_score
        
        print(f"  [합격] Score: {final_score:.1f} | 참여도: {engagement_rate:.2f}% | 주기: {avg_interval:.1f}일 | 최신: {days_since_upload}일 전")
        
        # [데이터 구조 변경] 영상 개별 저장 대신, 채널 정보에 요약본 통합 (RAG 최적화)
        recent_titles = [v["title"] for v in videos[:5]] # 최신 5개 제목
        
        # 키워드 단순 추출 (제목에서 명사형 단어만 대충 뽑음 - 추후 RAG/LLM으로 고도화)
        all_text = " ".join(recent_titles)
        keywords = set(re.findall(r'[가-힣a-zA-Z]{2,}', all_text))
        
        channel_info["content_summary"] = {
            "recent_titles": recent_titles,
            "extracted_keywords": list(keywords)[:10], # 상위 10개만
            "latest_video_id": videos[0]["_id"],
            "last_upload_date": videos[0]["published_at"]
        }

        # [최종 스키마 정제] 사용자 요청 필드 중심으로 재구성
        # 요청: 이메일, 아이디(Title), 설명, 평균 조회수, 구독자, 업로드 주기
        final_profile = {
            "_id": channel_info["_id"],
            "title": channel_info["title"],            # 아이디 (채널명)
            "description": channel_info["description"],# 설명
            "email": channel_info["email"],            # 이메일
            "stats": {
                "subscribers": channel_info["stats"]["subscribers"], # 구독자
                "avg_views": int(avg_views),                         # 평균 조회수
                "upload_cycle": round(avg_interval, 1)               # 업로드 주기
            },
            # RAG/검색을 위한 최소한의 메타데이터 유지
            "keywords": list(keywords)[:10],
            "inma_score": round(final_score, 2),
            "last_analyzed": datetime.utcnow()
        }
        
        return final_profile, videos

    def search_channels(self, query: str, context_keyword: str = None, limit: int = 5) -> List[Tuple[Dict, List[Dict]]]:
        """
        키워드로 채널을 검색하고, 필터링 파이프라인(기본->심층)을 통과한 채널만 반환합니다.
        context_keyword가 주어지면, 채널 제목이나 설명에 해당 단어가 포함되어야만 합격시킵니다.
        
        Pipeline: 
        1. Discovery(검색) -> 2. Keyword Filter(문맥) -> 3. Metadata Filter(기본) -> 4. Deep Analysis(심층)
        
        Args:
            query: 검색 키워드 (API 쿼리용)
            context_keyword: 필수 포함 단어 (예: '의류')
            limit: 찾을 목표 채널 수

        Returns:
            (채널정보, 영상리스트) 튜플의 리스트
        """
        print(f"검색 시작: 쿼리 '{query}' + 필수포함 '{context_keyword}' (목표: {limit}개)...")
        results = []
        next_page_token = None
        
        # 1000명의 후보를 검토하기 위해 시도 횟수 증가 (20 Pages * 50 Results = 1000 Candidates)
        max_attempts = 20 
        attempts = 0

        while len(results) < limit and attempts < max_attempts:
            attempts += 1
            try:
                # 1. 탐색 (Cost: 100) - 가장 비싼 호출
                request = self.youtube.search().list(
                    part="snippet",
                    maxResults=50, # 한 번에 최대한 많이 가져와서 가성비 높임
                    order="viewCount",
                    type="channel",
                    q=query,
                    regionCode="KR", 
                    relevanceLanguage="ko",
                    pageToken=next_page_token
                )
                response = request.execute()
                items = response.get("items", [])
                print(f"  [DEBUG] API returned {len(items)} items for page {attempts}.")
                if not items:
                    print("  [DEBUG] No items found in this page.")
                    break

                # 2. 배치 처리를 위한 ID 추출
                candidate_ids = [item["id"]["channelId"] for item in items]
                
                # 3. 기본 통계 일괄 조회 (Cost: 1)
                stats_request = self.youtube.channels().list(
                    part="snippet,contentDetails,statistics",
                    id=",".join(candidate_ids)
                )
                stats_response = stats_request.execute()

                for item in stats_response.get("items", []):
                    if len(results) >= limit:
                        break
                    
                    # 이메일 추출
                    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', item["snippet"]["description"])
                    email_text = ", ".join(set(emails)) if emails else None
                    if email_text:
                        print(f"  [Info] 이메일 발견: {email_text}")

                    # 채널 정보 객체 생성
                    channel_info = {
                        "_id": item["id"],
                        "platform": "youtube",
                        "title": item["snippet"]["title"],
                        "description": item["snippet"]["description"],
                        "email": email_text,
                        "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
                        "stats": {
                            "subscribers": int(item["statistics"].get("subscriberCount", 0)),
                            "video_count": int(item["statistics"].get("videoCount", 0)),
                            "view_count": int(item["statistics"].get("viewCount", 0)),
                        },
                        "inma_score": 0.0,
                        "category": [],
                        "last_updated": datetime.utcnow()
                    }
                    
                    # [Safety Mechanism] 블랙리스트 필터 (유해/부적절 키워드 제외)
                    BLACKLIST = ["도박", "코인", "주식", "정치", "가상화폐", "토토", "홀덤", "카지노", "FX", "성인", "19금"]
                    full_text = channel_info["title"] + " " + channel_info["description"]
                    if any(bad_word in full_text for bad_word in BLACKLIST):
                        print(f"  [차단] 블랙리스트 키워드 발견 ({channel_info['title']})")
                        continue

                    # [0차 필터] 문맥(주 키워드) 포함 여부 검사 (옵션으로 변경)
                    # 브랜드 매칭 시, 브랜드명이 반드시 있어야 하는 것은 아님 (경쟁사나 카테고리 유튜버도 찾아야 함)
                    if context_keyword:
                        # 너무 엄격하면 0건이 되므로, '점수 가산' 방식으로 변경하거나 로깅만 수행
                        if context_keyword in full_text:
                            channel_info["inma_score"] += 10 # 가산점
                        # else:
                        #     continue # 주석 처리: 엄격 필터 해제

                    # [1차 필터] 기본 조건 검사 - 디버그 로그 추가
                    if channel_info["stats"]["subscribers"] < 1000:
                        print(f"  [Skip] 구독자 미달: {channel_info['stats']['subscribers']} < 1000 ({channel_info['title']})")
                        continue
                    if channel_info["stats"]["video_count"] < 5:
                        print(f"  [Skip] 영상 수 미달: {channel_info['stats']['video_count']} < 5 ({channel_info['title']})")
                        continue
                    if not channel_info["description"].strip():
                        print(f"  [Skip] 설명 없음 ({channel_info['title']})")
                        continue
                        
                    print(f"후보 발견: {channel_info['title']} (구독자: {channel_info['stats']['subscribers']}) - 분석 중...")
                    
                    # [2차 필터] 심층 분석 (Cost 발생: Playlist + Video Stats)
                    # 여기서 반환된 videos는 이미 상세 metrics가 채워져 있음 (최적화 포인트)
                    analyzed_channel, analyzed_videos = self.deep_analyze_channel(channel_info)
                    
                    if analyzed_channel:
                        print(f" >> [최종 합격]: {analyzed_channel['title']}")
                        
                        # 채널 DB 저장 (모든 정보가 통합된 analyzed_channel 저장)
                        self.save_to_mongo("influencers", analyzed_channel)
                        
                        # [변경] 영상 DB 저장 로직 제거 (인플루언서 정보에 통합)
                        # for vid in analyzed_videos:
                        #     self.save_to_mongo("contents", vid)
                            
                        results.append((analyzed_channel, analyzed_videos))

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break
            
            except Exception as e:
                print(f"검색 중 오류 발생: {e}")
                break
        
        print(f"검색 완료. 총 {len(results)}개의 유효 채널을 찾았습니다.")
        return results

# 메인 실행 블록
# 메인 실행 블록
# 메인 실행 블록
if __name__ == "__main__":
    # 전략: 넓게 찾고(Broad Search) -> 좁히기(Relavance Filter)
    # 1. API에는 '육아', '운동' 만 검색 (결과 많이 나옴)
    # 2. 코드 레벨에서 '의류' 라는 단어가 있는지 검사
    
    PRIMARY_KEYWORD = "의류" 
    SECONDARY_KEYWORDS = ["패션", "운동", "육아"]
    
    MAX_WORKERS = 3 
    
    print(f"=== INMA 검색 엔진 가동: Broad Search 전략 ===")
    print(f"검색어(API): {SECONDARY_KEYWORDS}")
    print(f"필수검증(주 키워드): {PRIMARY_KEYWORD}")
    
    all_qualified_data = []

    def process_query(target_keyword):
        """
        단일 쿼리에 대해 수집기 인스턴스를 생성하고 검색을 수행하는 래퍼 함수
        """
        local_collector = YouTubeCollector()
        print(f"\n[Thread-Start] 카테고리 '{target_keyword}' 탐색 시작")
        # API에는 target_keyword("육아")만 던지고, context_keyword로 "의류"를 넘겨서 필터링
        return local_collector.search_channels(target_keyword, context_keyword=PRIMARY_KEYWORD, limit=3) 

    # ThreadPoolExecutor를 사용하여 병렬 실행
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_query = {executor.submit(process_query, kw): kw for kw in SECONDARY_KEYWORDS}
        
        for future in concurrent.futures.as_completed(future_to_query):
            kw = future_to_query[future]
            try:
                data = future.result()
                all_qualified_data.extend(data)
                print(f"[Thread-End] 카테고리 '{kw}' 탐색 완료 ({len(data)}개 발견)")
            except Exception as exc:
                print(f"카테고리 '{kw}' 처리 중 예외 발생: {exc}")

    print(f"\n=== 총 {len(all_qualified_data)}개의 유효 채널 확보. 자막(Content) 수집 시작 ===")
    
    # 자막 데이터 보강
    collector = YouTubeCollector() 
    
    for channel, videos in all_qualified_data:
        print(f"\n[채널] {channel['title']} 자막 수집 중...")
        
        for video in videos:
            print(f"    - 자막 추출: {video['title']}")
            transcript = collector.get_video_transcript(video["_id"])
            
            video["transcript_summary"] = transcript[:500] + "..." if transcript else ""
            collector.save_to_mongo("contents", video)

    print("\n=== 모든 수집 작업 완료 ===")
