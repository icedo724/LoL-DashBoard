import pandas as pd
from sqlalchemy import create_engine
import os
import json
import time

# =======================================================
# 설정
# =======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_FOLDER = os.path.join(BASE_DIR, 'advanced_reports')
CONFIG_FILE = os.path.join(BASE_DIR, 'default_info', 'db_config.txt')

if not os.path.exists(CONFIG_FILE):
    print("설정 파일이 없습니다.")
    exit()

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

DB_URL = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['db_name']}?charset=utf8mb4"
engine = create_engine(DB_URL)

if not os.path.exists(EXPORT_FOLDER):
    os.makedirs(EXPORT_FOLDER)

start_time_total = time.time()

# =======================================================
# 1. 상대 전적
# =======================================================
print("1. 챔피언 상성 분석")
try:
    sql_counter = """
    SELECT 
        t1.position,
        t1.champion as me,
        t2.champion as enemy,
        COUNT(*) as total_games,
        SUM(t1.win) as win_count
    FROM match_data t1
    JOIN match_data t2 
        ON t1.match_id = t2.match_id 
        AND t1.position = t2.position
        AND t1.champion != t2.champion
    GROUP BY t1.position, t1.champion, t2.champion
    HAVING total_games >= 10
    """
    df_counter = pd.read_sql(sql_counter, engine)
    df_counter['win_rate'] = (df_counter['win_count'] / df_counter['total_games']) * 100
    df_counter['win_rate'] = df_counter['win_rate'].round(2)

    df_counter.to_csv(os.path.join(EXPORT_FOLDER, "champion_counters.csv"), index=False, encoding='utf-8-sig')
    print("완료")
except Exception as e:
    print(f"실패: {e}")

# =======================================================
# 2. 시간대별 승률
# =======================================================
print("2. 시간대별 승률 분석")
try:
    sql_time = """
    SELECT 
        position,
        champion,
        CASE 
            WHEN gameDuration < 1200 THEN '0-20분' -- 초반
            WHEN gameDuration < 1500 THEN '20-25분'
            WHEN gameDuration < 1800 THEN '25-30분' -- 중반
            WHEN gameDuration < 2100 THEN '30-35분'
            WHEN gameDuration < 2400 THEN '35-40분' -- 후반
            ELSE '40분+' -- 극후반
        END as game_time,
        COUNT(*) as total_games,
        SUM(win) as win_count
    FROM match_data
    GROUP BY position, champion, game_time
    HAVING total_games >= 5
    """
    df_time = pd.read_sql(sql_time, engine)
    df_time['win_rate'] = (df_time['win_count'] / df_time['total_games']) * 100
    df_time['win_rate'] = df_time['win_rate'].round(2)

    df_time.to_csv(os.path.join(EXPORT_FOLDER, "champion_time_stats.csv"), index=False, encoding='utf-8-sig')
    print("완료")
except Exception as e:
    print(f"실패: {e}")

# =======================================================
# 3. 3코어 아이템 빌드
# =======================================================
print("3. 3코어 아이템 빌드 분석")

BOOTS_LIST = [
    '장화', '약간 신비한 신발', '광전사의 군화', '마법사의 신발', '명석함의 아이오니아 장화',
    '신속의 장화', '판금 장화', '헤르메스의 발걸음', '공생형 밑창', '영혼의 발걸음',
    '영원한 전진', '건메탈 군화', '주문투척자의 신발', '핏빛 명석함', '신속행진', '무장 진격', '사슬끈 분쇄자'
]
EXCLUDE_ITEMS = [
    'None', 'Unknown', None, '',
    '도란의 검', '도란의 반지', '도란의 방패', '수확의 낫', '암흑의 인장', '여신의 눈물', '부패 물약',
    '세계 지도집', '룬 나침반', '세계의 결실', '청가오리', '피의 노래', '꿈 생성기', '자자크의 세계가시', '태양의 썰매',
    '새끼 화염발톱', '새끼 이끼쿵쿵', '새끼 바람돌이',
    '체력 물약', '충전형 물약', '제어 와드', '비스킷',
    '강철의 영약', '마법의 영약', '분노의 영약', '민첩의 영약',
    '와드 토템', '예언자의 렌즈', '망원형 개조'
]

sql_items = "SELECT position, champion, item0, item1, item2, item3, item4, item5, win FROM match_data"
df_items = pd.read_sql(sql_items, engine)


def get_core_build(row):
    items = [row[f'item{i}'] for i in range(6)]
    core_items = []
    for item in items:
        if item is None: continue
        item_str = str(item).strip()
        if item_str == 'None' or item_str == '': continue
        if item_str not in EXCLUDE_ITEMS and item_str not in BOOTS_LIST:
            core_items.append(item_str)

    if len(core_items) < 3: return None
    return " ➜ ".join(core_items[:3])


df_items['build_path'] = df_items.apply(get_core_build, axis=1)
df_builds = df_items.dropna(subset=['build_path'])

df_build_stats = df_builds.groupby(['position', 'champion', 'build_path']).agg(
    total_games=('win', 'count'),
    win_count=('win', 'sum')
).reset_index()

df_build_stats['win_rate'] = (df_build_stats['win_count'] / df_build_stats['total_games']) * 100
df_build_stats['win_rate'] = df_build_stats['win_rate'].round(2)
df_build_stats = df_build_stats[df_build_stats['total_games'] >= 5]

df_build_stats.to_csv(os.path.join(EXPORT_FOLDER, "champion_builds.csv"), index=False, encoding='utf-8-sig')
print("완료")

# =======================================================
# 4. 🏁 시작 아이템 분석
# =======================================================
print("4. 시작 아이템 분석")

STARTER_TARGETS = [
    '도란의 검', '도란의 반지', '도란의 방패', '수확의 낫', '암흑의 인장', '여신의 눈물', '부패 물약',
    '세계 지도집', '룬 나침반', '세계의 결실', '새끼 화염발톱', '새끼 이끼쿵쿵', '새끼 바람돌이',
    '롱소드', '증폭의 고서', '사파이어 수정', '천갑옷', '마법무효화의 망토', '장화'
]

df_melted = df_items.melt(id_vars=['position', 'champion', 'win'], value_vars=[f'item{i}' for i in range(6)],
                          value_name='item_name')
df_starters = df_melted[df_melted['item_name'].isin(STARTER_TARGETS)]

if not df_starters.empty:
    df_starter_stats = df_starters.groupby(['position', 'champion', 'item_name']).agg(
        total_games=('win', 'count'),
        win_count=('win', 'sum')
    ).reset_index()
    df_starter_stats['win_rate'] = (df_starter_stats['win_count'] / df_starter_stats['total_games']) * 100
    df_starter_stats['win_rate'] = df_starter_stats['win_rate'].round(2)
    df_starter_stats = df_starter_stats[df_starter_stats['total_games'] >= 5]

    df_starter_stats.to_csv(os.path.join(EXPORT_FOLDER, "champion_starters.csv"), index=False, encoding='utf-8-sig')
    print("완료")

# =======================================================
# 5. 장신구 분석
# =======================================================
print("📊 5. 장신구 분석")
sql_trinket = "SELECT position, champion, item6 as item_name, count(*) as total_games, sum(win) as win_count FROM match_data GROUP BY position, champion, item6"
df_trinket = pd.read_sql(sql_trinket, engine)
TRINKET_LIST = ['와드 토템', '예언자의 렌즈', '망원형 개조', '투명 와드']
df_trinket = df_trinket[df_trinket['item_name'].isin(TRINKET_LIST)]
if not df_trinket.empty:
    df_trinket['win_rate'] = (df_trinket['win_count'] / df_trinket['total_games']) * 100
    df_trinket['win_rate'] = df_trinket['win_rate'].round(2)
    df_trinket.to_csv(os.path.join(EXPORT_FOLDER, "champion_trinkets.csv"), index=False, encoding='utf-8-sig')
    print("완료")

# =======================================================
# 6. 🔮 룬 분석
# =======================================================
print("6. 룬 세팅 분석")
sql_runes = "SELECT position, champion, rune_key, rune_main, rune_sub, win FROM match_data"
df_runes = pd.read_sql(sql_runes, engine).dropna()
df_runes[['rune_key', 'rune_main', 'rune_sub']] = df_runes[['rune_key', 'rune_main', 'rune_sub']].astype(str)

df_rune_stats = df_runes.groupby(['position', 'champion', 'rune_key', 'rune_main', 'rune_sub']).agg(
    total_games=('win', 'count'),
    win_count=('win', 'sum')
).reset_index()
df_rune_stats['win_rate'] = (df_rune_stats['win_count'] / df_rune_stats['total_games']) * 100
df_rune_stats['win_rate'] = df_rune_stats['win_rate'].round(2)
df_rune_stats = df_rune_stats[df_rune_stats['total_games'] >= 5]

df_rune_stats.to_csv(os.path.join(EXPORT_FOLDER, "champion_runes.csv"), index=False, encoding='utf-8-sig')
print("완료")

# =======================================================
# 7. 진영별 승률
# =======================================================
print("7. 진영별 승률 분석")
sql_sides = "SELECT position, champion, team, win FROM match_data"
df_sides = pd.read_sql(sql_sides, engine)
df_side_stats = df_sides.groupby(['position', 'champion', 'team']).agg(
    total_games=('win', 'count'),
    win_count=('win', 'sum')
).reset_index()
df_side_stats['win_rate'] = (df_side_stats['win_count'] / df_side_stats['total_games']) * 100
df_side_stats['win_rate'] = df_side_stats['win_rate'].round(2)
df_side_stats.to_csv(os.path.join(EXPORT_FOLDER, "champion_sides.csv"), index=False, encoding='utf-8-sig')
print("완료")

# =======================================================
# 8. 챔피언 상세 스탯
# =======================================================
print("8. 챔피언 전투/운영 스탯(KDA, DPM 등) 분석")
sql_stats = """
SELECT 
    position, champion,
    AVG(kills) as avg_kills, AVG(deaths) as avg_deaths, AVG(assists) as avg_assists,
    AVG(kda) as avg_kda, AVG(total_damage) as avg_damage, AVG(damage_taken) as avg_tanking,
    AVG(vision_score) as avg_vision, AVG(gold_earned) as avg_gold, AVG(cs_total) as avg_cs,
    AVG(gameDuration) as avg_time, AVG(solo_kills) as avg_solokills 
FROM match_data
GROUP BY position, champion
"""
df_stats = pd.read_sql(sql_stats, engine)
df_stats['DPM'] = df_stats['avg_damage'] / (df_stats['avg_time'] / 60)
df_stats['GPM'] = df_stats['avg_gold'] / (df_stats['avg_time'] / 60)
df_stats['VSPM'] = df_stats['avg_vision'] / (df_stats['avg_time'] / 60)
df_stats['DTM'] = df_stats['avg_tanking'] / (df_stats['avg_time'] / 60)

cols_to_round = ['avg_kills', 'avg_deaths', 'avg_assists', 'avg_kda', 'DPM', 'GPM', 'VSPM', 'DTM', 'avg_solokills',
                 'avg_time']
df_stats[cols_to_round] = df_stats[cols_to_round].round(2)
df_stats.to_csv(os.path.join(EXPORT_FOLDER, "champion_stats.csv"), index=False, encoding='utf-8-sig')
print("완료")

# =======================================================
# 9. ⚡ 스펠 분석
# =======================================================
print("9. 스펠 분석")
sql_spells = "SELECT position, champion, spell1, spell2, win FROM match_data"
df_spells = pd.read_sql(sql_spells, engine)


def normalize_spells(row):
    s1, s2 = str(row['spell1']), str(row['spell2'])
    if s1 == '점멸':
        return pd.Series([s2, s1])
    elif s2 == '점멸':
        return pd.Series([s1, s2])
    spells = sorted([s1, s2])
    return pd.Series([spells[0], spells[1]])


if not df_spells.empty:
    df_spells[['spell1', 'spell2']] = df_spells.apply(normalize_spells, axis=1)
    df_spell_stats = df_spells.groupby(['position', 'champion', 'spell1', 'spell2']).agg(
        total_games=('win', 'count'), win_count=('win', 'sum')
    ).reset_index()
    df_spell_stats['win_rate'] = (df_spell_stats['win_count'] / df_spell_stats['total_games']) * 100
    df_spell_stats['win_rate'] = df_spell_stats['win_rate'].round(2)
    df_spell_stats = df_spell_stats[df_spell_stats['total_games'] >= 5]
    df_spell_stats.to_csv(os.path.join(EXPORT_FOLDER, "champion_spells.csv"), index=False, encoding='utf-8-sig')
    print("완료")

# =======================================================
# 10. 라인전 분석
# =======================================================
print("10. 라인전 분석")
# A. 포탑 방패 채굴
sql_plates = """
SELECT 
    m.position,
    m.champion,
    COUNT(t.match_id) as total_plates_taken, 
    COUNT(DISTINCT m.match_id) as plate_games_count 
FROM match_data m
JOIN timeline_objectives t 
    ON m.match_id = t.match_id 
    AND t.type = 'TURRET_PLATE_DESTROYED'
WHERE 
    (m.team = 'Blue' AND t.teamId = 100) OR 
    (m.team = 'Red' AND t.teamId = 200)
    AND (
        (m.position = 'TOP' AND t.lane = 'TOP_LANE') OR
        (m.position = 'MIDDLE' AND t.lane = 'MID_LANE') OR
        (m.position = 'BOTTOM' AND t.lane = 'BOT_LANE') OR
        (m.position = 'UTILITY' AND t.lane = 'BOT_LANE')
    )
GROUP BY m.position, m.champion
"""
try:
    df_plates = pd.read_sql(sql_plates, engine)
    df_plates['avg_plates'] = (df_plates['total_plates_taken'] / df_plates['plate_games_count']).round(2)
except Exception as e:
    print(f"   (방패 분석 Skip: {e})")
    df_plates = pd.DataFrame()

# B. 라인전 공격성 지표
sql_early_kills = """
SELECT 
    m.position,
    m.champion,
    COUNT(k.match_id) as early_kills_count,
    COUNT(DISTINCT m.match_id) as kill_games_count
FROM match_data m
JOIN timeline_kills k 
    ON m.match_id = k.match_id
WHERE k.killerId = m.participant_id  
  AND k.timestamp <= 840000        
GROUP BY m.position, m.champion
"""
try:
    df_early = pd.read_sql(sql_early_kills, engine)
    df_early['avg_early_kills'] = (df_early['early_kills_count'] / df_early['kill_games_count']).round(2)
except Exception as e:
    print(f"   (초반 킬 분석 Skip: {e})")
    df_early = pd.DataFrame()

# C. 데이터 병합
try:
    df_laning = df_stats[['position', 'champion', 'avg_cs', 'avg_gold']].copy()

    if not df_plates.empty:
        df_laning = pd.merge(df_laning, df_plates[['position', 'champion', 'avg_plates']], on=['position', 'champion'],
                             how='left')
    else:
        df_laning['avg_plates'] = 0

    if not df_early.empty:
        df_laning = pd.merge(df_laning, df_early[['position', 'champion', 'avg_early_kills']],
                             on=['position', 'champion'], how='left')
    else:
        df_laning['avg_early_kills'] = 0

    df_laning = df_laning.fillna(0)

    df_laning.to_csv(os.path.join(EXPORT_FOLDER, "champion_laning.csv"), index=False, encoding='utf-8-sig')
    print(f"라인전 지표 저장 완료 ({len(df_laning)} rows)")

except Exception as e:
    print(f"라인전 데이터 병합 실패: {e}")

# =======================================================
# 🏁 종료
# =======================================================
end_time_total = time.time()
elapsed = int(end_time_total - start_time_total)
print(f"\n 분석 완료 (총 소요시간: {elapsed}초)")