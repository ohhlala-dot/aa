
# main.py
# 영화진흥위원회(KOBIS)의 어제 박스오피스를 보여 주는 앱입니다.
# 영화 포스터, 순위 변동, 관객수 그래프를 함께 제공합니다.

import streamlit as st
import pandas as pd
import requests

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ==================================================
# 1. 페이지 설정과 디자인
# ==================================================

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.markdown("""
<style>
    .stApp {
        background-color: #fffaf0;
        color: #382b20;
    }

    h1, h2, h3 {
        color: #9b5b18;
    }

    div[data-testid="stMetric"] {
        background-color: #fff0c9;
        border: 1px solid #f0d58a;
        border-radius: 15px;
        padding: 16px;
    }

    div[data-testid="stMetricValue"] {
        color: #9b5b18;
    }

    .subtitle {
        color: #765c42;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎬 어제의 박스오피스")
st.markdown(
    '<p class="subtitle">'
    '어제 가장 많은 관객을 모은 영화는 무엇일까요?'
    '</p>',
    unsafe_allow_html=True
)


# ==================================================
# 2. 한국 시간 기준으로 어제 날짜 계산
# ==================================================

# 서버의 시간대가 아닌 한국 시간대를 사용합니다.
korea_now = datetime.now(ZoneInfo("Asia/Seoul"))
yesterday = korea_now.date() - timedelta(days=1)

# KOBIS API에서 사용하는 날짜 형식: YYYYMMDD
target_date = yesterday.strftime("%Y%m%d")
display_date = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"📅 조회 기준일: {display_date} (한국 시간)")


# ==================================================
# 3. API 인증키 불러오기
# ==================================================

# 인증키를 코드에 직접 작성하지 않습니다.
# Streamlit Cloud의 Settings → Secrets에서 설정합니다.
try:
    kobis_key = st.secrets["KOBIS_KEY"]
except Exception:
    st.error("🔑 KOBIS API 인증키를 찾을 수 없습니다.")
    st.markdown("""
    **해결 방법**

    1. Streamlit Cloud에서 앱의 Settings → Secrets를 엽니다.
    2. `KOBIS_KEY` 항목을 추가합니다.
    3. 발급받은 인증키가 정확한지 확인합니다.

    설정 형식:

    `KOBIS_KEY = "발급받은_인증키"`
    """)
    st.stop()

# 포스터 검색용 TMDB 키는 선택 사항입니다.
# 키가 없더라도 박스오피스 표와 그래프는 작동합니다.
try:
    tmdb_key = st.secrets.get("TMDB_KEY", "")
except Exception:
    tmdb_key = ""


# ==================================================
# 4. 영화 포스터 검색 함수
# ==================================================

@st.cache_data(ttl=3600)
def get_movie_poster(movie_title, api_key):
    """TMDB에서 영화 제목으로 포스터 주소를 검색합니다."""

    if not api_key:
        return None

    try:
        response = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params={
                "api_key": api_key,
                "query": movie_title,
                "language": "ko-KR"
            },
            timeout=10
        )
        response.raise_for_status()

        results = response.json().get("results", [])

        # 검색 결과 중 포스터가 있는 첫 번째 영화를 사용합니다.
        for movie in results:
            poster_path = movie.get("poster_path")

            if poster_path:
                return (
                    "https://image.tmdb.org/t/p/w500"
                    + poster_path
                )

    except (requests.exceptions.RequestException, ValueError):
        # 포스터 검색이 실패해도 앱 전체를 중단하지 않습니다.
        return None

    return None


# ==================================================
# 5. 순위 변동 표시 함수
# ==================================================

def format_rank_change(row):
    """전날 대비 순위 변동을 한국어로 표시합니다."""

    # NEW는 박스오피스 신규 진입을 의미합니다.
    if str(row.get("rankOldAndNew", "")).upper() == "NEW":
        return "🆕 신규 진입"

    try:
        change = int(row.get("rankInten", 0))
    except (ValueError, TypeError):
        return "변동 정보 없음"

    # KOBIS rankInten의 양수는 순위 상승을 뜻합니다.
    if change > 0:
        return f"🔺 {change}계단 상승"

    if change < 0:
        return f"🔻 {abs(change)}계단 하락"

    return "➖ 순위 유지"


# ==================================================
# 6. 개봉일 표시 함수
# ==================================================

def format_open_date(value):
    """개봉일을 YYYY-MM-DD 형식으로 표시합니다."""

    value = str(value).strip()

    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    return value if value else "-"


# ==================================================
# 7. KOBIS 일별 박스오피스 API 요청
# ==================================================

API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/"
    "rest/boxoffice/searchDailyBoxOfficeList.json"
)

params = {
    "key": kobis_key,
    "targetDt": target_date
}

try:
    with st.spinner("🎞️ 영화 순위를 불러오는 중입니다..."):
        response = requests.get(
            API_URL,
            params=params,
            timeout=20
        )
        response.raise_for_status()
        data = response.json()

except requests.exceptions.Timeout:
    st.error("⏰ API 응답 시간이 초과되었습니다.")
    st.info("잠시 기다린 뒤 다시 실행해 주세요.")
    st.stop()

except requests.exceptions.HTTPError:
    st.error(
        f"🌐 API 서버 HTTP 오류가 발생했습니다. "
        f"(상태 코드: {response.status_code})"
    )
    st.info("KOBIS API 주소와 서버 상태를 확인해 주세요.")
    st.stop()

except requests.exceptions.RequestException as error:
    st.error("🌐 KOBIS API에 연결할 수 없습니다.")
    st.info("인터넷 연결, API 주소 또는 서버 상태를 확인해 주세요.")
    st.caption(f"오류 종류: {type(error).__name__}")
    st.stop()

except ValueError:
    st.error("📦 API 응답을 JSON으로 읽을 수 없습니다.")
    st.info("KOBIS API 서버가 정상적인 데이터를 반환하는지 확인해 주세요.")
    st.stop()


# ==================================================
# 8. API 오류 응답 확인
# ==================================================

# 인증키가 틀려도 HTTP 상태 코드가 200일 수 있습니다.
# 따라서 응답 본문의 faultInfo도 확인해야 합니다.
if not isinstance(data, dict):
    st.error("API 응답 형식이 올바르지 않습니다.")
    st.info("KOBIS API 응답을 확인해 주세요.")
    st.stop()

if "faultInfo" in data:
    fault = data["faultInfo"]

    st.error("🚨 KOBIS API에서 오류를 반환했습니다.")
    st.write("**오류 코드:**", fault.get("errorCode", "알 수 없음"))
    st.write("**오류 내용:**", fault.get("message", "내용 없음"))

    st.info(
        "인증키가 정확한지, API 사용 신청이 승인되었는지, "
        "요청 날짜와 API 설정이 올바른지 확인해 주세요."
    )
    st.stop()


# ==================================================
# 9. 영화 목록 확인
# ==================================================

box_office = data.get("boxOfficeResult", {})
movie_list = box_office.get("dailyBoxOfficeList", [])

if not movie_list:
    st.warning(f"📭 {display_date}의 영화 순위 데이터가 없습니다.")
    st.markdown("""
    **확인할 사항**

    - 해당 날짜의 박스오피스 집계가 완료되었는지 확인합니다.
    - API 응답에 `dailyBoxOfficeList`가 있는지 확인합니다.
    - 인증키와 요청 날짜가 올바른지 확인합니다.
    """)
    st.stop()

# API 응답을 표와 그래프에 사용하기 편한 데이터프레임으로 만듭니다.
df = pd.DataFrame(movie_list)

required_columns = [
    "rank",
    "rankInten",
    "movieNm",
    "openDt",
    "audiCnt",
    "audiAcc",
    "scrnCnt"
]

missing_columns = [
    column for column in required_columns
    if column not in df.columns
]

if missing_columns:
    st.error("📋 API 응답에 필요한 항목이 누락되었습니다.")
    st.write("누락된 항목:", ", ".join(missing_columns))
    st.info("KOBIS API의 응답 구조를 확인해 주세요.")
    st.stop()

# API 숫자 값은 문자열이므로 숫자로 변환합니다.
number_columns = [
    "rank", "rankInten", "audiCnt",
    "audiAcc", "scrnCnt", "showCnt"
]

for column in number_columns:
    if column in df.columns:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        ).fillna(0)

# 순위가 낮은 숫자부터 정렬합니다.
df = df.sort_values("rank").reset_index(drop=True)

# 순위 변동에 필요한 값이 없는 경우에도 안전하게 처리합니다.
if "rankOldAndNew" not in df.columns:
    df["rankOldAndNew"] = ""


# ==================================================
# 10. 1위 영화 포스터와 주요 지표
# ==================================================

first_movie = df.iloc[0]

st.divider()
st.subheader("🏆 어제의 1위 영화")

left, right = st.columns([1, 2])

with left:
    first_poster = get_movie_poster(
        str(first_movie["movieNm"]),
        tmdb_key
    )

    if first_poster:
        st.image(first_poster, use_container_width=True)
    else:
        st.info(
            "🎞️ 포스터를 표시할 수 없습니다.\n\n"
            "TMDB_KEY 설정 또는 검색 결과를 확인해 주세요."
        )

with right:
    st.markdown(f"## 🥇 {first_movie['movieNm']}")
    st.markdown(
        f"**순위 변동:** {format_rank_change(first_movie)}"
    )

    # 큰 지표 카드 세 장을 나란히 보여 줍니다.
    metric1, metric2, metric3 = st.columns(3)

    with metric1:
        st.metric(
            "당일 관객수",
            f"{int(first_movie['audiCnt']):,}명"
        )

    with metric2:
        st.metric(
            "누적 관객수",
            f"{int(first_movie['audiAcc']):,}명"
        )

    with metric3:
        st.metric(
            "스크린 수",
            f"{int(first_movie['scrnCnt']):,}개"
        )


# ==================================================
# 11. 관객수 상위 5편 막대그래프
# ==================================================

st.divider()
st.subheader("📊 관객수 TOP 5")

top5 = (
    df.sort_values("audiCnt", ascending=False)
      .head(5)
      .sort_values("audiCnt", ascending=True)
)

# 영화 제목을 세로축에 표시하는 가로 막대그래프입니다.
chart_df = top5.set_index("movieNm")[["audiCnt"]]

st.bar_chart(
    chart_df,
    x_label="영화",
    y_label="관객수 (명)",
    horizontal=True
)


# ==================================================
# 12. TOP 5 영화 포스터 모아 보기
# ==================================================

st.subheader("🍿 인기 영화 포스터")

poster_movies = df.sort_values(
    "audiCnt", ascending=False
).head(5)

poster_columns = st.columns(5)

for column, (_, movie) in zip(
    poster_columns, poster_movies.iterrows()
):
    with column:
        poster_url = get_movie_poster(
            str(movie["movieNm"]),
            tmdb_key
        )

        if poster_url:
            st.image(
                poster_url,
                use_container_width=True
            )
        else:
            st.caption("포스터 없음")

        st.markdown(f"**{int(movie['rank'])}위**")
        st.write(str(movie["movieNm"]))
        st.caption(format_rank_change(movie))
        st.caption(f"관객 {int(movie['audiCnt']):,}명")


# ==================================================
# 13. 전체 영화 순위 표
# ==================================================

st.divider()
st.subheader("🎞️ 전체 일별 박스오피스")

table_df = pd.DataFrame({
    "순위": df["rank"].astype(int),
    "순위 변동": df.apply(format_rank_change, axis=1),
    "영화명": df["movieNm"],
    "개봉일": df["openDt"].apply(format_open_date),
    "관객수": df["audiCnt"].map(lambda x: f"{int(x):,}"),
    "누적관객": df["audiAcc"].map(lambda x: f"{int(x):,}"),
    "스크린수": df["scrnCnt"].map(lambda x: f"{int(x):,}")
})

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True
)


# ==================================================
# 14. 데이터 출처와 포스터 안내
# ==================================================

st.caption(
    "박스오피스 데이터: 영화진흥위원회(KOBIS) Open API"
)

st.caption(
    "포스터 이미지: TMDB 검색 결과. "
    "포스터 표시에는 TMDB API 키와 인터넷 연결이 필요합니다."
)
