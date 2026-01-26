import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import os
import json

# =======================================================
# ⚙️ 설정
# =======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'default_info', 'db_config.txt')
EXPORT_FOLDER = os.path.join(BASE_DIR, 'tier_reports')

if not os.path.exists(CONFIG_FILE):
    print(f"설정 파일이 없습니다: {CONFIG_FILE}")
    exit()

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

DB_URL = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['db_name']}?charset=utf8mb4"
engine = create_engine(DB_URL)

POSITIONS = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']

# 폴더 생성
if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)
    os.makedirs(os.path.join(EXPORT_FOLDER, 'Major'), exist_ok=True)
    os.makedirs(os.path.join(EXPORT_FOLDER, 'Minor'), exist_ok=True)


def analyze_tiers():
    print("[티어 분석기] 시작\n")

    # =======================================================
    # 1. 글로벌 밴률 계산
    # =======================================================
    print("[1/2] 글로벌 밴률 계산 중")

    sql_total = "SELECT COUNT(DISTINCT match_id) FROM match_data"
    total_matches = pd.read_sql(sql_total, engine).iloc[0, 0]
    print(f"   - 총 매치 수: {total_matches:,} 게임")

    if total_matches == 0:
        print("데이터 부족으로 종료.")
        return

    # 중복 제거된 밴 데이터 로드
    sql_ban = "SELECT DISTINCT match_id, ban_1, ban_2, ban_3, ban_4, ban_5 FROM match_data"
    df_bans = pd.read_sql(sql_ban, engine)

    # Wide -> Long 변환
    bans_melted = df_bans.melt(id_vars=['match_id'], value_vars=['ban_1', 'ban_2', 'ban_3', 'ban_4', 'ban_5'],
                               value_name='champion')
    ban_counts = bans_melted['champion'].value_counts().reset_index()
    ban_counts.columns = ['champion', 'ban_count']

    # 밴률 계산
    ban_counts['champion'] = ban_counts['champion'].astype(str)
    ban_counts['ban_rate'] = (ban_counts['ban_count'] / total_matches) * 100

    # =======================================================
    # 2. 포지션별 티어 산정
    # =======================================================
    print(f"\n[2/2] 포지션별 티어 분석 시작")

    for pos in POSITIONS:
        file_pos_name = "SUPPORT" if pos == "UTILITY" else pos
        print(f"{file_pos_name}", end=" ")

        # 데이터 조회
        sql_pick = f"""
            SELECT champion, COUNT(*) as pick_count, SUM(win) as win_count
            FROM match_data 
            WHERE position = '{pos}'
            GROUP BY champion
        """
        stats = pd.read_sql(sql_pick, engine)

        if stats.empty:
            print("데이터 없음 (Pass)")
            continue

        stats['champion'] = stats['champion'].astype(str)

        # 승률/픽률 계산
        stats['win_rate'] = (stats['win_count'] / stats['pick_count']) * 100
        stats['pick_rate'] = (stats['pick_count'] / total_matches) * 100

        # 밴률 병합
        stats = pd.merge(stats, ban_counts[['champion', 'ban_rate']], on='champion', how='left')
        stats['ban_rate'] = stats['ban_rate'].fillna(0)

        # -------------------------------------------------------
        # OP Score 및 티어 계산
        # -------------------------------------------------------

        # 정규화
        win_min, win_max = stats['win_rate'].min(), stats['win_rate'].max()
        stats['win_norm'] = 0 if win_max == win_min else (stats['win_rate'] - win_min) / (win_max - win_min)

        stats['pick_ban'] = stats['pick_rate'] + stats['ban_rate']
        pb_min, pb_max = stats['pick_ban'].min(), stats['pick_ban'].max()
        stats['pb_norm'] = 0 if pb_max == pb_min else (stats['pick_ban'] - pb_min) / (pb_max - pb_min)

        # OP Score (승률 7 : 픽밴 3)
        stats['op_score'] = (stats['win_norm'] * 7.0) + (stats['pb_norm'] * 3.0)

        # 백분위수 기반 티어 분류
        stats['percentile'] = stats['op_score'].rank(pct=True)
        minor_threshold = total_matches * 0.005  # 0.5% 미만은 연구용

        conditions = [
            (stats['pick_count'] < minor_threshold),
            (stats['percentile'] >= 0.96),
            (stats['percentile'] >= 0.85),
            (stats['percentile'] >= 0.65),
            (stats['percentile'] >= 0.40),
            (stats['percentile'] >= 0.15)
        ]
        choices = ['연구용', 'OP', '1티어', '2티어', '3티어', '4티어']

        stats['tier'] = np.select(conditions, choices, default='5티어')

        # -------------------------------------------------------

        # 정렬 및 포맷팅
        stats = stats.sort_values(by='op_score', ascending=False)
        for col in ['win_rate', 'pick_rate', 'ban_rate', 'op_score']:
            stats[col] = stats[col].round(2)

        # 저장
        output_cols = ['champion', 'tier', 'win_rate', 'pick_rate', 'ban_rate', 'pick_count', 'op_score']

        major_df = stats[stats['tier'] != '연구용'][output_cols]
        minor_df = stats[stats['tier'] == '연구용'][output_cols]

        major_df.to_csv(os.path.join(EXPORT_FOLDER, 'Major', f"{file_pos_name}_TierList.csv"), index=False,
                        encoding='utf-8-sig')
        minor_df.to_csv(os.path.join(EXPORT_FOLDER, 'Minor', f"{file_pos_name}_MinorList.csv"), index=False,
                        encoding='utf-8-sig')

        print(f"완료 (Major: {len(major_df)}, Minor: {len(minor_df)})")

    print("\n 분석 완료")


if __name__ == "__main__":
    analyze_tiers()