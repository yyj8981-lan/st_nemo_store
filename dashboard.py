import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import json
import numpy as np

# 페이지 설정
st.set_page_config(page_title="네모스토어 고도화 대시보드", layout="wide")

# 가상 위경도 데이터 (지도를 위해 Jung-gu 주변으로 생성)
def add_mock_coords(df):
    if 'lat' not in df.columns or 'lon' not in df.columns:
        # 서울 중구 중심 좌표: 37.5635, 126.9975
        df['lat'] = 37.5635 + np.random.uniform(-0.01, 0.01, len(df))
        df['lon'] = 126.9975 + np.random.uniform(-0.01, 0.01, len(df))
    return df

# 데이터 로드 및 전처리
@st.cache_data
def load_and_preprocess_data():
    conn = sqlite3.connect('nemostore/data/store_database.db')
    df = pd.read_sql_query("SELECT * FROM stores", conn)
    conn.close()
    
    # 1. 컬럼명 한글 매핑 (표시용)
    column_mapping = {
        'title': '매물명',
        'businessMiddleCodeName': '업종',
        'deposit': '보증금(만)',
        'monthlyRent': '월세(만)',
        'premium': '권리금(만)',
        'size': '전용면적(㎡)',
        'floor': '층',
        'nearSubwayStation': '인접역',
        'viewCount': '조회수',
        'createdDateUtc': '등록일'
    }
    
    # 2. 이미지 URL 파싱
    def parse_urls(url_str):
        try:
            return json.loads(url_str) if url_str else []
        except:
            return []
            
    df['small_photos'] = df['smallPhotoUrls'].apply(parse_urls)
    df['large_photos'] = df['originPhotoUrls'].apply(parse_urls)
    
    # 3. 벤치마킹 분석을 위한 평균값 계산
    df['avg_rent_by_biz'] = df.groupby('businessMiddleCodeName')['monthlyRent'].transform('mean')
    df['avg_deposit_by_biz'] = df.groupby('businessMiddleCodeName')['deposit'].transform('mean')
    
    # 4. 가성비 지표 (단위 면적당 월세)
    df['rent_per_area'] = df['monthlyRent'] / (df['size'] + 0.1) # 0 나누기 방지
    
    # 5. 좌표 추가 (Mock)
    df = add_mock_coords(df)
    
    return df, column_mapping

try:
    df_raw, col_map = load_and_preprocess_data()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# 세션 상태 관리 (상세 매물 선택 용)
if 'selected_article_id' not in st.session_state:
    st.session_state.selected_article_id = None

# 사이드바 공통 필터
st.sidebar.header("🔍 통합 검색 및 필터")
search_query = st.sidebar.text_input("매물명/키워드 검색", "")
selected_biz = st.sidebar.multiselect("업종 필터", sorted(df_raw['businessMiddleCodeName'].unique()), default=[])

# 가격 필터 (공통)
st.sidebar.subheader("💰 가격 필터")
deposit_range = st.sidebar.slider("보증금(만원)", int(df_raw['deposit'].min()), int(df_raw['deposit'].max()), (0, int(df_raw['deposit'].max())))
rent_range = st.sidebar.slider("월세(만원)", int(df_raw['monthlyRent'].min()), int(df_raw['monthlyRent'].max()), (0, int(df_raw['monthlyRent'].max())))

# 데이터 필터링 로직
df = df_raw.copy()
if search_query:
    df = df[df['title'].str.contains(search_query, case=False, na=False)]
if selected_biz:
    df = df[df['businessMiddleCodeName'].isin(selected_biz)]
df = df[(df['deposit'].between(deposit_range[0], deposit_range[1])) & (df['monthlyRent'].between(rent_range[0], rent_range[1]))]

# 탭 레이아웃 (개선사항 10)
tab1, tab2, tab3 = st.tabs(["🖼️ 매물 탐색 (갤러리/지도)", "📊 통계 및 시각화", "📄 매물 상세 정보"])

# Tab 1: 갤러리/지도 탐색
with tab1:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("📍 매물 위치 (지점 분포)")
        st.map(df[['lat', 'lon']]) # 개선사항 1
        
    with col_right:
        st.subheader("🎨 매물 갤러리 (클릭 시 상세 이동)") # 개선사항 2
        # 정렬 옵션 추가 (개선사항 8)
        sort_opt = st.selectbox("정렬 기준", ["조회수순", "최신순", "가격순", "가성비순"])
        if sort_opt == "조회수순": df_sorted = df.sort_values('viewCount', ascending=False)
        elif sort_opt == "최신순": df_sorted = df.sort_values('createdDateUtc', ascending=False)
        elif sort_opt == "가격순": df_sorted = df.sort_values('monthlyRent', ascending=True)
        else: df_sorted = df.sort_values('rent_per_area', ascending=True)
        
        # 갤러리 카드 뷰
        cols_gallery = st.columns(2)
        for i, row in enumerate(df_sorted.head(10).itertuples()):
            with cols_gallery[i % 2]:
                img_url = row.small_photos[0] if row.small_photos else "https://via.placeholder.com/150"
                st.image(img_url, use_container_width=True)
                if st.button(f"상세보기: {row.title[:15]}...", key=row.id):
                    st.session_state.selected_article_id = row.id
                    st.toast(f"매물 '{row.title[:10]}' 선택됨. 상세 탭을 확인하세요.")

# Tab 2: 시각화 및 가치 평가
with tab2:
    st.subheader("📈 시장 트렌드 및 데이터 분석")
    
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.bar(df['businessMiddleCodeName'].value_counts().head(10), title="업종별 매물 분포"), use_container_width=True)
    with c2:
        # 층별 임대료 분석 (개선사항 5)
        floor_rent = df.groupby('floor')['monthlyRent'].mean().reset_index()
        st.plotly_chart(px.line(floor_rent, x='floor', y='monthlyRent', title="층수별 평균 월세 추이"), use_container_width=True)

    # 데이터 테이블 (개선사항 6 - 한글 적용)
    st.subheader("📋 매물 검색 리스트")
    display_df = df[['title', 'businessMiddleCodeName', 'deposit', 'monthlyRent', 'premium', 'size', 'viewCount']].rename(columns=col_map)
    st.dataframe(display_df, use_container_width=True)

# Tab 3: 매물 상세 정보 (개선사항 3)
with tab3:
    if st.session_state.selected_article_id:
        target = df_raw[df_raw['id'] == st.session_state.selected_article_id].iloc[0]
        
        st.header(target['title'])
        st.subheader(f"{target['businessMiddleCodeName']} | {target['nearSubwayStation']}")
        
        # 벤치마킹 지표 (개선사항 4)
        st.divider()
        st.markdown("### 🏆 가치 평가 (Benchmarking)")
        b1, b2, b3 = st.columns(3)
        
        rent_diff = ((target['monthlyRent'] - target['avg_rent_by_biz']) / target['avg_rent_by_biz']) * 100
        dep_diff = ((target['deposit'] - target['avg_deposit_by_biz']) / target['avg_deposit_by_biz']) * 100
        
        with b1:
            color = "inverse" if rent_diff > 0 else "normal"
            st.metric("업종 평균 대비 월세", f"{target['monthlyRent']:,.0f} 만", f"{rent_diff:+.1f}%", delta_color=color)
        with b2:
            st.metric("업종 평균 대비 보증금", f"{target['deposit']:,.0f} 만", f"{dep_diff:+.1f}%")
        with b3:
            # 가성비 스코어 (개선사항 9)
            score = 100 - (target['rent_per_area'] / df_raw['rent_per_area'].mean() * 50)
            st.metric("가성비 스코어", f"{max(0, min(100, score)):.1f} / 100")

        # 상세 사진 갤러리
        st.divider()
        st.subheader("📸 상세 사진")
        if target['large_photos']:
            img_cols = st.columns(3)
            for i, img in enumerate(target['large_photos']):
                img_cols[i % 3].image(img, use_container_width=True)
        else:
            st.info("상세 사진이 없습니다.")
            
        # 기타 정보
        st.divider()
        with st.expander("📝 상세 제원"):
            st.write(f"**전용면적:** {target['size']} ㎡")
            st.write(f"**층:** {target['floor']} 층")
            st.write(f"**관리비:** {target['maintenanceFee']} 만원")
            st.write(f"**권리금:** {target['premium']} 만원")
            st.write(f"**가까운 지하철역:** {target['nearSubwayStation']}")
            st.write(f"**등록일:** {target['createdDateUtc']}")
    else:
        st.info("매물 탐색 탭에서 매물을 선택하거나 '상세보기' 버튼을 클릭해 주세요.")

# 푸터 (개선사항 6 - 한글 언어)
st.caption("네모스토어 데이터 플랫폼 - 전문 분석 모드")
