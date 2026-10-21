
import streamlit as st
import pandas as pd
import requests

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# -----------------------------
# 화면 설정
# -----------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background-color: #FFFDF7;
    }
    h1, h2, h3 {
        color: #B87508;
    }
    [data-testid="stMetric"] {
        background-color: #FFF3D0;
        border: 1px solid #F0D99C;
        padding: 18px;
        border-radius: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# 한국 시간 기준 어제 날짜 계산
# -----------------------------
KST = ZoneInfo("Asia/Seoul")
yesterday = datetime.now(KST).date() - timedelta(days=1)

target_date = yesterday.strftime("%Y%m%d")
display_date = yesterday.strftime("%Y년 %m월 %d일")

st.title("🎬 어제의 박스오피스")
st.caption(f"조회 기준일: {display_date} · 자료: KOBIS")
st.write("어제 가장 많은 관객을 모은 영화들을 확인해 보세요.")

# -----------------------------
# KOBIS API 주소
# -----------------------------
API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)


# API 결과는 10분간 저장해 반복 요청을 줄입니다.
@st.cache_data(ttl=600, show_spinner=False)
def get_boxoffice(date_string, api_key):
    response = requests.get(
        API_URL,
        params={
            "key": api_key,
            "targetDt": date_string,
        },
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    # 인증키 오류는 HTTP 200으로 올 수도 있습니다.
    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "인증키 또는 API 요청을 확인하세요.")
        code = fault.get("errorCode", "알 수 없는 오류")
        raise ValueError(f"{code}: {message}")

    result = data.get("boxOfficeResult")

    if not isinstance(result, dict):
        raise ValueError("API 응답에 boxOfficeResult가 없습니다.")

    movies = result.get("dailyBoxOfficeList")

    if not isinstance(movies, list):
        raise ValueError("영화 목록이 올바른 형식이 아닙니다.")

    return movies


# -----------------------------
# Secrets에서 인증키 가져오기
# -----------------------------
try:
    api_key = st.secrets["KOBIS_KEY"]

    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("인증키가 비어 있습니다.")

except (KeyError, FileNotFoundError, TypeError, ValueError):
    st.error("🔑 KOBIS 인증키를 찾을 수 없습니다.")
    st.markdown(
        """
        **해결 방법**

        1. Streamlit Cloud에서 앱의 Settings → Secrets를 엽니다.
        2. 다음 형식으로 인증키를 등록합니다.
        3. 저장한 뒤 앱을 다시 실행합니다.
        """
    )
    st.code('KOBIS_KEY = "발급받은_인증키"')
    st.stop()


# -----------------------------
# 데이터 새로고침 버튼
# -----------------------------
if st.button("🔄 데이터 새로고침"):
    get_boxoffice.clear()
    st.rerun()


# -----------------------------
# API 요청 및 오류 안내
# -----------------------------
try:
    with st.spinner("박스오피스 데이터를 불러오는 중입니다..."):
        movies = get_boxoffice(target_date, api_key.strip())

except requests.exceptions.Timeout:
    st.error("KOBIS 서버 응답 시간이 초과되었습니다.")
    st.info("인터넷 연결을 확인하고 잠시 후 다시 시도해 주세요.")
    st.stop()

except requests.exceptions.HTTPError as error:
    st.error("KOBIS 서버에서 요청을 처리하지 못했습니다.")
    st.info(f"HTTP 오류: {error}")
    st.info("API 주소와 KOBIS 서비스 상태를 확인해 주세요.")
    st.stop()

except requests.exceptions.RequestException as error:
    st.error("KOBIS API에 연결하지 못했습니다.")
    st.info(f"연결 오류: {error}")
    st.info("네트워크 연결을 확인하고 다시 시도해 주세요.")
    st.stop()

except ValueError as error:
    st.error("박스오피스 데이터를 확인할 수 없습니다.")
    st.info(str(error))
    st.info("인증키와 KOBIS API 응답을 확인해 주세요.")
    st.stop()

except Exception as error:
    st.error("예상하지 못한 오류가 발생했습니다.")
    st.info(f"{type(error).__name__}: {error}")
    st.stop()


# -----------------------------
# 영화 목록 확인
# -----------------------------
if not movies:
    st.warning(f"{display_date}의 영화 목록이 비어 있습니다.")
    st.info(
        "KOBIS에서 해당 날짜의 집계가 완료되었는지, "
        "인증키와 API 응답이 올바른지 확인해 주세요."
    )
    st.stop()


# -----------------------------
# 데이터 정리
# -----------------------------
df = pd.DataFrame(movies)

required_columns = [
    "rank", "movieNm", "openDt",
    "audiCnt", "audiAcc", "scrnCnt",
]

missing = [column for column in required_columns if column not in df.columns]

if missing:
    st.error("API 응답에 필요한 항목이 없습니다: " + ", ".join(missing))
    st.stop()

# API 숫자 값은 문자열이므로 숫자 자료형으로 바꿉니다.
for column in ["rank", "audiCnt", "audiAcc", "scrnCnt"]:
    df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)

df = df.sort_values("rank").reset_index(drop=True)


# -----------------------------
# 1위 영화 지표 카드 3개
# -----------------------------
first = df.iloc[0]

st.divider()
st.subheader(f"🏆 박스오피스 1위: {first['movieNm']}")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("🎟️ 일일 관객수", f"{first['audiCnt']:,}명")

with col2:
    st.metric("👥 누적 관객수", f"{first['audiAcc']:,}명")

with col3:
    st.metric("🎥 스크린수", f"{first['scrnCnt']:,}개")

st.caption(f"개봉일: {first['openDt'] or '정보 없음'}")


# -----------------------------
# 관객수 상위 5편 막대그래프
# -----------------------------
st.divider()
st.subheader("📊 관객수 TOP 5")

top5 = df.nlargest(5, "audiCnt").copy()
chart = top5.set_index("movieNm")[["audiCnt"]]
chart.columns = ["일일 관객수"]

st.bar_chart(chart, horizontal=True)


# -----------------------------
# 전체 영화 순위 표
# -----------------------------
st.divider()
st.subheader("🎞️ 전체 박스오피스 순위")

table = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()

table.columns = [
    "순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"
]

for column in ["관객수", "누적관객", "스크린수"]:
    table[column] = table[column].map(lambda value: f"{value:,}")

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
)

st.caption(f"총 {len(table)}편 · 기준일: {display_date}")
