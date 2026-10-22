
import html
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# -----------------------------
# 페이지 설정
# -----------------------------
st.set_page_config(
    page_title="일일 박스오피스",
    page_icon="🎬",
    layout="wide",
)

KST = ZoneInfo("Asia/Seoul")
TODAY = datetime.now(KST).date()
YESTERDAY = TODAY - timedelta(days=1)

KOBIS_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"


# -----------------------------
# 따뜻한 크림색과 노란색 디자인
# -----------------------------
st.markdown(
    """
    <style>
    .stApp {
        background-color: #fffdf7;
        color: #3a2e1a;
    }

    h1, h2, h3 {
        color: #a96b00;
    }

    div[data-testid="stMetric"] {
        background-color: #fff6e0;
        border: 1px solid #f0dfb3;
        border-radius: 14px;
        padding: 16px;
    }

    div[data-testid="stMetricLabel"] {
        color: #75551b;
    }

    .movie-card {
        background-color: #fff6e0;
        border: 1px solid #f0dfb3;
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 12px;
    }

    .movie-title {
        font-size: 18px;
        font-weight: bold;
        color: #704800;
    }

    .small-note {
        color: #786b55;
        font-size: 13px;
    }

    .up-arrow {
        color: #e53935;
        font-weight: bold;
    }

    .down-arrow {
        color: #1976d2;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# 날짜 및 숫자 표시 함수
# -----------------------------
def format_date(value):
    """날짜를 YYYY.MM.DD 형식으로 표시합니다."""
    if not value or len(str(value)) != 8:
        return "-"
    value = str(value)
    return f"{value[:4]}.{value[4:6]}.{value[6:8]}"


def format_number(value):
    """숫자를 천 단위 쉼표와 함께 표시합니다."""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return "0"


def rank_change_label(rank_inten, old_and_new):
    """
    KOBIS 순위 증감 표시:
    양수 = 순위 상승, 음수 = 순위 하락, 0 = 변동 없음
    """
    if old_and_new == "NEW":
        return "NEW"

    try:
        change = int(rank_inten)
    except (ValueError, TypeError):
        change = 0

    if change > 0:
        return f"UP:{change}"
    elif change < 0:
        return f"DOWN:{abs(change)}"
    return "변동 없음"


def display_rank_change(label):
    """표에 표시할 색상 화살표 HTML을 만듭니다."""
    if label.startswith("UP:"):
        number = label.split(":")[1]
        return (
            f'<span class="up-arrow">↑ {html.escape(number)}</span>'
        )

    if label.startswith("DOWN:"):
        number = label.split(":")[1]
        return (
            f'<span class="down-arrow">↓ {html.escape(number)}</span>'
        )

    if label == "NEW":
        return '<span style="color:#e8930c;font-weight:bold;">NEW</span>'

    return '<span style="color:#786b55;">—</span>'


# -----------------------------
# KOBIS 박스오피스 데이터 가져오기
# -----------------------------
@st.cache_data(ttl=1800)
def get_boxoffice(target_date, api_key):
    """선택한 날짜의 일일 박스오피스를 가져옵니다."""
    response = requests.get(
        KOBIS_URL,
        params={
            "key": api_key,
            "targetDt": target_date,
        },
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    # KOBIS API가 오류 정보를 반환했는지 확인합니다.
    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 API 오류")
        raise ValueError(f"KOBIS API 오류: {message}")

    boxoffice = data.get("boxOfficeResult", {})
    movies = boxoffice.get("dailyBoxOfficeList", [])

    return movies


# -----------------------------
# TMDB 영화 포스터 가져오기
# -----------------------------
@st.cache_data(ttl=3600)
def get_movie_poster(movie_name, api_key):
    """TMDB에서 영화 포스터를 검색합니다."""
    if not api_key:
        return None

    try:
        response = requests.get(
            TMDB_SEARCH_URL,
            params={
                "api_key": api_key,
                "query": movie_name,
                "language": "ko-KR",
                "include_adult": "false",
            },
            timeout=10,
        )

        response.raise_for_status()
        results = response.json().get("results", [])

        if not results:
            return None

        poster_path = results[0].get("poster_path")
        if poster_path:
            return f"https://image.tmdb.org/t/p/w500{poster_path}"

    except (requests.RequestException, ValueError, KeyError):
        return None

    return None


# -----------------------------
# 제목
# -----------------------------
st.title("🎬 일일 박스오피스")
st.write("보고 싶은 날짜를 선택하고 그날의 영화 순위를 확인해 보세요!")
st.caption("영화 순위와 관객 수: 영화진흥위원회(KOBIS) 일일 박스오피스")


# -----------------------------
# API 키 확인
# -----------------------------
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "KOBIS API 키를 찾을 수 없어요. "
        "Streamlit Cloud의 앱 설정에서 Secrets에 KOBIS_KEY를 등록해 주세요."
    )
    st.stop()

try:
    TMDB_KEY = st.secrets.get("TMDB_KEY", "")
except Exception:
    TMDB_KEY = ""


# -----------------------------
# 날짜 선택
# -----------------------------
st.subheader("📅 날짜 선택")

selected_date = st.date_input(
    "조회할 날짜",
    value=YESTERDAY,
    min_value=date(2004, 1, 1),
    max_value=YESTERDAY,
    help="오늘은 아직 집계가 완료되지 않았으므로 어제까지 선택할 수 있어요.",
)

target_date = selected_date.strftime("%Y%m%d")
st.caption(f"선택한 날짜: {selected_date.strftime('%Y년 %m월 %d일')}")


# -----------------------------
# 데이터 조회
# -----------------------------
try:
    movies = get_boxoffice(target_date, KOBIS_KEY)

except requests.Timeout:
    st.error("서버 응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.")
    st.stop()

except requests.RequestException:
    st.error("박스오피스 데이터를 가져오지 못했어요. 인터넷 연결을 확인해 주세요.")
    st.stop()

except ValueError as error:
    st.error(str(error))
    st.stop()

except Exception:
    st.error(
        "데이터를 불러오는 중 문제가 발생했어요. "
        "API 키와 Streamlit Secrets 설정을 확인해 주세요."
    )
    st.stop()


# -----------------------------
# 데이터가 없을 때
# -----------------------------
if not movies:
    st.warning("그날은 아직 집계 전입니다")
    st.info("다른 날짜를 선택해 다시 확인해 주세요.")
    st.stop()


# -----------------------------
# 데이터 정리
# -----------------------------
df = pd.DataFrame(movies)

required_columns = [
    "rank",
    "movieNm",
    "openDt",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "rankInten",
    "rankOldAndNew",
]

for column in required_columns:
    if column not in df.columns:
        df[column] = ""

# 관객 수와 스크린 수를 숫자로 변환합니다.
for column in ["rank", "audiCnt", "audiAcc", "scrnCnt", "rankInten"]:
    df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)

# 누적 관객 수가 100만 명을 초과하면 트로피를 표시합니다.
df["표시 영화명"] = df.apply(
    lambda row: (
        f"{row['movieNm']} 🏆"
        if row["audiAcc"] > 1_000_000
        else row["movieNm"]
    ),
    axis=1,
)

# 순위 변동 정보를 정리합니다.
df["순위 변동"] = df.apply(
    lambda row: rank_change_label(
        row["rankInten"],
        row["rankOldAndNew"],
    ),
    axis=1,
)


# -----------------------------
# 1위 영화 소개
# -----------------------------
first_movie = df.iloc[0]

st.divider()
st.subheader("🏆 오늘의 1위 영화")

col_poster, col_info = st.columns([1, 2])

with col_poster:
    poster_url = get_movie_poster(first_movie["movieNm"], TMDB_KEY)

    if poster_url:
        st.image(poster_url, width=230)
    else:
        st.markdown("## 🎞️")
        st.caption("포스터를 찾지 못했어요.")

with col_info:
    first_title = first_movie["movieNm"]
    if first_movie["audiAcc"] > 1_000_000:
        first_title += " 🏆"

    st.markdown(f"### 🥇 {first_title}")
    st.write(f"개봉일: {format_date(first_movie['openDt'])}")

    metric1, metric2, metric3 = st.columns(3)

    metric1.metric(
        "일일 관객 수",
        f"{format_number(first_movie['audiCnt'])}명",
    )
    metric2.metric(
        "누적 관객 수",
        f"{format_number(first_movie['audiAcc'])}명",
    )
    metric3.metric(
        "스크린 수",
        f"{format_number(first_movie['scrnCnt'])}개",
    )


# -----------------------------
# TOP 5 관객 수 그래프
# -----------------------------
st.divider()
st.subheader("📊 관객 수 TOP 5")

top5 = df.head(5).copy()
chart_df = pd.DataFrame({
    "영화": top5["표시 영화명"],
    "관객 수": top5["audiCnt"],
})

st.bar_chart(
    chart_df.set_index("영화")["관객 수"],
    horizontal=True,
)

st.caption("그래프는 선택한 날짜의 일일 관객 수를 기준으로 합니다.")


# -----------------------------
# TOP 5 영화 포스터
# -----------------------------
st.divider()
st.subheader("🍿 TOP 5 영화 포스터")

poster_columns = st.columns(5)

for index, (_, movie) in enumerate(top5.iterrows()):
    with poster_columns[index]:
        poster_url = get_movie_poster(movie["movieNm"], TMDB_KEY)

        st.markdown(f"**{index + 1}위**")

        if poster_url:
            st.image(poster_url, use_container_width=True)
        else:
            st.markdown("🎬")
            st.caption("포스터 없음")

        title = html.escape(movie["movieNm"])
        if movie["audiAcc"] > 1_000_000:
            title += " 🏆"

        st.markdown(f"**{title}**", unsafe_allow_html=True)
        st.caption(f"일일 관객 {format_number(movie['audiCnt'])}명")


# -----------------------------
# 전체 순위표
# -----------------------------
st.divider()
st.subheader("📋 전체 박스오피스 순위")

table_html = """
<table style="width:100%; border-collapse:collapse; background:#fffdf7;">
<thead>
<tr style="background:#fff0c2; border-bottom:2px solid #e7d6a7;">
<th style="padding:10px; text-align:center;">순위</th>
<th style="padding:10px; text-align:left;">영화명</th>
<th style="padding:10px; text-align:center;">순위 변동</th>
<th style="padding:10px; text-align:center;">개봉일</th>
<th style="padding:10px; text-align:right;">일일 관객</th>
<th style="padding:10px; text-align:right;">누적 관객</th>
<th style="padding:10px; text-align:right;">스크린 수</th>
</tr>
</thead>
<tbody>
"""

for _, movie in df.iterrows():
    rank = int(movie["rank"])
    movie_name = html.escape(str(movie["movieNm"]))

    if movie["audiAcc"] > 1_000_000:
        movie_name += " 🏆"

    change_html = display_rank_change(movie["순위 변동"])

    table_html += f"""
    <tr style="border-bottom:1px solid #eee2c8;">
      <td style="padding:10px; text-align:center;">{rank}</td>
      <td style="padding:10px; text-align:left; font-weight:600;">{movie_name}</td>
      <td style="padding:10px; text-align:center;">{change_html}</td>
      <td style="padding:10px; text-align:center;">{format_date(movie["openDt"])}</td>
      <td style="padding:10px; text-align:right;">{format_number(movie["audiCnt"])}</td>
      <td style="padding:10px; text-align:right;">{format_number(movie["audiAcc"])}</td>
      <td style="padding:10px; text-align:right;">{format_number(movie["scrnCnt"])}</td>
    </tr>
    """

table_html += "</tbody></table>"

st.markdown(table_html, unsafe_allow_html=True)

st.divider()
st.markdown(
    """
    <p class="small-note">
    데이터 출처: 영화진흥위원회(KOBIS) 일일 박스오피스<br>
    포스터: TMDB 검색 결과 (TMDB API 키가 설정된 경우 표시)
    </p>
    """,
    unsafe_allow_html=True,
)
