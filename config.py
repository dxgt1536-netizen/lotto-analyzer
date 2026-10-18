"""배포 관련 설정. 전부 환경변수로 주입하고, 값이 없으면 기능을 그냥 끈다.

.env 파일에 실제 값을 채우면 되고, 이 저장소에는 예시(.env.example)만 커밋한다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

SITE_NAME = os.environ.get("SITE_NAME", "로또 분석기")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")  # 예: https://lottostat.kr
SITE_DESCRIPTION = os.environ.get(
    "SITE_DESCRIPTION",
    "로또 6/45 전체 회차 데이터를 기반으로 번호별 출현 빈도, 홀짝/구간 비율, 합계 분포를 "
    "분석하고 번호를 추천해주는 무료 로또 분석기·로또 번호 추천기.",
)

# 광고 미승인 상태에서는 비워두면 자동으로 광고 코드가 렌더링되지 않는다.
ADSENSE_CLIENT_ID = os.environ.get("ADSENSE_CLIENT_ID", "")  # 예: ca-pub-1234567890123456
ADSENSE_SLOT_TOP = os.environ.get("ADSENSE_SLOT_TOP", "")
ADSENSE_SLOT_INLINE = os.environ.get("ADSENSE_SLOT_INLINE", "")

GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
NAVER_SITE_VERIFICATION = os.environ.get("NAVER_SITE_VERIFICATION", "")

ADS_ENABLED = bool(ADSENSE_CLIENT_ID)

# 게시판 글은 이 비밀번호로도 지울 수 있다 (글쓴이가 정한 비밀번호를 몰라도 관리자가 삭제 가능).
# 비워두면 관리자 삭제 기능이 꺼진다.
BOARD_ADMIN_PASSWORD = os.environ.get("BOARD_ADMIN_PASSWORD", "")
