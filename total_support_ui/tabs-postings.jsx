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
          const d = p.end_date ? MOCK.dDay(p.end_date) : null;
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
  const ad = a.end_date ? MOCK.dDay(a.end_date) : 999;
  const bd = b.end_date ? MOCK.dDay(b.end_date) : 999;
  if (ad !== bd) return ad - bd;
  return new Date(b.first_seen_at) - new Date(a.first_seen_at);
}

/* ============================================================
 * Tab 1 · Unreviewed
 * ============================================================ */
function UnreviewedTab({ hook, domains, onChangeReview, onChangeReviewBulk, onOpenDetail, removingIds }) {
  // hook: 백엔드 페이지네이션 + 정렬 + 필터. 클라이언트 sort/filter 없음.
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

  const { selectedIds, toggleOne, toggleAll, clear } = useRowSelection(pg.pageItems);
  const handleBulk = (newStatus) => {
    onChangeReviewBulk(Array.from(selectedIds), newStatus);
    clear();
  };

  return (
    <div>
      <SectionHead
        title="신규 미검토"
        sub="아직 검토하지 않은 공고 — 검토를 마치면 목록에서 빠집니다"
      />
      <Toolbar>
        <Toolbar.Label>적합도</Toolbar.Label>
        <ChipGroup
          value={filters.suitability || 'ALL'}
          onChange={(v) => setFilters({ suitability: v === 'ALL' ? undefined : v })}
          options={[
            { value: 'ALL', label: '전체' },
            { value: 'HIGH', label: '상' },
            { value: 'NORMAL', label: '일반' },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>출처</Toolbar.Label>
        <ChipGroup
          value={filters.site || 'ALL'}
          onChange={(v) => setFilters({ site: v === 'ALL' ? undefined : v })}
          options={[
            { value: 'ALL', label: '전체' },
            { value: 'BIZINFO', label: SITE_LABEL.BIZINFO },
            { value: 'IRIS', label: SITE_LABEL.IRIS },
            { value: 'SBA', label: SITE_LABEL.SBA },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>분야</Toolbar.Label>
        <DomainFilterChips
          domains={domains}
          value={filters.domain || 'ALL'}
          onChange={(v) => setFilters({ domain: v === 'ALL' ? undefined : v })}
        />
        <Toolbar.Divider />
        <SearchPill value={queryDraft} onChange={setQueryDraft} placeholder="사업명 검색" />
        <Toolbar.Spacer />
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
        onChange={pg.setPage}
        loadedCount={items.length}
        canLoadMore={canLoadMore}
        loading={loading}
        onLoadMore={loadMore}
      />
    </div>
  );
}

/* ============================================================
 * Tab 2 · Status Monitoring
 * ============================================================ */
function StatusTab({ hook, domains, onChangeReview, onChangeReviewBulk, onOpenDetail, removingIds }) {
  const { items, total, loading, filters, setFilters, loadMore, canLoadMore } = hook;
  const status = filters.status || 'NEEDS_REVIEW';
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

  const bulkOptions = [
    { value: 'UNREVIEWED',   label: '미검토로 되돌리기' },
    { value: 'NEEDS_REVIEW', label: '검토 필요로 이동' },
    { value: 'IN_PROGRESS',  label: '지원 진행으로 이동' },
    { value: 'EXCLUDED',     label: '제외로 이동' },
  ].filter(o => o.value !== status);

  return (
    <div>
      <SectionHead
        title="검토 상태별 확인"
        sub="검토 필요 · 지원 진행 · 제외 상태를 일괄 관리합니다"
      />
      <Toolbar>
        <Toolbar.Label>상태</Toolbar.Label>
        <ChipGroup
          value={status}
          onChange={(v) => setFilters({ status: v })}
          options={[
            { value: 'NEEDS_REVIEW', label: '검토 필요' },
            { value: 'IN_PROGRESS',  label: '지원 진행' },
            { value: 'EXCLUDED',     label: '제외' },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>출처</Toolbar.Label>
        <ChipGroup
          value={filters.site || 'ALL'}
          onChange={(v) => setFilters({ site: v === 'ALL' ? undefined : v })}
          options={[
            { value: 'ALL', label: '전체' },
            { value: 'BIZINFO', label: SITE_LABEL.BIZINFO },
            { value: 'IRIS', label: SITE_LABEL.IRIS },
            { value: 'SBA', label: SITE_LABEL.SBA },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>분야</Toolbar.Label>
        <DomainFilterChips
          domains={domains}
          value={filters.domain || 'ALL'}
          onChange={(v) => setFilters({ domain: v === 'ALL' ? undefined : v })}
        />
        <Toolbar.Divider />
        <SearchPill value={queryDraft} onChange={setQueryDraft} placeholder="사업명 검색" />
        <Toolbar.Spacer />
        {status !== 'EXCLUDED' && (
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
