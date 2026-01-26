import pandas as pd
from sqlalchemy import create_engine
import json
import os

# =======================================================
# ⚙️ 설정
# =======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'default_info', 'db_config.txt')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'advanced_reports')

if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

if not os.path.exists(CONFIG_FILE):
    print(f"'{CONFIG_FILE}' 파일이 없습니다.")
    exit()

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

DB_URL = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['db_name']}?charset=utf8mb4"
engine = create_engine(DB_URL)


def analyze_meta_stats():
    print("메타 & 오브젝트 분석")
    print("1. 기본 메타(진영/시간/오브젝트수) 분석")

    query = """
    SELECT 
        match_id, 
        team, 
        MAX(win) as win, 
        MAX(gameDuration) as gameDuration,
        MAX(team_dragon) as dragon_count,
        MAX(team_baron) as baron_count,
        MAX(team_horde) as horde_count,
        SUM(kills) as total_kills
    FROM match_data
    WHERE gameDuration >= 600
    GROUP BY match_id, team
    """
    df = pd.read_sql(query, engine)

    if df.empty:
        print("match_data 데이터가 없습니다.")
        return

    # --- 1-1. 진영별 승률 ---
    # [수정] reset_index() 추가
    side_stats = df.groupby('team')['win'].mean().reset_index()
    # [수정] str(x) 변환 추가
    side_stats['team_name'] = side_stats['team'].apply(
        lambda x: 'Blue' if '100' in str(x) or 'Blue' in str(x) else 'Red')
    side_stats['win_rate'] = (side_stats['win'] * 100).round(2)
    side_stats.to_csv(os.path.join(OUTPUT_FOLDER, "meta_side_win.csv"), index=False)
    print("진영별 승률 저장 완료")

    # --- 1-2. 오브젝트 획득 수별 승률 ---
    def get_obj_win_rate(col_name):
        stats = df.groupby(col_name).agg(
            match_count=('match_id', 'count'),
            win_count=('win', 'sum')
        ).reset_index()
        stats['win_rate'] = (stats['win_count'] / stats['match_count'] * 100).round(2)
        return stats[stats['match_count'] >= 10]

    get_obj_win_rate('dragon_count').to_csv(os.path.join(OUTPUT_FOLDER, "meta_dragon_count.csv"), index=False)
    get_obj_win_rate('baron_count').to_csv(os.path.join(OUTPUT_FOLDER, "meta_baron_count.csv"), index=False)
    get_obj_win_rate('horde_count').to_csv(os.path.join(OUTPUT_FOLDER, "meta_horde_count.csv"), index=False)
    print("오브젝트 개수별 승률 저장 완료")

    # --- 1-3. 게임 시간 분포 ---
    df['duration_min'] = (df['gameDuration'] / 60).round(1)
    time_dist = df[['match_id', 'duration_min']].drop_duplicates(subset=['match_id'])
    time_dist.to_csv(os.path.join(OUTPUT_FOLDER, "meta_time_dist.csv"), index=False)
    print("게임 시간 데이터 저장 완료")

    print("2. 오브젝트 정밀 분석")

    query_timeline = """
    SELECT 
        t.match_id,
        t.type,
        t.subtype,
        t.teamId as killer_team_id,
        t.timestamp,
        MAX(CASE WHEN m.team = 'Blue' THEN m.win ELSE 0 END) as blue_win,
        MAX(CASE WHEN m.team = 'Red' THEN m.win ELSE 0 END) as red_win
    FROM timeline_objectives t
    JOIN match_data m ON t.match_id = m.match_id
    WHERE t.type = 'ELITE_MONSTER_KILL'
    GROUP BY t.match_id, t.type, t.subtype, t.teamId, t.timestamp
    ORDER BY t.match_id, t.timestamp ASC
    """

    try:
        df_objs = pd.read_sql(query_timeline, engine)

        if df_objs.empty:
            print("상세 오브젝트 데이터가 없습니다.")
        else:
            df_objs['is_killer_winner'] = df_objs.apply(lambda x:
                                                        1 if (x['killer_team_id'] == 100 and x['blue_win'] == 1) or
                                                             (x['killer_team_id'] == 200 and x['red_win'] == 1) else 0,
                                                        axis=1)

            # --- 2-1. 드래곤 종류별 승률 ---
            dragons = df_objs[df_objs['subtype'].str.contains('DRAGON', na=False)].copy()
            if not dragons.empty:
                type_stats = dragons.groupby('subtype').agg(
                    kill_count=('match_id', 'count'), win_count=('is_killer_winner', 'sum')
                ).reset_index()
                type_stats['win_rate'] = (type_stats['win_count'] / type_stats['kill_count'] * 100).round(2)

                name_map = {
                    'AIR_DRAGON': '바람용', 'EARTH_DRAGON': '대지용 ️', 'FIRE_DRAGON': '화염용',
                    'WATER_DRAGON': '바다용', 'HEXTECH_DRAGON': '마공용', 'CHEMTECH_DRAGON': '화공용',
                    'ELDER_DRAGON': '장로용', 'DRAGON': '미상'
                }
                type_stats['dragon_name'] = type_stats['subtype'].map(name_map).fillna(type_stats['subtype'])
                type_stats.sort_values('win_rate', ascending=False).to_csv(
                    os.path.join(OUTPUT_FOLDER, "dragon_type_stats.csv"), index=False, encoding='utf-8-sig')
                print("드래곤 종류별 승률 저장 완료")

                elemental = dragons[~dragons['subtype'].str.contains("ELDER")].copy()
                elemental['rank'] = elemental.groupby(['match_id', 'killer_team_id']).cumcount() + 1
                souls = elemental[elemental['rank'] == 4]

                if not souls.empty:
                    soul_stats = souls.groupby('subtype').agg(
                        count=('match_id', 'count'), win=('is_killer_winner', 'sum')
                    ).reset_index()
                    soul_stats['win_rate'] = (soul_stats['win'] / soul_stats['count'] * 100).round(2)
                    soul_stats['dragon_name'] = soul_stats['subtype'].map(name_map).fillna(soul_stats['subtype'])
                    soul_stats.to_csv(os.path.join(OUTPUT_FOLDER, "dragon_soul_stats.csv"), index=False,
                                      encoding='utf-8-sig')
                    print("드래곤 영혼 승률 저장 완료")

            # --- 2-2. 공허 유충 & 바론 상세 ---
            grubs = df_objs[df_objs['subtype'].str.contains('HORDE|ATAKHAN|GRUB', case=False, na=False)].copy()
            if not grubs.empty:
                grub_counts = grubs.groupby(['match_id', 'killer_team_id']).agg(
                    count=('subtype', 'count'), win=('is_killer_winner', 'max')
                ).reset_index()
                grub_stats = grub_counts.groupby('count').agg(
                    total=('match_id', 'count'), win=('win', 'sum')
                ).reset_index()
                grub_stats['win_rate'] = (grub_stats['win'] / grub_stats['total'] * 100).round(2)
                grub_stats.to_csv(os.path.join(OUTPUT_FOLDER, "void_grub_stats.csv"), index=False, encoding='utf-8-sig')
                print("공허 유충 승률 저장 완료")

    except Exception as e:
        print(f"오브젝트 분석 오류: {e}")

    print("3. 포탑 방패 분석")

    query_plates = """
    SELECT 
        m.match_id,
        m.gameDuration,
        COUNT(t.match_id) as total_plates
    FROM match_data m
    JOIN timeline_objectives t ON m.match_id = t.match_id
    WHERE t.type = 'TURRET_PLATE_DESTROYED'
    GROUP BY m.match_id, m.gameDuration
    """
    try:
        df_plates = pd.read_sql(query_plates, engine)
        if not df_plates.empty:
            df_plates['duration_min'] = df_plates['gameDuration'] / 60
            plate_impact = df_plates.groupby('total_plates')['duration_min'].mean().reset_index()
            plate_impact.columns = ['Total Plates Taken', 'Avg Game Time (min)']
            plate_impact = plate_impact.round(2)

            plate_impact.to_csv(os.path.join(OUTPUT_FOLDER, "meta_plate_impact.csv"), index=False)
            print("포탑 방패 메타 데이터 저장 완료")
    except Exception as e:
        print(f"포탑 방패 분석 오류: {e}")

    print("\n모든 메타 데이터 분석 완료")


if __name__ == "__main__":
    analyze_meta_stats()