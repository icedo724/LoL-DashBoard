# League of Legends High-Rating Players Data Analytics

## 프로젝트 개요
이 프로젝트는 라이엇 게임즈 API를 활용하여 챌린저, 그랜드마스터, 마스터 등 최상위권 플레이어들의 매치 데이터를 수집합니다. 수집된 데이터를 관계형 데이터베이스(MySQL)로 구축하고, 통계적 기법을 통해 메타를 분석하며, Streamlit 대시보드를 통해 결과를 시각화합니다.

## 주요 기능

### 1. 챔피언 티어 분석
- 승률, 픽률, 밴률을 기반으로 챔피언 티어를 산정합니다.
- 승률과 픽밴률에 가중치를 부여하는 자체 OP Score 알고리즘을 적용합니다.
- 표본 수에 따라 메이저(정석)와 마이너(연구용) 데이터를 분리하여 신뢰도를 높입니다.

### 2. 챔피언 심층 분석
- **빌드 경로:** 시작 아이템, 핵심 3코어 빌드, 신발 선택에 따른 승률을 분석합니다.
- **스킬 트리:** 타임라인 데이터를 분석하여 스킬 마스터 순서(예: Q > E > W)를 도출합니다.
- **룬 & 스펠:** 가장 효율적인 룬 세팅과 소환사 주문 조합을 식별합니다.
- **파워 스파이크:** 코어 아이템 완성 시간을 분 단위로 시각화하여 챔피언의 전성기를 파악합니다.
- **상성:** 라인별 상대 챔피언과의 승률 데이터를 제공합니다.

### 3. 운영 및 오브젝트 분석
- **포탑 방패:** 챔피언별 평균 방패 채굴량을 포지션 평균과 비교합니다.
- **오브젝트 기여:** 드래곤, 바론, 공허 유충 처치 관여율과 승률의 상관관계를 분석합니다.
- **시야:** 분당 시야 점수 및 제어 와드 구매 횟수를 분석합니다.

### 4. 메타 분석
- **진영 밸런스:** 블루팀과 레드팀 간의 승률 격차를 분석합니다.
- **게임 양상:** 게임 시간 분포와 주요 오브젝트 획득 시 승률 변화를 추적합니다.

## 기술 스택
- **언어:** Python 3.10+
- **데이터 수집:** Riot Games API, Requests
- **데이터베이스:** MySQL, SQLAlchemy
- **데이터 분석:** Pandas, NumPy, SciPy (통계 검정)
- **시각화:** Streamlit, Plotly Express

## 폴더 구조
```
LoL-Challenger-Analytics/
├── data_collection/        # Riot API 데이터 수집 스크립트
├── data_processing/        # JSON 데이터 파싱 및 DB 적재 스크립트
├── analysis/               # 통계 분석 및 CSV 리포트 생성 스크립트
├── app/                    # Streamlit 대시보드 애플리케이션
├── reports/                # 대시보드에서 사용하는 결과 CSV 파일 저장소
├── default_info/           # 설정 파일 (API 키, DB 정보) - 깃허브 제외됨
├── requirements.txt        # 파이썬 라이브러리 목록
└── README.md               # 프로젝트 문서
```

## 설치 및 설정

### 1. 환경 설정

#### 저장소 복제

````git clone [Repository URL]````

#### 가상 환경 생성
````python -m venv .venv````

#### 가상 환경 활성화
#### Windows:
````.venv\Scripts\activate````
#### Mac/Linux:
````source .venv/bin/activate````

#### 필수 라이브러리 설치
````pip install -r requirements.txt````

### 2. 설정 파일 구성
프로젝트 최상위 경로에 `default_info` 폴더를 생성하고 다음 두 파일을 추가해야 합니다.

**default_info/api.txt**
- Riot Games Developer Portal에서 발급받은 API Key를 입력합니다.

**default_info/db_config.txt**
- 데이터베이스 접속 정보를 JSON 형식으로 저장합니다.
````
{
  "host": "localhost",
  "user": "root",
  "password": "your_password",
  "db_name": "lol_analytics"
}
````

## 실행 방법

데이터 수집부터 시각화까지 다음 순서대로 스크립트를 실행합니다.

### 1단계: 데이터 수집
랭커 목록을 확보하고 매치 및 타임라인 데이터를 수집합니다.

````
python data_collection/01_get_rankers.py
python data_collection/02_get_matches.py
python data_collection/03_get_timelines.py
````

### 2단계: 데이터 전처리 및 DB 적재
수집된 JSON 데이터를 파싱하여 MySQL 데이터베이스에 저장합니다.
````
python data_processing/04_clean_data.py
python data_processing/05_timeline_upload.py
````

### 3단계: 통계 분석 (CSV 생성)
DB 데이터를 기반으로 각종 지표를 분석하여 `reports` 폴더에 CSV 파일을 생성합니다.
````
python analysis/06_tier_by_postion.py
python analysis/07_item_details.py
python analysis/08_advanced.py
python analysis/09_champion_macro.py
python analysis/10_meta_analyze.py
python analysis/11_timeline_analyze.py
````

### 4단계: 대시보드 실행
분석된 데이터를 바탕으로 웹 대시보드를 실행합니다.

````streamlit run app/dashboard.py````