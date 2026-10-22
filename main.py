
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
