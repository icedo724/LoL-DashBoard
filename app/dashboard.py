import streamlit as st
import pandas as pd
import plotly.express as px
import os
import requests
from scipy.stats import chi2_contingency

# =======================================================
# 설정 & 세션 상태 초기화
# =======================================================
st.set_page_config(layout="wide", page_title="리그오브레전드 상위 플레이어 통계")

# UI
st.markdown("""
<style>
    /* 1. 라디오 버튼 컨테이너 */
    [data-testid="stRadio"] > div {
        display: flex;
        flex-direction: row;
        overflow-x: auto;
        white-space: nowrap;
        padding-bottom: 0px;
        border-bottom: 1px solid #e0e0e0;
    }

    [data-testid="stRadio"] {
        margin-bottom: -15px !important;
        padding-bottom: 0px !important;
    }

    /* 2. 라디오 버튼 라벨 */
    [data-testid="stRadio"] label {
        background-color: transparent !important;
        border: none !important;
        color: #555 !important;
        padding: 8px 16px !important;
        margin-right: 10px;
        cursor: pointer;
        font-weight: 500;
        border-radius: 0px !important;
        transition: all 0.2s;
    }
    /* 3. 동그라미 숨기기 */
    [data-testid="stRadio"] label > div:first-child {
        display: none;
    }
    /* 4. 선택된 항목 스타일 */
    [data-testid="stRadio"] label:has(input:checked) {
        color: #FF4B4B !important;
        font-weight: bold !important;
        border-bottom: 3px solid #FF4B4B !important;
        background-color: transparent !important;
    }
    [data-testid="stRadio"] label:hover {
        color: #FF4B4B !important;
        background-color: transparent !important;
    }

    h3[data-testid="stSubheader"] {
        margin-top: 0px !important;
        padding-top: 10px !important; 
    }

    .stMarkdown p {
        margin-bottom: 5px !important;
    }
</style>
""", unsafe_allow_html=True)

POS_OPTIONS = ['탑 (TOP)', '정글 (JUNGLE)', '미드 (MIDDLE)', '원딜 (BOTTOM)', '서포터 (SUPPORT)']

if 'current_tab' not in st.session_state:
    st.session_state['current_tab'] = "챔피언 티어표"
if 'target_champ' not in st.session_state:
    st.session_state['target_champ'] = None
if 'selected_pos_storage' not in st.session_state:
    st.session_state['selected_pos_storage'] = POS_OPTIONS[0]
if 'last_pos' not in st.session_state:
    st.session_state['last_pos'] = POS_OPTIONS[0]
if 'champ_analysis_tab' not in st.session_state:
    st.session_state['champ_analysis_tab'] = "룬 & 스펠"

TIER_FOLDER = 'reports/tier_reports'
ITEM_FOLDER = 'reports/item_reports'
ADVANCED_FOLDER = 'reports/advanced_reports'

BOOTS_LIST = [
    '장화', '약간 신비한 신발', '광전사의 군화', '마법사의 신발', '명석함의 아이오니아 장화',
    '신속의 장화', '판금 장화', '헤르메스의 발걸음', '공생형 밑창', '영혼의 발걸음',
    '영원한 전진', '건메탈 군화', '주문투척자의 신발', '핏빛 명석함', '신속행진', '무장 진격', '사슬끈 분쇄자'
]


# =======================================================
# 통계 검정 로직
# =======================================================
def check_significance(df, name_col='item_name', count_col='pick_count', alpha=0.05):
    valid_df = df[df[count_col] >= 10].copy()
    if len(valid_df) < 2: return None

    valid_df = valid_df.sort_values(by='win_rate', ascending=False)
    best = valid_df.iloc[0]
    second = valid_df.iloc[1]

    best_cnt = best[count_col]
    best_win = int(best_cnt * (best['win_rate'] / 100))
    best_lose = best_cnt - best_win

    sec_cnt = second[count_col]
    sec_win = int(sec_cnt * (second['win_rate'] / 100))
    sec_lose = sec_cnt - sec_win

    obs = [[best_win, best_lose], [sec_win, sec_lose]]
    try:
        chi2, p_value, dof, expected = chi2_contingency(obs)
    except:
        return None

    return {
        "best_name": best[name_col],
        "sec_name": second[name_col],
        "p_value": p_value,
        "significant": p_value < alpha,
        "best_win_rate": best['win_rate'],
        "sec_win_rate": second['win_rate']
    }


def display_stat_insight(result, context="아이템"):
    if not result: return
    with st.expander(f"통계 기반 {context} 비교 리포트", expanded=True):
        p = result['p_value']
        if result['significant']:
            st.success(
                f"**유의미한 차이 (P={p:.4f})**: **{result['best_name']}** 승률 {result['best_win_rate']:.1f}% > {result['sec_name']}")
        else:
            st.info(f"**큰 차이 없음 (P={p:.4f})**: **{result['best_name']}**와 **{result['sec_name']}**은(는) 성능이 비슷합니다.")


# =======================================================
# 데이터 로드 및 헬퍼 함수
# =======================================================
@st.cache_data
def load_tier_data(position, category):
    pos_map = {'탑 (TOP)': 'TOP', '정글 (JUNGLE)': 'JUNGLE', '미드 (MIDDLE)': 'MIDDLE', '원딜 (BOTTOM)': 'BOTTOM',
               '서포터 (SUPPORT)': 'UTILITY'}
    file_pos = pos_map[position]
    filename_pos = "SUPPORT" if file_pos == "UTILITY" else file_pos
    folder = 'Major' if category == '메이저 (정석)' else 'Minor'
    path = os.path.join(TIER_FOLDER, folder, f"{filename_pos}_{'TierList' if folder == 'Major' else 'MinorList'}.csv")
    if os.path.exists(path): return pd.read_csv(path)
    return None


@st.cache_data
def load_item_data(position):
    pos_map = {'탑 (TOP)': 'TOP', '정글 (JUNGLE)': 'JUNGLE', '미드 (MIDDLE)': 'MIDDLE', '원딜 (BOTTOM)': 'BOTTOM',
               '서포터 (SUPPORT)': 'UTILITY'}
    file_pos = pos_map[position]
    filename_pos = "SUPPORT" if file_pos == "UTILITY" else file_pos
    path = os.path.join(ITEM_FOLDER, f"{filename_pos}_ItemDetail.csv")
    if os.path.exists(path): return pd.read_csv(path)
    return None


@st.cache_data
def load_real_stats(position, champion):
    pos_map = {'탑 (TOP)': 'TOP', '정글 (JUNGLE)': 'JUNGLE', '미드 (MIDDLE)': 'MIDDLE', '원딜 (BOTTOM)': 'BOTTOM',
               '서포터 (SUPPORT)': 'UTILITY'}
    target_pos = pos_map.get(position, 'TOP')
    if target_pos == 'UTILITY': target_pos = 'UTILITY'

    results = {}
    files = {
        'starter': 'real_starters.csv',
        'build': 'real_builds.csv',
        'skill': 'real_skills.csv',
        'trinket': 'real_trinkets.csv',
        'item_detail': 'real_items.csv',
        'shoes': 'real_shoes.csv',
        'support_quest': 'real_support_quest.csv',
        'vision_timeline': 'timeline_vision.csv',
        'item_spikes': 'timeline_item_spikes.csv'
    }

    for key, filename in files.items():
        try:
            path = os.path.join(ADVANCED_FOLDER, filename)
            if os.path.exists(path):
                df = pd.read_csv(path)
                if key == 'item_spikes' and 'champion' in df.columns:
                    results[key] = df[df['champion'] == champion]

                elif 'position' in df.columns and 'champion' in df.columns:
                    results[key] = df[(df['position'] == target_pos) & (df['champion'] == champion)]
                else:
                    results[key] = df
            else:
                results[key] = pd.DataFrame()
        except:
            results[key] = pd.DataFrame()

    return results


@st.cache_data
def load_macro_data():
    path = os.path.join(ADVANCED_FOLDER, "champion_macro.csv")
    if os.path.exists(path): return pd.read_csv(path)
    return None


@st.cache_data
def get_completed_item_names():
    try:
        ver_url = "https://ddragon.leagueoflegends.com/api/versions.json"
        latest_ver = requests.get(ver_url).json()[0]
        item_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_ver}/data/ko_KR/item.json"
        data = requests.get(item_url).json()['data']
        completed = set()
        for k, v in data.items():
            depth = v.get('depth', 1)
            gold = v.get('gold', {}).get('total', 0)
            if depth >= 3 or gold >= 2200:
                completed.add(v['name'])
        return completed
    except:
        return set()


# =======================================================
# 스타일링 함수
# =======================================================
TIER_COLORS = {
    "OP": "background-color: #FFD7D7; color: black;",
    "1티어": "background-color: #FFE5CC; color: black;",
    "2티어": "background-color: #D7E8FF; color: black;",
    "3티어": "background-color: #D7FFD9; color: black;",
    "4티어": "background-color: #F0F0F0; color: black;",
    "5티어": "background-color: #F8F8F8; color: #888888;",
    "연구용": "background-color: #E8D7FF; color: black;"
}


def highlight_tier_row(row):
    tier = row['티어']
    return [TIER_COLORS.get(tier, "")] * len(row)


def display_html_table(df, styler):
    html = styler.to_html()
    st.markdown(f"<style>table {{width: 100% !important;}}</style>{html}", unsafe_allow_html=True)


# =======================================================
# 사이드바
# =======================================================
st.sidebar.title("분석 메뉴")
menu_list = ["챔피언 티어표", "챔피언 통합 분석", "메타 & 오브젝트 분석", "재미로 보는 통계"]
try:
    current_idx = menu_list.index(st.session_state['current_tab'])
except:
    current_idx = 0
selected_menu = st.sidebar.radio("분석 모드 선택", menu_list, index=current_idx)

if selected_menu != st.session_state['current_tab']:
    st.session_state['current_tab'] = selected_menu
    st.rerun()

st.sidebar.markdown("---")

is_meta_tab = (st.session_state['current_tab'] == "메타 & 오브젝트 분석")

if not is_meta_tab:
    def on_position_change():
        st.session_state['target_champ'] = None


    try:
        default_ix = POS_OPTIONS.index(st.session_state['selected_pos_storage'])
    except:
        default_ix = 0

    selected_pos = st.sidebar.selectbox(
        "포지션 선택",
        POS_OPTIONS,
        index=default_ix,
        key='selected_pos_storage',
        on_change=on_position_change
    )

    if selected_pos != st.session_state['last_pos']:
        st.session_state['last_pos'] = selected_pos
        st.session_state['target_champ'] = None
        st.rerun()

    selected_category = st.sidebar.radio("데이터 유형", ['메이저 (정석)', '마이너 (연구)'])

else:
    selected_pos = st.session_state.get('selected_pos_storage', POS_OPTIONS[0])
    selected_category = '메이저 (정석)'
    st.sidebar.info("메타 분석은 협곡 전체 데이터를 다루므로 포지션 선택이 필요 없습니다.")

current_tier_df = load_tier_data(selected_pos, selected_category)
valid_champions = []
if current_tier_df is not None:
    valid_champions = current_tier_df['champion'].unique().tolist()

# =======================================================
# [모드 1] 챔피언 티어표
# =======================================================
if selected_menu == "챔피언 티어표":
    st.title(f"{selected_pos.split()[0]} 라인 챔피언 티어 ({selected_category})")
    df = current_tier_df
    if df is None:
        st.error("데이터가 없습니다.")
    else:
        col1, col2 = st.columns([2, 1])
        with col2:
            st.subheader("챔피언 순위")
            st.caption("챔피언을 선택하면 통합 분석으로 이동합니다.")
            with st.popover("정렬 설정", use_container_width=True):
                sort_option = st.radio("정렬 기준", ["티어 순", "승률 순", "픽률 순", "밴률 순"])

            if "티어" in sort_option:
                tier_order = {"OP": 0, "1티어": 1, "2티어": 2, "3티어": 3, "4티어": 4, "5티어": 5, "연구용": 6}
                df['tier_rank'] = df['tier'].map(tier_order)
                df = df.sort_values(by=['tier_rank', 'win_rate', 'pick_rate', 'ban_rate'],
                                    ascending=[True, False, False, False])
            elif "승률" in sort_option:
                df = df.sort_values(by=['win_rate', 'pick_rate'], ascending=[False, False])
            elif "픽률" in sort_option:
                df = df.sort_values(by=['pick_rate', 'win_rate'], ascending=[False, False])
            elif "밴률" in sort_option:
                df = df.sort_values(by=['ban_rate', 'win_rate'], ascending=[False, False])

            display_df = df[['tier', 'champion', 'win_rate', 'pick_rate', 'ban_rate']].copy()
            display_df.columns = ['티어', '챔피언', '승률 (%)', '픽률 (%)', '밴률 (%)']
            display_df.reset_index(drop=True, inplace=True)
            styler = (display_df.style.apply(highlight_tier_row, axis=1).format("{:.1f}",
                                                                                subset=['승률 (%)', '픽률 (%)', '밴률 (%)']))
            event = st.dataframe(styler, use_container_width=True, hide_index=True, on_select="rerun",
                                 selection_mode="single-row", height=650)
            if len(event.selection['rows']) > 0:
                st.session_state['target_champ'] = display_df.iloc[event.selection['rows'][0]]['챔피언']
                st.session_state['current_tab'] = "챔피언 통합 분석"
                st.rerun()

        with col1:
            if '메이저' in selected_category:
                min_score = df['op_score'].min()
                df['visual_size'] = df['op_score'] - min_score + 5
            else:
                df['visual_size'] = df['pick_count']
            df['챔피언'] = df['champion']
            show_names = st.checkbox("챔피언 이름 보기", value=True)
            fig = px.scatter(
                df, x="pick_rate", y="win_rate", size="visual_size", color="tier",
                hover_name="챔피언", text="챔피언" if show_names else None,
                title=f"승률 / 픽률 ({selected_pos})",
                color_discrete_map={"OP": "#EF4444", "1티어": "#F97316", "2티어": "#3B82F6", "3티어": "#10B981",
                                    "4티어": "#6B7280", "5티어": "#9CA3AF", "연구용": "#8B5CF6"},
                labels={"pick_rate": "픽률 (%)", "win_rate": "승률 (%)", "tier": "티어"}, size_max=15
            )
            fig.add_hline(y=50, line_dash="dash", line_color="gray", opacity=0.5)
            fig.update_traces(marker=dict(line=dict(width=1, color='DarkSlateGrey'), opacity=0.8),
                              textposition='top center', textfont=dict(size=13, color='black', family="Arial Black"))
            fig.update_layout(height=800)
            st.plotly_chart(fig, use_container_width=True)

# =======================================================
# [모드 2] 챔피언 통합 분석
# =======================================================
elif selected_menu == "챔피언 통합 분석":
    st.title(f"{selected_pos.split()[0]} - 챔피언 상세 통계")
    try:
        df_counter = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_counters.csv"))
        df_time = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_time_stats.csv"))
        df_runes = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_runes.csv"))
        df_sides = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_sides.csv"))
        df_stats = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_stats.csv"))
        df_spells = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_spells.csv"))
    except:
        st.error("분석 데이터가 부족합니다.")
        st.stop()

    db_pos = {'탑 (TOP)': 'TOP', '정글 (JUNGLE)': 'JUNGLE', '미드 (MIDDLE)': 'MIDDLE', '원딜 (BOTTOM)': 'BOTTOM',
              '서포터 (SUPPORT)': 'UTILITY'}[selected_pos]
    full_list = sorted(df_counter[df_counter['position'] == db_pos]['me'].unique())
    filtered_list = [c for c in full_list if c in valid_champions]

    if not filtered_list:
        st.warning("데이터가 없습니다.")
        st.stop()

    default_idx = filtered_list.index(st.session_state['target_champ']) if st.session_state[
                                                                               'target_champ'] in filtered_list else 0
    target_champ = st.selectbox("분석할 챔피언 선택", filtered_list, index=default_idx)
    if target_champ != st.session_state['target_champ']:
        st.session_state['target_champ'] = target_champ
        st.rerun()

    real_stats = load_real_stats(selected_pos, target_champ)

    # 탭 메뉴 정의
    analysis_tabs = ["룬 & 스펠", "빌드 요약", "아이템 상세", "스킬 트리", "시야 전략", "상대 전적", "시간 & 진영", "능력치 분석",
                     "운영 & 오브젝트"]

    if st.session_state.get('champ_analysis_tab') not in analysis_tabs:
        st.session_state['champ_analysis_tab'] = analysis_tabs[0]

    current_sub_tab = st.radio("분석 항목", analysis_tabs, horizontal=True, label_visibility="collapsed",
                               key='champ_analysis_tab')

    # --- 헬퍼 함수 ---
    def highlight_win_row(row):
        try:
            win_col = next((c for c in row.index if '승률' in c), None)
            if not win_col: return [''] * len(row)
            win_rate = float(row[win_col])
            if win_rate >= 55:
                return ['background-color: #3CB371; color: white; font-weight: bold;'] * len(row)
            elif win_rate >= 52:
                return ['background-color: #90EE90; color: black;'] * len(row)
            elif win_rate >= 50:
                return ['background-color: #F0FFF0; color: black;'] * len(row)
            elif win_rate < 48:
                return ['background-color: #FFE4E1; color: black;'] * len(row)
            else:
                return [''] * len(row)
        except:
            return [''] * len(row)


    def highlight_power_score_row(row):
        try:
            tier_label = str(row['평가'])
            if "추천" in tier_label: return [
                'background-color: #FFD700; color: black; font-weight: bold; border-bottom: 2px solid white;'] * len(
                row)
            score = float(row['power_score'])
            if score >= 70:
                return ['background-color: #d1e7dd; color: black; font-weight: bold;'] * len(row)
            elif score >= 60:
                return ['background-color: #e2e3e5; color: black;'] * len(row)
            elif score >= 50:
                return ['background-color: #f8f9fa; color: black;'] * len(row)
            else:
                return ['background-color: #ffffff; color: #555555;'] * len(row)
        except:
            return [''] * len(row)


    # --- Tab 0: 룬 & 스펠 ---
    if current_sub_tab == "룬 & 스펠":
        st.subheader(f"{target_champ} 룬/스펠")
        c1, c2 = st.columns([1.5, 1])

        with c1:
            st.markdown("##### 룬 조합")
            rune_data = df_runes[(df_runes['position'] == db_pos) & (df_runes['champion'] == target_champ)].copy()
            if not rune_data.empty:
                top_runes = rune_data.sort_values(by='total_games', ascending=False).head(3)
                for _, row in top_runes.iterrows():
                    with st.container(border=True):
                        rc1, rc2 = st.columns([2, 1])
                        rc1.markdown(f"**{row['rune_key']}** ({row['rune_main']} + {row['rune_sub']})")
                        rc2.markdown(f"**{row['win_rate']}%** ({row['total_games']}판)")
                        st.progress(row['win_rate'] / 100)

                stats_df = rune_data.copy()
                stats_df['name_display'] = stats_df['rune_main'] + " + " + stats_df['rune_sub']
                res = check_significance(stats_df, name_col='name_display', count_col='total_games')
                display_stat_insight(res, context="룬 세팅")
            else:
                st.info("데이터 없음")

        with c2:
            st.markdown("##### 스펠 조합")
            spell_data = df_spells[(df_spells['position'] == db_pos) & (df_spells['champion'] == target_champ)].copy()
            if not spell_data.empty:
                total = spell_data['total_games'].sum()
                threshold = total * 0.05 if total >= 20 else 1
                valid_spells = spell_data[spell_data['total_games'] >= threshold]
                s_df = valid_spells.sort_values(by=['win_rate', 'total_games'], ascending=[False, False]).head(5)
                s_df = s_df[['spell1', 'spell2', 'win_rate', 'total_games']].rename(
                    columns={'spell1': '스펠 1', 'spell2': '스펠 2', 'win_rate': '승률 (%)',
                             'total_games': '판수'}).reset_index(drop=True)
                styler = s_df.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['승률 (%)']).hide(
                    axis='index')
                display_html_table(s_df, styler)

                stats_df = spell_data.copy()
                stats_df['name_display'] = stats_df['spell1'] + " + " + stats_df['spell2']
                res = check_significance(stats_df, name_col='name_display', count_col='total_games')
                display_stat_insight(res, context="스펠 조합")
            else:
                st.info("데이터 없음")

    # --- Tab 1: 빌드 요약 ---
    elif current_sub_tab == "빌드 요약":
        st.subheader(f"{target_champ}의 빌드 요약")
        c_start, c_shoes = st.columns([2, 1])
        with c_start:
            if selected_pos == '서포터 (SUPPORT)':
                st.markdown("###### 서포팅 퀘스트")
                if 'support_quest' in real_stats and not real_stats['support_quest'].empty:
                    df_sup = real_stats['support_quest'].copy()
                    d = df_sup.sort_values(by=['win_rate', 'pick_count'], ascending=[False, False]).head(5)
                    d_show = d[['item_name', 'win_rate', 'pick_count']].rename(
                        columns={'item_name': '퀘스트 완성', 'win_rate': '승률 (%)', 'pick_count': '선택'})
                    styler = d_show.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['승률 (%)']).hide(
                        axis='index')
                    display_html_table(d_show, styler)
                    res = check_significance(df_sup, name_col='item_name')
                    display_stat_insight(res, context="서포터 아이템")
                else:
                    st.info("데이터 부족")
            else:
                st.markdown("###### 시작 아이템")
                if not real_stats['starter'].empty:
                    df_start = real_stats['starter'].copy()
                    total = df_start['pick_count'].sum()
                    threshold = total * 0.05 if total >= 20 else 1
                    valid_starters = df_start[df_start['pick_count'] >= threshold]
                    d = valid_starters.sort_values(by=['win_rate', 'pick_count'], ascending=[False, False]).head(5)
                    d_show = d[['item_name', 'win_rate', 'pick_count']].rename(
                        columns={'item_name': '아이템 조합', 'win_rate': '승률 (%)', 'pick_count': '선택'})
                    styler = d_show.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['승률 (%)']).hide(
                        axis='index')
                    display_html_table(d_show, styler)
                    res = check_significance(valid_starters if not valid_starters.empty else df_start,
                                             name_col='item_name')
                    display_stat_insight(res, context="시작 아이템")
                else:
                    st.info("데이터 부족")

        with c_shoes:
            st.markdown("###### 추천 신발")
            if 'shoes' in real_stats and not real_stats['shoes'].empty:
                d = real_stats['shoes'].copy()
                d = d[~d['item_name'].isin(['장화', '약간 신비한 신발'])]
                d = d.sort_values('win_rate', ascending=False).head(5)[['item_name', 'win_rate']].rename(
                    columns={'item_name': '신발', 'win_rate': '승률 (%)'}).reset_index(drop=True)
                styler = d.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['승률 (%)']).hide(axis='index')
                display_html_table(d, styler)
            else:
                st.info("데이터 없음")

        st.divider()
        st.markdown("###### 핵심 3코어 빌드")
        if not real_stats['build'].empty:
            df_build = real_stats['build'].copy()
            total_games = df_build['pick_count'].sum()
            threshold = total_games * 0.05 if total_games >= 20 else 1
            valid_builds = df_build[df_build['pick_count'] >= threshold]

            b_df = valid_builds.sort_values(by=['win_rate', 'pick_count'], ascending=[False, False]).head(10)
            b_df_show = b_df[['build_path', 'win_rate', 'pick_count']].rename(
                columns={'build_path': '아이템 빌드 순서', 'win_rate': '승률 (%)', 'pick_count': '게임 수'})
            styler = b_df_show.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['승률 (%)']).hide(
                axis='index')
            display_html_table(b_df_show, styler)

            res = check_significance(valid_builds if not valid_builds.empty else df_build, name_col='build_path')
            display_stat_insight(res, context="빌드")
        else:
            st.warning("데이터 부족")

    # --- Tab 2: 아이템 상세 ---
    elif current_sub_tab == "아이템 상세":
        st.subheader("아이템별 상세 분석 & 파워 스파이크")
        has_items = 'item_detail' in real_stats and not real_stats['item_detail'].empty

        if 'item_spikes' in real_stats and not real_stats['item_spikes'].empty:
            with st.expander("⚡ 코어 아이템 완성 타이밍 (Power Spike) 보기", expanded=True):
                spike_data = real_stats['item_spikes'].copy()

                t1, t2, t3 = st.tabs(["1코어", "2코어", "3코어"])


                def plot_spike(rank, title_prefix):
                    if 'core_rank' not in spike_data.columns:
                        st.info("코어 랭크 정보가 없습니다.")
                        return

                    df = spike_data[(spike_data['core_rank'] == rank) & (spike_data['count'] >= 10)].copy()
                    df = df.sort_values('count', ascending=False).head(15)

                    if not df.empty:
                        x_label = "평균 완성 시간 (게임 시작 후)" if rank == 1 else "평균 소요 시간 (직전 코어 구매 후)"

                        fig = px.scatter(df, x="avg_min", y="win_rate", size="count", color="win_rate",
                                         text="item_name",
                                         hover_name="item_name",
                                         color_continuous_scale="RdYlGn",
                                         labels={'avg_min': x_label, 'win_rate': '승률 (%)', 'count': '표본 수',
                                                 'item_name': '아이템'},
                                         title=f"{target_champ}의 {title_prefix} 타이밍")

                        fig.add_hline(y=50, line_dash="dash", line_color="gray")
                        fig.update_layout(height=450)
                        fig.update_traces(textposition='top center',
                                          textfont=dict(size=12, color='black', family="Arial Black"))
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info(f"{rank}코어 분석 데이터가 충분하지 않습니다.")


                with t1:
                    plot_spike(1, "1코어(신화/핵심)")
                with t2:
                    plot_spike(2, "2코어")
                with t3:
                    plot_spike(3, "3코어")

                st.caption("※ **1코어**: 게임 시작부터 걸린 시간 / **2,3코어**: 이전 코어템 구매 후 추가로 걸린 시간")
        else:
            st.warning("아이템 타이밍 데이터가 없습니다.")

        st.divider()

        if has_items:
            show_data = real_stats['item_detail'].copy()[
                (~real_stats['item_detail']['item_name'].isin(BOOTS_LIST)) & (
                    real_stats['item_detail']['item_name'].isin(get_completed_item_names()))]

            c1, c2 = st.columns([1, 1])
            with c1:
                min_limit = 5 if show_data['pick_count'].sum() > 50 else 1
                valid_items = show_data[show_data['pick_count'] >= min_limit].copy()

                if not valid_items.empty:
                    max_pick = valid_items['pick_count'].max()
                    valid_items['power_score'] = valid_items['win_rate'] + (valid_items['pick_count'] / max_pick * 20)


                    def assign_label(row):
                        s = row['power_score']
                        if s >= 70:
                            return "핵심"
                        elif s >= 60:
                            return "강력"
                        elif s >= 50:
                            return "준수"
                        else:
                            return "연구"


                    valid_items['평가'] = valid_items.apply(assign_label, axis=1)
                    rank_map = {"핵심": 4, "강력": 3, "준수": 2, "연구": 1}
                    valid_items['rank_score'] = valid_items['평가'].map(rank_map)
                    table_d = valid_items.sort_values(by=['rank_score', 'win_rate', 'pick_count'],
                                                      ascending=[False, False, False])

                    display_cols = ['평가', 'item_name', 'win_rate', 'pick_count', 'power_score']
                    table_d = table_d[display_cols].rename(
                        columns={'item_name': '아이템', 'win_rate': '승률 (%)', 'pick_count': '구매'}).reset_index(drop=True)
                    styler = table_d.style.apply(highlight_power_score_row, axis=1).format("{:.1f}",
                                                                                           subset=['승률 (%)']).hide(
                        axis='index').hide(subset=['power_score'], axis='columns')
                    display_html_table(table_d, styler)

                    res = check_significance(valid_items, name_col='item_name')
                    display_stat_insight(res, context="코어 아이템")
                else:
                    st.info("조건에 맞는 아이템 데이터가 없습니다.")
            with c2:
                fig = px.scatter(show_data, x="pick_count", y="win_rate", size="pick_count", color="win_rate",
                                 text="item_name", hover_name="item_name",
                                 color_continuous_scale="RdYlGn", title="구매 횟수 / 승률",
                                 labels={'pick_count': '구매 횟수', 'win_rate': '승률 (%)', 'item_name': '아이템'})
                fig.add_hline(y=50, line_dash="dash", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("아이템 데이터가 없습니다.")

    # --- Tab 3: 스킬 트리 ---
    elif current_sub_tab == "스킬 트리":
        st.subheader(f"{target_champ} 스킬 마스터 순서")
        if not real_stats['skill'].empty:
            s_df = real_stats['skill'].sort_values('pick_count', ascending=False).head(5)
            for idx, row in s_df.iterrows():
                master_str = row['master_order']
                path_list = row['skill_path'].split(',')
                with st.container(border=True):
                    c_head1, c_head2, c_head3 = st.columns([4, 1, 1])
                    with c_head1: st.markdown(f"<h4 style='margin:0; padding:0;'> {master_str} 선마</h4>",
                                              unsafe_allow_html=True)
                    with c_head2: st.metric("승률", f"{row['win_rate']:.1f}%")
                    with c_head3: st.metric("게임 수", f"{row['pick_count']}")
                    skill_html = "<div style='margin-top: 10px; display: flex; flex-wrap: wrap; gap: 4px;'>"
                    for i, skill in enumerate(path_list):
                        color_map = {'Q': '#2980b9', 'W': '#27ae60', 'E': '#e67e22', 'R': '#c0392b'}
                        bg_color = color_map.get(skill, '#95a5a6')
                        box_style = f"width:28px;height:28px;line-height:28px;background-color:{bg_color};color:white;text-align:center;border-radius:4px;font-weight:bold;font-size:13px;"
                        spacer_style = "margin-right: 12px;" if (i + 1) in [6, 11, 16] else "margin-right: 2px;"
                        skill_html += f"""<div style="display:flex; flex-direction:column; align-items:center; {spacer_style}"><span style="font-size:9px; color:#888; margin-bottom:1px;">{i + 1}</span><div style="{box_style}">{skill}</div></div>"""
                    skill_html += "</div>"
                    st.markdown(skill_html, unsafe_allow_html=True)
        else:
            st.info("데이터 부족")

    # --- Tab 4: 시야 전략 ---
    elif current_sub_tab == "시야 전략":
        st.subheader(f"{target_champ} 시야 운영 전략")

        if 'vision_timeline' in real_stats and not real_stats['vision_timeline'].empty:
            st.markdown("##### 시간대별 와드 설치/제거 흐름")
            v_time = real_stats['vision_timeline'].copy()
            # [수정] 한글 범례 적용
            v_time.rename(columns={'placed': '와드 설치', 'killed': '와드 제거'}, inplace=True)

            fig = px.line(v_time, x='time_min', y=['와드 설치', '와드 제거'], markers=True,
                          labels={'time_min': '게임 시간 (분)', 'value': '횟수 (평균)', 'variable': '활동'},
                          color_discrete_map={'와드 설치': '#2ecc71', '와드 제거': '#e74c3c'})
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
            st.divider()

        st.caption("장신구 교체 타이밍 분석")
        if 'trinket' in real_stats and not real_stats['trinket'].empty:
            t_df = real_stats['trinket'].copy()


            def format_swap_time(row):
                if "유지" in row['strategy'] or row['avg_swap_time'] < 1000:
                    return "계속 사용"
                else:
                    return f"평균 {int(row['avg_swap_time'] / 1000) // 60}분 경 교체"


            t_df['timing'] = t_df.apply(format_swap_time, axis=1)
            t_df = t_df.sort_values(by=['win_rate', 'pick_count'], ascending=[False, False]).head(5)
            view_df = t_df[['strategy', 'timing', 'win_rate', 'pick_count']].rename(
                columns={'strategy': '운영 전략', 'timing': '타이밍', 'win_rate': '승률 (%)', 'pick_count': '게임 수'})
            styler = view_df.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['승률 (%)']).hide(
                axis='index')
            display_html_table(view_df, styler)
        else:
            st.warning("데이터 부족")

    # --- Tab 5: 상대 전적 ---
    elif current_sub_tab == "상대 전적":
        st.subheader(f"{target_champ}의 상성")
        my_data = df_counter[(df_counter['position'] == db_pos) & (df_counter['me'] == target_champ)].copy()
        if not my_data.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 불리 (승률 ▼)")
                hard_df = my_data.sort_values(by='win_rate', ascending=True).head(5)[
                    ['enemy', 'win_rate', 'total_games']].rename(
                    columns={'enemy': '상대', 'win_rate': '내 승률 (%)', 'total_games': '전적'}).reset_index(drop=True)
                styler = hard_df.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['내 승률 (%)']).hide(
                    axis='index')
                display_html_table(hard_df, styler)
            with c2:
                st.markdown("#### 유리 (승률 ▲)")
                easy_df = my_data.sort_values(by='win_rate', ascending=False).head(5)[
                    ['enemy', 'win_rate', 'total_games']].rename(
                    columns={'enemy': '상대', 'win_rate': '내 승률 (%)', 'total_games': '전적'}).reset_index(drop=True)
                styler = easy_df.style.apply(highlight_win_row, axis=1).format("{:.1f}", subset=['내 승률 (%)']).hide(
                    axis='index')
                display_html_table(easy_df, styler)
        else:
            st.info("데이터 부족")

    # --- Tab 6: 시간 & 진영 ---
    elif current_sub_tab == "시간 & 진영":
        st.subheader("시간대 및 진영 분석")
        col_time, col_side = st.columns(2)
        with col_time:
            st.markdown("##### 시간대별 승률")
            t_data = df_time[(df_time['position'] == db_pos) & (df_time['champion'] == target_champ)].copy()
            if not t_data.empty:
                time_order = {'0-20분': 0, '20-25분': 1, '25-30분': 2, '30-35분': 3, '35-40분': 4, '40분+': 5}
                t_data['sort_key'] = t_data['game_time'].map(time_order)
                t_data = t_data.sort_values('sort_key')
                fig = px.line(t_data, x='game_time', y='win_rate', markers=True, text='win_rate',
                              labels={'game_time': '게임 시간', 'win_rate': '승률 (%)'})
                fig.update_traces(line=dict(color='#636EFA', width=4, shape='spline'), fill='tozeroy',
                                  texttemplate='%{text:.1f}%', textposition="top center")
                fig.add_hline(y=50, line_dash="dash", line_color="red")
                fig.update_yaxes(range=[35, 65])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("데이터 없음")
        with col_side:
            st.markdown("##### 진영별 승률")
            s_data = df_sides[(df_sides['position'] == db_pos) & (df_sides['champion'] == target_champ)].copy()
            if not s_data.empty:
                fig = px.bar(s_data, x='team', y='win_rate', color='team', text='win_rate',
                             color_discrete_map={'Blue': '#2980b9', 'Red': '#e74c3c'},
                             labels={'team': '진영', 'win_rate': '승률 (%)'})
                fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig.add_hline(y=50, line_dash="dash", line_color="gray")
                fig.update_yaxes(range=[40, 60])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("데이터 없음")

    # --- Tab 7: 능력치 분석 ---
    elif current_sub_tab == "능력치 분석":
        st.subheader("챔피언 능력치")
        pos_stats = df_stats[df_stats['position'] == db_pos].copy()
        my_stat = pos_stats[pos_stats['champion'] == target_champ]
        if not my_stat.empty:
            def get_score(val, col_name):
                max_val = pos_stats[col_name].max();
                min_val = pos_stats[col_name].min()
                if max_val == min_val: return 50
                return ((val - min_val) / (max_val - min_val)) * 100


            r_data = pd.DataFrame({
                'r': [get_score(my_stat['DPM'].values[0], 'DPM'), get_score(my_stat['avg_kda'].values[0], 'avg_kda'),
                      get_score(my_stat['GPM'].values[0], 'GPM'), get_score(my_stat['DTM'].values[0], 'DTM'),
                      get_score(my_stat['VSPM'].values[0], 'VSPM')],
                'theta': ['공격력', '생존력', '성장력', '탱킹력', '시야']
            })
            c1, c2 = st.columns([1, 2])
            with c1:
                fig = px.line_polar(r_data, r='r', theta='theta', line_close=True)
                fig.update_traces(fill='toself', line_color='#8B5CF6')
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False,
                                  height=350)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                m = my_stat.iloc[0]
                c2.markdown("#### 상세 수치")
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("KDA", f"{m['avg_kda']:.2f}")
                cc2.metric("DPM", f"{int(m['DPM']):,}")
                cc3.metric("GPM", f"{int(m['GPM']):,}")
                cc4, cc5, cc6 = st.columns(3)
                cc4.metric("받은피해", f"{int(m['DTM']):,}")
                cc5.metric("시야점수", f"{m['VSPM']:.2f}")
                cc6.metric("평균 CS", f"{int(m['avg_cs'])}")

    # --- Tab 8: 운영 & 오브젝트 ---
    elif current_sub_tab == "운영 & 오브젝트":
        st.subheader(f"{target_champ}의 운영 능력 (오브젝트 & 방패)")

        macro_df = load_macro_data()
        if macro_df is not None:
            my_macro = macro_df[(macro_df['position'] == db_pos) & (macro_df['champion'] == target_champ)]

            if not my_macro.empty:
                row = my_macro.iloc[0]

                st.markdown("##### 오브젝트 및 방패 채굴 (평균 대비)")
                obj_data = pd.DataFrame({
                    '항목': ['드래곤', '바론', '공허 유충', '포탑 방패'],
                    '내 챔피언': [row['avg_dragon'], row['avg_baron'], row['avg_horde'], row['avg_plates']],
                    '포지션 평균': [row['pos_dragon'], row['pos_baron'], row['pos_horde'], row['pos_plates']]
                })
                obj_melt = obj_data.melt(id_vars='항목', var_name='구분', value_name='획득 수')

                c1, c2 = st.columns([2, 1])
                with c1:
                    fig = px.bar(obj_melt, x='항목', y='획득 수', color='구분', barmode='group',
                                 color_discrete_map={'내 챔피언': '#636EFA', '포지션 평균': '#EF553B'}, text_auto='.2f')
                    fig.update_layout(height=350)
                    st.plotly_chart(fig, use_container_width=True)

                with c2:
                    st.info(f"""
                    **운영 분석**

                    * **방패 채굴:** 평균보다 **{row['diff_plates']:+.2f}**개
                    * **드래곤:** 평균보다 **{row['diff_dragon']:+.2f}**마리
                    * **유충:** 평균보다 **{row['diff_horde']:+.2f}**마리

                    (포탑 방패 수치가 높으면 강력한 라인전을, 드래곤 수치가 높으면 훌륭한 합류/운영 능력을 의미합니다.)
                    """)

                st.divider()

                st.markdown("##### 시야 장악 능력")
                v1, v2, v3 = st.columns(3)
                v1.metric("평균 시야 점수", f"{row['avg_vision']:.1f}점", f"{row['diff_vision']:+.1f}점")
                v2.metric("제어 와드 구매", f"{row['avg_ward']:.2f}개",
                          f"{row['diff_ward'] if 'diff_ward' in row else row['avg_ward'] - row['pos_ward']:+.2f}개")

                vision_grade = "S급 (맵핵 수준)" if row['diff_vision'] > 5 else "A급" if row[
                                                                                               'diff_vision'] > 0 else "B급" if \
                row['diff_vision'] > -5 else "C급"
                v3.markdown(f"**🕵️ 시야 등급:**\n### {vision_grade}")

            else:
                st.warning("데이터 부족")
        else:
            st.error("champion_macro.csv 파일이 없습니다.")

# =======================================================
# [모드 3] 메타 & 오브젝트 분석
# =======================================================
elif selected_menu == "메타 & 오브젝트 분석":
    st.title("협곡 메타 리포트 (전체 매치 분석)")
    st.caption("※ 드래곤, 영혼, 방패 등 게임의 승패를 가르는 핵심 요소를 분석합니다.")

    try:
        df_side = pd.read_csv(os.path.join(ADVANCED_FOLDER, "meta_side_win.csv"))
        df_dragon = pd.read_csv(os.path.join(ADVANCED_FOLDER, "meta_dragon_count.csv"))
        df_baron = pd.read_csv(os.path.join(ADVANCED_FOLDER, "meta_baron_count.csv"))
        df_horde = pd.read_csv(os.path.join(ADVANCED_FOLDER, "meta_horde_count.csv"))
        df_time = pd.read_csv(os.path.join(ADVANCED_FOLDER, "meta_time_dist.csv"))

        path_soul = os.path.join(ADVANCED_FOLDER, "dragon_soul_stats.csv")
        df_soul = pd.read_csv(path_soul) if os.path.exists(path_soul) else pd.DataFrame()

        path_type = os.path.join(ADVANCED_FOLDER, "dragon_type_stats.csv")
        df_type = pd.read_csv(path_type) if os.path.exists(path_type) else pd.DataFrame()

        path_plate = os.path.join(ADVANCED_FOLDER, "meta_plate_impact.csv")
        df_plate_meta = pd.read_csv(path_plate) if os.path.exists(path_plate) else pd.DataFrame()

        path_grub = os.path.join(ADVANCED_FOLDER, "void_grub_stats.csv")
        df_grub = pd.read_csv(path_grub) if os.path.exists(path_grub) else pd.DataFrame()

    except:
        st.error("메타 분석 데이터가 일부 부족합니다.")
        st.stop()

    tabs = st.tabs(["진영 밸런스", "드래곤 & 영혼", "유충 & 바론", "방패 & 시간"])

    # --- Tab 1: 진영 ---
    with tabs[0]:
        st.subheader("블루팀 vs 레드팀 승률")
        c1_list = st.columns(1)
        c1 = c1_list[0]
        with c1:
            fig = px.pie(df_side, values='win_rate', names='team_name',
                         color='team_name',
                         color_discrete_map={'Blue': '#2980b9', 'Red': '#e74c3c'}, hole=0.4)
            fig.update_traces(textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)

    # --- Tab 2: 드래곤 ---
    with tabs[1]:
        st.subheader("드래곤의 지배자")
        c_soul, c_type = st.columns(2)

        with c_soul:
            if not df_soul.empty:
                st.markdown("##### 드래곤 영혼 승률")
                fig = px.bar(df_soul, x='dragon_name', y='win_rate', color='win_rate',
                             text='win_rate', title="영혼 획득 시 승률",
                             labels={'dragon_name': '드래곤 종류', 'win_rate': '승률 (%)'},
                             color_continuous_scale='Bluyl')
                fig.update_traces(texttemplate='%{text:.1f}%')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("영혼 데이터 없음")

        with c_type:
            if not df_type.empty:
                st.markdown("##### 드래곤 종류별 처치 승률")
                fig = px.bar(df_type, x='dragon_name', y='win_rate', text='win_rate',
                             title="1마리라도 처치했을 때 승률",
                             labels={'dragon_name': '드래곤 종류', 'win_rate': '승률 (%)'})
                fig.update_traces(texttemplate='%{text:.1f}%')
                fig.add_hline(y=50, line_dash="dash", line_color="gray")
                fig.update_yaxes(range=[40, 70])
                st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.markdown("##### 드래곤 획득 수별 승률")
        fig = px.bar(df_dragon, x='dragon_count', y='win_rate', text='win_rate', color='win_rate',
                     labels={'dragon_count': '드래곤 획득 수', 'win_rate': '승률 (%)'})
        fig.update_traces(texttemplate='%{text:.1f}%')
        st.plotly_chart(fig, use_container_width=True)

    # --- Tab 3: 유충 & 바론 ---
    with tabs[2]:
        c_grub, c_baron = st.columns(2)
        with c_grub:
            st.markdown("##### 공허 유충 승률")
            if not df_grub.empty:
                fig = px.bar(df_grub, x='count', y='win_rate', text='win_rate',
                             labels={'count': '유충 처치 수', 'win_rate': '승률 (%)'},
                             color='win_rate', color_continuous_scale='Purples')
                fig.update_traces(texttemplate='%{text:.1f}%')
                fig.update_xaxes(dtick=1)
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = px.bar(df_horde, x='horde_count', y='win_rate', text='win_rate',
                             labels={'horde_count': '유충 처치 수', 'win_rate': '승률 (%)'})
                fig.update_xaxes(dtick=1)
                st.plotly_chart(fig, use_container_width=True)

        with c_baron:
            st.markdown("##### 바론 처치 승률")
            fig = px.line(df_baron, x='baron_count', y='win_rate', markers=True, text='win_rate',
                          labels={'baron_count': '바론 처치 수', 'win_rate': '승률 (%)'})
            fig.update_xaxes(dtick=1)
            fig.update_traces(line_color='#8e44ad', line_width=4, texttemplate='%{text:.1f}%',
                              textposition="top center")
            st.plotly_chart(fig, use_container_width=True)

    # --- Tab 4: 방패 & 시간  ---
    with tabs[3]:
        st.subheader("포탑 방패 & 게임 시간")
        c1, c2 = st.columns(2)

        with c1:
            if not df_plate_meta.empty:
                st.markdown("##### 방패 채굴과 게임 시간의 관계")
                fig = px.scatter(df_plate_meta, x='Total Plates Taken', y='Avg Game Time (min)',
                                 trendline="ols", title="방패를 많이 깰수록 게임이 빨리 끝날까?",
                                 labels={'Total Plates Taken': '총 방패 파괴 수', 'Avg Game Time (min)': '평균 게임 시간 (분)'})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("방패 메타 데이터 없음")

        with c2:
            st.markdown("##### 게임 시간 분포")
            avg_time = df_time['duration_min'].mean()
            fig = px.histogram(df_time, x="duration_min", nbins=20, color_discrete_sequence=['#2ecc71'],
                               labels={'duration_min': '게임 시간 (분)', 'count': '게임 수'})
            fig.update_layout(yaxis_title="게임 수")
            fig.add_vline(x=avg_time, line_dash="dash", line_color="red", annotation_text=f"평균 {avg_time:.1f}분")
            st.plotly_chart(fig, use_container_width=True)


# =======================================================
# [모드 4] 재미로 보는 통계
# =======================================================
elif selected_menu == "재미로 보는 통계":
    st.title(f"{selected_pos.split()[0]} 라인 - 재미로 보는 랭킹 ({selected_category})")
    try:
        df_stats = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_stats.csv"))
        df_sides = pd.read_csv(os.path.join(ADVANCED_FOLDER, "champion_sides.csv"))
    except:
        st.error("데이터가 없습니다.")
        st.stop()
    db_pos = {'탑 (TOP)': 'TOP', '정글 (JUNGLE)': 'JUNGLE', '미드 (MIDDLE)': 'MIDDLE', '원딜 (BOTTOM)': 'BOTTOM',
              '서포터 (SUPPORT)': 'UTILITY'}[selected_pos]
    rank_data = df_stats[df_stats['position'] == db_pos].copy()
    rank_data = rank_data[rank_data['champion'].isin(valid_champions)]

    if rank_data.empty:
        st.warning("데이터가 없습니다.")
    else:
        st.subheader("전투 민족 랭킹")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 솔로킬 머신")
            top_solo = rank_data.sort_values(by='avg_solokills', ascending=False).head(5)
            fig = px.bar(top_solo, x='avg_solokills', y='champion', orientation='h', text='avg_solokills',
                         color='avg_solokills', color_continuous_scale='Reds',
                         labels={'avg_solokills': '평균 솔로킬 횟수', 'champion': '챔피언'})
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="평균 솔로킬 횟수", showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("##### 회색 화면 수집가")
            top_death = rank_data.sort_values(by='avg_deaths', ascending=False).head(5)
            fig = px.bar(top_death, x='avg_deaths', y='champion', orientation='h', text='avg_deaths',
                         color='avg_deaths', color_continuous_scale='Greys',
                         labels={'avg_deaths': '평균 데스', 'champion': '챔피언'})
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="평균 데스", showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
        st.divider()
        st.subheader("게임 시간 랭킹")
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("##### 스피드 게임러")
            short_game = rank_data.sort_values(by='avg_time', ascending=True).head(5).copy()
            short_game['분'] = (short_game['avg_time'] / 60).round(1)
            fig = px.bar(short_game, x='분', y='champion', orientation='h', text='분', color='분',
                         color_continuous_scale='Teal',
                         labels={'분': '평균 게임 시간 (분)', 'champion': '챔피언'})
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="평균 게임 시간 (분)", showlegend=False,
                              height=300)
            st.plotly_chart(fig, use_container_width=True)
        with c4:
            st.markdown("##### 눕롤 전문가")
            long_game = rank_data.sort_values(by='avg_time', ascending=False).head(5).copy()
            long_game['분'] = (long_game['avg_time'] / 60).round(1)
            fig = px.bar(long_game, x='분', y='champion', orientation='h', text='분', color='분',
                         color_continuous_scale='Oranges',
                         labels={'분': '평균 게임 시간 (분)', 'champion': '챔피언'})
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="평균 게임 시간 (분)", showlegend=False,
                              height=300)
            st.plotly_chart(fig, use_container_width=True)
        st.divider()
        st.subheader("블루빨 / 레드빨 잘 받는 챔피언")
        side_df_pos = df_sides[df_sides['position'] == db_pos].copy()
        side_df_pos = side_df_pos[side_df_pos['champion'].isin(valid_champions)]
        side_pivot = side_df_pos.pivot_table(index='champion', columns='team', values='win_rate')
        if 'Blue' in side_pivot.columns and 'Red' in side_pivot.columns:
            side_pivot = side_pivot.dropna()
            side_pivot['diff'] = side_pivot['Blue'] - side_pivot['Red']
            c5, c6 = st.columns(2)
            with c5:
                st.markdown("##### 블루팀일 때 더 센 챔피언")
                blue_top = side_pivot.sort_values(by='diff', ascending=False).head(5).reset_index()
                fig = px.bar(blue_top, x='diff', y='champion', orientation='h', text='diff', color='diff',
                             color_continuous_scale='Blues',
                             labels={'diff': '승률 차이 (블루 - 레드)', 'champion': '챔피언'})
                fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="블루팀 승률 - 레드팀 승률", showlegend=False,
                                  height=300)
                fig.update_traces(texttemplate='+%{text:.1f}%')
                st.plotly_chart(fig, use_container_width=True)
            with c6:
                st.markdown("##### 레드팀일 때 더 센 챔피언")
                red_top = side_pivot.sort_values(by='diff', ascending=True).head(5).reset_index()
                red_top['abs_diff'] = red_top['diff'].abs()
                fig = px.bar(red_top, x='abs_diff', y='champion', orientation='h', text='abs_diff', color='abs_diff',
                             color_continuous_scale='Reds',
                             labels={'abs_diff': '승률 차이 (레드 - 블루)', 'champion': '챔피언'})
                fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="레드팀 승률 - 블루팀 승률", showlegend=False,
                                  height=300)
                fig.update_traces(texttemplate='+%{text:.1f}%')
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("진영 데이터가 충분하지 않습니다.")