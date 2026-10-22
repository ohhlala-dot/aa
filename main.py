
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
# 1. 페이지 설정
# =========================================
st.set_page_config(
    page_title="CINÉ | 박스오피스",
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
# 2. 세련된 다크 테마
# =========================================
st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(ellipse at top left,
                #1b1730 0%, #0b0d14 42%);
        color: #eef0f8;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stSidebar"] {
        background: #11131d;
    }

    h1, h2, h3 {
        color: #f8fafc !important;
        letter-spacing: -0.5px;
    }

    p, label {
        color: #c4c9d8;
    }

    div[data-testid="stMetric"] {
        background: #191d2a;
        border: 1px solid #2d3245;
        border-radius: 15px;
        padding: 16px 18px;
    }

    div[data-testid="stMetricLabel"] {
        color: #a5aec3 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #f8fafc !important;
        font-weight: 700;
    }

    div[data-testid="stMetricDelta"] {
        color: #a78bfa !important;
    }

    div[data-testid="stDateInput"] input {
        background: #191d2a;
        border-color: #34394d;
        border-radius: 10px;
        color: #f8fafc;
    }

    div.stButton > button {
        border: 1px solid #45405f;
        border-radius: 10px;
        background: #191d2a;
        color: #e9e7ff;
    }

    div.stButton > button:hover {
        border-color: #a78bfa;
        color: white;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #30364a;
        border-radius: 14px;
        overflow: hidden;
    }

    hr {
        border-color: #292e40;
    }

    .brand {
        color: #c4b5fd;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 4px;
    }

    .hero {
        background: linear-gradient(135deg, #211c38, #171b2a 70%);
        border: 1px solid #39334f;
        border-radius: 22px;
        padding: 24px;
        margin: 8px 0 20px 0;
    }

    .eyebrow {
        color: #b8a6ff;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 2px;
    }

    .hero-title {
        color: #ffffff;
        font-size: 30px;
        font-weight: 800;
        line-height: 1.35;
        margin: 8px 0;
    }

    .muted {
        color: #a5aec3;
        font-size: 13px;
    }

    .poster-title {
        color: #f1f3fa;
        font-size: 14px;
        font-weight: 700;
        line-height: 1.5;
        min-height: 42px;
        margin-top: 8px;
    }

    .rank-up {
        color: #fb7185;
        font-weight: 800;
    }

    .rank-down {
        color: #60a5fa;
        font-weight: 800;
    }

    .section-kicker {
        color: #a78bfa;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================
# 3. 공통 함수
# =========================================
def to_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def fmt_number(value):
    return f"{to_int(value):,}"


def fmt_date(value):
    value = str(value or "")
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}.{value[4:6]}.{value[6:8]}"
    return "-"


def trophy_title(name, cumulative):
    name = str(name)
    if to_int(cumulative) > 1_000_000:
        return name + " 🏆"
    return name


def rank_change(rank_inten, old_and_new):
    if str(old_and_new).upper() == "NEW":
        return "NEW"

    change = to_int(rank_inten)

    if change > 0:
        return f"🔺 +{change}"
    if change < 0:
        return f"🔻 {change}"
    return "—"


# =========================================
# 4. KOBIS 데이터 조회
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
            "KOBIS에서 올바른 데이터를 받지 못했어요."
        ) from error

    if "faultInfo" in data:
        message = data["faultInfo"].get(
            "message", "알 수 없는 API 오류"
        )
        raise ValueError(f"KOBIS API 오류: {message}")

    result = data.get("boxOfficeResult", {})
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

                content = image_response.content

                if (
                    not content_type.startswith("image/")
                    or not content
                    or len(content) > 8 * 1024 * 1024
                ):
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
# 6. 헤더
# =========================================
st.markdown(
    '<div class="brand">C I N É &nbsp; / &nbsp; FILM CULTURE</div>',
    unsafe_allow_html=True,
)

st.title("영화의 흐름을 한눈에.")
st.markdown(
    '<p class="muted">DAILY BOX OFFICE · 일일 박스오피스 차트</p>',
    unsafe_allow_html=True,
)


# =========================================
# 7. API 키 확인
# =========================================
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "KOBIS API 키가 없어요. "
        "Streamlit Cloud → Settings → Secrets에서 "
        "KOBIS_KEY를 등록해 주세요."
    )
    st.stop()


# =========================================
# 8. 날짜 선택
# =========================================
date_col, note_col = st.columns([1, 2])

with date_col:
    selected_date = st.date_input(
        "📅 조회 날짜",
        value=YESTERDAY,
        min_value=date(2004, 1, 1),
        max_value=YESTERDAY,
    )

with note_col:
    st.markdown(
        f"""
        <div style="
            background:#191d2a;
            border:1px solid #30364a;
            border-radius:12px;
            padding:13px 16px;
            margin-top:29px;
        ">
        <span style="color:#a78bfa;font-weight:700;">
        SELECTED DATE
        </span><br>
        <span style="color:#f8fafc;font-size:18px;font-weight:700;">
        {selected_date:%Y년 %m월 %d일}
        </span>
        <span style="color:#929bb0;font-size:12px;">
        &nbsp; · &nbsp; 한국 시간 기준
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

target_date = selected_date.strftime("%Y%m%d")


# =========================================
# 9. 데이터 조회 및 오류 처리
# =========================================
try:
    with st.spinner("영화 데이터를 불러오는 중..."):
        movies = get_boxoffice(target_date, KOBIS_KEY)

except requests.Timeout:
    st.error("서버 응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.")
    st.stop()

except requests.HTTPError:
    st.error("KOBIS 서버에서 오류가 발생했어요. API 키를 확인해 주세요.")
    st.stop()

except requests.RequestException:
    st.error("인터넷 연결 또는 KOBIS 서버를 확인해 주세요.")
    st.stop()

except ValueError as error:
    st.error(str(error))
    st.stop()

except Exception as error:
    st.error("데이터를 불러오지 못했어요.")
    st.caption(str(error))
    st.stop()

if not movies:
    st.warning("그날은 아직 집계 전입니다")
    st.info("다른 날짜를 선택해 다시 확인해 주세요.")
    st.stop()


# =========================================
# 10. 데이터 정리
# =========================================
df = pd.DataFrame(movies)

columns_needed = [
    "rank", "movieNm", "openDt",
    "audiCnt", "audiAcc", "scrnCnt",
    "rankInten", "rankOldAndNew",
]

for col in columns_needed:
    if col not in df.columns:
        df[col] = ""

for col in ["rank", "audiCnt", "audiAcc", "scrnCnt", "rankInten"]:
    df[col] = (
        pd.to_numeric(df[col], errors="coerce")
        .fillna(0)
        .astype(int)
    )

df = df.sort_values("rank").reset_index(drop=True)

df["표시 영화명"] = df.apply(
    lambda row: trophy_title(row["movieNm"], row["audiAcc"]),
    axis=1,
)

df["순위 변동"] = df.apply(
    lambda row: rank_change(
        row["rankInten"], row["rankOldAndNew"]
    ),
    axis=1,
)


# =========================================
# 11. 1위 히어로 영역
# =========================================
first = df.iloc[0]

st.markdown(
    '<div class="section-kicker">01 / FEATURED FILM</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hero-title">오늘의 박스오피스 1위</div>',
    unsafe_allow_html=True,
)

poster_col, info_col = st.columns([1, 2.2], gap="large")

with poster_col:
    poster = get_movie_poster(first["movieNm"], first["openDt"])

    if poster:
        st.image(poster, use_container_width=True)
    else:
        st.markdown(
            """
            <div style="
                background:#191d2a;
                border:1px solid #30364a;
                border-radius:16px;
                height:280px;
                display:flex;
                align-items:center;
                justify-content:center;
                font-size:64px;
            ">🎬</div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("포스터를 찾지 못했어요.")

with info_col:
    st.markdown(
        f"""
        <div class="eyebrow">RANK NO. 01</div>
        <div class="hero-title">
            {html.escape(first["표시 영화명"])}
        </div>
        <div class="muted">
            개봉일 · {fmt_date(first["openDt"])}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "일일 관객 수",
        f"{fmt_number(first['audiCnt'])}명",
    )
    m2.metric(
        "누적 관객 수",
        f"{fmt_number(first['audiAcc'])}명",
    )
    m3.metric(
        "스크린 수",
        f"{fmt_number(first['scrnCnt'])}개",
    )


# =========================================
# 12. TOP 5 관객 수 차트
# =========================================
st.divider()

st.markdown(
    '<div class="section-kicker">02 / AUDIENCE CHART</div>',
    unsafe_allow_html=True,
)
st.subheader("관객 수 TOP 5")

top5 = df.head(5).copy()

chart_df = pd.DataFrame({
    "영화": top5["표시 영화명"].tolist(),
    "일일 관객 수": top5["audiCnt"].tolist(),
})

st.bar_chart(
    chart_df.set_index("영화")["일일 관객 수"],
    horizontal=True,
)

st.caption("선택한 날짜의 일일 관객 수 기준입니다.")


# =========================================
# 13. 포스터 카드
# =========================================
st.divider()

st.markdown(
    '<div class="section-kicker">03 / NOW SHOWING</div>',
    unsafe_allow_html=True,
)
st.subheader("지금 주목할 영화")

poster_cols = st.columns(5, gap="medium")

for i, (_, movie) in enumerate(top5.iterrows()):
    with poster_cols[i]:
        st.markdown(
            f"""
            <div class="eyebrow">RANK {int(movie['rank']):02d}</div>
            """,
            unsafe_allow_html=True,
        )

        poster = get_movie_poster(
            movie["movieNm"], movie["openDt"]
        )

        if poster:
            st.image(poster, use_container_width=True)
        else:
            st.markdown(
                """
                <div style="
                    background:#191d2a;
                    border:1px solid #30364a;
                    border-radius:12px;
                    aspect-ratio:2/3;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    font-size:36px;
                ">🎬</div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            f"""
            <div class="poster-title">
                {html.escape(movie["표시 영화명"])}
            </div>
            <div class="muted">
                관객 {fmt_number(movie["audiCnt"])}명
            </div>
            """,
            unsafe_allow_html=True,
        )


# =========================================
# 14. 전체 순위표
# =========================================
st.divider()

st.markdown(
    '<div class="section-kicker">04 / FULL RANKINGS</div>',
    unsafe_allow_html=True,
)
st.subheader("전체 박스오피스 순위")
st.caption(
    f"{selected_date:%Y년 %m월 %d일} · "
    f"총 {len(df)}개 영화"
)

table_df = pd.DataFrame({
    "순위": df["rank"].astype(int),
    "영화명": df["표시 영화명"],
    "순위 변동": df["순위 변동"],
    "개봉일": df["openDt"].apply(fmt_date),
    "일일 관객 수": df["audiCnt"].apply(fmt_number),
    "누적 관객 수": df["audiAcc"].apply(fmt_number),
    "스크린 수": df["scrnCnt"].apply(fmt_number),
})

def style_rank(value):
    if isinstance(value, str) and value.startswith("🔺"):
        return "color: #fb7185; font-weight: bold"
    if isinstance(value, str) and value.startswith("🔻"):
        return "color: #60a5fa; font-weight: bold"
    if value == "NEW":
        return "color: #c4b5fd; font-weight: bold"
    return "color: #cbd5e1"

styled_table = (
    table_df.style
    .map(style_rank, subset=["순위 변동"])
    .set_properties(
        **{
            "background-color": "#151925",
            "color": "#e5e7eb",
            "border-color": "#30364a",
        }
    )
    .set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", "#22273a"),
                ("color", "#c4b5fd"),
                ("border-color", "#30364a"),
                ("font-weight", "bold"),
                ("padding", "12px"),
            ],
        },
        {
            "selector": "td",
            "props": [
                ("padding", "10px"),
                ("border-color", "#30364a"),
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
    "🔺 순위 상승  ·  🔻 순위 하락  ·  "
    "🏆 누적 관객 100만 명 초과"
)


# =========================================
# 15. 출처
# =========================================
st.divider()

st.markdown(
    """
    <div class="muted">
        DATA SOURCE · 영화진흥위원회(KOBIS)<br>
        POSTER SEARCH · Bing 이미지 검색<br>
        포스터는 검색 사이트의 접근 제한에 따라 표시되지 않을 수 있습니다.
    </div>
    """,
    unsafe_allow_html=True,
)
