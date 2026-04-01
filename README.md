# Influencer Invite AI (INMA)

## 📌 프로젝트 소개 (Project Overview)
**Influencer Invite AI**는 YouTube Data API와 OpenAI 임베딩을 이용한 RAG(Retrieval-Augmented Generation) 엔진을 활용하여, 특정 브랜드나 상품에 가장 최적화된 **유튜브 인플루언서를 자동으로 탐색, 분석 및 추천**해 주는 AI 기반 시스템입니다. 

단순히 키워드만 일치하는 유튜버를 찾는 것을 넘어, 채널의 **참여도(Engagement Rate), 최근 활동성(Recency), 업로드 주기** 등을 정밀하게 스코어링하고 이메일 정보를 추출하여 효과적인 인플루언서 섭외(Invite) 워크플로우를 돕습니다.

---

## 🚀 주요 기능 (Key Features)

### 1. 지능형 유튜브 채널 수집 (`collector.py`)
- **다중 뎁스(Multi-depth) 필터링**: 구독자 수, 최근 영상 개수, 스팸/유해 채널(블랙리스트) 배제.
- **채널 심층 분석 (Deep Analysis)**: 평균 조회수 대비 구독자 비율(참여도 2% 이상), 최근 6개월 이내 활동 여부, 업로드 주기를 분석.
- **INMA Score 산출**: 데이터를 종합하여 채널의 가치 점수를 산출 및 DB(MongoDB) 적재.
- **API 비용 최적화 전략**: 가성비 높은 YouTube API 호출 전략 및 `youtube-transcript-api`를 활용한 자막 데이터 확보.

### 2. RAG 기반 시맨틱 벡터 검색 (`rag_engine.py`)
- **OpenAI 텍스트 임베딩 (`text-embedding-3-small`)**: 인플루언서의 최근 영상, 설명, 추출된 키워드 등 문맥 정보를 벡터로 변환.
- **MongoDB Atlas Vector Search**: 자연어 질문(예: *"패션 하울 영상을 주로 올리는 유튜버 추천해줘"*)에 대해 가장 의미적으로 유사한 인플루언서나 브랜드/제품을 즉시 검색 및 매칭.

### 3. FastAPI 기반 프론트엔드 연동 지원
- `inma-frontend` 와 연동하기 위한 백엔드 API (FastAPI, Uvicorn) 아키텍처 제공.

---

## 🛠 기술 스택 (Tech Stack)

### Backend & AI
- **Language**: Python 3.11+
- **Framework**: FastAPI (uvicorn)
- **Database**: MongoDB (Atlas Vector Search 지원), `pymongo`
- **AI/LLM**: OpenAI API 
- **Data Scraping**: Google YouTube Data API v3, `youtube-transcript-api`, `beautifulsoup4`

### Package Management
- `uv` 패키지 매니저 (`pyproject.toml`)

---

## ⚙️ 설치 및 실행 방법 (Getting Started)

### 1. 패키지 설치
이 프로젝트는 최신 파이썬 패키지 매니저인 `uv`를 사용합니다.
```bash
# 의존성 설치
uv sync
```

### 2. 환경 변수 설정 (.env)
루트 디렉토리에 `.env` 파일을 생성하고 다음 값을 채워야 합니다.
```ini
YOUTUBE_API_KEY=your_youtube_api_key_here
MONGO_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/
MONGO_DB_NAME=inma_db
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. 모듈 실행

**인플루언서 데이터 수집 스크립트 실행:**
```bash
python -m src.influencer_inviteai.collector
```

**RAG 엔진 임베딩 생성 및 벡터 인덱싱:**
```bash
python -m src.influencer_inviteai.run_indexing
```

**테스트 스크립트 실행:**
작동 및 데이터가 정상적으로 들어갔는지 확인할 수 있습니다.
```bash
python verify_db.py     # MongoDB 데이터 체크
python verify_rag.py    # Vector Search 및 RAG 검색 검증
```

---

## 👨‍💻 작성자 (Author)
- **김동환** (kimdonghwandeveloper@gmail.com)
