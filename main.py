
# main.py
# 영화진흥위원회(KOBIS) 일별 박스오피스 대시보드
# 초보자도 이해하기 쉽도록 주요 부분에 한국어 주석을 달았습니다.

import streamlit as st
import pandas as pd
import requests

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# --------------------------------------------------
# 1. 기본 화면 설정
# --------------------------------------------------

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

# 따뜻한 크림색과 노란색을 사용해 화면을 꾸밉니다.
st.markdown(
    """
    <style>
    .stApp {
        background-color: #FFFDF7;
        color: #3A2E1A;
    }

    h1, h2, h3 {
        color: #B87508 !important;
    }

    [data-testid="stMetric"] {
        background-color: #FFF3D0;
        border: 1px solid #F0D99C;
        padding: 20px;
        border-radius: 16px;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid #F0E2BC;
        border-radius: 10px;
    }

    div.stButton > button {
        background-color: #E9A526;
        color: #FFFFFF;
        border: none;
        border-radius: 10px;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 2. 한국 시간 기준으로 어제 날짜 계산
# --------------------------------------------------

# 배포 서버가 어느 나라 시간대를 사용하든 한국 시간으로 계산합니다.
KST = ZoneInfo("Asia/Seoul")

today_kst = datetime.now(KST).date()
yesterday = today_kst - timedelta(days=1)

# KOBIS API는 날짜를 YYYYMMDD 형식으로 받습니다.
target_date = yesterday.strftime("%Y%m%d")
display_date = yesterday.strftime("%Y년 %m월 %d일")


# --------------------------------------------------
# 3. 화면 제목
# --------------------------------------------------

st.title("🎬 어제의 박스오피스")
st.caption(f"영화진흥위원회(KOBIS) 공식 API · 조회 기준일: {display_date}")

st.markdown(
    "어제 영화관에서 가장 많은 관객을 모은 영화는 무엇일까요?"
)

st.divider()


# --------------------------------------------------
# 4. API 데이터 가져오기
# --------------------------------------------------

API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)


@st.cache_data(ttl=600, show_spinner=False)
def get_boxoffice_data(date_string, api_key):
    """KOBIS API에 요청하고 응답 데이터를 반환합니다."""

    response = requests.get(
        API_URL,
        params={
            "key": api_key,
            "targetDt": date_string,
        },
        timeout=15,
    )

    # HTTP 상태 코드가 정상 범위인지 확인합니다.
    response.raise_for_status()

    # JSON 형식으로 응답을 읽습니다.
    data = response.json()

    # 인증키가 잘못되면 상태 코드가 200이어도
    # faultInfo라는 오류 정보가 반환될 수 있습니다.
    if "faultInfo" in data:
        fault = data["faultInfo"]

        error_code = fault.get("errorCode", "알 수 없음")
        error_message = fault.get("message", "오류 메시지가 없습니다.")

        raise ValueError(
            f"KOBIS API 오류 ({error_code}): {error_message}"
        )

    # 정상적인 응답 구조인지 확인합니다.
    boxoffice_result = data.get("boxOfficeResult")

    if not isinstance(boxoffice_result, dict):
        raise ValueError(
            "박스오피스 결과를 찾을 수 없습니다. "
            "KOBIS API 응답 형식을 확인해 주세요."
        )

    movie_list = boxoffice_result.get("dailyBoxOfficeList")

    if not isinstance(movie_list, list):
        raise ValueError(
            "영화 목록이 올바른 형식으로 반환되지 않았습니다."
        )

    return movie_list


# --------------------------------------------------
# 5. 인증키 확인 및 데이터 조회
# --------------------------------------------------

# Streamlit Cloud의 앱 설정에서 Secrets를 등록해야 합니다.
# 예: KOBIS_KEY = "발급받은 인증키"
try:
    api_key = st.secrets["KOBIS_KEY"]

    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("KOBIS_KEY가 비어 있습니다.")

except (KeyError, FileNotFoundError, TypeError, ValueError):
    st.error("🔑 KOBIS 인증키를 찾을 수 없습니다.")
    st.markdown(
        """
        다음 사항을 확인해 주세요.

        1. Streamlit Cloud에서 앱의 **Settings → Secrets**를 엽니다.
        2. `KOBIS_KEY`라는 이름으로 인증키를 등록합니다.
        3. 키 이름의 철자와 따옴표를 확인합니다.
        4. 저장한 뒤 앱을 다시 실행합니다.
        """
    )
    st.stop()


# 사용자가 버튼을 눌러 최신 데이터를 다시 가져올 수 있습니다.
if st.button("🔄 데이터 새로고침"):
    get_boxoffice_data.clear()
    st.rerun()


try:
    with st.spinner("어제의 영화 순위를 불러오는 중입니다..."):
        movie_list = get_boxoffice_data(target_date, api_key.strip())

except requests.exceptions.Timeout:
    st.error("⏱️ KOBIS 서버 응답 시간이 초과되었습니다.")
    st.info(
        "인터넷 연결을 확인하고 잠시 후 다시 시도해 주세요."
    )
    st.stop()

except requests.exceptions.HTTPError as e:
    st.error("🌐 KOBIS 서버에서 요청을 정상 처리하지 못했습니다.")
    st.info(
        f"HTTP 오류: {e}. 잠시 후 다시 시도하거나 "
        "KOBIS API 서비스 상태를 확인해 주세요."
    )
    st.stop()

except requests.exceptions.RequestException as e:
    st.error("🌐 KOBIS API에 연결하지 못했습니다.")
    st.info(
        f"연결 오류: {e}. 네트워크 연결과 API 주소를 확인해 주세요."
    )
    st.stop()

except ValueError as e:
    st.error("⚠️ 박스오피스 데이터를 가져오지 못했습니다.")
    st.info(str(e))
    st.markdown(
        "인증키가 유효한지, KOBIS API 응답에 오류가 포함되어 있는지 확인해 주세요."
    )
    st.stop()

except Exception as e:
    st.error("⚠️ 예상하지 못한 오류가 발생했습니다.")
    st.info(
        f"오류 종류: {type(e).__name__}. "
        "앱 설정과 API 응답을 확인해 주세요."
    )
    st.stop()


# --------------------------------------------------
# 6. 영화 목록이 비어 있는 경우 안내
# --------------------------------------------------

if not movie_list:
    st.warning(f"{display_date}의 영화 순위 데이터가 없습니다.")
    st.markdown(
        """
        다음 사항을 확인해 주세요.

        - KOBIS에서 해당 날짜의 일별 박스오피스가 집계되었는지 확인합니다.
        - API 응답에 `faultInfo`가 있는지 확인합니다.
        - 조회 날짜가 올바르게 계산되었는지 확인합니다.
        - 잠시 후 새로고침 버튼을 눌러 다시 조회합니다.
        """
    )
    st.stop()


# --------------------------------------------------
# 7. 데이터를 표와 그래프에 사용할 수 있도록 정리
# --------------------------------------------------

# KOBIS는 숫자도 문자열로 반환하므로 숫자 자료형으로 변환합니다.
df = pd.DataFrame(movie_list)

required_columns = [
    "rank",
    "movieNm",
    "openDt",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
]

# 필요한 데이터가 응답에 모두 들어 있는지 확인합니다.
missing_columns = [
    col for col in required_columns if col not in df.columns
]

if missing_columns:
    st.error(
        "응답에 필요한 항목이 없습니다: "
        + ", ".join(missing_columns)
    )
    st.info(
        "KOBIS API 응답 구조가 변경되었는지 확인해 주세요."
    )
    st.stop()


# 숫자 변환에 실패한 값은 0으로 처리해 앱이 중단되지 않도록 합니다.
numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]

for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# 순위 순서대로 정렬합니다.
df = df.sort_values("rank").reset_index(drop=True)


# --------------------------------------------------
# 8. 1위 영화 지표 카드 세 장
# --------------------------------------------------

first_movie = df.iloc[0]

st.subheader("🏆 오늘의 주인공, 1위 영화")

st.markdown(
    f"### {int(first_movie['rank'])}위 · {first_movie['movieNm']}"
)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="🎟️ 일일 관객수",
        value=f"{int(first_movie['audiCnt']):,}명",
    )

with col2:
    st.metric(
        label="👥 누적 관객수",
        value=f"{int(first_movie['audiAcc']):,}명",
    )

with col3:
    st.metric(
        label="🎥 스크린수",
        value=f"{int(first_movie['scrnCnt']):,}개",
    )

if first_movie["openDt"]:
    st.caption(f"개봉일: {first_movie['openDt']}")

st.divider()


# --------------------------------------------------
# 9. 관객수 상위 5편 막대그래프
# --------------------------------------------------

st.subheader("📊 관객수 TOP 5")

# 관객수가 많은 영화 5편을 선택합니다.
top5 = df.nlargest(5, "audiCnt").copy()

# 차트에서는 영화명이 세로축, 관객수가 가로축에 나타납니다.
chart_df = top5.set_index("movieNm")[["audiCnt"]]
chart_df.columns = ["일일 관객수"]

st.bar_chart(
    chart_df,
    horizontal=True,
    x_label="관객수 (명)",
    y_label="영화명",
)

st.caption("막대가 길수록 해당 날짜의 관객수가 많습니다.")

st.divider()


# --------------------------------------------------
# 10. 전체 박스오피스 순위 표
# --------------------------------------------------

st.subheader("🎞️ 전체 영화 순위")

# 화면에 표시할 열 이름을 한국어로 바꿉니다.
table_df = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()

table_df.columns = [
    "순위",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수",
]

# 숫자를 보기 편하게 천 단위 쉼표로 표시합니다.
for col in ["관객수", "누적관객", "스크린수"]:
    table_df[col] = table_df[col].map(lambda x: f"{x:,}")

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
)

st.caption(
    f"총 {len(table_df)}편 · 기준일: {display_date} · "
    "자료: 영화진흥위원회(KOBIS)"
)
