import requests
import time
import pandas as pd
import os

# =======================================================
# 🛠️ 설정
# 기준일: 2026-01-17
# =======================================================
SOURCE_FILE = "../raw_data/top_1000_by_lp.csv"
OUTPUT_FILE = "../raw_data/match_data_current_patch_10x.csv"
QUEUE_ID = 420

with open('../default_info/api.txt', 'r', encoding='utf-8') as f:
    api_key = f.read().strip()
headers = {"X-Riot-Token": api_key}

# =======================================================
# 1. 패치 버전 확인
# =======================================================
print("현재 패치 버전을 확인합니다.")
try:
    ver_url = "https://ddragon.leagueoflegends.com/api/versions.json"
    versions = requests.get(ver_url).json()
    latest_full_ver = versions[0]
    target_patch = ".".join(latest_full_ver.split(".")[:2])
    print(f"타겟 패치 버전: {target_patch}")
except Exception as e:
    print(f"버전 확인 실패: {e}")
    exit()

# =======================================================
# 2. 이어하기 준비
# =======================================================
if not os.path.exists(SOURCE_FILE):
    print(f"'{SOURCE_FILE}' 파일이 없습니다.")
    exit()

df_rankers = pd.read_csv(SOURCE_FILE)
total_rankers = len(df_rankers)

collected_match_ids = set()
if os.path.exists(OUTPUT_FILE):
    try:
        existing_df = pd.read_csv(OUTPUT_FILE, usecols=['match_id'])
        collected_match_ids = set(existing_df['match_id'].unique())
        print(f"기존 데이터 로드 완료: {len(collected_match_ids)}개의 매치 스킵 예정")
    except:
        pass

print(f"수집 시작")

# =======================================================
# 수집 루프
# =======================================================
for idx, row in df_rankers.iterrows():
    target_puuid = row['puuid']
    rank = row['rank_idx']
    summ_name = row.get('summoner_name', 'Unknown')

    print(f"\n [{rank}/{total_rankers}위] {summ_name} 탐색 시작")

    start_index = 0
    batch_size = 100
    user_games_collected = 0
    keep_searching = True

    while keep_searching:
        url_list = f"https://asia.api.riotgames.com/lol/match/v5/matches/by-puuid/{target_puuid}/ids?queue={QUEUE_ID}&start={start_index}&count={batch_size}"

        try:
            r = requests.get(url_list, headers=headers)
            while r.status_code == 429:
                print("ID 목록 조회 제한 10초 대기")
                time.sleep(10)
                r = requests.get(url_list, headers=headers)

            match_ids = r.json()
            if not match_ids: break

        except Exception as e:
            print(f"ID 요청 에러: {e}")
            break

        current_batch_data = []
        for m_i, match_id in enumerate(match_ids):
            if match_id in collected_match_ids:
                continue

            url_detail = f"https://asia.api.riotgames.com/lol/match/v5/matches/{match_id}"
            try:
                r_d = requests.get(url_detail, headers=headers)
                while r_d.status_code == 429:
                    print("상세 조회 제한 5초 대기")
                    time.sleep(5)
                    r_d = requests.get(url_detail, headers=headers)

                if r_d.status_code != 200: continue

                data = r_d.json()
                info = data['info']
                game_version = info['gameVersion']

                if not game_version.startswith(target_patch):
                    keep_searching = False
                    break
                game_duration = info['gameDuration']
                ban_list = []
                for team in info['teams']:
                    for ban in team['bans']:
                        ban_list.append(ban['championId'])
                while len(ban_list) < 10: ban_list.append(-1)
                team_objs = {}
                for team in info['teams']:
                    team_objs[team['teamId']] = {
                        'baron': team['objectives']['baron']['kills'],
                        'dragon': team['objectives']['dragon']['kills'],
                        'horde': team['objectives']['horde']['kills'],
                        'first_blood': 1 if team['objectives']['champion']['first'] else 0
                    }
                for p in info['participants']:
                    try:
                        main_style = p['perks']['styles'][0]['style']
                        rune_main_1 = p['perks']['styles'][0]['selections'][0]['perk']
                        rune_main_2 = p['perks']['styles'][0]['selections'][1]['perk']
                        rune_main_3 = p['perks']['styles'][0]['selections'][2]['perk']
                        rune_main_4 = p['perks']['styles'][0]['selections'][3]['perk']
                        sub_style = p['perks']['styles'][1]['style']
                        rune_sub_1 = p['perks']['styles'][1]['selections'][0]['perk']
                        rune_sub_2 = p['perks']['styles'][1]['selections'][1]['perk']
                    except:
                        main_style = sub_style = rune_main_1 = -1
                        rune_main_2 = rune_main_3 = rune_main_4 = -1
                        rune_sub_1 = rune_sub_2 = -1

                    my_team_obj = team_objs.get(p['teamId'], {})

                    row_data = {
                        'match_id': match_id,
                        'puuid': p['puuid'],
                        'game_version': game_version,
                        'game_duration': game_duration,
                        'win': 1 if p['win'] else 0,
                        'champion': p['championName'],
                        'position': p['teamPosition'],
                        'lane': p['lane'],
                        'kills': p['kills'], 'deaths': p['deaths'], 'assists': p['assists'],
                        'kda': p['challenges'].get('kda', 0),
                        'solo_kills': p['challenges'].get('soloKills', 0),
                        'total_damage': p['totalDamageDealtToChampions'],
                        'damage_taken': p['totalDamageTaken'],
                        'cs_total': p['totalMinionsKilled'] + p['neutralMinionsKilled'],
                        'gold_earned': p['goldEarned'],
                        'vision_score': p['visionScore'],
                        'control_wards': p['visionWardsBoughtInGame'],
                        'item0': p['item0'], 'item1': p['item1'], 'item2': p['item2'],
                        'item3': p['item3'], 'item4': p['item4'], 'item5': p['item5'], 'item6': p['item6'],
                        'rune_main': main_style, 'rune_key': rune_main_1,
                        'rune_sub': sub_style,
                        'spell1': p['summoner1Id'], 'spell2': p['summoner2Id'],
                        'team_dragon': my_team_obj.get('dragon', 0),
                        'team_baron': my_team_obj.get('baron', 0),
                        'team_horde': my_team_obj.get('horde', 0),
                        'ban_1': ban_list[0], 'ban_2': ban_list[1], 'ban_3': ban_list[2],
                        'ban_4': ban_list[3], 'ban_5': ban_list[4]
                    }
                    current_batch_data.append(row_data)

                collected_match_ids.add(match_id)
                user_games_collected += 1

                time.sleep(1.2)
                print(f"    -> {match_id} (10명 데이터) 저장 완료", end='\r')

            except Exception as e:
                print(f"   Pass: 상세 조회 에러 ({e})")
                time.sleep(1.2)

        # [Step 3] 저장
        if current_batch_data:
            df_new = pd.DataFrame(current_batch_data)
            if not os.path.exists(OUTPUT_FILE):
                df_new.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig', mode='w')
            else:
                df_new.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig', mode='a', header=False)

        if not keep_searching: break

        start_index += batch_size
        print(f"페이지 넘김 (다음 100개 탐색, 현재 start={start_index})")

        if user_games_collected > 500: break

print("\n완료")