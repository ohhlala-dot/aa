
import html
import json
from datetime import date, datetime, timedelta
from io import BytesIO
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image


# =========================================
# 1. 기본 설정
# =========================================
st.set_page_config(
    page_title="다크 박스오피스",
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


# =========================================
# 2. 다크 테마 디자인
# =========================================
st.markdown(
    """
    <style>
    .stApp {
        background-color: #101218;
        color: #e8eaf0;
    }

    [data-testid="stHeader"] {
        background-color: #101218;
    }

    h1, h2, h3 {
        color: #f0c674 !important;
    }

    p, label, span {
        color: inherit;
    }

    div[data-testid="stMetric"] {
        background-color: #1b1f2b;
        border: 1px solid #353b4c;
        border-radius: 14px;
        padding: 16px;
    }

    div[data-testid="stMetricLabel"] {
        color: #b9c0d0 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #f0c674 !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #353b4c;
    }

    div[data-testid="stAlert"] {
        border-radius: 12px;
    }

    hr {
        border-color: #353b4c;
    }

    .movie-panel {
        background: #1b1f2b;
        border: 1px solid #353b4c;
        border-radius: 16px;
        padding: 18px;
        margin-bottom: 12px;
    }

    .gold-text {
        color: #f0c674;
        font-weight: bold;
    }

    .muted-text {
        color: #aab1c2;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================
# 3. 공통 함수
# =========================================
def number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def fmt_number(value):
    return f"{number(value):,}"


def fmt_date(value):
    value = str(value or "")

    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}.{value[4:6]}.{value[6:8]}"

    return value if value else "-"


def title_with_trophy(name, cumulative):
    name = str(name)

    if number(cumulative) > 1_000_000:
        return name + " 🏆"

    return name


def rank_change(rank_inten, old_and_new):
    if str(old_and_new).upper() == "NEW":
        return "NEW"

    change = number(rank_inten)

    # 요청한 기준: 양수는 상승, 음수는 하락
    if change > 0:
        return f"🔺 +{change}"

    if change < 0:
        return f"🔻 {change}"

    return "—"


# =========================================
# 4. KOBIS 데이터 가져오기
# =========================================
@st.cache_data(ttl=1800)
def get_boxoffice(target_date, api_key):
    response = requests.get(
        KOBIS_URL,
        params={
            "key": api_key,
            "targetDt": target_date,
        },
        timeout=20,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as error:
        raise ValueError(
            "KOBIS에서 올바른 JSON 데이터를 받지 못했어요."
        ) from error

    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 API 오류")
        raise ValueError(f"KOBIS API 오류: {message}")

    result = data.get("boxOfficeResult")

    if not isinstance(result, dict):
        raise ValueError(
            "KOBIS 응답에 박스오피스 결과가 없어요. API 키를 확인해 주세요."
        )

    return result.get("dailyBoxOfficeList", [])


# =========================================
# 5. TMDB 키 없이 포스터 검색
# =========================================
@st.cache_data(ttl=21600, show_spinner=False)
def get_movie_poster(movie_name, open_date=""):
    query = f"{movie_name} 영화 포스터"

    if open_date and len(str(open_date)) >= 4:
        query += f" {str(open_date)[:4]}"

    search_url = (
        "https://www.bing.com/images/search?"
        + urlencode({"q": query, "form": "HDRSC3"})
    )

    try:
        response = requests.get(
            search_url,
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        image_urls = []

        for item in soup.select("a.iusc"):
            metadata = item.get("m")

            if not metadata:
                continue

            try:
                info = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                continue

            url = info.get("murl", "")

            if (
                isinstance(url, str)
                and url.startswith(("https://", "http://"))
                and url not in image_urls
            ):
                image_urls.append(url)

            if len(image_urls) >= 4:
                break

        for url in image_urls:
            try:
                image_response = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=7,
                )
                image_response.raise_for_status()

                content_type = image_response.headers.get(
                    "Content-Type", ""
                ).lower()

                if not content_type.startswith("image/"):
                    continue

                content = image_response.content

                if not content or len(content) > 8 * 1024 * 1024:
                    continue

                try:
                    image = Image.open(BytesIO(content))
                    image.verify()
                except Exception:
                    continue

                return content

            except requests.RequestException:
                continue

        return None

    except requests.RequestException:
        return None


# =========================================
# 6. 제목 및 API 키
# =========================================
st.title("🎬 BOX OFFICE")
st.caption("DAILY MOVIE RANKINGS  /  영화진흥위원회 KOBIS")

try:
    api_key = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "KOBIS API 키가 없어요. Streamlit Cloud의 "
        "Settings → Secrets에 KOBIS_KEY를 등록해 주세요."
    )
    st.stop()


# =========================================
# 7. 날짜 선택
# =========================================
st.subheader("📅 조회 날짜")

selected_date = st.date_input(
    "날짜를 선택하세요",
    value=YESTERDAY,
    min_value=date(2004, 1, 1),
    max_value=YESTERDAY,
)

target_date = selected_date.strftime("%Y%m%d")

st.caption(
    f"조회 날짜: {selected_date:%Y년 %m월 %d일}"
    "  ·  오늘 날짜는 아직 선택할 수 없어요."
)


# =========================================
# 8. 데이터 조회
# =========================================
try:
    with st.spinner("박스오피스 데이터를 불러오는 중..."):
        movies = get_boxoffice(target_date, api_key)

except requests.Timeout:
    st.error("서버 응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.")
    st.stop()

except requests.HTTPError as error:
    st.error("KOBIS 서버에서 오류 응답을 받았어요.")
    st.caption(str(error))
    st.stop()

except requests.RequestException:
    st.error("인터넷 연결 또는 KOBIS 서버를 확인해 주세요.")
    st.stop()

except ValueError as error:
    st.error(str(error))
    st.stop()

except Exception as error:
    st.error("데이터를 불러오는 중 오류가 발생했어요.")
    st.caption(str(error))
    st.stop()


# =========================================
# 9. 빈 결과 처리
# =========================================
if not movies:
    st.warning("그날은 아직 집계 전입니다")
    st.info("달력에서 다른 날짜를 선택해 주세요.")
    st.stop()


# =========================================
# 10. 데이터 정리
# =========================================
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

for col in required_columns:
    if col not in df.columns:
        df[col] = ""

for col in [
    "rank",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "rankInten",
]:
    df[col] = pd.to_numeric(
        df[col], errors="coerce"
    ).fillna(0).astype(int)

# 순위는 숫자로 정렬합니다.
df = df.sort_values("rank", ascending=True).reset_index(drop=True)

df["영화명"] = df.apply(
    lambda row: title_with_trophy(
        row["movieNm"], row["audiAcc"]
    ),
    axis=1,
)

df["순위 변동"] = df.apply(
    lambda row: rank_change(
        row["rankInten"], row["rankOldAndNew"]
    ),
    axis=1,
)


# =========================================
# 11. 1위 영화
# =========================================
first = df.iloc[0]

st.divider()
st.subheader("🥇 TODAY'S NUMBER ONE")

poster_col, detail_col = st.columns([1, 2])

with poster_col:
    with st.spinner("포스터 검색 중..."):
        poster = get_movie_poster(
            first["movieNm"], first["openDt"]
        )

    if poster:
        st.image(poster, width=230)
    else:
        st.markdown("## 🎬")
        st.caption("포스터를 찾지 못했어요.")

with detail_col:
    st.markdown(f"### {first['영화명']}")
    st.write(f"개봉일: {fmt_date(first['openDt'])}")

    m1, m2, m3 = st.columns(3)

    m1.metric("일일 관객 수", f"{fmt_number(first['audiCnt'])}명")
    m2.metric("누적 관객 수", f"{fmt_number(first['audiAcc'])}명")
    m3.metric("스크린 수", f"{fmt_number(first['scrnCnt'])}개")


# =========================================
# 12. TOP 5 그래프
# =========================================
st.divider()
st.subheader("📊 TOP 5 · 일일 관객 수")

top5 = df.head(5).copy()

chart_df = pd.DataFrame({
    "영화": top5["영화명"].tolist(),
    "관객 수": top5["audiCnt"].tolist(),
})

st.bar_chart(
    chart_df.set_index("영화")["관객 수"]
)


# =========================================
# 13. TOP 5 포스터
# =========================================
st.divider()
st.subheader("🍿 TOP 5 MOVIES")

poster_columns = st.columns(5)

for i, (_, movie) in enumerate(top5.iterrows()):
    with poster_columns[i]:
        st.markdown(f"**{number(movie['rank'])}위**")

        poster = get_movie_poster(
            movie["movieNm"], movie["openDt"]
        )

        if poster:
            st.image(poster, use_container_width=True)
        else:
            st.markdown("## 🎬")
            st.caption("포스터 없음")

        st.write(movie["영화명"])
        st.caption(f"관객 {fmt_number(movie['audiCnt'])}명")


# =========================================
# 14. 전체 박스오피스 순위
# =========================================
st.divider()
st.subheader("📋 전체 박스오피스 순위")
st.caption(f"총 {len(df)}개 영화 · KOBIS API 반환 순위 기준")

# HTML 문자열로 표를 직접 만들지 않고,
# Streamlit의 표 컴포넌트로 표시해 누락 및 레이아웃 문제를 줄입니다.
table_df = pd.DataFrame({
    "순위": df["rank"].astype(int),
    "영화명": df["영화명"].astype(str),
    "순위 변동": df["순위 변동"].astype(str),
    "개봉일": df["openDt"].apply(fmt_date),
    "일일 관객 수": df["audiCnt"].apply(fmt_number),
    "누적 관객 수": df["audiAcc"].apply(fmt_number),
    "스크린 수": df["scrnCnt"].apply(fmt_number),
})

# 다크 배경과 잘 어울리는 표 스타일
styled_table = (
    table_df.style
    .set_properties(
        **{
            "background-color": "#1b1f2b",
            "color": "#e8eaf0",
            "border-color": "#353b4c",
        }
    )
    .set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", "#292f40"),
                ("color", "#f0c674"),
                ("border-color", "#454c60"),
                ("font-weight", "bold"),
            ],
        },
        {
            "selector": "td",
            "props": [
                ("border-color", "#353b4c"),
            ],
        },
    ])
)

st.dataframe(
    styled_table,
    use_container_width=True,
    hide_index=True,
    height=min(650, 38 * (len(table_df) + 1)),
)

st.caption(
    "🔺 순위 상승  ·  🔻 순위 하락  ·  🏆 누적 관객 100만 명 초과"
)


# =========================================
# 15. 출처 및 안내
# =========================================
st.divider()

st.markdown(
    """
    <div class="muted-text">
    박스오피스 데이터: 영화진흥위원회(KOBIS)<br>
    포스터: Bing 이미지 검색 결과<br>
    KOBIS 일일 박스오피스 API는 기본적으로 상위 10개 영화를 반환합니다.
    포스터는 검색 사이트의 접근 제한에 따라 표시되지 않을 수 있습니다.
    </div>
    """,
    unsafe_allow_html=True,
)
