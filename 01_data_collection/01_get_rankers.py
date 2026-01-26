import requests
import pandas as pd

# =======================================================
# 1. 설정
# 기준일: 2026-01-17
# =======================================================
with open('../default_info/api.txt', 'r', encoding='utf-8') as f:
    api_key = f.read().strip()

headers = {"X-Riot-Token": api_key}
TARGET_COUNT = 1000

TARGET_TIERS = ["CHALLENGER", "GRANDMASTER", "MASTER"]

all_candidates = []

print(f"LP 기준 상위 {TARGET_COUNT}명 선별을 시작합니다.")
print("   (Challenger, Grandmaster, Master 데이터를 모두 모은 뒤 정렬합니다)")

# =======================================================
# 2. 데이터 수집
# =======================================================
for tier in TARGET_TIERS:
    print(f"\n[{tier}] 리그 명단 요청 중")
    url = f"https://kr.api.riotgames.com/lol/league/v4/{tier.lower()}leagues/by-queue/RANKED_SOLO_5x5"

    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            print(f"요청 실패 ({r.status_code}) - {tier}")
            continue

        data = r.json()
        entries = data['entries']
        print(f"   -> {len(entries)}명 데이터 수신 완료.")
        for entry in entries:
            if 'puuid' in entry:
                all_candidates.append({
                    'summoner_name': entry.get('summonerName', 'Unknown'),
                    'tier': tier,
                    'lp': entry['leaguePoints'],
                    'wins': entry['wins'],
                    'losses': entry['losses'],
                    'puuid': entry['puuid']
                })

    except Exception as e:
        print(f"에러 발생: {e}")

# =======================================================
# 3. LP 기준 정렬 및 자르기
# =======================================================
print(f"\n총 {len(all_candidates)}명의 후보를 확보했습니다.")
print("랭킹 산정 중 (LP 내림차순 정렬)")

all_candidates.sort(key=lambda x: x['lp'], reverse=True)

top_1000 = all_candidates[:TARGET_COUNT]

for idx, player in enumerate(top_1000):
    player['rank_idx'] = idx + 1

# =======================================================
# 4. 파일 저장
# =======================================================
if top_1000:
    df = pd.DataFrame(top_1000)

    df = df[['rank_idx', 'summoner_name', 'lp', 'tier', 'wins', 'losses', 'puuid']]

    file_name = "../raw_data/top_1000_by_lp.csv"
    df.to_csv(file_name, index=False, encoding='utf-8-sig')

    print(f"\n[완료] LP 기준 상위 1000명 명단 생성 완료!")
    print(f"파일명: {file_name}")
else:
    print("데이터 수집에 실패했습니다.")