import html
import json
import re
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image

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
def get_movie_poster(movie_name: str, open_date: str):
    """
    Bing 이미지 검색 결과에서 포스터 후보를 찾아 이미지 바이트를 반환합니다.
    검색 사이트의 구조나 네트워크 정책에 따라 포스터를 못 찾을 수 있습니다.
    """
    query = f"{movie_name} 영화 포스터"
    search_url = "https://www.bing.com/images/search"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        page = requests.get(
            search_url, params={"q": query, "form": "HDRSC3"},
            headers=headers, timeout=12
        )
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")

        candidates = []
        # Bing 이미지 결과의 murl 속성에서 원본 이미지 주소를 가져옵니다.
        for tag in soup.select("a.iusc"):
            raw = tag.get("m")
            if not raw:
                continue
            try:
                metadata = json.loads(raw)
                url = metadata.get("murl", "")
                if url.startswith("https://") or url.startswith("http://"):
                    candidates.append(url)
            except (json.JSONDecodeError, TypeError):
                continue

        # 검색 HTML 형식이 달라졌을 때를 위한 보조 추출
        if not candidates:
            for match in re.findall(r'"murl":"(https?://[^"]+)"', page.text):
                candidates.append(match.replace("\\/", "/").replace("&amp;", "&"))

        for image_url in candidates[:8]:
            try:
                image_response = requests.get(
                    image_url, headers=headers, timeout=8
                )
                image_response.raise_for_status()
                content = image_response.content
                if not content or len(content) > 12_000_000:
                    continue
                with Image.open(BytesIO(content)) as image:
                    image.verify()
                return content
            except Exception:
                continue
    except Exception:
        return None

    return None


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


def show_poster(movie_name, open_date, width=None):
    image_bytes = get_movie_poster(movie_name, open_date)
    if image_bytes:
        st.image(image_bytes, use_container_width=True)
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

if not api_key:
    st.error(
        "KOBIS API 키를 찾을 수 없습니다. Streamlit Cloud의 "
        "앱 설정 → Secrets에 `KOBIS_KEY = \"발급받은_API_키\"`를 추가해 주세요."
    )
    st.stop()

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
    show_poster(first_name, first_open_date)
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
# TOP 5 관객 수 차트
# ------------------------------------------------------------
st.markdown("## 📊 TOP 5 관객 수")
top5 = df.head(5).copy()
chart_df = pd.DataFrame({
    "영화": top5["표시 영화명"].astype(str),
    "일일 관객 수": top5["audiCnt"].astype(int),
})
st.bar_chart(chart_df.set_index("영화"), horizontal=True)

# ------------------------------------------------------------
# TOP 5 포스터
# ------------------------------------------------------------
st.markdown("## 🍿 TOP 5 영화")
poster_cols = st.columns(5, gap="medium")
for index, (_, row) in enumerate(top5.iterrows()):
    with poster_cols[index]:
        st.markdown('<div class="poster-card">', unsafe_allow_html=True)
        show_poster(str(row.get("movieNm", "")), str(row.get("openDt", "")))
        st.markdown(
            f'<div class="poster-name">{html.escape(str(row["표시 영화명"]))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="poster-meta">#{int(row["rank"])} · {number(row["audiCnt"])}명</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

st.write("")
st.divider()

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
      Data: 영화관입장권통합전산망(KOBIS) · 포스터: Bing 이미지 검색 결과
    </div>
    """,
    unsafe_allow_html=True,
)
