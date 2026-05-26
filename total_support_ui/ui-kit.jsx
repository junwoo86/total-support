/* ============================================================
 * UI Kit — Total Support · Design System v2
 *
 * Centralized, reusable component library. All visual primitives
 * and shared patterns live here. Tab files only compose these.
 *
 * Sections
 *   1. Tokens & Maps
 *   2. Layout primitives  (PageHero, SectionHead, Toolbar, Toast)
 *   3. Buttons            (Button, IconButton)
 *   4. Badges             (Badge, SiteBadge, DomainBadges, …)
 *   5. Form inputs        (TextInput, SelectInput, SearchPill,
 *                          CheckboxRow, Field, TagInput, ChipGroup,
 *                          ReviewSelect)
 *   6. Tables             (DataTable thin wrapper)
 *   7. Overlays           (Modal, ConfirmModal)
 *   8. Domain helpers     (DomainFilterChips, DDayCell)
 *   9. Posting detail     (PostingDetailModal)
 * ============================================================ */

const { useState, useEffect, useRef, useMemo, useCallback, createContext } = React;

/* ============================================================
 * 1. Tokens & Maps
 * ============================================================ */
const SITE_LABEL = {
  BIZINFO: '기업마당',
  IRIS:    'IRIS',
  SBA:     'SBA',
};
const SITE_FULL = {
  BIZINFO: '기업마당',
  IRIS:    'IRIS',
  SBA:     'SBA',
};
const SITE_SUB = {
  BIZINFO: 'bizinfo.go.kr',
  IRIS:    '범부처 R&D · iris.go.kr',
  SBA:     '서울경제진흥원 · sba.seoul.kr',
};
const REVIEW_LABEL = {
  UNREVIEWED:   '미검토',
  NEEDS_REVIEW: '검토 필요',
  IN_PROGRESS:  '지원 진행',
  EXCLUDED:     '제외',
};
const POSTING_STATUS_LABEL = {
  ONGOING:   '접수중',
  SCHEDULED: '접수예정',
  CLOSED:    '마감',
};
const SUITABILITY_LABEL = { HIGH: '상', NORMAL: '일반' };
const MATCH_MODE_LABEL  = {
  WORD_BOUNDARY: 'WORD_BOUNDARY',
  EXACT_HANGUL:  'EXACT_HANGUL',
  SUBSTRING:     'SUBSTRING',
  REGEX:         'REGEX',
};

/* ============================================================
 * 2. Layout primitives
 * ============================================================ */
function PageHero({ eyebrow, title, lede, actions }) {
  return (
    <div className="page-hero" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 24 }}>
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        {title && <h1>{title}</h1>}
        {lede && <p className="lede">{lede}</p>}
      </div>
      {actions && <div className="section-head__actions" style={{ display: 'flex', gap: 8 }}>{actions}</div>}
    </div>
  );
}

function SectionHead({ title, sub, actions }) {
  return (
    <div className="section-head">
      <div className="title-block">
        <h2>{title}</h2>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

function Toolbar({ children }) {
  return <div className="toolbar">{children}</div>;
}
Toolbar.Label    = ({ children }) => <span className="label">{children}</span>;
Toolbar.Divider  = () => <span className="divider" />;
Toolbar.Spacer   = () => <span className="spacer" />;
Toolbar.Count    = ({ n, suffix = '건 표시' }) => <span className="result-count"><b>{n}</b>{suffix}</span>;

/* Toast manager — context based, push toasts from anywhere */
const ToastCtx = createContext(null);
function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((msg, kind = 'info', ms = 3200) => {
    const id = Math.random().toString(36).slice(2, 9);
    setToasts(t => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), ms);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <span className="dot" />
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
const useToast = () => React.useContext(ToastCtx);

/* ============================================================
 * 3. Buttons
 * ============================================================ */
function Button({ variant = 'primary', size, disabled, onClick, children, title, type = 'button', className = '' }) {
  const cls = ['btn', variant, size, className].filter(Boolean).join(' ');
  return (
    <button type={type} className={cls} disabled={disabled} onClick={onClick} title={title}>
      {children}
    </button>
  );
}

function IconButton({ size = '', onClick, title, children, danger, disabled }) {
  return (
    <button
      className={`btn-icon ${size}`}
      onClick={onClick}
      title={title}
      disabled={disabled}
      style={danger ? { color: 'var(--coral)' } : null}
    >
      {children}
    </button>
  );
}

/* ============================================================
 * 4. Badges
 * ============================================================ */
function Badge({ tone = 'neutral', children, className = '' }) {
  return <span className={`badge ${tone} ${className}`}>{children}</span>;
}

function SiteBadge({ site }) {
  return <span className={`badge site ${site.toLowerCase()}`}>{SITE_LABEL[site]}</span>;
}

function SuitabilityBadge({ value }) {
  if (value === 'HIGH') return <Badge tone="coral">{SUITABILITY_LABEL.HIGH}</Badge>;
  return <Badge tone="neutral">{SUITABILITY_LABEL.NORMAL}</Badge>;
}

function PostingStatusBadge({ value }) {
  if (value === 'ONGOING')   return <Badge tone="success">{POSTING_STATUS_LABEL.ONGOING}</Badge>;
  if (value === 'SCHEDULED') return <Badge tone="blue-soft">{POSTING_STATUS_LABEL.SCHEDULED}</Badge>;
  return <Badge tone="neutral">{POSTING_STATUS_LABEL.CLOSED}</Badge>;
}

/* RelevanceScore — 회사 적합도 평가 (0~100, NULL=미평가).
 * 80%↑ 는 추천 강조, ? 버튼 클릭 시 평가 사유 popover. */
function RelevanceScore({ value, reason }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  if (value == null) {
    return <span className="relevance-cell relevance-na" title="회사 지침 미설정 또는 평가 실패">—</span>;
  }
  const tone = value >= 80 ? 'relevance-high' : value >= 50 ? 'relevance-mid' : 'relevance-low';
  const hasReason = !!(reason && reason.trim());
  return (
    <span className={`relevance-cell ${tone}`} ref={ref}>
      <span className="relevance-score">{value}%</span>
      {hasReason && (
        <button
          type="button"
          className="relevance-hint"
          onClick={() => setOpen(o => !o)}
          aria-label="평가 사유 보기"
          title="평가 사유 보기"
        >?</button>
      )}
      {value >= 80 && <span className="relevance-badge">추천</span>}
      {open && hasReason && (
        <div className="relevance-popover" role="tooltip">
          <div className="relevance-popover-head">AI 평가 사유 ({value}%)</div>
          <div className="relevance-popover-body">{reason}</div>
        </div>
      )}
    </span>
  );
}

function RunStatusBadge({ value }) {
  if (value === 'OK')      return <Badge tone="success">OK</Badge>;
  if (value === 'WARN')    return <Badge tone="warning">WARN</Badge>;
  if (value === 'FAIL')    return <Badge tone="coral-soft">FAIL</Badge>;
  if (value === 'RUNNING') return <Badge tone="blue-soft">RUNNING</Badge>;
  return <Badge>{value}</Badge>;
}

function DomainBadges({ names, domains }) {
  if (!names || names.length === 0) return <span style={{ color: 'var(--muted)' }}>—</span>;
  return (
    <div className="domain-badges">
      {names.map(n => {
        const d = domains.find(x => x.label_ko === n);
        const color = d ? d.color : '#777';
        return <span key={n} className="domain-badge" style={{ background: color }}>{n}</span>;
      })}
    </div>
  );
}

/* ============================================================
 * 5. Form inputs
 * ============================================================ */
function TextInput({ value, onChange, placeholder, type = 'text', error, style, monospace }) {
  return (
    <input
      type={type}
      className={`text-input ${error ? 'error' : ''}`}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={Object.assign(monospace ? { fontFamily: 'ui-monospace, monospace' } : {}, style || {})}
    />
  );
}

function SelectInput({ value, onChange, children, style }) {
  return (
    <select className="select-input" value={value} onChange={e => onChange(e.target.value)} style={style}>
      {children}
    </select>
  );
}

function SearchPill({ value, onChange, placeholder = '검색...', style }) {
  return (
    <input
      type="search"
      className="search-pill"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={style}
    />
  );
}

function CheckboxRow({ checked, onChange, children, style }) {
  return (
    <label className="checkbox-row" style={style}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

function Field({ label, required, hint, hintWarn, children }) {
  return (
    <div className="field">
      {label && <label>{label}{required && <span className="req">*</span>}</label>}
      {children}
      {hint && <div className={`hint ${hintWarn ? 'warn' : ''}`}>{hint}</div>}
    </div>
  );
}

function TagInput({ tags, setTags, placeholder }) {
  const [v, setV] = useState('');
  const add = () => {
    const t = v.trim();
    if (!t) return;
    if (!tags.includes(t)) setTags([...tags, t]);
    setV('');
  };
  return (
    <div className="tag-input-wrap">
      {tags.map(t => (
        <span key={t} className="tag">
          {t}
          <button onClick={() => setTags(tags.filter(x => x !== t))} aria-label="remove">×</button>
        </span>
      ))}
      <input
        value={v}
        onChange={e => setV(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter') { e.preventDefault(); add(); }
          if (e.key === 'Backspace' && v === '' && tags.length) setTags(tags.slice(0, -1));
        }}
        onBlur={add}
        placeholder={placeholder || 'Enter로 항목 추가'}
      />
    </div>
  );
}

/* Pill chip group — used for filters (적합도/출처/분야/상태/레벨) */
function ChipGroup({ value, onChange, options }) {
  return (
    <div className="chip-group">
      {options.map(o => (
        <button
          key={o.value}
          className={`chip ${value === o.value ? 'active' : ''}`}
          onClick={() => onChange(o.value)}
          title={o.title}
        >
          {o.swatch && <span className="swatch" style={{ background: o.swatch }} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* Per-row inline review-status select */
function ReviewSelect({ value, onChange }) {
  return (
    <select
      className="review-select"
      data-status={value}
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      <option value="UNREVIEWED">{REVIEW_LABEL.UNREVIEWED}</option>
      <option value="NEEDS_REVIEW">{REVIEW_LABEL.NEEDS_REVIEW}</option>
      <option value="IN_PROGRESS">{REVIEW_LABEL.IN_PROGRESS}</option>
      <option value="EXCLUDED">{REVIEW_LABEL.EXCLUDED}</option>
    </select>
  );
}

/* ============================================================
 * 6. Tables — thin wrapper
 * ============================================================ */
function DataTable({ children, className = '' }) {
  return <div className={`data-table ${className}`}><table>{children}</table></div>;
}

function EmptyState({ icon = '🗂️', head, sub }) {
  return (
    <div className="data-table">
      <div className="empty-state">
        <div className="icon">{icon}</div>
        <div className="head">{head}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
    </div>
  );
}

/* ============================================================
 * 7. Overlays — Modal, ConfirmModal
 * ============================================================ */
function Modal({ open, onClose, title, sub, footer, danger, children, maxWidth }) {
  useEffect(() => {
    if (!open) return;
    const onKey = e => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className={`modal${danger ? ' danger' : ''}`}
        style={maxWidth ? { maxWidth: maxWidth + 'px' } : null}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            {sub && <div className="sub">{sub}</div>}
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

function ConfirmModal({ open, title, message, confirmLabel = '확인', danger, onCancel, onConfirm }) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      danger={danger}
      maxWidth={480}
      footer={
        <>
          <Button variant="tertiary" onClick={onCancel}>취소</Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>{confirmLabel}</Button>
        </>
      }
    >
      <div style={{ fontSize: 14, color: 'var(--charcoal)', lineHeight: 1.65 }}>{message}</div>
    </Modal>
  );
}

/* ============================================================
 * 8. Domain helpers — DomainFilterChips, DDayCell
 * ============================================================ */
function DomainFilterChips({ domains, value, onChange }) {
  const opts = [
    { value: 'ALL', label: '전체' },
    ...domains.filter(d => d.enabled).map(d => ({
      value: d.label_ko,
      label: d.label_ko,
      swatch: d.color,
    })),
    { value: 'NONE', label: '미매칭' },
  ];
  return <ChipGroup value={value} onChange={onChange} options={opts} />;
}

function DDayCell({ posting }) {
  const { end_date, raw_period, start_date } = posting;
  if (!end_date) return <span className="dday always" title={raw_period}>{raw_period}</span>;
  const d = MOCK.dDay(end_date);
  const isPassed = d < 0;
  const isUrgent = !isPassed && d <= 7;
  const cls = isPassed ? 'passed' : isUrgent ? 'urgent' : '';
  const label = `${end_date.slice(5)} (${d >= 0 ? `D-${d}` : `D+${-d}`})`;
  return (
    <span className={`dday ${cls}`}>
      {label}
      {start_date && <span className="range">{start_date.slice(5)} ~ {end_date.slice(5)}</span>}
    </span>
  );
}

/* ============================================================
 * 9. PostingDetailModal — uses everything above
 * ============================================================ */
function PostingDetailModal({ posting, domains, open, onClose }) {
  if (!posting) return null;
  const isIRIS = posting.source_site === 'IRIS';
  const ddayInfo = posting.end_date
    ? `${posting.end_date} (${MOCK.dDay(posting.end_date) >= 0 ? `D-${MOCK.dDay(posting.end_date)}` : `D+${-MOCK.dDay(posting.end_date)}`})`
    : posting.raw_period;
  const openOriginal = () => window.open(posting.detail_url, '_blank', 'noopener');
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={posting.title}
      sub={
        <>
          <SiteBadge site={posting.source_site} />
          <PostingStatusBadge value={posting.posting_status} />
          <SuitabilityBadge value={posting.ai_suitability} />
          <DomainBadges names={posting.assigned_fields} domains={domains} />
        </>
      }
      maxWidth={860}
      footer={
        <>
          {isIRIS && (
            <span style={{ marginRight: 'auto', fontSize: 12, color: 'var(--steel)' }}>
              ⚠ IRIS는 상세가 POST 전용 — 원본 버튼은 목록 페이지로 안내합니다.
            </span>
          )}
          <Button variant="tertiary" onClick={onClose}>닫기</Button>
          <Button variant="primary" onClick={openOriginal}>
            {isIRIS ? '원본 IRIS에서 열기 ↗' : '원본 사이트에서 열기 ↗'}
          </Button>
        </>
      }
    >
      <div className="detail-meta">
        <div className="k">source_id</div>
        <div className="v mono">{posting.source_id}</div>
        <div className="k">접수기간 (원문)</div>
        <div className="v">{posting.raw_period}</div>
        <div className="k">D-Day</div>
        <div className="v">{ddayInfo}</div>
        <div className="k">최초 수집</div>
        <div className="v">{MOCK.fmtDateTime(posting.first_seen_at)}</div>
        <div className="k">최근 갱신</div>
        <div className="v">{MOCK.fmtDateTime(posting.last_updated_at)}</div>
        <div className="k">스크리닝 버전</div>
        <div className="v mono">v{posting.screened_with_version}</div>
        <div className="k">detail_url</div>
        <div className="v mono" style={{ wordBreak: 'break-all' }}>{posting.detail_url}</div>
      </div>
      {/* G5 · PRD §6.3-③: iframe sandbox 이중 방어.
          백엔드에서 sanitize되지만, 정책상 격리 컨텍스트로 한 번 더 보호. */}
      <iframe
        title="공고 본문"
        sandbox=""
        srcDoc={`<!doctype html><meta charset="utf-8"><base target="_blank"><style>
          body{font-family:'Pretendard','Helvetica Neue',sans-serif;color:#1e293b;font-size:14px;line-height:1.65;padding:8px;}
          h1,h2,h3,h4{color:#0f172a;margin:18px 0 8px;}
          h4{font-size:14px;color:#0284c7;letter-spacing:-0.2px;}
          ul,ol{padding-left:20px;}
          table{border-collapse:collapse;font-size:13px;}
          th,td{border:1px solid #cbd5e1;padding:8px 10px;}
          th{background:#f1f5f9;}
          img{max-width:100%;height:auto;}
        </style>${posting.content_html || '<p style="color:#64748b">본문이 비어있습니다.</p>'}`}
        className="detail-content"
        style={{ width: '100%', minHeight: 280, border: '1px solid var(--hairline-soft)', borderRadius: 8 }}
      />
    </Modal>
  );
}

/* ============================================================
 * Pagination — 클라이언트 사이드 30개씩 페이징
 * ============================================================ */
function usePagination(items, pageSize = 30) {
  const [page, setPage] = useState(1);
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // 필터 등으로 결과가 줄어들어 현재 page가 범위 밖이면 1로 리셋
  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [totalPages, page]);

  const safePage = Math.min(page, totalPages);
  const start = (safePage - 1) * pageSize;
  const pageItems = items.slice(start, start + pageSize);

  return {
    page: safePage,
    setPage,
    pageSize,
    totalPages,
    total,
    pageItems,
    showingFrom: total === 0 ? 0 : start + 1,
    showingTo: Math.min(start + pageSize, total),
  };
}

function Pagination({ page, totalPages, total, showingFrom, showingTo, onChange }) {
  if (total === 0) return null;
  const go = (p) => onChange(Math.max(1, Math.min(totalPages, p)));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  // 페이지 번호 윈도우 (현재 페이지 기준 ±2)
  const windowSize = 5;
  let from = Math.max(1, page - 2);
  let to = Math.min(totalPages, from + windowSize - 1);
  from = Math.max(1, to - windowSize + 1);
  const nums = [];
  for (let i = from; i <= to; i++) nums.push(i);

  return (
    <div className="pagination">
      <span className="pagination-info">
        <b>{showingFrom}–{showingTo}</b> / {total}건
      </span>
      <span className="pagination-spacer" />
      <button className="pg-btn" onClick={() => go(1)} disabled={!canPrev} title="처음">«</button>
      <button className="pg-btn" onClick={() => go(page - 1)} disabled={!canPrev} title="이전">‹</button>
      {from > 1 && <span className="pg-ellipsis">…</span>}
      {nums.map(n => (
        <button
          key={n}
          className={`pg-btn ${n === page ? 'active' : ''}`}
          onClick={() => go(n)}
        >
          {n}
        </button>
      ))}
      {to < totalPages && <span className="pg-ellipsis">…</span>}
      <button className="pg-btn" onClick={() => go(page + 1)} disabled={!canNext} title="다음">›</button>
      <button className="pg-btn" onClick={() => go(totalPages)} disabled={!canNext} title="마지막">»</button>
    </div>
  );
}

/* ============================================================
 * Bulk action bar (used by posting tabs)
 * ============================================================ */
function BulkBar({ count, options, onApply, onClear }) {
  return (
    <div className="bulk-bar">
      <span className="count"><b>{count}</b>건 선택됨</span>
      <span className="label">선택한 공고를 일괄 변경:</span>
      <select
        value=""
        onChange={e => {
          const v = e.target.value;
          if (!v) return;
          onApply(v);
        }}
      >
        <option value="">내부 검토 상태 선택...</option>
        {options.map(o => <option key={o.value} value={o.value}>→ {o.label}</option>)}
      </select>
      <Toolbar.Spacer />
      <Button variant="tertiary" size="sm" onClick={onClear}>선택 해제</Button>
    </div>
  );
}

/* ============================================================
 * Export to window
 * ============================================================ */
Object.assign(window, {
  // tokens & maps
  SITE_LABEL, SITE_FULL, SITE_SUB, REVIEW_LABEL, POSTING_STATUS_LABEL,
  SUITABILITY_LABEL, MATCH_MODE_LABEL,
  // layout
  PageHero, SectionHead, Toolbar, ToastProvider, useToast,
  // buttons
  Button, IconButton,
  // badges
  Badge, SiteBadge, SuitabilityBadge, PostingStatusBadge, RunStatusBadge, DomainBadges,
  // forms
  TextInput, SelectInput, SearchPill, CheckboxRow, Field, TagInput, ChipGroup, ReviewSelect,
  // tables
  DataTable, EmptyState,
  // overlays
  Modal, ConfirmModal,
  // domain helpers
  DomainFilterChips, DDayCell,
  // composite
  PostingDetailModal, BulkBar,
  // pagination
  usePagination, Pagination,
});
