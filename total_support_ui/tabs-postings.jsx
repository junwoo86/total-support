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
        <col style={{ width: '8%' }} />
        <col style={{ width: '7%' }} />
        <col style={{ width: '5%' }} />
        <col style={{ width: '10%' }} />
        <col style={{ width: '6%' }} />
        <col style={{ width: '6%' }} />
        <col style={{ width: '18%' }} />
        <col style={{ width: '15%' }} />
        <col style={{ width: '10%' }} />
        <col style={{ width: '12%' }} />
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
          <th className="id-cell" title="DB에 적재된 KST 날짜">수집일</th>
          <th title="회사 지침 기준 AI 평가 (0~100)">추천</th>
          <th>적합도</th>
          <th>분야</th>
          <th>출처</th>
          <th>상태</th>
          <th>지원 사업명</th>
          <th>사업 상세 요약</th>
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
              <td className="id-cell">{MOCK.fmtDateKST(p.first_seen_at)}</td>
              <td><RelevanceScore value={p.relevance_score} reason={p.relevance_reason} /></td>
              <td><SuitabilityBadge value={p.ai_suitability} /></td>
              <td><DomainBadges names={p.assigned_fields} domains={domains} /></td>
              <td><SiteBadge site={p.source_site} /></td>
              <td><PostingStatusBadge value={p.posting_status} /></td>
              <td>
                <span className="project-link" onClick={() => onOpenDetail(p)} title="자체 상세 모달 열기">
                  {p.title}
                </span>
              </td>
              <td>
                <div className="summary-cell" onClick={() => onOpenDetail(p)} title="클릭하여 본문 전체 보기">
                  {p.summary}
                </div>
              </td>
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

/* ============================================================
 * Tab 1 · Unreviewed
 * ============================================================ */
function UnreviewedTab({ postings, domains, onChangeReview, onChangeReviewBulk, onOpenDetail, removingIds }) {
  const [suitability, setSuitability] = useState('ALL');
  const [site, setSite] = useState('ALL');
  const [domain, setDomain] = useState('ALL');
  const [query, setQuery] = useState('');

  const rows = useMemo(() => {
    return postings.filter(p =>
      p.review_status === 'UNREVIEWED' &&
      (suitability === 'ALL' || p.ai_suitability === suitability) &&
      (site === 'ALL' || p.source_site === site) &&
      applyDomainFilter(p, domain) &&
      applySearch(p, query)
    ).sort((a, b) => {
      if (a.ai_suitability !== b.ai_suitability) return a.ai_suitability === 'HIGH' ? -1 : 1;
      const ad = a.end_date ? MOCK.dDay(a.end_date) : 999;
      const bd = b.end_date ? MOCK.dDay(b.end_date) : 999;
      if (ad !== bd) return ad - bd;
      return new Date(b.first_seen_at) - new Date(a.first_seen_at);
    });
  }, [postings, suitability, site, domain, query]);

  // 30개씩 페이징 (대시보드 무한 노출 방지)
  const pg = usePagination(rows, 30);
  const { selectedIds, toggleOne, toggleAll, clear } = useRowSelection(pg.pageItems);
  const handleBulk = (newStatus) => {
    onChangeReviewBulk(Array.from(selectedIds), newStatus);
    clear();
  };

  return (
    <div>
      <SectionHead
        title="신규 미검토 큐"
        sub="팀이 아직 분류하지 않은 공고 — 상태를 변경하면 큐에서 빠집니다"
      />
      <Toolbar>
        <Toolbar.Label>적합도</Toolbar.Label>
        <ChipGroup
          value={suitability}
          onChange={setSuitability}
          options={[
            { value: 'ALL', label: '전체' },
            { value: 'HIGH', label: '상' },
            { value: 'NORMAL', label: '일반' },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>출처</Toolbar.Label>
        <ChipGroup
          value={site}
          onChange={setSite}
          options={[
            { value: 'ALL', label: '전체' },
            { value: 'BIZINFO', label: SITE_LABEL.BIZINFO },
            { value: 'IRIS', label: SITE_LABEL.IRIS },
            { value: 'SBA', label: SITE_LABEL.SBA },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>분야</Toolbar.Label>
        <DomainFilterChips domains={domains} value={domain} onChange={setDomain} />
        <Toolbar.Divider />
        <SearchPill value={query} onChange={setQuery} placeholder="사업명 / 요약 검색" />
        <Toolbar.Spacer />
        <Toolbar.Count n={rows.length} />
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
        total={pg.total}
        showingFrom={pg.showingFrom}
        showingTo={pg.showingTo}
        onChange={pg.setPage}
      />
    </div>
  );
}

/* ============================================================
 * Tab 2 · Status Monitoring
 * ============================================================ */
function StatusTab({ postings, domains, onChangeReview, onChangeReviewBulk, onOpenDetail, removingIds }) {
  const [status, setStatus] = useState('NEEDS_REVIEW');
  const [hideExpired, setHideExpired] = useState(true);
  const [site, setSite] = useState('ALL');
  const [domain, setDomain] = useState('ALL');
  const [query, setQuery] = useState('');

  const expiredOK = (p) => {
    if (status === 'EXCLUDED') return true;
    if (!hideExpired) return true;
    if (!p.end_date) return true;
    return MOCK.dDay(p.end_date) >= 0;
  };

  const rows = useMemo(() => {
    return postings.filter(p =>
      p.review_status !== 'UNREVIEWED' &&
      (status === 'ALL' || p.review_status === status) &&
      expiredOK(p) &&
      (site === 'ALL' || p.source_site === site) &&
      applyDomainFilter(p, domain) &&
      applySearch(p, query)
    ).sort((a, b) => {
      const ad = a.end_date ? MOCK.dDay(a.end_date) : 999;
      const bd = b.end_date ? MOCK.dDay(b.end_date) : 999;
      return ad - bd;
    });
  }, [postings, status, hideExpired, site, domain, query]);

  const pg = usePagination(rows, 30);
  const { selectedIds, toggleOne, toggleAll, clear } = useRowSelection(pg.pageItems);
  const handleBulk = (newStatus) => {
    onChangeReviewBulk(Array.from(selectedIds), newStatus);
    clear();
  };

  const counts = useMemo(() => {
    const out = { NEEDS_REVIEW: 0, IN_PROGRESS: 0, EXCLUDED: 0 };
    for (const p of postings) if (p.review_status in out) out[p.review_status]++;
    return out;
  }, [postings]);

  const bulkOptions = [
    { value: 'UNREVIEWED',   label: '미검토로 되돌리기' },
    { value: 'NEEDS_REVIEW', label: '검토 필요로 이동' },
    { value: 'IN_PROGRESS',  label: '지원 진행으로 이동' },
    { value: 'EXCLUDED',     label: '제외로 이동' },
  ].filter(o => status === 'ALL' ? true : o.value !== status);

  return (
    <div>
      <SectionHead
        title="상태별 통합 모니터링"
        sub="검토 필요 · 지원 진행 · 제외 상태를 일괄 관리합니다"
      />
      <Toolbar>
        <Toolbar.Label>상태</Toolbar.Label>
        <ChipGroup
          value={status}
          onChange={setStatus}
          options={[
            { value: 'NEEDS_REVIEW', label: `검토 필요 (${counts.NEEDS_REVIEW})` },
            { value: 'IN_PROGRESS',  label: `지원 진행 (${counts.IN_PROGRESS})` },
            { value: 'EXCLUDED',     label: `제외 (${counts.EXCLUDED})` },
            { value: 'ALL',          label: '전체' },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>출처</Toolbar.Label>
        <ChipGroup
          value={site}
          onChange={setSite}
          options={[
            { value: 'ALL', label: '전체' },
            { value: 'BIZINFO', label: SITE_LABEL.BIZINFO },
            { value: 'IRIS', label: SITE_LABEL.IRIS },
            { value: 'SBA', label: SITE_LABEL.SBA },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>분야</Toolbar.Label>
        <DomainFilterChips domains={domains} value={domain} onChange={setDomain} />
        <Toolbar.Divider />
        <SearchPill value={query} onChange={setQuery} placeholder="사업명 / 요약 검색" />
        <Toolbar.Spacer />
        {status !== 'EXCLUDED' && (
          <CheckboxRow checked={hideExpired} onChange={setHideExpired} style={{ fontSize: 12, color: 'var(--steel)' }}>
            만료 자동 숨김 (§5.2)
          </CheckboxRow>
        )}
        <Toolbar.Count n={rows.length} />
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
        total={pg.total}
        showingFrom={pg.showingFrom}
        showingTo={pg.showingTo}
        onChange={pg.setPage}
      />
    </div>
  );
}

Object.assign(window, { PostingsTable, UnreviewedTab, StatusTab });
