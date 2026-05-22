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
                  <span className="mode">{k.match_mode}</span>
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
            <option value="WORD_BOUNDARY">WORD_BOUNDARY — 영문 단축어 (\b...\b)</option>
            <option value="EXACT_HANGUL">EXACT_HANGUL — 한글 단어</option>
            <option value="SUBSTRING">SUBSTRING — 부분 매칭</option>
            <option value="REGEX">REGEX — 사용자 지정</option>
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

Object.assign(window, { KeywordsTab });
