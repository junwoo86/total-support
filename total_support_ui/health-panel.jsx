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
      <div className="health-strip">
        {['BIZINFO', 'IRIS', 'SBA'].map(site => (
          <HealthCard
            key={site}
            site={site}
            latest={latestPerSite[site]}
            lastOk={lastOkPerSite[site]}
            running={runningSites.includes(site)}
            elapsed={runningCounters[site] || 0}
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

function HealthCard({ site, latest, lastOk, running: runningProp, elapsed, onTrigger }) {
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

  let resultText = '—';
  let okText = '—';
  if (lastOk) okText = MOCK.fmtDateTime(lastOk.finished_at || lastOk.started_at);
  if (running) {
    // LIVE 모드: 30초 헬스 폴링이 가져온 latest_run에서 page/new 누적을 노출.
    // base.py가 매 페이지 후 incremental update하므로 분 단위로 갱신됨.
    if (latest && latest.status === 'RUNNING' && (latest.pages_visited || latest.new_records)) {
      resultText = `진행 중 — 페이지 ${latest.pages_visited || 0} · 신규 ${latest.new_records || 0}건`;
    } else {
      resultText = '수집 진행 중...';
    }
  } else if (latest) {
    if (latest.status === 'OK') {
      resultText = `신규 ${latest.new_records}건 · 갱신 ${latest.updated_records}건 · 소요 ${(latest.duration_ms / 1000).toFixed(1)}초`;
    } else if (latest.status === 'WARN') {
      resultText = latest.error_message || '일부 행 파싱 예외';
    } else if (latest.status === 'FAIL') {
      resultText = latest.error_message || '수집 실패';
    }
  }

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
        <span className="k">마지막 OK</span><span className="v">{okText}</span>
        <span className="k">최근 결과</span><span className="v" style={{ color: status === 'FAIL' ? 'var(--coral)' : status === 'WARN' ? 'var(--warning-text)' : 'var(--ink)' }}>{resultText}</span>
      </div>
      <div className="run-bar">
        <span className="last-run">{latest ? `마지막 시도 ${MOCK.fmtDateTime(latest.started_at)}` : '\u00A0'}</span>
        <button
          className={`run-btn ${running ? 'running' : ''} ${flashCls}`}
          disabled={running}
          onClick={onTrigger}
          title={running ? `이미 수집 중 (${elapsedDisp}s 경과)` : '지금 즉시 수집'}
        >
          {running ? <>● 수집 중... ({elapsedDisp}s)</> : <>▶ 지금 실행</>}
        </button>
      </div>
    </div>
  );
}

Object.assign(window, { HealthPanel });
