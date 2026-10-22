import html
import json
import re
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="오늘의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

KST = ZoneInfo("Asia/Seoul")
TODAY_KST = datetime.now(KST).date()
YESTERDAY = TODAY_KST - timedelta(days=1)
KOBIS_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# ------------------------------------------------------------
# 디자인
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800;900&display=swap');

    :root { color-scheme: dark; }
    .stApp {
        background:
            radial-gradient(circle at 12% 0%, rgba(112, 75, 190, .16), transparent 30%),
            radial-gradient(circle at 90% 15%, rgba(28, 174, 190, .09), transparent 25%),
            #0b0d14;
        color: #f4f5fb;
        font-family: 'Noto Sans KR', sans-serif;
    }
    .block-container { max-width: 1400px; padding-top: 2rem; padding-bottom: 3rem; }
    h1, h2, h3 { letter-spacing: -0.04em; }
    h1 { font-weight: 900 !important; }
    .eyebrow {
        color: #a99af8; font-size: .82rem; font-weight: 800;
        letter-spacing: .15em; text-transform: uppercase; margin-bottom: .4rem;
    }
    .subtitle { color: #9ca3b8; margin-top: -.6rem; margin-bottom: 1.4rem; }
    .panel {
        background: linear-gradient(145deg, rgba(27,31,46,.96), rgba(18,21,32,.96));
        border: 1px solid #2d3448; border-radius: 20px;
        padding: 22px; height: 100%;
    }
    .hero-title { font-size: 1.55rem; font-weight: 900; line-height: 1.35; margin: .2rem 0 .4rem; }
    .muted { color: #9ca3b8; font-size: .9rem; }
    .metric-label { color: #a6adc2; font-size: .82rem; margin-bottom: .45rem; }
    .metric-value { font-size: 1.55rem; font-weight: 900; letter-spacing: -.04em; }
    .metric-card {
        background: #171b29; border: 1px solid #30374b; border-radius: 16px;
        padding: 17px 18px; min-height: 104px;
    }
    .rank-pill {
        display: inline-block; background: #292344; color: #c8baff;
        padding: 5px 10px; border-radius: 999px; font-size: .8rem; font-weight: 800;
    }
    .poster-card {
        background: #171b29; border: 1px solid #30374b; border-radius: 16px;
        padding: 12px; height: 100%;
    }
    .poster-name { font-weight: 800; font-size: .92rem; line-height: 1.45; margin-top: 8px; }
    .poster-meta { color: #9ca3b8; font-size: .8rem; margin-top: 4px; }
    div[data-testid="stMetric"] {
        background: #171b29; border: 1px solid #30374b;
        border-radius: 15px; padding: 16px;
    }
    div[data-testid="stMetricLabel"] { color: #a6adc2; }
    div[data-testid="stMetricValue"] { color: #f5f6ff; }
    div[data-testid="stDateInput"] label, div[data-testid="stSelectbox"] label { color: #d9dced; }
    .stButton button {
        border-radius: 10px; border: 1px solid #4b426e;
        background: #28213e; color: #f5f1ff; font-weight: 700;
    }
    .stButton button:hover { border-color: #a99af8; color: white; }
    hr { border-color: #292f40; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# 데이터 가져오기
# ------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_boxoffice(api_key: str, target_date: str):
    """KOBIS 일별 박스오피스 데이터를 가져옵니다."""
    response = requests.get(
        KOBIS_URL,
        params={"key": api_key, "targetDt": target_date},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    if "faultInfo" in payload:
        fault = payload["faultInfo"]
        raise RuntimeError(
            fault.get("message", "KOBIS API에서 오류를 반환했습니다.")
        )

    return payload.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])


@st.cache_data(ttl=21600, show_spinner=False)
def get_tmdb_movie(movie_name: str, open_date: str, api_key: str):
    """
    TMDB에서 제목과 개봉 연도를 기준으로 영화를 검색합니다.
    이미지 검색 엔진의 무관한 이미지가 포스터로 표시되는 문제를 피합니다.
    """
    if not api_key:
        return None

    headers = {"accept": "application/json"}
    try:
        year = open_date[:4] if open_date and len(open_date) >= 4 else ""
        params = {
            "api_key": api_key,
            "query": movie_name,
            "language": "ko-KR",
            "include_adult": "false",
        }
        if year.isdigit():
            params["year"] = year

        response = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params=params, headers=headers, timeout=12
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            # 연도 조건 때문에 검색이 안 되는 경우 제목으로 한 번 더 검색
            params.pop("year", None)
            response = requests.get(
                "https://api.themoviedb.org/3/search/movie",
                params=params, headers=headers, timeout=12
            )
            response.raise_for_status()
            results = response.json().get("results", [])

        if not results:
            return None

        def normalize(text):
            return re.sub(r"[^0-9a-z가-힣]", "", str(text).lower())

        target = normalize(movie_name)
        def score(item):
            titles = [item.get("title", ""), item.get("original_title", "")]
            title_score = max(
                (100 if normalize(t) == target else
                 70 if target and (target in normalize(t) or normalize(t) in target) else 0)
                for t in titles
            )
            item_date = str(item.get("release_date", ""))
            if year and item_date.startswith(year):
                title_score += 10
            if item.get("poster_path"):
                title_score += 2
            return title_score

        best_movie = max(results, key=score)
        # 제목이 충분히 일치하지 않으면 엉뚱한 포스터를 보여주지 않습니다.
        if score(best_movie) < 70:
            return None
        movie = best_movie
        movie_id = movie.get("id")
        # 선택한 영화의 한국어 줄거리를 상세 API에서 확인
        detail_response = requests.get(
            f"https://api.themoviedb.org/3/movie/{movie_id}",
            params={"api_key": api_key, "language": "ko-KR"},
            headers=headers, timeout=12
        )
        detail_response.raise_for_status()
        details = detail_response.json()

        overview = (details.get("overview") or movie.get("overview") or "").strip()
        if not overview:
            en_response = requests.get(
                f"https://api.themoviedb.org/3/movie/{movie_id}",
                params={"api_key": api_key, "language": "en-US"},
                headers=headers, timeout=12
            )
            en_response.raise_for_status()
            overview = (en_response.json().get("overview") or "").strip()

        poster_path = details.get("poster_path") or movie.get("poster_path")
        poster_url = (
            f"https://image.tmdb.org/t/p/w500{poster_path}"
            if poster_path else None
        )
        return {
            "id": movie_id,
            "title": details.get("title") or movie.get("title") or movie_name,
            "overview": overview,
            "poster_url": poster_url,
            "release_date": details.get("release_date") or movie.get("release_date", ""),
            "runtime": details.get("runtime"),
            "genres": [g.get("name", "") for g in details.get("genres", []) if g.get("name")],
            "vote_average": details.get("vote_average"),
        }
    except (requests.RequestException, ValueError, TypeError):
        return None


def get_movie_poster(movie_name: str, open_date: str, api_key: str):
    movie = get_tmdb_movie(movie_name, open_date, api_key)
    return movie.get("poster_url") if movie else None


def number(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def safe_movie_title(row):
    title = str(row.get("movieNm", "제목 미상"))
    try:
        audience = int(row.get("audiAcc", "0") or 0)
    except (ValueError, TypeError):
        audience = 0
    return f"{title} 🏆" if audience > 1_000_000 else title


def rank_change(row):
    try:
        movement = int(row.get("rankInten", "0") or 0)
    except (ValueError, TypeError):
        movement = 0

    old_new = row.get("rankOldAndNew", "")
    if old_new == "NEW":
        return "NEW"
    if movement > 0:
        return f"🔺 +{movement}"
    if movement < 0:
        return f"🔻 {movement}"
    return "—"


def show_poster(movie_name, open_date, api_key, height=320):
    poster_url = get_movie_poster(movie_name, open_date, api_key)
    if poster_url:
        st.image(poster_url, use_container_width=True)
        return True
    st.markdown(
        """
        <div style="
            min-height:230px; display:flex; align-items:center; justify-content:center;
            background:#1a1e2b; border:1px solid #30374b; border-radius:14px;
            color:#a99af8; font-size:3.3rem;">🎬</div>
        """,
        unsafe_allow_html=True,
    )
    return False


# ------------------------------------------------------------
# 상단 제목 / 날짜 선택
# ------------------------------------------------------------
st.markdown('<div class="eyebrow">KOREAN BOX OFFICE · DAILY REPORT</div>', unsafe_allow_html=True)
st.title("🎬 오늘의 박스오피스")
st.markdown(
    '<div class="subtitle">매일의 영화 흥행 순위를 한눈에 확인하세요.</div>',
    unsafe_allow_html=True,
)

left, right = st.columns([3, 1])
with left:
    selected_date = st.date_input(
        "조회 날짜",
        value=YESTERDAY,
        min_value=date(2004, 1, 1),
        max_value=YESTERDAY,
        format="YYYY-MM-DD",
    )
with right:
    st.markdown("<div style='height:29px'></div>", unsafe_allow_html=True)
    st.caption(f"최대 조회 날짜: {YESTERDAY.strftime('%Y-%m-%d')}")

st.divider()

# ------------------------------------------------------------
# API 키 확인 및 조회
# ------------------------------------------------------------
api_key = st.secrets.get("KOBIS_KEY", "")
tmdb_api_key = st.secrets.get("TMDB_API_KEY", "")

if not api_key:
    st.error(
        "KOBIS API 키를 찾을 수 없습니다. Streamlit Cloud의 "
        "앱 설정 → Secrets에 `KOBIS_KEY = \"발급받은_API_키\"`를 추가해 주세요."
    )
    st.stop()

if not tmdb_api_key:
    st.info(
        "포스터와 줄거리 기능을 정확하게 사용하려면 Streamlit Secrets에 "
        '`TMDB_API_KEY = "발급받은_TMDB_API_키"`를 추가해 주세요. '
        "API 키가 없으면 포스터는 기본 이미지로 표시됩니다."
    )

target_dt = selected_date.strftime("%Y%m%d")

try:
    with st.spinner("박스오피스 데이터를 불러오는 중입니다..."):
        rows = fetch_boxoffice(api_key, target_dt)
except requests.exceptions.Timeout:
    st.error("KOBIS 서버 응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.")
    st.stop()
except requests.exceptions.RequestException as exc:
    st.error(f"KOBIS 서버에 연결하지 못했습니다: {exc}")
    st.stop()
except (ValueError, RuntimeError) as exc:
    st.error(f"박스오피스 데이터를 읽지 못했습니다: {exc}")
    st.stop()
except Exception as exc:
    st.error(f"예상하지 못한 오류가 발생했습니다: {exc}")
    st.stop()

if not rows:
    st.info("그날은 아직 집계 전입니다")
    st.caption("다른 날짜를 선택해 다시 조회해 보세요.")
    st.stop()

# API 결과를 숫자형으로 정리
df = pd.DataFrame(rows)
numeric_columns = [
    "rank", "rankInten", "openDt", "salesAmt", "salesAcc",
    "audiCnt", "audiAcc", "scrnCnt", "showCnt"
]
for column in numeric_columns:
    if column in df.columns:
        if column == "openDt":
            continue
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)

df = df.sort_values("rank", ascending=True).reset_index(drop=True)
df["표시 영화명"] = df.apply(safe_movie_title, axis=1)
df["순위 변동"] = df.apply(rank_change, axis=1)

# ------------------------------------------------------------
# 1위 영화 요약
# ------------------------------------------------------------
first = df.iloc[0]
first_name = str(first.get("movieNm", "제목 미상"))
first_open_date = str(first.get("openDt", "정보 없음"))
first_audience = int(first.get("audiCnt", 0))
first_total = int(first.get("audiAcc", 0))
first_sales = int(first.get("salesAmt", 0))

st.markdown("## 오늘의 박스오피스 1위")
hero_col, info_col = st.columns([1.05, 1.6], gap="large")

with hero_col:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    show_poster(first_name, first_open_date, tmdb_api_key)
    st.markdown("</div>", unsafe_allow_html=True)

with info_col:
    st.markdown('<div class="eyebrow">RANK #1</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="hero-title">{html.escape(safe_movie_title(first))}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="muted">개봉일 · {html.escape(first_open_date)}</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("일일 관객 수", f"{number(first_audience)}명")
    with m2:
        st.metric("누적 관객 수", f"{number(first_total)}명")
    with m3:
        st.metric("일일 매출액", f"{number(first_sales)}원")

    st.markdown(
        f"""
        <div class="metric-card" style="margin-top:12px">
          <div class="metric-label">상영 스크린 수</div>
          <div class="metric-value">{number(first.get("scrnCnt", 0))}<span style="font-size:.9rem;color:#9ca3b8"> 개</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")
st.divider()

# ------------------------------------------------------------
# TOP 10 관객 수 차트
# ------------------------------------------------------------
st.markdown("## 📊 TOP 10 관객 수")
top10 = df.head(10).copy()
max_audience = max(1, int(top10["audiCnt"].max()))
for _, movie_row in top10.iterrows():
    rank_col, name_col, bar_col, count_col = st.columns([0.45, 2.0, 4.2, 1.2])
    with rank_col:
        st.markdown(
            f'<div style="color:#a99af8;font-weight:900;padding-top:7px">#{int(movie_row["rank"])}</div>',
            unsafe_allow_html=True,
        )
    with name_col:
        st.markdown(
            f'<div style="padding-top:7px;font-weight:700">{html.escape(str(movie_row["movieNm"]))}</div>',
            unsafe_allow_html=True,
        )
    with bar_col:
        pct = int(int(movie_row["audiCnt"]) / max_audience * 100)
        st.markdown(
            f'<div style="margin-top:11px;height:12px;background:#202537;border-radius:99px;overflow:hidden">'
            f'<div style="width:{pct}%;height:12px;border-radius:99px;background:linear-gradient(90deg,#8b5cf6,#4dd6c8)"></div></div>',
            unsafe_allow_html=True,
        )
    with count_col:
        st.markdown(
            f'<div style="text-align:right;color:#b9c2d8;padding-top:6px;font-size:.88rem">{number(movie_row["audiCnt"])}명</div>',
            unsafe_allow_html=True,
        )

st.write("")
st.divider()

# ------------------------------------------------------------
# TOP 10 포스터 + 클릭해서 줄거리 보기
# ------------------------------------------------------------
st.markdown("## 🍿 TOP 10 영화")
st.caption("영화 제목 아래의 ‘줄거리 보기’를 누르면 해당 영화의 정보가 열립니다.")

for row_start in range(0, len(top10), 5):
    poster_cols = st.columns(5, gap="medium")
    batch = top10.iloc[row_start:row_start + 5]
    for col, (_, movie_row) in zip(poster_cols, batch.iterrows()):
        movie_name = str(movie_row.get("movieNm", ""))
        movie_open_date = str(movie_row.get("openDt", ""))
        with col:
            st.markdown('<div class="poster-card">', unsafe_allow_html=True)
            poster_url = get_movie_poster(movie_name, movie_open_date, tmdb_api_key)
            if poster_url:
                st.image(poster_url, use_container_width=True)
            else:
                st.markdown(
                    '<div style="height:230px;display:flex;align-items:center;justify-content:center;'
                    'background:#1a1e2b;border:1px solid #30374b;border-radius:12px;font-size:3rem">🎬</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<div class="poster-name">#{int(movie_row["rank"])} · {html.escape(movie_name)}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="poster-meta">{number(movie_row["audiCnt"])}명 · 개봉 {html.escape(movie_open_date)}</div>',
                unsafe_allow_html=True,
            )
            if st.button("줄거리 보기", key=f"plot_{int(movie_row['rank'])}_{row_start}_{movie_name}", use_container_width=True):
                st.session_state["selected_plot_movie"] = {
                    "name": movie_name,
                    "open_date": movie_open_date,
                    "rank": int(movie_row["rank"]),
                }
            st.markdown("</div>", unsafe_allow_html=True)

selected_movie = st.session_state.get("selected_plot_movie")
if selected_movie:
    st.write("")
    st.markdown("---")
    st.markdown(f"## 🎞️ {html.escape(selected_movie['name'])}")
    if not tmdb_api_key:
        st.warning(
            "정확한 포스터와 줄거리 정보를 연결하려면 TMDB API 키가 필요해요. "
            "Streamlit Cloud → Manage app → Settings → Secrets에 "
            '`TMDB_API_KEY = "발급받은_TMDB_API_키"`를 추가해 주세요.'
        )
    else:
        with st.spinner("영화 정보와 줄거리를 불러오는 중..."):
            movie_info = get_tmdb_movie(
                selected_movie["name"], selected_movie["open_date"], tmdb_api_key
            )
        if movie_info:
            detail_left, detail_right = st.columns([1, 2], gap="large")
            with detail_left:
                if movie_info.get("poster_url"):
                    st.image(movie_info["poster_url"], use_container_width=True)
                else:
                    st.info("등록된 포스터가 없습니다.")
            with detail_right:
                st.markdown(f"### {html.escape(movie_info.get('title') or selected_movie['name'])}")
                metadata = []
                if movie_info.get("release_date"):
                    metadata.append(f"개봉일 {movie_info['release_date']}")
                if movie_info.get("runtime"):
                    metadata.append(f"{movie_info['runtime']}분")
                if movie_info.get("genres"):
                    metadata.append(" · ".join(movie_info["genres"]))
                if metadata:
                    st.caption("  |  ".join(metadata))
                overview = movie_info.get("overview")
                if overview:
                    st.write(overview)
                else:
                    st.info("이 영화의 줄거리는 데이터베이스에 등록되어 있지 않습니다.")
                if movie_info.get("vote_average"):
                    st.caption(f"TMDB 평점: {float(movie_info['vote_average']):.1f}/10")
        else:
            st.warning("영화 정보를 찾지 못했어요. TMDB API 키 또는 해당 영화의 등록 정보를 확인해 주세요.")
    if st.button("줄거리 닫기", key="close_plot"):
        del st.session_state["selected_plot_movie"]
        st.rerun()


# ------------------------------------------------------------
# 전체 순위 표
# ------------------------------------------------------------
st.markdown("## 📋 전체 박스오피스 순위")
st.caption("🔺 순위 상승 · 🔻 순위 하락 · NEW 신규 진입 · 🏆 누적 관객 100만 명 초과")

table = pd.DataFrame({
    "순위": df["rank"].astype(int),
    "영화명": df["표시 영화명"],
    "순위 변동": df["순위 변동"],
    "개봉일": df["openDt"].astype(str),
    "일일 관객 수": df["audiCnt"].map(number),
    "누적 관객 수": df["audiAcc"].map(number),
    "스크린 수": df["scrnCnt"].map(number),
})

def style_rank(value):
    if isinstance(value, str) and value.startswith("🔺"):
        return "color: #ff6b7a; font-weight: 800;"
    if isinstance(value, str) and value.startswith("🔻"):
        return "color: #69a9ff; font-weight: 800;"
    if value == "NEW":
        return "color: #c4b5fd; font-weight: 800;"
    return "color: #aab1c5;"

try:
    styled_table = (
        table.style
        .map(style_rank, subset=["순위 변동"])
        .set_properties(**{
            "background-color": "#111521",
            "color": "#eef0f8",
            "border-color": "#2d3448",
        })
    )
    st.dataframe(styled_table, use_container_width=True, hide_index=True)
except (AttributeError, TypeError):
    # 구버전 pandas와의 호환을 위한 대체 표시
    st.dataframe(table, use_container_width=True, hide_index=True)

st.markdown(
    """
    <div style="text-align:center;color:#737b91;font-size:.8rem;margin-top:28px">
      순위 데이터: 영화관입장권통합전산망(KOBIS) · 포스터/줄거리: TMDB
    </div>
    """,
    unsafe_allow_html=True,
)
