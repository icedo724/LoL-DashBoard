import pandas as pd
from sqlalchemy import create_engine
import os
import json

# =======================================================
# 설정
# =======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'default_info', 'db_config.txt')
EXPORT_FOLDER = os.path.join(BASE_DIR, 'item_reports')

if not os.path.exists(CONFIG_FILE):
    print("설정 파일이 없습니다.")
    exit()

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

DB_URL = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['db_name']}?charset=utf8mb4"
engine = create_engine(DB_URL)

POSITIONS = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']

if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)

print(f"아이템 분석\n")

# =======================================================
# 데이터 추출 및 분석
# =======================================================
for pos in POSITIONS:
    file_pos_name = "SUPPORT" if pos == "UTILITY" else pos
    print(f"[포지션: {file_pos_name}] 데이터 정밀 분석", end=" ")

    sql = f"""
        WITH RealPurchases AS (
            SELECT 
                m.champion,
                t.itemId,
                m.win,
                t.timestamp
            FROM timeline_items t
            JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
            WHERE m.position = '{pos}'
              AND t.type = 'ITEM_PURCHASED'
              AND NOT EXISTS (
                  SELECT 1 FROM timeline_items undo
                  WHERE undo.match_id = t.match_id
                    AND undo.participantId = t.participantId
                    AND undo.itemId = t.itemId
                    AND undo.type = 'ITEM_UNDO'
                    AND undo.timestamp >= t.timestamp
                    AND undo.timestamp <= t.timestamp + 10000 
              )
        )
        SELECT 
            champion,
            itemId as item_id, 
            COUNT(*) as pick_count,
            ROUND(AVG(win) * 100, 2) as win_rate,
            ROUND(AVG(timestamp) / 60000, 1) as avg_purchase_time_min 
        FROM RealPurchases
        WHERE itemId != 0 
        GROUP BY champion, itemId
        HAVING pick_count >= 10 
        ORDER BY champion ASC, pick_count DESC;
    """

    try:
        df = pd.read_sql(sql, con=engine)

        if df.empty:
            print("데이터 없음 (Skip)")
            continue
        filename = f"{file_pos_name}_ItemDetail.csv"
        df.to_csv(os.path.join(EXPORT_FOLDER, filename), index=False, encoding='utf-8-sig')
        print("완료")

    except Exception as e:
        print(f"\n쿼리 실행 중 에러: {e}")

print("\n" + "=" * 50)
print("분석 완료")
print("=" * 50)