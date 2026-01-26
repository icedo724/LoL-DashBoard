import pandas as pd
from sqlalchemy import create_engine
import json
import os
import requests
from collections import Counter

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

print("아이템 정보(DataDragon) 다운로드 중")
try:
    ver_url = "https://ddragon.leagueoflegends.com/api/versions.json"
    latest_ver = requests.get(ver_url).json()[0]
    item_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_ver}/data/ko_KR/item.json"
    item_data = requests.get(item_url).json()['data']
    ITEM_MAP = {int(k): v['name'] for k, v in item_data.items()}
    print("아이템 데이터 준비 완료")
except:
    print("아이템 정보 가져오기 실패.")
    ITEM_MAP = {}
    item_data = {}


def get_item_name(item_id):
    return ITEM_MAP.get(item_id, str(item_id))


EXCLUDE_ITEMS_BUILD = [
    1001, 3005, 3006, 3009, 3020, 3047, 3111, 3117, 3158,
    3340, 3363, 3364,
    2003, 2010, 2031, 2033, 2055, 2140, 2139
]


# =======================================================
# 1. 시작 아이템
# =======================================================
def analyze_starters():
    print("📊 1. 시작 아이템 분석")
    query = """
    SELECT 
        m.position, m.champion, m.match_id, m.win,
        GROUP_CONCAT(t.itemId ORDER BY t.timestamp SEPARATOR ',') as raw_items
    FROM timeline_items t
    JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.timestamp < 120000 
      AND t.itemId NOT IN (3340, 3363, 3364)
      AND t.type = 'ITEM_PURCHASED'
    GROUP BY m.match_id, m.participant_id, m.position, m.champion, m.win
    """
    df = pd.read_sql(query, engine)

    def get_simple_starter(item_str):
        if not item_str: return None
        items = [int(x) for x in item_str.split(',')]
        starter_items = items[:2]
        names = [get_item_name(i) for i in starter_items]
        counts = Counter(names)
        parts = []
        for name in sorted(counts.keys()):
            cnt = counts[name]
            if cnt > 1:
                parts.append(f"{cnt} {name}")
            else:
                parts.append(name)
        return " + ".join(parts)

    df['item_set'] = df['raw_items'].apply(get_simple_starter)
    df_agg = df.groupby(['position', 'champion', 'item_set']).agg(
        pick_count=('match_id', 'count'), win_count=('win', 'sum')
    ).reset_index()
    df_agg['win_rate'] = (df_agg['win_count'] / df_agg['pick_count']) * 100

    df_agg = df_agg[df_agg['pick_count'] >= 1]
    df_agg = df_agg.rename(columns={'item_set': 'item_name'})

    df_agg.to_csv(os.path.join(OUTPUT_FOLDER, "real_starters.csv"), index=False)
    print("저장 완료")


# =======================================================
# 2. 서포터 퀘스트 아이템 분석
# =======================================================
def analyze_support_quest():
    print("2. 서포터 퀘스트 아이템 분석")
    SUPPORT_QUEST_IDS = [3869, 3870, 3871, 3876, 3877]
    query = f"""
    SELECT m.position, m.champion, m.match_id, m.participant_id, m.win, t.itemId
    FROM timeline_items t
    JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.itemId IN ({','.join(map(str, SUPPORT_QUEST_IDS))})
      AND t.type = 'ITEM_PURCHASED'
    ORDER BY t.timestamp
    """
    df = pd.read_sql(query, engine)
    if df.empty: return

    df_final = df.drop_duplicates(subset=['match_id', 'participant_id'], keep='last').copy()
    df_final['item_name'] = df_final['itemId'].apply(get_item_name)

    df_agg = df_final.groupby(['position', 'champion', 'item_name']).agg(
        pick_count=('match_id', 'count'), win_count=('win', 'sum')
    ).reset_index()
    df_agg['win_rate'] = (df_agg['win_count'] / df_agg['pick_count']) * 100

    df_agg = df_agg[df_agg['pick_count'] >= 1]

    df_agg.to_csv(os.path.join(OUTPUT_FOLDER, "real_support_quest.csv"), index=False)
    print("   💾 저장 완료")


# =======================================================
# 3. 스킬 트리
# =======================================================
def analyze_skills():
    print("3. 스킬 트리 분석")
    query = """
    SELECT m.position, m.champion, m.match_id, m.win, 
    GROUP_CONCAT(t.skillSlot ORDER BY t.timestamp SEPARATOR ',') as skill_order
    FROM timeline_skills t
    JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.skillSlot IN (1, 2, 3, 4)
    GROUP BY m.position, m.champion, m.match_id, m.win
    """
    df_raw = pd.read_sql(query, engine)
    slot_map = {'1': 'Q', '2': 'W', '3': 'E', '4': 'R'}

    def get_master_order(order_str):
        if not order_str: return None
        slots = order_str.split(',')
        counts = {'Q': 0, 'W': 0, 'E': 0, 'R': 0}
        mastered = []
        for s in slots:
            key = slot_map.get(s, s)
            if key in counts:
                counts[key] += 1
                if key in ['Q', 'W', 'E'] and counts[key] == 5 and key not in mastered:
                    mastered.append(key)
        if len(mastered) < 3:
            remain = sorted(['Q', 'W', 'E'], key=lambda x: counts.get(x, 0), reverse=True)
            for r in remain:
                if r not in mastered: mastered.append(r)
        return " > ".join(mastered)

    def format_skills(order_str):
        if not order_str: return None
        slots = order_str.split(',')[:18]
        return ','.join([slot_map.get(s, s) for s in slots])

    def get_merge_key(skill_path_str):
        if not skill_path_str: return ""
        return ",".join(skill_path_str.split(',')[:15])

    df_raw['skill_path'] = df_raw['skill_order'].apply(format_skills)
    df_raw['master_order'] = df_raw['skill_order'].apply(get_master_order)
    df_raw['merge_key'] = df_raw['skill_path'].apply(get_merge_key)

    df_agg = df_raw.groupby(['position', 'champion', 'master_order', 'merge_key']).agg(
        pick_count=('match_id', 'count'), win_count=('win', 'sum'),
        skill_path=('skill_path', lambda x: max(x, key=len))
    ).reset_index()
    df_agg['win_rate'] = (df_agg['win_count'] / df_agg['pick_count']) * 100

    df_agg = df_agg[df_agg['pick_count'] >= 1]

    df_agg.to_csv(os.path.join(OUTPUT_FOLDER, "real_skills.csv"), index=False)
    print("저장 완료")


# =======================================================
# 4. 3코어 빌드
# =======================================================
def analyze_builds():
    print("4. 3코어 빌드 분석")
    query = """
    SELECT m.position, m.champion, m.match_id, m.win,
    GROUP_CONCAT(t.itemId ORDER BY t.timestamp SEPARATOR ',') as full_items
    FROM timeline_items t
    JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.type = 'ITEM_PURCHASED'
    GROUP BY m.match_id, m.participant_id, m.position, m.champion, m.win
    """
    df = pd.read_sql(query, engine)

    def is_completed_item(item_id):
        sid = str(item_id)
        if sid not in item_data: return False
        info = item_data[sid]
        depth = info.get('depth', 1)
        gold = info.get('gold', {}).get('total', 0)
        if item_id in EXCLUDE_ITEMS_BUILD: return False
        if depth >= 3 or gold >= 2200: return True
        return False

    def parse_build_str(item_str):
        if not item_str: return None
        items = [int(x) for x in item_str.split(',')]
        core = []
        for item in items:
            if is_completed_item(item):
                core.append(get_item_name(item))
                if len(core) == 3: break
        if len(core) < 3: return None
        return " > ".join(core)

    df['build_path'] = df['full_items'].apply(parse_build_str)
    df_agg = df.groupby(['position', 'champion', 'build_path']).agg(
        pick_count=('match_id', 'count'), win_count=('win', 'sum')
    ).reset_index()
    df_agg['win_rate'] = (df_agg['win_count'] / df_agg['pick_count']) * 100

    df_agg = df_agg[df_agg['pick_count'] >= 1]

    df_agg.to_csv(os.path.join(OUTPUT_FOLDER, "real_builds.csv"), index=False)
    print("저장 완료")


# =======================================================
# 5. 장신구
# =======================================================
def analyze_trinkets():
    print("5. 장신구 전략 분석")
    TRINKET_IDS = [3340, 3363, 3364]
    query = f"""
    SELECT m.position, m.champion, m.match_id, m.participant_id, m.win, t.itemId, t.timestamp
    FROM timeline_items t
    JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.itemId IN ({','.join(map(str, TRINKET_IDS))})
      AND t.type = 'ITEM_PURCHASED'
    ORDER BY m.match_id, m.participant_id, t.timestamp
    """
    df = pd.read_sql(query, engine)

    def get_trinket_strategy(group):
        if group.empty: return None
        items = group['itemId'].tolist()
        times = group['timestamp'].tolist()
        start, final = items[0], items[-1]
        start_name, final_name = get_item_name(start), get_item_name(final)

        if start == final:
            strategy = f"{start_name} (유지)";
            swap_time = 0
        else:
            strategy = f"{start_name} ➡ {final_name}";
            swap_time = 0
            for t, item in zip(times, items):
                if item != start: swap_time = t; break
        return pd.Series([strategy, swap_time], index=['strategy', 'swap_time'])

    strategies = df.groupby(['match_id', 'participant_id', 'position', 'champion', 'win'])[
        ['itemId', 'timestamp']].apply(get_trinket_strategy).reset_index()
    df_agg = strategies.groupby(['position', 'champion', 'strategy']).agg(
        pick_count=('match_id', 'count'), win_count=('win', 'sum'), avg_swap_time=('swap_time', 'mean')
    ).reset_index()
    df_agg['win_rate'] = (df_agg['win_count'] / df_agg['pick_count']) * 100

    df_agg = df_agg[df_agg['pick_count'] >= 1]

    df_agg.to_csv(os.path.join(OUTPUT_FOLDER, "real_trinkets.csv"), index=False)
    print("저장 완료")


# =======================================================
# 6. 아이템 상세
# =======================================================
def analyze_all_items():
    print("6. 아이템 상세 분석")
    query = """
    SELECT DISTINCT m.position, m.champion, m.match_id, m.participant_id, m.win, t.itemId
    FROM timeline_items t 
    JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.type = 'ITEM_PURCHASED'
    """
    df = pd.read_sql(query, engine)
    df['item_name'] = df['itemId'].apply(get_item_name)
    df_agg = df.groupby(['position', 'champion', 'item_name']).agg(
        pick_count=('match_id', 'count'), win_count=('win', 'sum')
    ).reset_index()
    df_agg['win_rate'] = (df_agg['win_count'] / df_agg['pick_count']) * 100

    df_agg = df_agg[df_agg['pick_count'] >= 1]

    df_agg.to_csv(os.path.join(OUTPUT_FOLDER, "real_items.csv"), index=False)
    print("저장 완료")


# =======================================================
# 7. 신발
# =======================================================
def analyze_shoes():
    print("7. 신발 분석")
    boot_ids = []
    for itemId, data in item_data.items():
        if 'tags' in data and 'Boots' in data['tags']: boot_ids.append(int(itemId))
    manual_boots = [1001, 2422, 3006, 3009, 3020, 3047, 3111, 3117, 3158]
    boot_ids = list(set(boot_ids + manual_boots))

    query = f"""
    SELECT m.position, m.champion, m.match_id, m.participant_id, m.win, t.itemId
    FROM timeline_items t JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.itemId IN ({','.join(map(str, boot_ids))}) 
      AND t.type = 'ITEM_PURCHASED'
    ORDER BY t.timestamp
    """
    df = pd.read_sql(query, engine)
    if df.empty: return
    df_final = df.drop_duplicates(subset=['match_id', 'participant_id'], keep='last').copy()
    df_final['item_name'] = df_final['itemId'].apply(get_item_name)
    df_agg = df_final.groupby(['position', 'champion', 'item_name']).agg(
        pick_count=('match_id', 'count'), win_count=('win', 'sum')
    ).reset_index()
    df_agg['win_rate'] = (df_agg['win_count'] / df_agg['pick_count']) * 100

    df_agg = df_agg[df_agg['pick_count'] >= 1]

    df_agg.to_csv(os.path.join(OUTPUT_FOLDER, "real_shoes.csv"), index=False)
    print("저장 완료")


# =======================================================
# 8. 시야 장악 흐름
# =======================================================
def analyze_vision_timeline():
    print("8. 시간대별 시야 장악 흐름 분석")

    query_wards = """
    SELECT 
        m.position,
        m.champion,
        FLOOR(w.timestamp / 300000) * 5 as time_min,
        w.type, 
        COUNT(*) as total_action_count,
        COUNT(DISTINCT m.match_id) as games 
    FROM timeline_wards w
    JOIN match_data m 
        ON w.match_id = m.match_id 
        AND (
            (w.creatorId = m.participant_id AND w.type='WARD_PLACED') OR 
            (w.killerId = m.participant_id AND w.type='WARD_KILL')
        )
    WHERE w.timestamp <= 2400000
    GROUP BY m.position, m.champion, time_min, w.type
    """
    try:
        df = pd.read_sql(query_wards, engine)
        if df.empty:
            print("와드 데이터 없음")
        df['avg_count'] = df['total_action_count'] / df['games']
        pivot = df.pivot_table(
            index=['position', 'champion', 'time_min'],
            columns='type',
            values='avg_count',
            fill_value=0
        ).reset_index()

        if 'WARD_PLACED' not in pivot.columns: pivot['WARD_PLACED'] = 0
        if 'WARD_KILL' not in pivot.columns: pivot['WARD_KILL'] = 0

        pivot.rename(columns={'WARD_PLACED': 'placed', 'WARD_KILL': 'killed'}, inplace=True)

        pivot.to_csv(os.path.join(OUTPUT_FOLDER, "timeline_vision.csv"), index=False)
        print("저장 완료")

    except Exception as e:
        print(f"시야 분석 실패: {e}")


# =======================================================
# 9. 코어 아이템 완성 타이밍
# =======================================================
def analyze_item_spikes():
    print("9. 코어 아이템 단계별 완성 시간 분석")
    query = """
    SELECT 
        m.match_id,
        m.participant_id, 
        m.champion,
        m.win,
        t.itemId,
        t.timestamp
    FROM timeline_items t
    JOIN match_data m ON t.match_id = m.match_id AND t.participantId = m.participant_id
    WHERE t.type = 'ITEM_PURCHASED' 
      AND t.timestamp > 180000 -- 3분 이후
      AND t.itemId NOT IN (3340, 3363, 3364) -- 장신구 제외
    ORDER BY m.match_id, m.participant_id, t.timestamp
    """
    try:
        df = pd.read_sql(query, engine)
        if df.empty: return
        def is_core(item_id):
            sid = str(item_id)
            if sid in item_data:
                return item_data[sid].get('gold', {}).get('total', 0) >= 2200
            return False

        df_core = df[df['itemId'].apply(is_core)].copy()

        if df_core.empty:
            print("코어 아이템 데이터가 없습니다.")
            return
        df_core['core_rank'] = df_core.groupby(['match_id', 'participant_id']).cumcount() + 1
        df_core = df_core[df_core['core_rank'] <= 3].copy()
        df_core['prev_time'] = df_core.groupby(['match_id', 'participant_id'])['timestamp'].shift(1)
        df_core['delta_time'] = df_core['timestamp'] - df_core['prev_time'].fillna(0)
        df_core['delta_min'] = df_core['delta_time'] / 60000
        df_core['item_name'] = df_core['itemId'].apply(get_item_name)

        result = df_core.groupby(['champion', 'itemId', 'item_name', 'core_rank']).agg(
            avg_min=('delta_min', 'mean'),
            win_rate=('win', 'mean'),
            count=('match_id', 'count')
        ).reset_index()

        result['avg_min'] = result['avg_min'].round(1)
        result['win_rate'] = (result['win_rate'] * 100).round(2)

        result.sort_values(['champion', 'core_rank', 'count'], ascending=[True, True, False], inplace=True)

        result.to_csv(os.path.join(OUTPUT_FOLDER, "timeline_item_spikes.csv"), index=False)
        print("저장 완료")

    except Exception as e:
        print(f"아이템 타이밍 분석 실패: {e}")


if __name__ == "__main__":
    analyze_starters()
    analyze_skills()
    analyze_builds()
    analyze_trinkets()
    analyze_all_items()
    analyze_shoes()
    analyze_support_quest()
    analyze_vision_timeline()
    analyze_item_spikes()

    print("\n모든 분석 완료")