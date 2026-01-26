import pandas as pd
from sqlalchemy import create_engine
import json
import os

# =======================================================
# 설정
# =======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'default_info', 'db_config.txt')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'advanced_reports')

if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)
DB_URL = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['db_name']}?charset=utf8mb4"
engine = create_engine(DB_URL)


def analyze_macro_stats():
    print("오브젝트 및 방패 채굴 기여도 분석")

    query_basic = """
    SELECT 
        match_id,
        position, 
        champion, 
        win,
        team_dragon, 
        team_baron, 
        team_horde, 
        vision_score, 
        control_wards
    FROM match_data
    """
    df = pd.read_sql(query_basic, engine)

    if df.empty:
        print("데이터가 없습니다.")
        return

    # 2. 포탑 방패 데이터 가져오기
    print("포탑 방패 데이터 연동")

    query_plates = """
    SELECT 
        m.match_id,
        m.position,
        m.champion,
        COUNT(t.match_id) as turret_plates
    FROM match_data m
    JOIN timeline_objectives t 
        ON m.match_id = t.match_id 
        AND t.type = 'TURRET_PLATE_DESTROYED'
    WHERE 
        ((m.team = 'Blue' AND t.teamId = 100) OR (m.team = 'Red' AND t.teamId = 200))
        AND (
            (m.position = 'TOP' AND t.lane = 'TOP_LANE') OR
            (m.position = 'MIDDLE' AND t.lane = 'MID_LANE') OR
            (m.position = 'BOTTOM' AND t.lane = 'BOT_LANE') OR
            (m.position = 'UTILITY' AND t.lane = 'BOT_LANE')
        )
    GROUP BY m.match_id, m.position, m.champion
    """

    try:
        df_plates = pd.read_sql(query_plates, engine)
        df = pd.merge(df, df_plates, on=['match_id', 'position', 'champion'], how='left')
        df['turret_plates'] = df['turret_plates'].fillna(0)
        print(f"방패 데이터 병합 완료")

    except Exception as e:
        print(f"방패 데이터 연동 실패: {e}")
        df['turret_plates'] = 0

    # 3. 챔피언별 평균 계산
    champ_stats = df.groupby(['position', 'champion']).agg(
        avg_dragon=('team_dragon', 'mean'),
        avg_baron=('team_baron', 'mean'),
        avg_horde=('team_horde', 'mean'),
        avg_vision=('vision_score', 'mean'),
        avg_ward=('control_wards', 'mean'),
        avg_plates=('turret_plates', 'mean'),
        win_rate=('win', 'mean'),
        game_count=('win', 'count')
    ).reset_index()

    # 4. 포지션별 평균 계산
    pos_stats = df.groupby('position').agg(
        pos_dragon=('team_dragon', 'mean'),
        pos_baron=('team_baron', 'mean'),
        pos_horde=('team_horde', 'mean'),
        pos_vision=('vision_score', 'mean'),
        pos_ward=('control_wards', 'mean'),
        pos_plates=('turret_plates', 'mean')
    ).reset_index()

    # 5. 데이터 병합 & 격차 계산
    merged = pd.merge(champ_stats, pos_stats, on='position', how='left')

    merged['win_rate'] = (merged['win_rate'] * 100).round(2)

    merged['diff_dragon'] = (merged['avg_dragon'] - merged['pos_dragon']).round(3)
    merged['diff_baron'] = (merged['avg_baron'] - merged['pos_baron']).round(3)
    merged['diff_horde'] = (merged['avg_horde'] - merged['pos_horde']).round(3)
    merged['diff_vision'] = (merged['avg_vision'] - merged['pos_vision']).round(2)
    merged['diff_plates'] = (merged['avg_plates'] - merged['pos_plates']).round(2)

    final_df = merged[merged['game_count'] >= 5]

    save_path = os.path.join(OUTPUT_FOLDER, "champion_macro.csv")
    final_df.to_csv(save_path, index=False, encoding='utf-8-sig')

    print(f"저장 완료: {save_path}")

if __name__ == "__main__":
    analyze_macro_stats()