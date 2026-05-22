"""Enum 정의 drift 방지 가드 — PRD §4.1.

`db/enums.py` 의 StrEnum 이 다음과 영원히 일치하도록 강제:
- models.py 가 CHECK constraint 에 쓰는 `_VALUES` 튜플
- api/schemas.py 가 Pydantic 응답 검증에 쓰는 `Literal[...]`

세 곳 중 하나만 바뀌면 이 테스트가 실패해서 동기화를 강제한다.
"""

from __future__ import annotations

import typing

import pytest

from total_support.api import schemas
from total_support.db import (
    AiSuitability,
    LogCategory,
    LogLevel,
    MatchMode,
    PostingStatus,
    ReviewStatus,
    RunStatus,
    SourceSite,
    TriggerKind,
)
from total_support.db import models


# ============================================================
# StrEnum 자체 계약: str 호환 + value/name 동일 + 중복 없음
# ============================================================
@pytest.mark.parametrize("enum_cls", [
    SourceSite, AiSuitability, ReviewStatus, PostingStatus,
    RunStatus, TriggerKind, LogLevel, LogCategory, MatchMode,
])
def test_str_compat_and_unique(enum_cls):
    values = [e.value for e in enum_cls]
    # 모든 멤버가 str (== StrEnum 계약)
    for e in enum_cls:
        assert isinstance(e, str)
        # name 과 value 는 1:1 (오타·snake/SCREAMING 혼용 방지)
        assert e.name == e.value
    # 중복 없음
    assert len(values) == len(set(values))


# ============================================================
# models.py _VALUES 튜플과 동기화
# ============================================================
@pytest.mark.parametrize("enum_cls, tuple_const", [
    (SourceSite,    models.SOURCE_SITE_VALUES),
    (AiSuitability, models.AI_SUITABILITY_VALUES),
    (ReviewStatus,  models.REVIEW_STATUS_VALUES),
    (PostingStatus, models.POSTING_STATUS_VALUES),
    (RunStatus,     models.RUN_STATUS_VALUES),
    (TriggerKind,   models.TRIGGER_KIND_VALUES),
    (LogLevel,      models.LOG_LEVEL_VALUES),
    (LogCategory,   models.LOG_CATEGORY_VALUES),
    (MatchMode,     models.MATCH_MODE_VALUES),
])
def test_models_tuple_matches_enum(enum_cls, tuple_const):
    assert tuple_const == tuple(e.value for e in enum_cls), (
        f"{enum_cls.__name__} drift — Enum 정의와 _VALUES 튜플 불일치"
    )


# ============================================================
# api/schemas.py Literal 과 동기화
# ============================================================
def _literal_args(field_type) -> tuple[str, ...]:
    """Pydantic field annotation 에서 Literal 인자 튜플 추출."""
    args = typing.get_args(field_type)
    return tuple(args)


def test_run_trigger_site_literal_matches_source_site_enum():
    field = schemas.RunTrigger.model_fields["site"].annotation
    assert _literal_args(field) == tuple(e.value for e in SourceSite)


def test_review_status_patch_literal_matches_review_status_enum():
    field = schemas.ReviewStatusPatch.model_fields["status"].annotation
    assert set(_literal_args(field)) == {e.value for e in ReviewStatus}


def test_match_mode_alias_literal_matches_match_mode_enum():
    """schemas.MatchMode 는 Literal alias — Enum 과 같은 집합이어야 함."""
    assert set(typing.get_args(schemas.MatchMode)) == {e.value for e in MatchMode}


def test_posting_list_item_literals_match_enums():
    fields = schemas.PostingListItem.model_fields
    assert set(_literal_args(fields["source_site"].annotation)) == set(SOURCE := {e.value for e in SourceSite})
    assert set(_literal_args(fields["posting_status"].annotation)) == {e.value for e in PostingStatus}
    assert set(_literal_args(fields["ai_suitability"].annotation)) == {e.value for e in AiSuitability}
    assert set(_literal_args(fields["review_status"].annotation)) == {e.value for e in ReviewStatus}


def test_collection_run_out_literals_match_enums():
    fields = schemas.CollectionRunOut.model_fields
    assert set(_literal_args(fields["source_site"].annotation)) == {e.value for e in SourceSite}
    assert set(_literal_args(fields["status"].annotation)) == {e.value for e in RunStatus}
    assert set(_literal_args(fields["trigger_kind"].annotation)) == {e.value for e in TriggerKind}


def test_system_log_out_literals_match_enums():
    fields = schemas.SystemLogOut.model_fields
    assert set(_literal_args(fields["level"].annotation)) == {e.value for e in LogLevel}
    assert set(_literal_args(fields["category"].annotation)) == {e.value for e in LogCategory}
