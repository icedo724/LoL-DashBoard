import pandas as pd
import requests
import os
import json
import time
from sqlalchemy import create_engine, text

# =======================================================
# 설정
# =======================================================
INPUT_FILE = "../raw_data/match_data_current_patch_10x.csv"
OUTPUT_CLEAN_FILE = "../raw_data/match_data_cleaned.csv"
DB_CONFIG_FILE = "../default_info/db_config.txt"
TABLE_NAME = "match_data"

# =======================================================
# 1. 라이엇 메타 데이터 로드 & 매핑 사전 구축
# =======================================================
print("[1/4] 메타 데이터 다운로드 및 매핑 사전 구축")

try:
    ver_url = "https://ddragon.leagueoflegends.com/api/versions.json"
    latest_version = requests.get(ver_url).json()[0]

    url_kr = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/ko_KR/champion.json"
    data_kr = requests.get(url_kr).json()['data']

    url_en = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json"
    data_en = requests.get(url_en).json()['data']

    item_data = requests.get(f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/ko_KR/item.json").json()[
        'data']
    spell_data = \
    requests.get(f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/ko_KR/summoner.json").json()['data']
    rune_data_list = requests.get(
        f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/ko_KR/runesReforged.json").json()

except Exception as e:
    print(f"메타 데이터 로드 실패: {e}")
    exit()

champ_map_final = {}
for key, val in data_kr.items():
    kr_name = val['name']
    champ_id = val['key']
    champ_map_final[key] = kr_name
    champ_map_final[key.lower()] = kr_name
    champ_map_final[champ_id] = kr_name

for key, val in data_en.items():
    en_name = val['name']
    if key in data_kr:
        kr_name = data_kr[key]['name']
        champ_map_final[en_name] = kr_name
        champ_map_final[en_name.replace(" ", "")] = kr_name

manual_fixes = {
    "FiddleSticks": "피들스틱", "Fiddlesticks": "피들스틱",
    "MonkeyKing": "오공", "Wukong": "오공",
    "DrMundo": "문도 박사", "JarvanIV": "자르반 4세",
    "Nunu": "누누와 윌럼프", "Belveth": "벨베스",
    "Renata": "레나타 글라스크", "KogMaw": "코그모", "RekSai": "렉사이",
    "LeeSin": "리 신", "Lee Sin": "리 신"
}
champ_map_final.update(manual_fixes)

item_map = {int(k): v['name'] for k, v in item_data.items()}
item_map[0] = "None"
spell_map = {int(v['key']): v['name'] for k, v in spell_data.items()}
rune_map = {}
for style in rune_data_list:
    rune_map[style['id']] = style['name']
    for slot in style['slots']:
        for rune in slot['runes']:
            rune_map[rune['id']] = rune['name']
rune_map[-1] = "Unknown"

# =======================================================
# 2. 데이터 로드 및 정제
# =======================================================
print(f"[2/4] 데이터 정제 중 ({INPUT_FILE})")

if not os.path.exists(INPUT_FILE):
    print("입력 파일이 없습니다.")
    exit()

df = pd.read_csv(INPUT_FILE)

if 'gameDuration' not in df.columns:
    if 'game_duration' in df.columns:
        df.rename(columns={'game_duration': 'gameDuration'}, inplace=True)
    else:
        print("경고: gameDuration 컬럼 없음. 필터링 불가.")
        df['gameDuration'] = 1500

original_count = len(df)
df = df[df['gameDuration'] >= 600]
filtered_count = len(df)
print(f"🧹 10분 미만 게임 {original_count - filtered_count}개 삭제 완료 ({filtered_count}개 남음)")

df['temp_idx'] = df.groupby('match_id').cumcount()
df['team'] = df['temp_idx'].apply(lambda x: 'Blue' if x < 5 else 'Red')

df['participant_id'] = df['temp_idx'] + 1

df.drop(columns=['temp_idx'], inplace=True)
print("✅ 'team' 및 'participant_id' 컬럼 생성 완료")


def robust_champ_map(value):
    try:
        if pd.isna(value) or value == "": return "Unknown"
        val_str = str(int(value)) if isinstance(value, (int, float)) else str(value)
        if val_str in champ_map_final: return champ_map_final[val_str]
        if val_str.lower() in champ_map_final: return champ_map_final[val_str.lower()]
        return val_str
    except:
        return str(value)


print("한글 변환 적용")
df['champion'] = df['champion'].apply(robust_champ_map)

for i in range(1, 6):
    col = f'ban_{i}'
    if col in df.columns:
        df[col] = df[col].apply(robust_champ_map)

for i in range(7):
    df[f'item{i}'] = df[f'item{i}'].apply(lambda x: item_map.get(x, "None"))
df['spell1'] = df['spell1'].apply(lambda x: spell_map.get(x, x))
df['spell2'] = df['spell2'].apply(lambda x: spell_map.get(x, x))
for col in ['rune_main', 'rune_key', 'rune_sub']:
    df[col] = df[col].apply(lambda x: rune_map.get(x, x))

df.to_csv(OUTPUT_CLEAN_FILE, index=False, encoding='utf-8-sig')
print(f"데이터 저장 완료: '{OUTPUT_CLEAN_FILE}'")

# =======================================================
# 3. DB 업로드
# =======================================================
print("[3/4] DB 업로드 시작")

try:
    with open(DB_CONFIG_FILE, 'r', encoding='utf-8') as f:
        db_cfg = json.load(f)

    db_url = f"mysql+pymysql://{db_cfg['user']}:{db_cfg['password']}@{db_cfg['host']}/{db_cfg['db_name']}?charset=utf8mb4"
    engine = create_engine(db_url)

    print(f"📤 '{TABLE_NAME}' 테이블 덮어쓰기 진행 중 (데이터: {len(df):,}행)")
    start_time = time.time()

    df.to_sql(name=TABLE_NAME, con=engine, if_exists='replace', index=False, chunksize=1000)

    end_time = time.time()
    print(f"DB 업로드 완료 (소요 시간: {end_time - start_time:.2f}초)")

except Exception as e:
    print(f"DB 업로드 실패: {e}")
    exit()

# =======================================================
# 4. DB 인덱스 최적화
# =======================================================
print("[4/4] 인덱스 생성")
try:
    with engine.connect() as conn:
        conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD INDEX idx_match_id (match_id(20));"))
        conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD INDEX idx_champion (champion(20));"))

        conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD INDEX idx_position (`position`(10));"))

        conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD INDEX idx_game_duration (gameDuration);"))

    print("\n 완료")

except Exception as e:
    print(f"인덱스 생성 중 경고 (이미 존재할 수 있음): {e}")