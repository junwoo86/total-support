/* ============================================================
 * Posting tabs — Unreviewed + Status Monitoring
 * Uses primitives from ui-kit.jsx
 * ============================================================ */

/* ---- Shared: postings table ---- */
function PostingsTable({
  rows, domains, onChangeReview, onOpenDetail, removingIds,
  selectedIds, onToggleSelect, onToggleAll,
}) {
  // ⚠ Hooks는 early return보다 먼저 호출되어야 한다 (React Rules of Hooks).
  // 이전 버그: 빈 rows일 때 EmptyState로 early return 후 useRef/useEffect를 호출해
  // hook 호출 순서가 매 렌더마다 달라져 "Expected static flag was missing" 내부 경고가 났다.
  const visibleIds  = rows ? rows.map(r => r.id) : [];
  const selectedVis = visibleIds.filter(id => selectedIds.has(id));
  const allChecked  = visibleIds.length > 0 && selectedVis.length === visibleIds.length;
  const someChecked = selectedVis.length > 0 && !allChecked;
  const headRef = useRef(null);
  useEffect(() => {
    if (headRef.current) headRef.current.indeterminate = someChecked;
  }, [someChecked]);

  if (!rows || rows.length === 0) {
    return (
      <EmptyState
        head="표시할 공고가 없습니다"
        sub="필터를 조정하거나 상단의 '지금 실행' 버튼으로 수집을 다시 시도하세요."
      />
    );
  }

  return (
    <DataTable>
      <colgroup>
        <col style={{ width: '3%' }} />
        <col style={{ width: '23%' }} />
        <col style={{ width: '10%' }} />
        <col style={{ width: '7%' }} />
        <col style={{ width: '28%' }} />
        <col style={{ width: '7%' }} />
        <col style={{ width: '11%' }} />
        <col style={{ width: '11%' }} />
      </colgroup>
      <thead>
        <tr>
          <th className="check-cell">
            <input
              ref={headRef}
              type="checkbox"
              className="head-check"
              checked={allChecked}
              onChange={() => onToggleAll(visibleIds)}
              title={allChecked ? '전체 해제' : '현재 표시 중인 행 전체 선택'}
            />
          </th>
          <th>지원 사업명</th>
          <th>분야</th>
          <th title="회사 지침 기준 AI 평가 (0~100)">적합도</th>
          <th>적합 사유</th>
          <th>상태</th>
          <th>접수 기간 · D-Day</th>
          <th>내부 검토</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(p => {
          const d = dDayOf(p);
          const isUrgent = p.end_date && d !== null && d <= 7 && d >= 0;
          const removing = removingIds.includes(p.id);
          const isSelected = selectedIds.has(p.id);
          const trCls = [
            isUrgent ? 'urgent' : '',
            removing ? 'removing' : '',
            isSelected ? 'selected' : '',
          ].filter(Boolean).join(' ');
          return (
            <tr key={p.id} className={trCls}>
              <td className="check-cell">
                <input
                  type="checkbox"
                  className="row-check"
                  checked={isSelected}
                  onChange={() => onToggleSelect(p.id)}
                />
              </td>
              <td>
                <span className="project-link" onClick={() => onOpenDetail(p)} title="자체 상세 모달 열기">
                  {p.title}
                </span>
              </td>
              <td><DomainBadges names={p.assigned_fields} domains={domains} /></td>
              <td><RelevanceScore value={p.relevance_score} failed={p.evaluation_failed} /></td>
              <td><RelevanceReason text={p.relevance_reason} failed={p.evaluation_failed} /></td>
              <td><PostingStatusBadge value={p.posting_status} /></td>
              <td><DDayCell posting={p} /></td>
              <td><ReviewSelect value={p.review_status} onChange={v => onChangeReview(p.id, v)} /></td>
            </tr>
          );
        })}
      </tbody>
    </DataTable>
  );
}

/* ============================================================
 * Hook: row selection (shared by both tabs)
 * ============================================================ */
function useRowSelection(rows) {
  const [selectedIds, setSelectedIds] = useState(() => new Set());

  // prune ids no longer visible after filter change
  useEffect(() => {
    setSelectedIds(prev => {
      const visible = new Set(rows.map(r => r.id));
      const next = new Set();
      prev.forEach(id => { if (visible.has(id)) next.add(id); });
      return next.size === prev.size ? prev : next;
    });
  }, [rows]);

  const toggleOne = (id) => setSelectedIds(s => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleAll = (visibleIds) => setSelectedIds(s => {
    const allChecked = visibleIds.length > 0 && visibleIds.every(id => s.has(id));
    if (allChecked) {
      const n = new Set(s); visibleIds.forEach(id => n.delete(id)); return n;
    }
    const n = new Set(s); visibleIds.forEach(id => n.add(id)); return n;
  });
  const clear = () => setSelectedIds(new Set());

  return { selectedIds, toggleOne, toggleAll, clear };
}

/* ============================================================
 * Helper: shared filter logic
 * ============================================================ */
function applyDomainFilter(p, domain) {
  if (domain === 'ALL') return true;
  if (domain === 'NONE') return !p.assigned_fields || p.assigned_fields.length === 0;
  return p.assigned_fields && p.assigned_fields.includes(domain);
}

function applySearch(p, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  return p.title.toLowerCase().includes(q) || p.summary.toLowerCase().includes(q);
}

/* 공통 정렬 — 백엔드 services/postings.py 의 ORDER BY 와 동일 규칙.
 *  1) evaluation_failed=true 가 최상단
 *  2) AI 회사 적합도 점수 DESC (NULL 후순위)
 *  3) 키워드 적합도 HIGH 우선
 *  4) D-Day 가까운 순
 *  5) 최근 적재 순
 */
function sortByRelevance(a, b) {
  const af = !!a.evaluation_failed, bf = !!b.evaluation_failed;
  if (af !== bf) return af ? -1 : 1;
  const as = a.relevance_score, bs = b.relevance_score;
  if (as !== bs) {
    if (as == null) return 1;
    if (bs == null) return -1;
    return bs - as;
  }
  if (a.ai_suitability !== b.ai_suitability) return a.ai_suitability === 'HIGH' ? -1 : 1;
  const ad = a.end_date ? (dDayOf(a) ?? 999) : 999;
  const bd = b.end_date ? (dDayOf(b) ?? 999) : 999;
  if (ad !== bd) return ad - bd;
  return new Date(b.first_seen_at) - new Date(a.first_seen_at);
}

/* ============================================================
 * Tab 1 · Unreviewed
 *
 * 필터:
 *   - 적합도 (relevance bucket — multi)
 *       상(80↑) · 중상(60↑) · 중(40↑) · 하(40↓)
 *   - 분야 (multi)
 *   - 검색 (debounce 300ms)
 * 정렬:
 *   - 기본: 백엔드 ORDER BY (회사 적합도 DESC)
 *   - D-Day 토글: 현재 화면 30건만 마감 가까운 순으로 클라이언트 재정렬
 *     ("적합도 상 + 마감 임박" 같은 워크플로우용 — page 별 동작)
 * 출처(site) 필터는 제거됨 (가치 낮고 칸 차지가 큼).
 * ============================================================ */
function UnreviewedTab({ hook, domains, onChangeReview, onChangeReviewBulk, onOpenDetail, removingIds }) {
  const { items, total, loading, filters, setFilters, loadMore, canLoadMore } = hook;

  // 검색은 디바운스 300ms 로 백엔드 호출 빈도 절제
  const [queryDraft, setQueryDraft] = useState(filters.q || '');
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.q || '') !== queryDraft) setFilters({ q: queryDraft || undefined });
    }, 300);
    return () => clearTimeout(t);
  }, [queryDraft]);

  // 30개씩 페이징은 "이미 로드된 items 안에서" 동작.
  // 마지막 페이지에 도달하면 자동으로 다음 200건 fetch.
  const pg = usePagination(items, 30);
  useEffect(() => {
    if (pg.page === pg.totalPages && canLoadMore && !loading) {
      loadMore();
    }
  }, [pg.page, pg.totalPages, canLoadMore, loading]);

  // D-Day 정렬 토글 — 현재 페이지(30건)만 클라이언트 재정렬.
  // end_date 가까운 순. NULL/상시는 후순위.
  const [sortByDDay, setSortByDDay] = useState(false);
  const visibleRows = useMemo(() => {
    if (!sortByDDay) return pg.pageItems;
    const sorted = [...pg.pageItems].sort((a, b) => {
      const ad = a.end_date ? (dDayOf(a) ?? Infinity) : Infinity;
      const bd = b.end_date ? (dDayOf(b) ?? Infinity) : Infinity;
      return ad - bd;
    });
    return sorted;
  }, [pg.pageItems, sortByDDay]);

  const { selectedIds, toggleOne, toggleAll, clear } = useRowSelection(visibleRows);
  const handleBulk = (newStatus) => {
    onChangeReviewBulk(Array.from(selectedIds), newStatus);
    clear();
  };

  const bucketsValue = filters.relevance_bucket || [];
  const domainValue  = filters.domain || [];

  return (
    <div>
      <SectionHead
        title="신규 미검토"
        sub="아직 검토하지 않은 공고 — 검토를 마치면 목록에서 빠집니다"
      />
      <Toolbar>
        <Toolbar.Label>적합도</Toolbar.Label>
        <ChipGroup
          multiSelect
          value={bucketsValue}
          onChange={(arr) => setFilters({ relevance_bucket: arr.length ? arr : undefined })}
          options={[
            { value: 'high',     label: '상 (80~100)' },
            { value: 'mid_high', label: '중상 (60~80)' },
            { value: 'mid',      label: '중 (40~60)' },
            { value: 'low',      label: '하 (0~40)' },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>분야</Toolbar.Label>
        <DomainFilterChips
          multiSelect
          domains={domains}
          value={domainValue}
          onChange={(arr) => setFilters({ domain: arr.length ? arr : undefined })}
        />
        <Toolbar.Divider />
        <SearchPill value={queryDraft} onChange={setQueryDraft} placeholder="사업명 검색" />
        <Toolbar.Spacer />
        <SortToggle
          active={sortByDDay}
          onToggle={() => setSortByDDay(v => !v)}
          activeLabel="D-Day순 (현재 페이지)"
          inactiveLabel="기본 정렬 (적합도)"
        />
        <Toolbar.Count n={total} />
      </Toolbar>

      {selectedIds.size > 0 && (
        <BulkBar
          count={selectedIds.size}
          options={[
            { value: 'NEEDS_REVIEW', label: '검토 필요로 이동' },
            { value: 'IN_PROGRESS',  label: '지원 진행으로 이동' },
            { value: 'EXCLUDED',     label: '제외로 이동' },
          ]}
          onApply={handleBulk}
          onClear={clear}
        />
      )}

      <PostingsTable
        rows={visibleRows}
        domains={domains}
        onChangeReview={onChangeReview}
        onOpenDetail={onOpenDetail}
        removingIds={removingIds}
        selectedIds={selectedIds}
        onToggleSelect={toggleOne}
        onToggleAll={toggleAll}
      />
      <Pagination
        page={pg.page}
        totalPages={pg.totalPages}
        total={total}
        showingFrom={pg.showingFrom}
        showingTo={pg.showingTo}
        onChange={pg.setPage}
        loadedCount={items.length}
        canLoadMore={canLoadMore}
        loading={loading}
        onLoadMore={loadMore}
      />
    </div>
  );
}

/* 정렬 토글 버튼 — Toolbar 우측, "기본 정렬" / "D-Day순 (현재 페이지)" */
function SortToggle({ active, onToggle, activeLabel, inactiveLabel }) {
  return (
    <button
      className={`chip sort-toggle ${active ? 'active' : ''}`}
      onClick={onToggle}
      title="현재 페이지의 30건을 마감 가까운 순으로 재정렬"
      style={{ marginRight: 8 }}
    >
      <span style={{ marginRight: 4 }}>{active ? '⏰' : '🔀'}</span>
      {active ? activeLabel : inactiveLabel}
    </button>
  );
}

/* ============================================================
 * Tab 2 · Status Monitoring
 *
 * 필터:
 *   - 상태 (multi: NEEDS_REVIEW + IN_PROGRESS + EXCLUDED) — 칩 옆 카운트 표시
 *   - 분야 (multi)
 *   - 검색 (debounce 300ms)
 *   - 만료 자동 숨김 (적용 가능한 상태가 선택되었을 때만)
 * 출처(site) 필터는 제거됨. statusCounts 는 부모(app.jsx) 에서 hook 으로
 * 받아 칩 옆 숫자에 사용 — list fetch 와 무관하게 status 별 분포 표시.
 * ============================================================ */
function StatusTab({
  hook, domains, statusCounts,
  onChangeReview, onChangeReviewBulk, onOpenDetail, removingIds,
}) {
  const { items, total, loading, filters, setFilters, loadMore, canLoadMore } = hook;
  // 초기값: ['NEEDS_REVIEW'] (가장 자주 보는 화면)
  const statusValue = Array.isArray(filters.status) ? filters.status : [];
  const hideExpired = !!filters.hide_expired;

  const [queryDraft, setQueryDraft] = useState(filters.q || '');
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.q || '') !== queryDraft) setFilters({ q: queryDraft || undefined });
    }, 300);
    return () => clearTimeout(t);
  }, [queryDraft]);

  const pg = usePagination(items, 30);
  useEffect(() => {
    if (pg.page === pg.totalPages && canLoadMore && !loading) {
      loadMore();
    }
  }, [pg.page, pg.totalPages, canLoadMore, loading]);

  const { selectedIds, toggleOne, toggleAll, clear } = useRowSelection(pg.pageItems);
  const handleBulk = (newStatus) => {
    onChangeReviewBulk(Array.from(selectedIds), newStatus);
    clear();
  };

  // 다중 status 모드에선 한 가지 status 행만 보이는 게 아니므로 모든 옵션 노출.
  const bulkOptions = [
    { value: 'UNREVIEWED',   label: '미검토로 되돌리기' },
    { value: 'NEEDS_REVIEW', label: '검토 필요로 이동' },
    { value: 'IN_PROGRESS',  label: '지원 진행으로 이동' },
    { value: 'EXCLUDED',     label: '제외로 이동' },
  ];

  // 만료 자동 숨김 체크박스 표시 조건:
  //   - 만료 영향 받는 status (NEEDS_REVIEW / IN_PROGRESS) 가 선택되었거나
  //   - 아무 status 도 선택 안 됨 (전체)
  //   - 단, EXPIRED 가 선택되어 있으면 이미 만료 행을 보여달라는 의도라 숨김.
  const expirable = (statusValue.length === 0
                  || statusValue.includes('NEEDS_REVIEW')
                  || statusValue.includes('IN_PROGRESS'))
                 && !statusValue.includes('EXPIRED');

  const domainValue = filters.domain || [];

  return (
    <div>
      <SectionHead
        title="검토 상태별 확인"
        sub="검토 필요 · 지원 진행 · 제외 상태를 일괄 관리합니다"
      />
      <Toolbar>
        <Toolbar.Label>상태</Toolbar.Label>
        <ChipGroup
          multiSelect
          value={statusValue}
          onChange={(arr) => setFilters({ status: arr.length ? arr : undefined })}
          options={[
            { value: 'NEEDS_REVIEW', label: '검토 필요', count: statusCounts.NEEDS_REVIEW },
            { value: 'IN_PROGRESS',  label: '지원 진행', count: statusCounts.IN_PROGRESS },
            { value: 'EXCLUDED',     label: '제외',     count: statusCounts.EXCLUDED },
            { value: 'EXPIRED',      label: '기간 만료', count: statusCounts.EXPIRED },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>분야</Toolbar.Label>
        <DomainFilterChips
          multiSelect
          domains={domains}
          value={domainValue}
          onChange={(arr) => setFilters({ domain: arr.length ? arr : undefined })}
        />
        <Toolbar.Divider />
        <SearchPill value={queryDraft} onChange={setQueryDraft} placeholder="사업명 검색" />
        <Toolbar.Spacer />
        {expirable && (
          <CheckboxRow
            checked={hideExpired}
            onChange={(v) => setFilters({ hide_expired: v })}
            style={{ fontSize: 12, color: 'var(--steel)' }}
          >
            만료 자동 숨김 (§5.2)
          </CheckboxRow>
        )}
        <Toolbar.Count n={total} />
      </Toolbar>

      {selectedIds.size > 0 && (
        <BulkBar
          count={selectedIds.size}
          options={bulkOptions}
          onApply={handleBulk}
          onClear={clear}
        />
      )}

      <PostingsTable
        rows={pg.pageItems}
        domains={domains}
        onChangeReview={onChangeReview}
        onOpenDetail={onOpenDetail}
        removingIds={removingIds}
        selectedIds={selectedIds}
        onToggleSelect={toggleOne}
        onToggleAll={toggleAll}
      />
      <Pagination
        page={pg.page}
        totalPages={pg.totalPages}
        total={total}
        showingFrom={pg.showingFrom}
        showingTo={pg.showingTo}
        loadedCount={items.length}
        canLoadMore={canLoadMore}
        loading={loading}
        onLoadMore={loadMore}
        onChange={pg.setPage}
      />
    </div>
  );
}

Object.assign(window, { PostingsTable, UnreviewedTab, StatusTab });
