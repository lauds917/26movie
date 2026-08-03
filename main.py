"""
어제자 일별 박스오피스 조회 앱
- KOBIS(영화진흥위원회) 공식 오픈 API 사용
- 스트림릿 클라우드 배포용
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # 파이썬 기본 내장 모듈 (별도 설치 불필요)

# ------------------------------------------------------------
# 0. 기본 페이지 설정
# ------------------------------------------------------------
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")
st.title("🎬 어제의 박스오피스")

# ------------------------------------------------------------
# 1. '어제' 날짜를 한국 시간(KST) 기준으로 계산하고,
#    달력에서 날짜를 고를 수 있게 한다.
#    - 배포 서버의 시계는 한국 시간이 아닐 수 있으므로
#      반드시 ZoneInfo("Asia/Seoul")로 현재 시각을 구한다.
#    - 오늘 데이터는 아직 집계 전이므로, 고를 수 있는 가장 늦은 날짜는 '어제'까지로 막는다.
# ------------------------------------------------------------
now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
yesterday_date_kst = (now_kst - timedelta(days=1)).date()

selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday_date_kst,           # 처음 열었을 때 기본값 = 어제
    max_value=yesterday_date_kst,       # 어제보다 미래(오늘 포함)는 선택 불가
    format="YYYY-MM-DD",
)

target_dt = selected_date.strftime("%Y%m%d")  # KOBIS가 요구하는 yyyymmdd 형식

st.caption(f"조회 기준일: {selected_date.strftime('%Y년 %m월 %d일')}")

# ------------------------------------------------------------
# 2. 비밀 금고(secrets)에서 인증키 불러오기
#    - 스트림릿 클라우드의 'Settings > Secrets'에 아래처럼 등록해야 함
#      KOBIS_KEY = "발급받은_인증키"
#    - 코드에는 절대 실제 키 값을 적지 않는다.
# ------------------------------------------------------------
if "KOBIS_KEY" not in st.secrets:
    st.error(
        "❌ 인증키를 찾을 수 없습니다.\n\n"
        "**확인해야 할 것**\n"
        "1. 스트림릿 클라우드의 'Settings → Secrets'에 들어가 있는지 확인하세요.\n"
        "2. 아래와 같은 형식으로 등록되어 있어야 합니다.\n\n"
        "```\nKOBIS_KEY = \"발급받은_인증키\"\n```\n"
        "3. 저장 후 앱을 재시작(Reboot)해야 반영됩니다."
    )
    st.stop()

API_KEY = st.secrets["KOBIS_KEY"]
API_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"


# ------------------------------------------------------------
# 3. API를 호출해서 박스오피스 데이터를 가져오는 함수
#    - 실패 상황을 하나씩 점검하고, 상황에 맞는 한국어 안내를 보여준다.
# ------------------------------------------------------------
@st.cache_data(ttl=3600)  # 같은 날짜는 1시간 동안 재사용해서 API 호출을 아낀다
def fetch_box_office(target_dt: str, api_key: str):
    """KOBIS API를 호출하고 (성공여부, 결과 or 에러메시지)를 돌려준다."""
    params = {"key": api_key, "targetDt": target_dt}

    # 3-1. 네트워크 요청 자체가 실패하는 경우 (타임아웃, 연결 오류 등)
    try:
        response = requests.get(API_URL, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        return False, (
            "❌ KOBIS 서버에 요청을 보내지 못했습니다.\n\n"
            "**확인해야 할 것**\n"
            "- 인터넷 연결 상태를 확인하세요.\n"
            "- KOBIS 서버가 일시적으로 점검 중일 수 있으니 잠시 후 다시 시도하세요.\n\n"
            f"(기술적 오류 내용: {e})"
        )

    # 3-2. HTTP 상태코드가 200이 아닌 경우 (서버 오류 등)
    if response.status_code != 200:
        return False, (
            f"❌ KOBIS 서버가 오류를 반환했습니다. (상태코드: {response.status_code})\n\n"
            "**확인해야 할 것**\n"
            "- 잠시 후 다시 시도해 보세요.\n"
            "- 문제가 계속되면 KOBIS 서버 상태를 확인하세요."
        )

    # 3-3. 응답이 JSON 형식이 아닌 경우
    try:
        data = response.json()
    except ValueError:
        return False, (
            "❌ 서버 응답을 이해할 수 없습니다(JSON 형식이 아님).\n\n"
            "**확인해야 할 것**\n"
            "- 요청 주소(URL)가 정확한지 확인하세요.\n"
            "- KOBIS API 문서가 변경되지 않았는지 확인하세요."
        )

    # 3-4. 인증키가 틀리는 등 API 자체 오류(faultInfo)가 오는 경우
    #      -> 문서에 나온 대로, 상태코드는 200이어도 이 상자가 올 수 있다.
    if "faultInfo" in data:
        message = data["faultInfo"].get("message", "알 수 없는 오류")
        return False, (
            f"❌ KOBIS API가 오류를 반환했습니다: {message}\n\n"
            "**확인해야 할 것**\n"
            "- 시크릿에 등록한 KOBIS_KEY 값이 정확한지 확인하세요(오타, 공백 포함 여부).\n"
            "- 발급받은 인증키가 아직 유효한지(사용 승인이 완료됐는지) 확인하세요.\n"
            "- 요청 변수(targetDt)가 8자리 날짜 형식인지 확인하세요."
        )

    # 3-5. 정상 구조인지 확인 (boxOfficeResult / dailyBoxOfficeList)
    box_office_result = data.get("boxOfficeResult")
    if not box_office_result:
        return False, (
            "❌ 응답에 boxOfficeResult 항목이 없습니다.\n\n"
            "**확인해야 할 것**\n"
            "- KOBIS API 응답 구조가 변경되었는지 확인하세요.\n"
            "- 요청 변수(key, targetDt)가 올바르게 전달됐는지 확인하세요."
        )

    movie_list = box_office_result.get("dailyBoxOfficeList")

    # 3-6. 영화 목록이 비어 있는 경우 -> "그날은 아직 집계 전입니다"로 안내
    if not movie_list:
        return False, "그날은 아직 집계 전입니다. 다른 날짜를 선택해 보세요."

    return True, movie_list


# ------------------------------------------------------------
# 4. 데이터 가져오기 실행
# ------------------------------------------------------------
success, result = fetch_box_office(target_dt, API_KEY)

if not success:
    # 실패 시: 빈 화면 대신 안내 문구를 보여주고 앱 실행을 멈춘다.
    # '아직 집계 전' 안내는 오류가 아니라 정상적인 상황이므로 info로,
    # 그 외 진짜 오류(키 문제, 통신 실패 등)는 warning으로 구분해서 보여준다.
    if result.startswith("그날은 아직 집계 전입니다"):
        st.info(result)
    else:
        st.warning(result)
    st.stop()

movie_list = result  # 성공했다면 result는 영화 리스트

# ------------------------------------------------------------
# 5. 데이터프레임으로 변환 + 숫자형 컬럼 변환
#    - API 응답의 모든 숫자 값은 문자열로 온다고 문서에 명시되어 있으므로
#      표시/그래프에 쓰기 위해 숫자 타입으로 바꿔준다.
# ------------------------------------------------------------
df = pd.DataFrame(movie_list)

numeric_cols = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# ------------------------------------------------------------
# 5-1. rankInten(전날 대비 순위 증감)을 화살표 텍스트로 바꾸기
#      - 문서 기준: 양수 = 순위 상승, 음수 = 순위 하락, 0 = 변동 없음
#      - 상승은 빨간 위쪽 화살표, 하락은 파란 아래쪽 화살표로 표시한다.
# ------------------------------------------------------------
def rank_change_text(inten):
    if pd.isna(inten):
        return "-"
    inten = int(inten)
    if inten > 0:
        return f"▲{inten}"       # 순위 상승
    elif inten < 0:
        return f"▼{abs(inten)}"  # 순위 하락
    else:
        return "-"                # 변동 없음

df["순위등락"] = df["rankInten"].apply(rank_change_text)

# ------------------------------------------------------------
# 5-2. 누적관객 100만 명 이상인 영화의 이름 옆에 트로피 이모지 붙이기
# ------------------------------------------------------------
def movie_name_with_trophy(row):
    if row["audiAcc"] >= 1_000_000:
        return f"🏆 {row['movieNm']}"
    return row["movieNm"]

df["영화명_표시"] = df.apply(movie_name_with_trophy, axis=1)

# 표에 보여줄 컬럼만 순서대로 정리하고 한글 이름으로 바꾸기
display_df = df[["rank", "순위등락", "영화명_표시", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
display_df.columns = ["순위", "순위등락", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# ------------------------------------------------------------
# 6. 1위 영화 - 지표 카드 세 장으로 크게 보여주기
# ------------------------------------------------------------
top_movie = df.iloc[0]

st.subheader(f"🏆 어제의 1위: {top_movie['movieNm']}")

col1, col2, col3 = st.columns(3)
col1.metric("어제 관객수", f"{int(top_movie['audiCnt']):,}명")
col2.metric("누적 관객수", f"{int(top_movie['audiAcc']):,}명")
col3.metric("스크린수", f"{int(top_movie['scrnCnt']):,}개")

st.divider()

# ------------------------------------------------------------
# 7. 전체 순위표
#    - '순위등락' 컬럼만 골라서 색을 입힌다(상승=빨강, 하락=파랑).
# ------------------------------------------------------------
st.subheader("📋 전체 순위표")


def style_rank_change(value):
    if isinstance(value, str) and value.startswith("▲"):
        return "color: red; font-weight: bold;"
    if isinstance(value, str) and value.startswith("▼"):
        return "color: blue; font-weight: bold;"
    return ""


styled_table = display_df.style.applymap(style_rank_change, subset=["순위등락"])

# pandas 버전에 따라 인덱스 숨기는 방식이 달라서 둘 다 시도한다.
try:
    styled_table = styled_table.hide(axis="index")
except AttributeError:
    styled_table = styled_table.hide_index()

st.dataframe(styled_table, use_container_width=True)

st.divider()

# ------------------------------------------------------------
# 8. 관객수 상위 5편 - 막대그래프
# ------------------------------------------------------------
st.subheader("📊 관객수 상위 5편")

top5 = df.nlargest(5, "audiCnt").set_index("영화명_표시")["audiCnt"]
st.bar_chart(top5)
