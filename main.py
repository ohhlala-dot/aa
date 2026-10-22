
import html
import json
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


# =====================================
# 1. 기본 설정
# =====================================
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


# =====================================
# 2. 화면 디자인
# =====================================
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
        background: #fff6e0;
        border: 1px solid #f0dfb3;
        border-radius: 14px;
        padding: 14px;
    }

    .up-arrow {
        color: #e53935;
        font-weight: bold;
    }

    .down-arrow {
        color: #1976d2;
        font-weight: bold;
    }

    .note {
        color: #786b55;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================
# 3. 공통 함수
# =====================================
def format_number(value):
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return "0"


def format_date(value):
    value = str(value or "")

    if len(value) != 8 or not value.isdigit():
        return "-"

    return f"{value[:4]}.{value[4:6]}.{value[6:8]}"


def movie_title(movie_name, audience):
    """누적 관객이 100만 명을 초과하면 트로피를 붙입니다."""
    try:
        audience = int(audience)
    except (ValueError, TypeError):
        audience = 0

    name = str(movie_name)

    if audience > 1_000_000:
        name += " 🏆"

    return name


def get_rank_change(rank_inten, old_and_new):
    """KOBIS 순위 증감 정보를 읽기 쉬운 문자열로 바꿉니다."""
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


def rank_change_html(value):
    if value.startswith("UP:"):
        number = html.escape(value.split(":")[1])
        return f'<span class="up-arrow">↑ {number}</span>'

    if value.startswith("DOWN:"):
        number = html.escape(value.split(":")[1])
        return f'<span class="down-arrow">↓ {number}</span>'

    if value == "NEW":
        return '<span style="color:#e8930c;font-weight:bold;">NEW</span>'

    return '<span style="color:#786b55;">—</span>'


# =====================================
# 4. KOBIS 데이터 조회
# =====================================
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
            "영화진흥위원회 서버에서 올바른 데이터를 받지 못했어요."
        ) from error

    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 API 오류")
        raise ValueError(f"KOBIS API 오류: {message}")

    result = data.get("boxOfficeResult", {})
    return result.get("dailyBoxOfficeList", [])


# =====================================
# 5. TMDB 키 없이 포스터 검색
# =====================================
@st.cache_data(ttl=21600, show_spinner=False)
def get_movie_poster(movie_name, open_date=""):
    """
    Bing 이미지 검색에서 영화 포스터를 찾습니다.
    검색이나 이미지 다운로드에 실패하면 None을 반환합니다.
    """
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

            image_url = info.get("murl", "")

            if (
                isinstance(image_url, str)
                and image_url.startswith(("https://", "http://"))
                and image_url not in image_urls
            ):
                image_urls.append(image_url)

            # 한 영화에 대해 너무 많은 주소를 요청하지 않습니다.
            if len(image_urls) >= 5:
                break

        # 검색 결과의 이미지 주소에 실제로 접근할 수 있는지 확인합니다.
        for image_url in image_urls:
            try:
                image_response = requests.get(
                    image_url,
                    headers=HEADERS,
                    timeout=8,
                    stream=True,
                )

                if image_response.status_code != 200:
                    image_response.close()
                    continue

                content_type = image_response.headers.get(
                    "Content-Type", ""
                ).lower()

                if not content_type.startswith("image/"):
                    image_response.close()
                    continue

                # 너무 큰 이미지 파일은 건너뜁니다.
                content_length = image_response.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > 8 * 1024 * 1024:
                            image_response.close()
                            continue
                    except ValueError:
                        pass

                image_bytes = image_response.raw.read(
                    8 * 1024 * 1024 + 1
                )
                image_response.close()

                if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
                    continue

                # Streamlit이 표시할 수 있는 이미지인지 확인합니다.
                from PIL import Image
                from io import BytesIO

                try:
                    image = Image.open(BytesIO(image_bytes))
                    image.verify()
                except Exception:
                    continue

                return image_bytes

            except requests.RequestException:
                continue

        return None

    except requests.RequestException:
        return None


# =====================================
# 6. 제목 및 API 키
# =====================================
st.title("🎬 일일 박스오피스")
st.write("달력에서 날짜를 선택해 그날의 영화 순위와 관객 수를 확인해 보세요.")
st.caption("박스오피스 데이터: 영화진흥위원회(KOBIS)")

try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "KOBIS API 키가 없어요. "
        "Streamlit Cloud의 Settings → Secrets에서 "
        "KOBIS_KEY를 설정해 주세요."
    )
    st.stop()


# =====================================
# 7. 날짜 선택
# =====================================
st.subheader("📅 날짜 선택")

selected_date = st.date_input(
    "조회할 날짜",
    value=YESTERDAY,
    min_value=date(2004, 1, 1),
    max_value=YESTERDAY,
    help="오늘은 아직 집계 전일 수 있어 어제까지만 선택할 수 있어요.",
)

st.caption(f"조회 날짜: {selected_date:%Y년 %m월 %d일}")

target_date = selected_date.strftime("%Y%m%d")


# =====================================
# 8. 박스오피스 데이터 불러오기
# =====================================
try:
    with st.spinner("박스오피스 데이터를 불러오는 중이에요..."):
        movies = get_boxoffice(target_date, KOBIS_KEY)

except requests.Timeout:
    st.error("서버 응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.")
    st.stop()

except requests.HTTPError:
    st.error("KOBIS 서버에서 오류 응답을 받았어요. API 키를 확인해 주세요.")
    st.stop()

except requests.RequestException:
    st.error("인터넷 연결이나 KOBIS 서버에 문제가 있어요.")
    st.stop()

except ValueError as error:
    st.error(str(error))
    st.stop()

except Exception as error:
    st.error("데이터를 불러오는 중 오류가 발생했어요.")
    st.code(str(error))
    st.stop()


# =====================================
# 9. 결과가 없는 날짜
# =====================================
if not movies:
    st.warning("그날은 아직 집계 전입니다")
    st.info("다른 날짜를 선택해 다시 확인해 주세요.")
    st.stop()


# =====================================
# 10. 데이터 정리
# =====================================
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
    lambda row: get_rank_change(
        row["rankInten"],
        row["rankOldAndNew"],
    ),
    axis=1,
)


# =====================================
# 11. 1위 영화
# =====================================
first_movie = df.iloc[0]

st.divider()
st.subheader("🥇 1위 영화")

poster_col, info_col = st.columns([1, 2])

with poster_col:
    with st.spinner("포스터를 검색하고 있어요..."):
        first_poster = get_movie_poster(
            first_movie["movieNm"],
            first_movie["openDt"],
        )

    if first_poster:
        st.image(first_poster, width=230)
    else:
        st.markdown("# 🎬")
        st.caption("포스터를 찾지 못했어요.")

with info_col:
    st.markdown(
        f"### {movie_title(first_movie['movieNm'], first_movie['audiAcc'])}"
    )
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


# =====================================
# 12. 관객 수 TOP 5 그래프
# =====================================
st.divider()
st.subheader("📊 일일 관객 수 TOP 5")

top5 = df.head(5).copy()

chart_df = pd.DataFrame({
    "영화": [
        movie_title(row["movieNm"], row["audiAcc"])
        for _, row in top5.iterrows()
    ],
    "관객 수": top5["audiCnt"].tolist(),
})

st.bar_chart(chart_df.set_index("영화")["관객 수"])
st.caption("선택한 날짜의 일일 관객 수를 비교한 그래프입니다.")


# =====================================
# 13. TOP 5 포스터
# =====================================
st.divider()
st.subheader("🍿 TOP 5 영화 포스터")

poster_columns = st.columns(5)

for index, (_, movie) in enumerate(top5.iterrows()):
    with poster_columns[index]:
        st.markdown(f"**{int(movie['rank'])}위**")

        poster = get_movie_poster(
            movie["movieNm"],
            movie["openDt"],
        )

        if poster:
            st.image(poster, use_column_width=True)
        else:
            st.markdown("## 🎬")
            st.caption("포스터 없음")

        st.markdown(
            f"**{movie_title(movie['movieNm'], movie['audiAcc'])}**"
        )
        st.caption(f"일일 관객 {format_number(movie['audiCnt'])}명")


# =====================================
# 14. 전체 순위표
# =====================================
st.divider()
st.subheader("📋 전체 박스오피스 순위")

table_html = """
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<thead>
<tr style="background:#fff0c2;border-bottom:2px solid #e7d6a7;">
<th style="padding:10px;">순위</th>
<th style="padding:10px;text-align:left;">영화명</th>
<th style="padding:10px;">순위 변동</th>
<th style="padding:10px;">개봉일</th>
<th style="padding:10px;text-align:right;">일일 관객</th>
<th style="padding:10px;text-align:right;">누적 관객</th>
<th style="padding:10px;text-align:right;">스크린 수</th>
</tr>
</thead>
<tbody>
"""

for _, movie in df.iterrows():
    rank = int(movie["rank"])

    name = html.escape(
        movie_title(movie["movieNm"], movie["audiAcc"])
    )
    change = rank_change_html(movie["순위 변동"])

    table_html += f"""
    <tr style="border-bottom:1px solid #eee2c8;">
      <td style="padding:10px;text-align:center;">{rank}</td>
      <td style="padding:10px;">{name}</td>
      <td style="padding:10px;text-align:center;">{change}</td>
      <td style="padding:10px;text-align:center;">{format_date(movie["openDt"])}</td>
      <td style="padding:10px;text-align:right;">{format_number(movie["audiCnt"])}</td>
      <td style="padding:10px;text-align:right;">{format_number(movie["audiAcc"])}</td>
      <td style="padding:10px;text-align:right;">{format_number(movie["scrnCnt"])}</td>
    </tr>
    """

table_html += "</tbody></table>"

st.markdown(table_html, unsafe_allow_html=True)


# =====================================
# 15. 출처
# =====================================
st.divider()
st.markdown(
    """
    <p class="note">
    박스오피스 데이터: 영화진흥위원회(KOBIS)<br>
    포스터: Bing 이미지 검색 결과<br>
    포스터는 검색 사이트의 접근 제한이나 이미지 주소에 따라
    표시되지 않을 수 있습니다.
    </p>
    """,
    unsafe_allow_html=True,
)
