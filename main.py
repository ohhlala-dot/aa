
import html
import json
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


# ==========================================
# 1. 기본 설정
# ==========================================
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


# ==========================================
# 2. 디자인
# ==========================================
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

    .movie-card {
        background-color: #fff6e0;
        border: 1px solid #f0dfb3;
        border-radius: 14px;
        padding: 12px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# 3. 날짜와 숫자 표시 함수
# ==========================================
def format_date(value):
    """YYYYMMDD를 YYYY.MM.DD로 바꿉니다."""
    value = str(value or "")

    if len(value) != 8 or not value.isdigit():
        return "-"

    return f"{value[:4]}.{value[4:6]}.{value[6:8]}"


def format_number(value):
    """숫자에 천 단위 쉼표를 붙입니다."""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return "0"


def rank_change_label(rank_inten, old_and_new):
    """
    KOBIS rankInten은 전날 대비 순위 변동입니다.
    양수: 순위 상승
    음수: 순위 하락
    0: 변동 없음
    """
    if str(old_and_new).upper() == "NEW":
        return "NEW"

    try:
        change = int(rank_inten)
    except (ValueError, TypeError):
        change = 0

    if change > 0:
        return f"UP:{change}"

    if change < 0:
        return f"DOWN:{abs(change)}"

    return "변동 없음"


def rank_change_html(label):
    """순위 변동을 색상 화살표로 표시합니다."""
    if label.startswith("UP:"):
        number = html.escape(label.split(":")[1])
        return f'<span class="up-arrow">↑ {number}</span>'

    if label.startswith("DOWN:"):
        number = html.escape(label.split(":")[1])
        return f'<span class="down-arrow">↓ {number}</span>'

    if label == "NEW":
        return (
            '<span style="color:#e8930c;font-weight:bold;">NEW</span>'
        )

    return '<span style="color:#786b55;">—</span>'


def movie_title_with_trophy(movie_name, cumulative_audience):
    """누적 관객 수가 100만 명을 초과하면 트로피를 붙입니다."""
    try:
        audience = int(cumulative_audience)
    except (ValueError, TypeError):
        audience = 0

    if audience > 1_000_000:
        return f"{movie_name} 🏆"

    return str(movie_name)


# ==========================================
# 4. KOBIS 박스오피스 조회
# ==========================================
@st.cache_data(ttl=1800)
def get_boxoffice(target_date, api_key):
    """선택한 날짜의 박스오피스 정보를 가져옵니다."""
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
            "박스오피스 서버가 올바른 JSON 데이터를 반환하지 않았어요."
        ) from error

    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 API 오류")
        raise ValueError(f"KOBIS API 오류: {message}")

    result = data.get("boxOfficeResult", {})
    return result.get("dailyBoxOfficeList", [])


# ==========================================
# 5. TMDB 키 없이 영화 포스터 검색
# ==========================================
@st.cache_data(ttl=21600, show_spinner=False)
def get_movie_poster(movie_name, open_date=""):
    """
    Bing 이미지 검색 결과에서 포스터 이미지 주소를 찾습니다.
    별도의 TMDB API 키가 필요하지 않습니다.

    주의:
    검색 사이트의 구조 변경, 접근 제한, 이미지 주소 만료 등으로
    검색에 실패할 수 있습니다.
    """
    query = f"{movie_name} 영화 공식 포스터"

    if open_date and len(str(open_date)) >= 4:
        query += f" {str(open_date)[:4]}"

    search_url = "https://www.bing.com/images/search?" + urlencode({
        "q": query,
        "form": "HDRSC3",
    })

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }

    try:
        response = requests.get(
            search_url,
            headers=headers,
            timeout=12,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Bing 이미지 검색 결과의 메타데이터를 읽습니다.
        for item in soup.select("a.iusc"):
            metadata = item.get("m")

            if not metadata:
                continue

            try:
                info = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                continue

            image_url = info.get("murl", "")

            # 웹 주소 형식이 올바른 이미지 주소인지 확인합니다.
            if (
                isinstance(image_url, str)
                and image_url.startswith(("https://", "http://"))
                and not any(char.isspace() for char in image_url)
            ):
                return image_url

        return None

    except (requests.RequestException, ValueError):
        return None


# ==========================================
# 6. 앱 제목
# ==========================================
st.title("🎬 일일 박스오피스")
st.write(
    "원하는 날짜를 선택해 영화 순위와 관객 수를 확인해 보세요!"
)
st.caption(
    "박스오피스 데이터 출처: 영화진흥위원회(KOBIS)"
)


# ==========================================
# 7. KOBIS API 키 확인
# ==========================================
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "KOBIS API 키를 찾을 수 없어요.\n\n"
        "Streamlit Cloud의 Settings → Secrets에서 "
        "KOBIS_KEY를 설정해 주세요."
    )
    st.stop()


# ==========================================
# 8. 날짜 선택
# ==========================================
st.subheader("📅 날짜 선택")

selected_date = st.date_input(
    "조회할 날짜",
    value=YESTERDAY,
    min_value=date(2004, 1, 1),
    max_value=YESTERDAY,
    help="오늘은 아직 집계가 완료되지 않았으므로 어제까지 선택할 수 있어요.",
)

st.caption(f"선택한 날짜: {selected_date:%Y년 %m월 %d일}")

target_date = selected_date.strftime("%Y%m%d")


# ==========================================
# 9. 데이터 조회 및 오류 처리
# ==========================================
with st.spinner("박스오피스 데이터를 불러오는 중이에요..."):
    try:
        movies = get_boxoffice(target_date, KOBIS_KEY)

    except requests.Timeout:
        st.error(
            "서버 응답 시간이 초과됐어요. "
            "잠시 후 다시 시도해 주세요."
        )
        st.stop()

    except requests.HTTPError as error:
        st.error(
            "박스오피스 서버에서 오류 응답을 받았어요. "
            "잠시 후 다시 시도해 주세요."
        )
        st.caption(str(error))
        st.stop()

    except requests.RequestException:
        st.error(
            "인터넷 연결 또는 KOBIS 서버에 문제가 있어요. "
            "잠시 후 다시 시도해 주세요."
        )
        st.stop()

    except ValueError as error:
        st.error(str(error))
        st.stop()

    except Exception as error:
        st.error("데이터를 불러오는 중 예상하지 못한 오류가 발생했어요.")
        st.caption(str(error))
        st.stop()


# ==========================================
# 10. 영화 목록이 비어 있는 경우
# ==========================================
if not movies:
    st.warning("그날은 아직 집계 전입니다")
    st.info("달력에서 다른 날짜를 선택해 다시 확인해 주세요.")
    st.stop()


# ==========================================
# 11. 데이터 정리
# ==========================================
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

for column in [
    "rank",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "rankInten",
]:
    df[column] = (
        pd.to_numeric(df[column], errors="coerce")
        .fillna(0)
        .astype(int)
    )

df["순위 변동"] = df.apply(
    lambda row: rank_change_label(
        row["rankInten"],
        row["rankOldAndNew"],
    ),
    axis=1,
)


# ==========================================
# 12. 1위 영화
# ==========================================
first_movie = df.iloc[0]

st.divider()
st.subheader("🥇 1위 영화")

poster_column, info_column = st.columns([1, 2])

with poster_column:
    with st.spinner("포스터를 검색하고 있어요..."):
        poster_url = get_movie_poster(
            first_movie["movieNm"],
            first_movie["openDt"],
        )

    if poster_url:
        st.image(poster_url, width=230)
    else:
        st.markdown("# 🎬")
        st.caption("포스터를 찾지 못했어요.")

with info_column:
    first_title = movie_title_with_trophy(
        first_movie["movieNm"],
        first_movie["audiAcc"],
    )

    st.markdown(f"### {first_title}")
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


# ==========================================
# 13. 관객 수 TOP 5 그래프
# ==========================================
st.divider()
st.subheader("📊 일일 관객 수 TOP 5")

top5 = df.head(5).copy()

chart_df = pd.DataFrame({
    "영화": [
        movie_title_with_trophy(row["movieNm"], row["audiAcc"])
        for _, row in top5.iterrows()
    ],
    "관객 수": top5["audiCnt"].tolist(),
})

st.bar_chart(
    chart_df.set_index("영화")["관객 수"],
    horizontal=True,
)

st.caption("선택한 날짜의 일일 관객 수를 비교한 그래프입니다.")


# ==========================================
# 14. TOP 5 포스터
# ==========================================
st.divider()
st.subheader("🍿 TOP 5 영화 포스터")

poster_columns = st.columns(5)

for index, (_, movie) in enumerate(top5.iterrows()):
    with poster_columns[index]:
        st.markdown(f"**{int(movie['rank'])}위**")

        with st.spinner("검색 중..."):
            poster_url = get_movie_poster(
                movie["movieNm"],
                movie["openDt"],
            )

        if poster_url:
            st.image(poster_url, use_container_width=True)
        else:
            st.markdown("## 🎬")
            st.caption("포스터 없음")

        title = movie_title_with_trophy(
            movie["movieNm"],
            movie["audiAcc"],
        )

        st.markdown(f"**{title}**")
        st.caption(
            f"일일 관객 {format_number(movie['audiCnt'])}명"
        )


# ==========================================
# 15. 전체 박스오피스 표
# ==========================================
st.divider()
st.subheader("📋 전체 박스오피스 순위")

table_html = """
<table style="
    width:100%;
    border-collapse:collapse;
    background:#fffdf7;
    font-size:14px;
">
<thead>
<tr style="
    background:#fff0c2;
    border-bottom:2px solid #e7d6a7;
">
<th style="padding:10px;text-align:center;">순위</th>
<th style="padding:10px;text-align:left;">영화명</th>
<th style="padding:10px;text-align:center;">순위 변동</th>
<th style="padding:10px;text-align:center;">개봉일</th>
<th style="padding:10px;text-align:right;">일일 관객</th>
<th style="padding:10px;text-align:right;">누적 관객</th>
<th style="padding:10px;text-align:right;">스크린 수</th>
</tr>
</thead>
<tbody>
"""

for _, movie in df.iterrows():
    rank = int(movie["rank"])

    title = movie_title_with_trophy(
        movie["movieNm"],
        movie["audiAcc"],
    )
    title = html.escape(title)

    change_html = rank_change_html(movie["순위 변동"])

    table_html += f"""
    <tr style="border-bottom:1px solid #eee2c8;">
        <td style="padding:10px;text-align:center;">{rank}</td>
        <td style="padding:10px;text-align:left;font-weight:600;">{title}</td>
        <td style="padding:10px;text-align:center;">{change_html}</td>
        <td style="padding:10px;text-align:center;">{format_date(movie["openDt"])}</td>
        <td style="padding:10px;text-align:right;">{format_number(movie["audiCnt"])}</td>
        <td style="padding:10px;text-align:right;">{format_number(movie["audiAcc"])}</td>
        <td style="padding:10px;text-align:right;">{format_number(movie["scrnCnt"])}</td>
    </tr>
    """

table_html += """
</tbody>
</table>
"""

st.markdown(table_html, unsafe_allow_html=True)


# ==========================================
# 16. 출처
# ==========================================
st.divider()

st.markdown(
    """
    <p class="small-note">
    박스오피스 데이터: 영화진흥위원회(KOBIS)<br>
    포스터 검색: Bing 이미지 검색 결과<br>
    포스터는 검색 결과에 따라 표시되지 않을 수 있습니다.
    </p>
    """,
    unsafe_allow_html=True,
)
