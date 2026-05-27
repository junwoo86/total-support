/* ============================================================
 * Health Panel — always visible at top of every tab
 * Design System v2: flat white card + accent strip + black pill CTA
 * ============================================================ */

function HealthPanel({ runs, onTriggerRun, runningSites, runningCounters }) {
  const latestPerSite = useMemo(() => {
    const out = {};
    for (const r of runs) {
      const cur = out[r.source_site];
      if (!cur || new Date(r.started_at) > new Date(cur.started_at)) out[r.source_site] = r;
    }
    return out;
  }, [runs]);

  const lastOkPerSite = useMemo(() => {
    const out = {};
    for (const r of runs) {
      if (r.status !== 'OK') continue;
      const cur = out[r.source_site];
      if (!cur || new Date(r.started_at) > new Date(cur.started_at)) out[r.source_site] = r;
    }
    return out;
  }, [runs]);

  // stale 계산은 LIVE 면 실시간 기준, MOCK 이면 시드 고정 시각 기준.
  const liveMode = window.API && window.API.LIVE_MODE;
  const nowMs = liveMode ? Date.now() : MOCK.TODAY.getTime();
  const staleSites = ['BIZINFO', 'IRIS', 'SBA'].filter(s => {
    const ok = lastOkPerSite[s];
    if (!ok) return true;
    const hrs = (nowMs - new Date(ok.started_at).getTime()) / 3600000;
    return hrs >= 36;
  });

  return (
    <>
      <div className="health-intro">
        <span className="health-intro-icon">📡</span>
        <span>
          세 사이트(<b>기업마당 · IRIS · SBA</b>)에서 <b>마지막 수집 이후 새로 올라온 공고</b>를
          확인해 가져옵니다. 매일 새벽 04:00 자동 실행되며, 아래 버튼으로 지금 즉시 확인할 수도 있습니다.
        </span>
      </div>
      <div className="health-strip">
        {['BIZINFO', 'IRIS', 'SBA'].map(site => (
          <HealthCard
            key={site}
            site={site}
            latest={latestPerSite[site]}
            lastOk={lastOkPerSite[site]}
            running={runningSites.includes(site)}
            elapsed={runningCounters[site] || 0}
            nowMs={nowMs}
            onTrigger={() => onTriggerRun(site)}
          />
        ))}
      </div>
      {staleSites.length > 0 && (
        <div className="stale-banner">
          <span>⚠</span>
          <div>
            <b>{staleSites.map(s => SITE_LABEL[s]).join(', ')}</b>
            {staleSites.length === 1 ? ' 사이트가' : ' 사이트들이'} 36시간 이상 정상 수집 기록이 없습니다 — 점검 필요
          </div>
        </div>
      )}
    </>
  );
}

/* nowMs 기준 상대시간 — LIVE 면 실제 now, MOCK 이면 시드 TODAY 기준
 * (mockdata.relTime 은 시나리오 앵커 로직이라 LIVE 부정확 → 자체 계산). */
function relTimeFrom(iso, nowMs) {
  if (!iso) return '—';
  const v = Math.max(0, (nowMs - new Date(iso).getTime()) / 1000);
  if (v < 60) return '방금 전';
  if (v < 3600) return `${Math.floor(v / 60)}분 전`;
  if (v < 86400) return `${Math.floor(v / 3600)}시간 전`;
  return `${Math.floor(v / 86400)}일 전`;
}

function HealthCard({ site, latest, lastOk, running: runningProp, elapsed, nowMs, onTrigger }) {
  // 서버가 보는 latest.status === 'RUNNING'이면 클라이언트 flag 무관하게
  // 버튼/카드 상태를 RUNNING으로 결합한다 (race condition + 다른 사용자 트리거 대응).
  const running = runningProp || (latest && latest.status === 'RUNNING');
  const [flashCls, setFlashCls] = useState('');
  const prevStatus = useRef(latest && latest.status);

  useEffect(() => {
    if (!latest) return;
    if (prevStatus.current && prevStatus.current !== latest.status && !running) {
      const cls = latest.status === 'OK' ? 'flash-ok' : latest.status === 'WARN' ? 'flash-warn' : 'flash-fail';
      setFlashCls(cls);
      const t = setTimeout(() => setFlashCls(''), 1000);
      return () => clearTimeout(t);
    }
    prevStatus.current = latest && latest.status;
  }, [latest && latest.status, running]);

  const status = running ? 'RUNNING' : (latest ? latest.status : 'OK');
  // 버튼 카운터(클라이언트 elapsed)가 없고 서버 RUNNING만 있는 경우엔
  // started_at으로 경과 시간 계산
  const elapsedDisp = elapsed || (
    running && latest && latest.started_at
      ? Math.max(0, Math.floor((Date.now() - new Date(latest.started_at).getTime()) / 1000))
      : 0
  );
  const cardCls =
    status === 'WARN' ? 'warn' :
    status === 'FAIL' ? 'fail' :
    status === 'RUNNING' ? 'running' : '';

  // "최근 확인" = 마지막 시도 시각 (성공/실패 무관). 상대시간 + 절대시각 툴팁.
  const checkedRel = latest ? relTimeFrom(latest.started_at, nowMs) : '아직 없음';
  const checkedAbs = latest ? MOCK.fmtDateTime(latest.started_at) : '';

  // "지난 결과" — 신규 공고 유무를 한국어로 의미부여.
  let resultText = '아직 수집한 적 없음';
  let resultTone = 'neutral';   // neutral | good | warn | fail
  let resultTitle = '';
  if (running) {
    if (latest && latest.status === 'RUNNING' && (latest.pages_visited || latest.new_records)) {
      resultText = `확인 중… 새 공고 ${latest.new_records || 0}건 (페이지 ${latest.pages_visited || 0})`;
    } else {
      resultText = '새 공고 확인 중…';
    }
  } else if (latest) {
    if (latest.status === 'OK') {
      const n = latest.new_records || 0;
      if (n > 0) {
        resultText = `새 공고 ${n}건 수집됨`;
        resultTone = 'good';
      } else {
        resultText = '새 공고 없음 (최신 상태)';
        resultTone = 'neutral';
      }
      resultTitle = `신규 ${n}건 · 갱신 ${latest.updated_records || 0}건 · 소요 ${(latest.duration_ms / 1000).toFixed(1)}초`;
    } else if (latest.status === 'WARN') {
      resultText = latest.error_message || '일부 공고 파싱 경고';
      resultTone = 'warn';
    } else if (latest.status === 'FAIL') {
      resultText = latest.error_message || '수집 실패 — 점검 필요';
      resultTone = 'fail';
    }
  }
  const resultColor =
    resultTone === 'fail' ? 'var(--coral)' :
    resultTone === 'warn' ? 'var(--warning-text)' :
    resultTone === 'good' ? 'var(--success-text, #15803d)' : 'var(--ink)';

  return (
    <div className={`health-card ${cardCls}`}>
      <div className="health-card-top">
        <div className="health-card-site">
          {SITE_FULL[site]}
          <span className="site-sub">{SITE_SUB[site]}</span>
        </div>
        <RunStatusBadge value={status} />
      </div>
      <div className="health-card-meta">
        <span className="k">최근 확인</span>
        <span className="v" title={checkedAbs}>{checkedRel}</span>
        <span className="k">지난 결과</span>
        <span className="v" style={{ color: resultColor }} title={resultTitle}>{resultText}</span>
      </div>
      <div className="run-bar">
        <span className="last-run">{latest ? `마지막 시도 ${MOCK.fmtDateTime(latest.started_at)}` : '\u00A0'}</span>
        <button
          className={`run-btn ${running ? 'running' : ''} ${flashCls}`}
          disabled={running}
          onClick={onTrigger}
          title={running
            ? `이미 확인 중 (${elapsedDisp}s 경과)`
            : '마지막 수집 이후 새로 올라온 공고를 지금 확인합니다'}
        >
          {running ? <>● 확인 중… ({elapsedDisp}s)</> : <>🔄 새 공고 확인</>}
        </button>
      </div>
    </div>
  );
}

Object.assign(window, { HealthPanel });
