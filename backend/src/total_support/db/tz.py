"""시간대 헬퍼 (PRD §2.3.2 · §11.2).

**중대 규칙**: DB/세션/롤 어디에서도 `SET TIME ZONE` 또는 `timezone` 파라미터를
변경하지 않는다. 모든 한국시간 비교는 쿼리식 `AT TIME ZONE 'Asia/Seoul'`로
수행한다. 본 모듈의 모든 ORM/raw 쿼리는 이 파일의 헬퍼만 사용한다.

올바른 사용:
    >>> from sqlalchemy import select
    >>> stmt = select(GrantPosting).where(
    ...     GrantPosting.end_date >= seoul_today_expr()
    ... )

금지:
    >>> conn.execute(text("SET TIME ZONE 'Asia/Seoul'"))  # 절대 금지
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import Date, Integer, func, literal
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.elements import quoted_name

#: Python 측 zoneinfo (Beat 스케줄러 등에서 사용)
SEOUL_TZ = ZoneInfo("Asia/Seoul")

#: 본 모듈 전용 시퀀스 이름 (PRD §3.3.3 · §4.4 트리거 함수에서 nextval)
KEYWORD_VERSION_SEQ_NAME = quoted_name("tb_grant_keyword_version_seq", quote=False)


def seoul_now_expr() -> ColumnElement:
    """`(now() AT TIME ZONE 'Asia/Seoul')::timestamp` — TZ naive timestamp."""
    return func.timezone(literal("Asia/Seoul"), func.now())


def seoul_today_expr() -> ColumnElement:
    """`(now() AT TIME ZONE 'Asia/Seoul')::date` — 한국 기준 오늘 날짜."""
    return func.cast(seoul_now_expr(), Date)


def dday_expr(end_date_col: ColumnElement) -> ColumnElement:
    """PRD §5.3 D-Day 계산: `end_date - 한국 오늘`.

    음수면 마감 경과, 0~7이면 적색 하이라이트 대상, 그 이상이면 여유.
    `end_date IS NULL`인 경우 NULL 반환 (UI에서 raw_period 원문 표시).
    """
    return func.cast(end_date_col - seoul_today_expr(), Integer)
