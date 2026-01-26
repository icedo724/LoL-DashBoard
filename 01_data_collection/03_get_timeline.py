import requests
import json
import time
import pandas as pd
from sqlalchemy import create_engine
import os

# =======================================================
# ⚙️ 설정
# =======================================================
API_KEY_FILE = "../default_info/api.txt"
CONFIG_FILE = "../default_info/db_config.txt"
REGION = "asia"

FILES = {
    "items": "raw_data/timeline_data/timeline_items.csv",
    "skills": "raw_data/timeline_data/timeline_skills.csv",
    "kills": "raw_data/timeline_data/timeline_kills.csv",
    "objectives": "raw_data/timeline_data/timeline_objectives.csv",
    "wards": "raw_data/timeline_data/timeline_wards.csv"
}

if not os.path.exists(API_KEY_FILE):
    print(f"'{API_KEY_FILE}' 파일이 없습니다.")
    exit()

with open(API_KEY_FILE, 'r', encoding='utf-8') as f:
    API_KEY = f.read().strip()

headers = {"X-Riot-Token": API_KEY}

if not os.path.exists(CONFIG_FILE):
    print(f"'{CONFIG_FILE}' 파일이 없습니다.")
    exit()

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

DB_URL = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['db_name']}?charset=utf8mb4"
engine = create_engine(DB_URL)


# =======================================================
# 함수 정의
# =======================================================

def get_match_timeline(match_id):
    url = f"https://{REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            print("API 제한 대기 (2분)")
            time.sleep(120)
            return get_match_timeline(match_id)
        elif response.status_code == 403:
            print("API 키 만료.")
            exit()
        return None
    except:
        return None


def parse_timeline(timeline_json, match_id):
    data_items = []
    data_skills = []
    data_kills = []
    data_objectives = []
    data_wards = []

    if 'info' not in timeline_json: return None, None, None, None, None

    try:
        frames = timeline_json['info']['frames']
        for frame in frames:
            timestamp = frame['timestamp']
            events = frame['events']

            for event in events:
                evt_type = event['type']

                if evt_type in ['ITEM_PURCHASED', 'ITEM_SOLD', 'ITEM_DESTROYED', 'ITEM_UNDO']:
                    item_id = event.get('itemId', 0)
                    if evt_type == 'ITEM_UNDO':
                        item_id = event.get('afterId', 0)

                    data_items.append({
                        'match_id': match_id,
                        'timestamp': timestamp,
                        'participantId': event['participantId'],
                        'itemId': item_id,
                        'type': evt_type
                    })

                elif evt_type == 'SKILL_LEVEL_UP':
                    data_skills.append({
                        'match_id': match_id, 'timestamp': timestamp,
                        'participantId': event['participantId'],
                        'skillSlot': event['skillSlot'], 'levelUpType': event['levelUpType']
                    })

                elif evt_type == 'CHAMPION_KILL':
                    pos = event.get('position', {'x': 0, 'y': 0})
                    data_kills.append({
                        'match_id': match_id, 'timestamp': timestamp,
                        'killerId': event.get('killerId', 0), 'victimId': event['victimId'],
                        'x': pos['x'], 'y': pos['y']
                    })

                elif evt_type == 'ELITE_MONSTER_KILL':
                    m_type = event.get('monsterType')
                    sub_type = m_type
                    if m_type == 'DRAGON':
                        sub_type = event.get('monsterSubType', 'DRAGON')

                    data_objectives.append({
                        'match_id': match_id, 'timestamp': timestamp,
                        'type': 'ELITE_MONSTER_KILL',
                        'subtype': sub_type,
                        'teamId': event.get('killerTeamId'),
                        'lane': None
                    })

                elif evt_type == 'BUILDING_KILL':
                    data_objectives.append({
                        'match_id': match_id, 'timestamp': timestamp,
                        'type': 'BUILDING_KILL',
                        'subtype': event.get('buildingType'),
                        'lane': event.get('laneType'),
                        'teamId': event.get('teamId')
                    })

                elif evt_type == 'TURRET_PLATE_DESTROYED':
                    data_objectives.append({
                        'match_id': match_id, 'timestamp': timestamp,
                        'type': 'TURRET_PLATE_DESTROYED',
                        'subtype': 'TURRET_PLATE',
                        'lane': event.get('laneType'),
                        'teamId': event.get('teamId')
                    })

                elif evt_type == 'WARD_PLACED':
                    data_wards.append({
                        'match_id': match_id, 'timestamp': timestamp,
                        'type': 'WARD_PLACED',
                        'wardType': event.get('wardType'),
                        'creatorId': event.get('creatorId'),
                        'x': event.get('position', {}).get('x'),
                        'y': event.get('position', {}).get('y')
                    })
                elif evt_type == 'WARD_KILL':
                    data_wards.append({
                        'match_id': match_id, 'timestamp': timestamp,
                        'type': 'WARD_KILL',
                        'wardType': event.get('wardType'),
                        'killerId': event.get('killerId'),
                        'x': event.get('position', {}).get('x'),
                        'y': event.get('position', {}).get('y')
                    })

        return data_items, data_skills, data_kills, data_objectives, data_wards
    except Exception as e:
        return None, None, None, None, None


def save_batch(data_dict, first_write=False):
    for key, filename in FILES.items():
        if data_dict[key]:
            directory = os.path.dirname(filename)
            if not os.path.exists(directory):
                os.makedirs(directory)

            df = pd.DataFrame(data_dict[key])
            mode = 'w' if first_write and not os.path.exists(filename) else 'a'
            header = True if mode == 'w' else False
            df.to_csv(filename, index=False, mode=mode, header=header, encoding='utf-8-sig')


# =======================================================
# 메인 실행
# =======================================================
def main():
    print("타임라인 수집")

    try:
        df_matches = pd.read_sql("SELECT DISTINCT match_id FROM match_data", engine)
        all_match_ids = set(df_matches['match_id'].tolist())
    except Exception as e:
        print(f"DB 연결 실패: {e}")
        exit()

    processed_ids = set()
    if os.path.exists(FILES['items']):
        try:
            done_df = pd.read_csv(FILES['items'], usecols=['match_id'])
            processed_ids = set(done_df['match_id'].unique())
        except:
            pass

    target_ids = list(all_match_ids - processed_ids)
    print(f"전체: {len(all_match_ids)} / 완료: {len(processed_ids)} / 수집 대상: {len(target_ids)}")

    batch_data = {"items": [], "skills": [], "kills": [], "objectives": [], "wards": []}

    for idx, match_id in enumerate(target_ids):
        print(f"[{idx + 1}/{len(target_ids)}] {match_id}", end=" ")

        timeline = get_match_timeline(match_id)
        if timeline:
            i, s, k, o, w = parse_timeline(timeline, match_id)
            if i is not None:
                batch_data['items'].extend(i)
                batch_data['skills'].extend(s)
                batch_data['kills'].extend(k)
                batch_data['objectives'].extend(o)
                batch_data['wards'].extend(w)
                print("✅")
        else:
            print("패스 (응답 없음)")

        time.sleep(1.2)

        if (idx + 1) % 50 == 0:
            save_batch(batch_data, first_write=(len(processed_ids) == 0 and idx < 50))
            print("\n 완료")
            batch_data = {"items": [], "skills": [], "kills": [], "objectives": [], "wards": []}

    if any(batch_data.values()):
        save_batch(batch_data)
        print("\n 최종 완료")


if __name__ == "__main__":
    main()