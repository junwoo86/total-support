/* ============================================================
 * Domain & Keyword Management — uses primitives from ui-kit.jsx
 * ============================================================ */

function KeywordsTab({
  domains, keywords, postings,
  onDomainCreate, onDomainUpdate, onDomainSoftDelete, onDomainHardDelete,
  onKeywordCreate, onKeywordUpdate, onKeywordDelete, onKeywordToggle,
  keywordVersion,
}) {
  const [selectedId, setSelectedId] = useState(domains[0] && domains[0].id);
  const [domainModal, setDomainModal] = useState(null);
  const [kwModal, setKwModal] = useState(null);
  const [confirmHardDel, setConfirmHardDel] = useState(null);

  const selected = domains.find(d => d.id === selectedId);
  const selectedKws = useMemo(
    () => keywords.filter(k => k.domain_id === selectedId),
    [keywords, selectedId]
  );

  const kwCount = useMemo(() => {
    const m = {};
    for (const k of keywords) {
      if (!k.enabled) continue;
      m[k.domain_id] = (m[k.domain_id] || 0) + 1;
    }
    return m;
  }, [keywords]);

  return (
    <div>
      <SectionHead
        title="분야 · 키워드 관리"
        sub="코드 배포 없이 분야와 매칭 키워드를 추가 · 수정 · 비활성화"
        actions={
          <span style={{ fontSize: 13, color: 'var(--steel)' }}>
            keyword_version <code>v{keywordVersion}</code>
          </span>
        }
      />

      <CompanyGuidelineCard />

      <div className="kw-layout">
        {/* 좌측: 분야 */}
        <div className="card flush">
          <div className="card-head">
            <h3>분야 <b>· Domain</b></h3>
            <Button variant="primary" size="sm" onClick={() => setDomainModal({ mode: 'create' })}>＋ 새 분야</Button>
          </div>
          {domains.length === 0 && (
            <div className="empty-state">
              <div className="icon">🏷️</div>
              <div className="head">등록된 분야가 없습니다</div>
            </div>
          )}
          {domains.map(d => (
            <div
              key={d.id}
              className={`domain-row ${selectedId === d.id ? 'active' : ''} ${!d.enabled ? 'disabled' : ''}`}
              onClick={() => setSelectedId(d.id)}
            >
              <span className="swatch" style={{ background: d.color }} />
              <span className="label-text">
                {d.label_ko}
                {!d.enabled && <Badge tone="neutral">비활성</Badge>}
              </span>
              <span className="count">{kwCount[d.id] || 0}개</span>
              <span className="row-actions">
                <IconButton
                  size="sm"
                  onClick={e => { e.stopPropagation(); setDomainModal({ mode: 'edit', domain: d }); }}
                  title="편집"
                >✏</IconButton>
                <IconButton
                  size="sm"
                  onClick={e => { e.stopPropagation(); onDomainSoftDelete(d.id); }}
                  title={d.enabled ? '비활성화 (Soft Delete)' : '활성화'}
                >{d.enabled ? '⏸' : '▶'}</IconButton>
                <IconButton
                  size="sm"
                  danger
                  onClick={e => { e.stopPropagation(); setConfirmHardDel(d); }}
                  title="영구 삭제 (Hard Delete)"
                >🗑</IconButton>
              </span>
            </div>
          ))}
        </div>

        {/* 우측: 키워드 */}
        <div className="card flush">
          <div className="card-head">
            <h3>
              키워드 <b>· Keyword</b>
              {selected && (
                <span style={{ marginLeft: 10, textTransform: 'none', letterSpacing: 0, fontWeight: 500, color: 'var(--steel)', fontSize: 13 }}>
                  →&nbsp;
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <span className="swatch" style={{ background: selected.color, width: 10, height: 10, borderRadius: 2, display: 'inline-block' }} />
                    <b style={{ color: 'var(--ink)' }}>{selected.label_ko}</b>
                  </span>
                </span>
              )}
            </h3>
            {selected && (
              <Button
                variant="primary"
                size="sm"
                disabled={!selected.enabled}
                onClick={() => setKwModal({ mode: 'create' })}
                title={selected.enabled ? '키워드 추가' : '비활성 분야에는 키워드를 추가할 수 없습니다'}
              >＋ 새 키워드</Button>
            )}
          </div>
          {!selected && (
            <div className="empty-state"><div className="head">왼쪽에서 분야를 선택하세요</div></div>
          )}
          {selected && selectedKws.length === 0 && (
            <div className="empty-state">
              <div className="icon">🔍</div>
              <div className="head">아직 키워드가 없습니다</div>
              <div className="sub">'＋ 새 키워드'로 매칭 규칙을 추가하세요.</div>
            </div>
          )}
          {selectedKws.map(k => (
            <div key={k.id} className={`kw-item ${!k.enabled ? 'disabled' : ''}`}>
              <div className="kw-item-main">
                <div className="kw-item-keyword">
                  {k.keyword}
                  {!k.enabled && <Badge tone="neutral" className="" >비활성</Badge>}
                </div>
                <div className="kw-item-meta">
                  <span className="mode" title={k.match_mode}>{MATCH_MODE_LABEL[k.match_mode] || k.match_mode}</span>
                  {k.case_sensitive && <span>대소문자 구분</span>}
                  {k.negative_context && k.negative_context.length > 0 && (
                    <span className="neg-list">⛔ {k.negative_context.join(', ')}</span>
                  )}
                </div>
              </div>
              <div className="kw-item-actions">
                <Button variant="tertiary" size="sm" onClick={() => setKwModal({ mode: 'edit', keyword: k })}>편집</Button>
                <Button variant="tertiary" size="sm" onClick={() => onKeywordToggle(k.id)}>
                  {k.enabled ? '비활성화' : '활성화'}
                </Button>
                <IconButton size="sm" danger onClick={() => onKeywordDelete(k.id)} title="삭제">🗑</IconButton>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Domain modal */}
      {domainModal && (
        <DomainEditModal
          mode={domainModal.mode}
          initial={domainModal.domain}
          onClose={() => setDomainModal(null)}
          onSubmit={(payload) => {
            if (domainModal.mode === 'create') onDomainCreate(payload);
            else onDomainUpdate(domainModal.domain.id, payload);
            setDomainModal(null);
          }}
        />
      )}

      {/* Keyword modal */}
      {kwModal && selected && (
        <KeywordEditModal
          mode={kwModal.mode}
          domain={selected}
          initial={kwModal.keyword}
          postings={postings}
          onClose={() => setKwModal(null)}
          onSubmit={(payload) => {
            if (kwModal.mode === 'create') onKeywordCreate({ ...payload, domain_id: selected.id });
            else onKeywordUpdate(kwModal.keyword.id, payload);
            setKwModal(null);
          }}
        />
      )}

      {/* Hard delete confirm */}
      {confirmHardDel && (
        <ConfirmModal
          open={true}
          danger
          title={`"${confirmHardDel.label_ko}" 분야를 영구 삭제할까요?`}
          confirmLabel="영구 삭제"
          message={
            <div>
              <p style={{ marginTop: 0 }}>이 작업은 <b>되돌릴 수 없습니다</b>:</p>
              <ul style={{ paddingLeft: 18 }}>
                <li>분야에 속한 <b>{keywords.filter(k => k.domain_id === confirmHardDel.id).length}개 키워드</b>가 <code>ON DELETE CASCADE</code>로 함께 삭제됩니다.</li>
                <li>이미 적재된 공고의 <code>assigned_fields</code>는 즉시 변하지 않으며, 직후 키워드 백필 잡이 자동으로 재스캔합니다.</li>
              </ul>
              <div style={{ background: 'var(--coral-bg)', color: 'var(--coral)', padding: '10px 14px', borderRadius: 8, fontSize: 13, marginTop: 10 }}>
                <b>운영 권장</b>: 비활성화(Soft Delete)를 먼저 검토하세요.
              </div>
            </div>
          }
          onCancel={() => setConfirmHardDel(null)}
          onConfirm={() => {
            onDomainHardDelete(confirmHardDel.id);
            if (selectedId === confirmHardDel.id) {
              const next = domains.find(d => d.id !== confirmHardDel.id);
              setSelectedId(next ? next.id : null);
            }
            setConfirmHardDel(null);
          }}
        />
      )}
    </div>
  );
}

/* ============================================================
 * DomainEditModal
 * ============================================================ */
function DomainEditModal({ mode, initial, onClose, onSubmit }) {
  const [code, setCode] = useState(initial ? initial.code : '');
  const [labelKo, setLabelKo] = useState(initial ? initial.label_ko : '');
  const [color, setColor] = useState(initial ? initial.color : '#2563eb');
  const [order, setOrder] = useState(initial ? initial.display_order : 99);
  const isEdit = mode === 'edit';
  const valid = labelKo.trim() && (isEdit || /^[A-Z0-9_]+$/.test(code));

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={isEdit ? '분야 편집' : '새 분야 추가'}
      sub={isEdit ? <span>code: <code>{initial.code}</code> · <span style={{ color: 'var(--muted)' }}>FK 안정성 보호 — 변경 불가</span></span> : null}
      maxWidth={520}
      footer={
        <>
          <Button variant="tertiary" onClick={onClose}>취소</Button>
          <Button variant="primary" disabled={!valid} onClick={() => onSubmit({
            code: isEdit ? initial.code : code.toUpperCase(),
            label_ko: labelKo.trim(),
            color,
            display_order: Number(order) || 99,
          })}>{isEdit ? '저장' : '추가'}</Button>
        </>
      }
    >
      {!isEdit && (
        <Field label="코드 (영문 대문자)" required hint="DB 저장값. 영문 대문자/숫자/언더스코어만 허용. 저장 후 변경 불가.">
          <TextInput
            value={code}
            onChange={v => setCode(v.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
            placeholder="예: AI, BIO, HEALTHCARE"
            monospace
          />
        </Field>
      )}
      <Field label="표시명 (한글)" required>
        <TextInput value={labelKo} onChange={setLabelKo} placeholder="예: 인공지능" />
      </Field>
      <div className="field-row">
        <Field label="배지 색상">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="color" value={color} onChange={e => setColor(e.target.value)} />
            <TextInput value={color} onChange={setColor} monospace style={{ flex: 1 }} />
          </div>
        </Field>
        <Field label="표시 순서">
          <TextInput type="number" value={order} onChange={setOrder} />
        </Field>
      </div>
      <Field label="미리보기">
        <span className="domain-badge" style={{ background: color, fontSize: 13, padding: '5px 12px' }}>
          {labelKo || '(표시명 입력)'}
        </span>
      </Field>
    </Modal>
  );
}

/* ============================================================
 * KeywordEditModal — preview + validation
 * ============================================================ */
function KeywordEditModal({ mode, domain, initial, postings, onClose, onSubmit }) {
  const [keyword, setKeyword] = useState(initial ? initial.keyword : '');
  const [matchMode, setMatchMode] = useState(initial ? initial.match_mode : 'WORD_BOUNDARY');
  const [caseSensitive, setCaseSensitive] = useState(initial ? initial.case_sensitive : false);
  const [negative, setNegative] = useState(initial ? [...initial.negative_context] : []);
  const [enabled, setEnabled] = useState(initial ? initial.enabled : true);
  const [previewing, setPreviewing] = useState(false);
  const [previewResult, setPreviewResult] = useState(null);
  const [regexErr, setRegexErr] = useState(null);
  const isEdit = mode === 'edit';

  useEffect(() => {
    if (matchMode === 'REGEX' && keyword) {
      try { new RegExp(keyword); setRegexErr(null); }
      catch (e) { setRegexErr(e.message); }
    } else setRegexErr(null);
  }, [matchMode, keyword]);

  const buildRegex = useCallback((kw, mode, cs) => {
    const flags = cs ? 'g' : 'gi';
    const esc = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (mode === 'WORD_BOUNDARY') return new RegExp(`\\b${esc}\\b`, flags);
    if (mode === 'EXACT_HANGUL')  return new RegExp(`(?<![가-힣])${esc}(?![가-힣])`, flags);
    if (mode === 'SUBSTRING')     return new RegExp(esc, flags);
    if (mode === 'REGEX')         return new RegExp(kw, flags);
    return new RegExp(esc, flags);
  }, []);

  const runPreview = () => {
    if (!keyword.trim()) return;
    setPreviewing(true);

    // G4: LIVE 모드면 백엔드 /keywords/preview 호출 (실 DB 100건 기준)
    if (window.API && window.API.LIVE_MODE) {
      window.API.previewKeyword({
        keyword,
        match_mode: matchMode,
        case_sensitive: caseSensitive,
        negative_context: negative,
      })
        .then(res => {
          setPreviewResult({
            total: res.scanned,
            matched: res.samples.map(s => ({
              id: s.posting_id,
              title: s.title,
              ctx: s.context,
              idx: s.start,
            })),
            matchedTotal: res.matched,
          });
        })
        .catch(e => setPreviewResult({ error: e.message }))
        .finally(() => setPreviewing(false));
      return;
    }

    // MOCK 모드: 클라이언트 매처
    setTimeout(() => {
      try {
        const re = buildRegex(keyword, matchMode, caseSensitive);
        const matches = [];
        for (const p of postings.slice(0, 100)) {
          const text = `${p.title}\n${p.summary}`;
          let m, found = null;
          re.lastIndex = 0;
          while ((m = re.exec(text))) {
            const start = Math.max(0, m.index - 30);
            const ctx = text.slice(start, m.index + m[0].length + 30);
            const blocked = negative.some(n => n && ctx.includes(n));
            if (!blocked) { found = { ctx, idx: m.index }; break; }
          }
          if (found) matches.push({ id: p.id, title: p.title, ctx: found.ctx, idx: found.idx });
        }
        setPreviewResult({ total: postings.slice(0, 100).length, matched: matches });
      } catch (e) {
        setPreviewResult({ error: e.message });
      } finally {
        setPreviewing(false);
      }
    }, 280);
  };

  const valid = keyword.trim() && (matchMode !== 'REGEX' || !regexErr);

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={isEdit ? '키워드 편집' : '새 키워드 추가'}
      sub={<>분야: <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 10, height: 10, borderRadius: 2, background: domain.color, display: 'inline-block' }} />
        <b style={{ color: 'var(--ink)' }}>{domain.label_ko}</b>
      </span></>}
      maxWidth={620}
      footer={
        <>
          <Button variant="tertiary" onClick={onClose}>취소</Button>
          <Button variant="primary" disabled={!valid} onClick={() => onSubmit({
            keyword: keyword.trim(),
            match_mode: matchMode,
            case_sensitive: caseSensitive,
            negative_context: negative,
            enabled,
          })}>{isEdit ? '저장' : '추가'}</Button>
        </>
      }
    >
      <Field label="키워드 / 정규식" required hint={regexErr ? `정규식 오류: ${regexErr}` : null} hintWarn={!!regexErr}>
        <TextInput
          value={keyword}
          onChange={setKeyword}
          placeholder={matchMode === 'REGEX' ? '예: \\bAI\\b|인공지능' : '예: AI'}
          monospace
          error={!!regexErr}
        />
      </Field>
      <div className="field-row">
        <Field label="매칭 모드">
          <SelectInput value={matchMode} onChange={setMatchMode}>
            <option value="WORD_BOUNDARY">영문 단어 — 단어 경계 매칭 (\b...\b)</option>
            <option value="EXACT_HANGUL">한글 단어 — 한글 좌우 음절 차단</option>
            <option value="SUBSTRING">부분 일치 — 어디든 포함되면 매칭</option>
            <option value="REGEX">정규식 — 사용자 지정 패턴</option>
          </SelectInput>
        </Field>
        <Field label="옵션">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 8 }}>
            <CheckboxRow checked={caseSensitive} onChange={setCaseSensitive}>대소문자 구분</CheckboxRow>
            <CheckboxRow checked={enabled} onChange={setEnabled}>활성화 (스크리닝 사용)</CheckboxRow>
          </div>
        </Field>
      </div>
      <Field label="부정 화이트리스트 (negative_context)" hint="이 단어가 매칭 위치 좌우 30자에 포함되면 매칭 무효. 예: AI + SAIPA → SAIPA에서는 매칭 안 됨">
        <TagInput tags={negative} setTags={setNegative} placeholder="Enter로 항목 추가" />
      </Field>

      <div style={{ borderTop: '1px solid var(--hairline-soft)', paddingTop: 16, marginTop: 4 }}>
        <Button variant="tertiary" onClick={runPreview} disabled={previewing || !keyword.trim()}>
          {previewing ? '시뮬레이션 중...' : '🔬 최근 100건 대조 미리보기'}
        </Button>
        {previewResult && (
          <div className="preview-block">
            {previewResult.error ? (
              <div style={{ color: 'var(--coral)' }}>오류: {previewResult.error}</div>
            ) : (
              <>
                <div className="preview-head">
                  <b>{previewResult.matchedTotal ?? previewResult.matched.length}건</b> 매칭 / {previewResult.total}건 조회
                  {previewResult.matchedTotal != null && previewResult.matched.length < previewResult.matchedTotal && (
                    <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--steel)' }}>(샘플 {previewResult.matched.length}개)</span>
                  )}
                </div>
                {previewResult.matched.slice(0, 4).map(m => (
                  <div key={m.id} className="preview-item">
                    <div className="title">{m.title}</div>
                    <div className="ctx">
                      …{m.ctx.replace(new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), s => `▶${s}◀`)}…
                    </div>
                  </div>
                ))}
                {previewResult.matched.length > 4 && (
                  <div style={{ color: 'var(--steel)', fontSize: 12 }}>… 외 {previewResult.matched.length - 4}건</div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

/* ============================================================
 * CompanyGuidelineCard — 회사 지침 (AI 적합도 평가용 시스템 프롬프트)
 * 저장 시 백엔드가 version +1 + UNREVIEWED 공고 자동 재평가 트리거.
 * ============================================================ */
function CompanyGuidelineCard() {
  const liveMode = window.API && window.API.LIVE_MODE;
  const [current, setCurrent] = useState(null);  // {content_md, version, updated_at}
  const [loading, setLoading] = useState(liveMode);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [expandedVersion, setExpandedVersion] = useState(null);
  const toast = useToast();

  useEffect(() => {
    if (!liveMode) { setLoading(false); return; }
    let cancelled = false;
    window.API.getGuideline()
      .then(g => { if (!cancelled) setCurrent(g); })
      .catch(e => toast(`지침 로드 실패: ${e.message}`, 'error'))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [liveMode]);

  const refreshHistory = () => {
    if (!liveMode) return;
    setHistoryLoading(true);
    window.API.getGuidelineHistory()
      .then(rows => setHistory(rows))
      .catch(e => toast(`히스토리 로드 실패: ${e.message}`, 'error'))
      .finally(() => setHistoryLoading(false));
  };

  const handleEdit = () => {
    setDraft(current ? current.content_md : '');
    setEditing(true);
  };
  const handleCancel = () => {
    setDraft('');
    setEditing(false);
  };
  const handleSave = () => {
    if (!liveMode) {
      toast('mock 모드 — LIVE 모드에서만 저장됩니다', 'warn');
      return;
    }
    if (draft.trim() === (current ? current.content_md : '').trim()) {
      toast('변경된 내용이 없습니다', 'info');
      setEditing(false);
      return;
    }
    setSaving(true);
    window.API.putGuideline(draft)
      .then(g => {
        setCurrent(g);
        setEditing(false);
        setDraft('');
        toast(`지침 저장 (v${g.version}) — 미검토 공고 자동 재평가 시작`, 'success');
        if (historyOpen) refreshHistory();
      })
      .catch(e => toast(`저장 실패: ${e.message}`, 'error'))
      .finally(() => setSaving(false));
  };

  const toggleHistory = () => {
    const next = !historyOpen;
    setHistoryOpen(next);
    if (next && history.length === 0) refreshHistory();
  };

  const fmtTs = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const kst = new Date(d.getTime() + 9 * 3600 * 1000);
    const pad = n => String(n).padStart(2, '0');
    return `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())} ${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}`;
  };

  const isEmpty = !loading && (!current || !(current.content_md || '').trim());

  return (
    <div className="card flush" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>회사 지침 <b>· AI 적합도 평가</b></h3>
        <span style={{ fontSize: 13, color: 'var(--steel)' }}>
          {current != null
            ? <>현재 <code>v{current.version}</code> · {fmtTs(current.updated_at)} KST</>
            : (loading ? '로딩…' : '미설정')}
        </span>
      </div>
      <div style={{ padding: '0 16px 12px 16px' }}>
        <div style={{ fontSize: 12, color: 'var(--steel)', marginBottom: 8, lineHeight: 1.55 }}>
          회사 소개 + 진행하고 싶은 지원사업의 방향성을 적으세요. 저장하면 새로 수집되는
          공고와 <strong>아직 검토하지 않은</strong> 공고들의 적합도(0~100%)를 자동 재평가합니다.
          검토를 시작한 공고의 historical 점수는 보존됩니다. 저장할 때마다 새 version
          으로 append 되며 과거 버전은 아래 '히스토리' 에서 다시 볼 수 있습니다.
        </div>

        {/* 현재 지침: 보기 모드 ↔ 편집 모드 토글 */}
        {!editing ? (
          <>
            <div className="guideline-view"
                 style={{
                   minHeight: 60, maxHeight: 320, overflowY: 'auto',
                   padding: '10px 12px',
                   background: isEmpty ? '#fafafa' : 'var(--surface, #f8fafc)',
                   border: '1px solid var(--border, #cbd5e1)', borderRadius: 6,
                   fontFamily: 'inherit', fontSize: 13, lineHeight: 1.6,
                   whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                   color: isEmpty ? 'var(--steel)' : 'var(--ink)',
                 }}>
              {loading
                ? '로딩 중…'
                : (isEmpty
                    ? '(회사 지침 미설정 — 수정 버튼을 눌러 작성하세요)'
                    : current.content_md)}
            </div>
            <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <Button size="sm" onClick={toggleHistory} disabled={!liveMode}>
                {historyOpen ? '히스토리 접기 ▲' : `히스토리 보기 ▼${history.length ? ` (${history.length})` : ''}`}
              </Button>
              <Button variant="primary" size="sm" onClick={handleEdit} disabled={loading || !liveMode}>
                {isEmpty ? '＋ 지침 작성' : '✎ 수정'}
              </Button>
            </div>
          </>
        ) : (
          <>
            <textarea
              className="guideline-textarea"
              rows={10}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={saving}
              placeholder={"예) 우리 회사는 AI 기반 의료 진단 솔루션을 개발하는 시리즈 A 스타트업입니다.\n주력 분야: 영상 진단, 디지털 헬스케어, FDA/MFDS 인허가 지원.\n관심 사업: R&D 자금, 임상시험 비용 매칭, 글로벌 진출 지원."}
              style={{
                width: '100%',
                padding: '10px 12px',
                border: '1px solid var(--coral, #ff5a4e)',
                borderRadius: 6,
                fontFamily: 'inherit', fontSize: 13, lineHeight: 1.6,
                resize: 'vertical', boxSizing: 'border-box',
              }}
            />
            <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button size="sm" onClick={handleCancel} disabled={saving}>취소</Button>
              <Button variant="primary" size="sm" onClick={handleSave} disabled={saving}>
                {saving ? '저장 중…' : '저장 (새 버전 + 재평가 트리거)'}
              </Button>
            </div>
          </>
        )}

        {/* 히스토리 섹션 */}
        {historyOpen && (
          <div className="guideline-history"
               style={{ marginTop: 12, borderTop: '1px solid var(--border, #cbd5e1)', paddingTop: 12 }}>
            <div style={{ fontSize: 12, color: 'var(--steel)', marginBottom: 8 }}>
              {historyLoading ? '로딩 중…' : `총 ${history.length}개 버전`}
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 360, overflowY: 'auto' }}>
              {history.map(h => {
                const isCurrent = current && h.version === current.version;
                const isExpanded = expandedVersion === h.version;
                const preview = (h.content_md || '').slice(0, 80).replace(/\n/g, ' ');
                return (
                  <li key={h.id}
                      style={{
                        borderLeft: isCurrent ? '3px solid var(--coral, #ff5a4e)' : '3px solid var(--border, #cbd5e1)',
                        padding: '6px 10px', marginBottom: 6,
                        background: isCurrent ? '#fff5f4' : 'var(--surface, #f8fafc)',
                        borderRadius: 4,
                      }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
                         onClick={() => setExpandedVersion(isExpanded ? null : h.version)}>
                      <code style={{ fontSize: 12, fontWeight: 600 }}>v{h.version}</code>
                      {isCurrent && <span style={{ fontSize: 10, padding: '1px 6px', background: 'var(--coral)', color: 'white', borderRadius: 999 }}>현재</span>}
                      <span style={{ fontSize: 11, color: 'var(--steel)' }}>{fmtTs(h.updated_at)} KST</span>
                      <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--steel)' }}>{isExpanded ? '▲' : '▼'}</span>
                    </div>
                    {isExpanded ? (
                      <pre style={{
                        marginTop: 8, padding: '8px 10px',
                        background: 'white', border: '1px solid var(--border)', borderRadius: 4,
                        fontFamily: 'inherit', fontSize: 12, lineHeight: 1.55,
                        whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 240, overflowY: 'auto',
                      }}>{h.content_md || '(빈 지침)'}</pre>
                    ) : (
                      <div style={{ fontSize: 11, color: 'var(--steel)', marginTop: 4 }}>
                        {preview}{(h.content_md || '').length > 80 ? '…' : ''}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { KeywordsTab, CompanyGuidelineCard });
