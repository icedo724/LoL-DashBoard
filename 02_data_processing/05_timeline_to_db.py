import pandas as pd
from sqlalchemy import create_engine, text
import os
import json
import time

# =======================================================
# 설정
# =======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'default_info', 'db_config.txt')

FILES_MAP = {
    os.path.join(BASE_DIR, "raw_data", "timeline_data", "timeline_items.csv"): "timeline_items",
    os.path.join(BASE_DIR, "raw_data", "timeline_data", "timeline_skills.csv"): "timeline_skills",
    os.path.join(BASE_DIR, "raw_data", "timeline_data", "timeline_kills.csv"): "timeline_kills",
    os.path.join(BASE_DIR, "raw_data", "timeline_data", "timeline_objectives.csv"): "timeline_objectives",
    os.path.join(BASE_DIR, "raw_data", "timeline_data", "timeline_wards.csv"): "timeline_wards"
}

CHUNK_SIZE = 5000

if not os.path.exists(CONFIG_FILE):
    print(f"'{CONFIG_FILE}' 파일이 없습니다!")
    exit()

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

DB_URL = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['db_name']}?charset=utf8mb4"

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20
)


# =======================================================
# 데이터 보정 함수
# =======================================================
def clean_objectives_chunk(df):
    if 'teamId' in df.columns:
        mixed_mask = pd.to_numeric(df['teamId'], errors='coerce').isna()
        if mixed_mask.any():
            if 'lane' in df.columns:
                bad_team_ids = df.loc[mixed_mask, 'teamId']
                bad_lanes = df.loc[mixed_mask, 'lane']
                df.loc[mixed_mask, 'teamId'] = bad_lanes
                df.loc[mixed_mask, 'lane'] = bad_team_ids
        df['teamId'] = pd.to_numeric(df['teamId'], errors='coerce')
    return df


# =======================================================
# 인덱스 생성 함수
# =======================================================
def add_indexes(table_name):
    print(f"   🔨 '{table_name}' 인덱스 생성 및 최적화")
    with engine.connect() as con:
        try:
            con.execute(text(f"CREATE INDEX idx_{table_name}_match ON {table_name} (match_id(20))"))

            if table_name == "timeline_items":
                con.execute(text(f"CREATE INDEX idx_item_id ON {table_name} (itemId)"))
                con.execute(text(f"CREATE INDEX idx_item_part ON {table_name} (participantId)"))
                res = con.execute(text(f"SHOW COLUMNS FROM {table_name} LIKE 'type'"))
                if res.fetchone():
                    con.execute(text(f"CREATE INDEX idx_item_type ON {table_name} (type(15))"))

            elif table_name == "timeline_skills":
                con.execute(text(f"CREATE INDEX idx_skill_part ON {table_name} (participantId)"))

            elif table_name == "timeline_objectives":
                con.execute(text(f"CREATE INDEX idx_obj_type ON {table_name} (type(15), subtype(20))"))

            elif table_name == "timeline_wards":
                con.execute(text(f"CREATE INDEX idx_ward_type ON {table_name} (type(15))"))
                con.execute(text(f"CREATE INDEX idx_ward_map ON {table_name} (x, y)"))

            print(f"인덱스 적용 완료")
        except Exception as e:
            pass


# =======================================================
# 실행
# =======================================================
def main():
    for csv_file, table_name in FILES_MAP.items():
        if not os.path.exists(csv_file):
            print(f"⚠️ '{os.path.basename(csv_file)}' 파일이 없어서 건너뜁니다.")
            continue

        print(f"\n📂 '{os.path.basename(csv_file)}' -> DB 테이블 '{table_name}'")
        start_time = time.time()

        try:
            total_rows = 0
            for i, chunk in enumerate(pd.read_csv(csv_file, chunksize=CHUNK_SIZE, low_memory=False)):
                if table_name == "timeline_objectives":
                    chunk = clean_objectives_chunk(chunk)
                if table_name == "timeline_wards":
                    if 'creatorId' in chunk.columns:
                        chunk['creatorId'] = chunk['creatorId'].fillna(0).astype(int)
                mode = 'replace' if i == 0 else 'append'
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        chunk.to_sql(name=table_name, con=engine, if_exists=mode, index=False)
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"전송 실패 (재시도 {attempt + 1}/{max_retries}) 잠시 대기")
                            time.sleep(2)
                            engine.dispose()
                        else:
                            raise e

                total_rows += len(chunk)
                print(f"   Writing chunk {i + 1} ({len(chunk):,} rows)", end='\r')

            print(f"\n적재 완료! (총 {total_rows:,} 행)")

            # 인덱스 생성
            add_indexes(table_name)

        except Exception as e:
            print(f"\n'{table_name}'에러: {e}")

        print(f"소요 시간: {int(time.time() - start_time)}초")

    print("\n적재 완료")


if __name__ == "__main__":
    main()