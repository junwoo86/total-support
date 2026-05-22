"""접수기간 파서 — PRD §2.3 6단계 우선순위 매트릭스.

3개 사이트(BIZINFO/IRIS/SBA)는 접수기간을 모두 자연어로 표기한다.
DB에는 다음 2개 컬럼을 병행 운영한다:
- `raw_period` TEXT : 원문 보존 (시간 정보 포함, 손실 없이)
- `start_date`, `end_date` DATE : 파싱 성공 시에만 채움 · 실패 시 NULL

대시보드 표기 규칙(§5.3):
- end_date가 있으면 "MM-DD (D-N)" 형태로 D-Day 계산
- NULL이면 raw_period 원문을 그대로 노출 ("상시", "예산 소진 시" 등)

본 함수는 announce_date(공고일)를 옵션 인자로 받아 P5(상대 표현)를 처리한다.
공고일을 모르면 P5는 NULL로 떨어진다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# ============================================================
# 파싱 결과 컨테이너
# ============================================================
@dataclass(frozen=True, slots=True)
class ParseOutcome:
    """parse_period 출력. raw_period은 손실 없이 원문 그대로."""

    start_date: date | None
    end_date: date | None
    raw_period: str
    #: 디버그/로그/§8.1 PARSE_PERIOD 카테고리 기록용 ("P1" ~ "P6")
    rule: str
    #: 시간 정보가 추출된 경우 "HH:MM" (raw_period에도 보존됨; 별도 컬럼 없음)
    end_time: str | None = None


# ============================================================
# 정규식 (PRD §2.3.1 매트릭스)
# ============================================================
# P1/P2 공통: yyyy-mm-dd / yyyy.mm.dd / yyyy/mm/dd
_DATE_RE = re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})")

# P2 보강: yyyy가 한 번만 명시되고 두 번째는 mm.dd / mm-dd / mm/dd로 줄어든 경우
# (예: "2026.05.22(금) ~ 06.22(월)") — 시간(18:00)과 구분하기 위해 구분자 강제
_SHORT_MMDD_RE = re.compile(r"(?<!\d)(\d{1,2})[-./](\d{1,2})(?!\d)")

# 시간: 18:00, 18시 등 (HH:MM 형태만 캡처; 라벨 변형은 raw_period에 보존)
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

# P3: 연도 생략 (~ 06.22)
_SHORT_END_RE = re.compile(r"~\s*(\d{1,2})[-./](\d{1,2})")

# P4: 상시/예산 소진 키워드
_ALWAYS_RE = re.compile(r"(상시|예산\s*소진|마감\s*시까지)")

# P5: 공고일/발표일 + N일
_RELATIVE_RE = re.compile(r"(?:공고일|발표일)로부터\s*(\d+)\s*일")


def _make_date(y: int, m: int, d: int) -> date | None:
    """안전한 date 생성. 잘못된 값(예: 2026-13-40)이면 None."""
    try:
        return date(y, m, d)
    except ValueError:
        return None


# ============================================================
# 메인 함수
# ============================================================
def parse_period(
    raw: str,
    *,
    announce_date: date | None = None,
    default_year: int | None = None,
) -> ParseOutcome:
    """접수기간 원문에서 (start, end, rule)을 뽑는다.

    Args:
        raw: 사이트에서 추출한 원문 (예: "2026-05-20 ~ 2026-06-08").
        announce_date: P5 (공고일로부터 N일) 처리를 위해 알 수 있으면 전달.
        default_year: P3 (연도 생략)에서 사용할 기본 연도. 기본값은 오늘 연도.

    Returns:
        ParseOutcome — start_date/end_date는 None일 수 있음. raw_period는
        반드시 원문 보존.
    """
    if raw is None:
        raise ValueError("raw 인자는 None일 수 없습니다 (DB에는 NULL 대신 빈 문자열을 저장).")

    # 원문 보존 (사이트가 준 그대로). 양 끝 공백 정리는 안전한 정규화.
    raw_period = raw.strip() or raw

    # ---- P4 키워드 우선 (P1~P3가 비어도 P4가 잡힐 수 있음) ---
    # 단, 본문에 yyyy-mm-dd가 함께 있으면 그 쪽이 우선이라
    # P1을 먼저 시도하고 매칭 0건일 때만 P4로 떨어진다.
    dates_p1 = _DATE_RE.findall(raw)

    if dates_p1:
        # ---- P1/P2 (yyyy-mm-dd가 1개 또는 2개 이상) ---------
        return _parse_p1_p2(raw, raw_period, dates_p1)

    # ---- P3 (연도 생략 단편형) ------------------------------
    short = _SHORT_END_RE.search(raw)
    if short:
        year = default_year or date.today().year
        m = int(short.group(1))
        d = int(short.group(2))
        end = _make_date(year, m, d)
        return ParseOutcome(
            start_date=None, end_date=end, raw_period=raw_period, rule="P3"
        )

    # ---- P4 (상시/예산 소진/마감 시까지) ---------------------
    if _ALWAYS_RE.search(raw):
        return ParseOutcome(
            start_date=None, end_date=None, raw_period=raw_period, rule="P4"
        )

    # ---- P5 (공고일로부터 N일) ------------------------------
    rel = _RELATIVE_RE.search(raw)
    if rel:
        n = int(rel.group(1))
        if announce_date is not None:
            from datetime import timedelta
            end = announce_date + timedelta(days=n)
            return ParseOutcome(
                start_date=announce_date,
                end_date=end,
                raw_period=raw_period,
                rule="P5",
            )
        # 공고일을 모르면 NULL로 두되 raw_period는 보존
        return ParseOutcome(
            start_date=None, end_date=None, raw_period=raw_period, rule="P5"
        )

    # ---- P6 (PARSE_UNKNOWN) --------------------------------
    return ParseOutcome(
        start_date=None, end_date=None, raw_period=raw_period, rule="P6"
    )


# ============================================================
# P1/P2 헬퍼
# ============================================================
def _parse_p1_p2(
    raw: str, raw_period: str, dates: list[tuple[str, str, str]]
) -> ParseOutcome:
    """yyyy-mm-dd 형식이 1개 이상일 때 처리.

    - 2개 이상이면 첫 번째=start, 두 번째=end.
    - 1개면 end만 채운다 (예: "마감 2026-06-22"). start는 None.
    - 시간 정보(18:00)가 있으면 end_time 캡처 (raw_period에도 보존).
    """
    parsed = [_make_date(int(y), int(m), int(d)) for y, m, d in dates]
    parsed = [p for p in parsed if p is not None]
    if not parsed:
        # 잘못된 날짜값 (예: 2026-13-40) — P6로 떨어뜨림
        return ParseOutcome(
            start_date=None, end_date=None, raw_period=raw_period, rule="P6"
        )

    if len(parsed) >= 2:
        start, end = parsed[0], parsed[1]
    else:
        # P2 보강: 풀 날짜가 1개고, 그 뒤쪽 텍스트에서 짧은 mm.dd가 나오면
        # 첫 날짜의 연도를 빌려서 end를 구성한다.
        # 예: "2026.05.22(금) ~ 06.22(월)" → end = 2026-06-22
        first_full_end = next(_DATE_RE.finditer(raw)).end()
        tail = raw[first_full_end:]
        # 시간 패턴(18:00)이 짧은 mm.dd로 잘못 잡히지 않도록 시간 영역을 마스킹
        tail_no_time = _TIME_RE.sub("", tail)
        m_short = _SHORT_MMDD_RE.search(tail_no_time)
        if m_short:
            mm, dd = int(m_short.group(1)), int(m_short.group(2))
            inferred = _make_date(parsed[0].year, mm, dd)
            if inferred is not None:
                start, end = parsed[0], inferred
            else:
                start, end = None, parsed[0]
        else:
            start, end = None, parsed[0]

    # 시간 정보 — P2 케이스: "06.22(월) 18:00 까지"
    time_match = _TIME_RE.search(raw)
    end_time = None
    rule = "P1"
    if time_match:
        end_time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
        rule = "P2"

    return ParseOutcome(
        start_date=start,
        end_date=end,
        raw_period=raw_period,
        rule=rule,
        end_time=end_time,
    )
