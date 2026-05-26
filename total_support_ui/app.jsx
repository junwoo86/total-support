/* ============================================================
 * App · root state + tab routing + render
 *
 * mutation/effect 로직은 hooks.jsx 의 use* 훅으로 분리됨.
 * 이 파일은 상태 선언, 훅 조립, 렌더링만 담당한다.
 * ============================================================ */

function App() {
  // ----- Core state -----
  const liveMode = window.API && window.API.LIVE_MODE;
  const [postings, setPostings] = useState(liveMode ? [] : MOCK.SEED_POSTINGS);
  const [domains, setDomains]   = useState(liveMode ? [] : MOCK.SEED_DOMAINS);
  const [keywords, setKeywords] = useState(liveMode ? [] : MOCK.SEED_KEYWORDS);
  const [runs, setRuns]         = useState(liveMode ? [] : MOCK.SEED_COLLECTION_RUNS);
  const [logs, setLogs]         = useState(liveMode ? [] : MOCK.SEED_SYSTEM_LOGS);
  const [keywordVersion, setKeywordVersion] = useState(liveMode ? 0 : 18);
  const [bootstrapped, setBootstrapped] = useState(!liveMode);

  const [tab, setTab] = useState('unreviewed');
  const [detail, setDetail] = useState(null);

  const [runningSites, setRunningSites] = useState([]);
  const [runningCounters, setRunningCounters] = useState({});
  const [removingIds, setRemovingIds] = useState([]);

  const toast = useToast();
  const nowLabel = MOCK.fmtDateTime(MOCK.TODAY.toISOString());
  const hasRunning = runningSites.length > 0;

  // ----- Effects & mutations (extracted to hooks.jsx) -----
  useLiveBootstrap({
    liveMode,
    setPostings, setDomains, setKeywords, setRuns, setLogs,
    setKeywordVersion, setBootstrapped, toast,
  });
  useRunningTimer(runningSites, setRunningCounters);
  useHealthPolling({ liveMode, hasRunning, setRuns });

  const review = usePostingReview({
    postings, setPostings, setLogs, setRemovingIds, tab, liveMode, toast,
  });
  const runner = useRunTrigger({
    liveMode, setRuns, setLogs,
    runningSites, setRunningSites, setRunningCounters, toast,
  });
  const ops = useDomainKeywordOps({
    liveMode,
    domains, setDomains,
    keywords, setKeywords,
    postings, keywordVersion, setKeywordVersion,
    setLogs, toast,
  });

  // ----- Tab counts -----
  const counts = useMemo(() => ({
    unreviewed: postings.filter(p => p.review_status === 'UNREVIEWED').length,
    status:     postings.filter(p => p.review_status !== 'UNREVIEWED').length,
    logs:       logs.length,
  }), [postings, logs]);

  // ----- Detail modal (LIVE: content_html 보강 fetch) -----
  const handleOpenDetail = (p) => {
    if (!liveMode) { setDetail(p); return; }
    setDetail(p);
    window.API.getPostingDetail(p.id)
      .then(full => setDetail(d => d && d.id === full.id ? { ...d, ...full } : d))
      .catch(e => toast(`상세 로드 실패: ${e.message}`, 'error'));
  };

  // ===== Render =====
  return (
    <div className="app">
      <div className="promo-banner">
        <span className="dot" />
        <span>매일 새벽 <code>04:00 KST</code> 자동 수집 · 기업마당 · IRIS · SBA</span>
        <span style={{ opacity: 0.6 }}>·</span>
        <span style={{ opacity: 0.85 }}>PRD v9.0 · Engineering-Ready</span>
      </div>

      <header className="top-nav">
        <div className="brand">
          <div className="wordmark">Total Support<span className="dot">.</span></div>
          <div className="tagline">지원사업 통합 수집 및 다중 분야 스크리닝</div>
        </div>
        <div className="nav-meta">
          <span>시나리오 · 2026-05-22 KST</span>
          <span className="now-clock">{nowLabel}</span>
        </div>
      </header>

      <main className="app-main">
        <HealthPanel
          runs={runs}
          onTriggerRun={runner.handleTriggerRun}
          runningSites={runningSites}
          runningCounters={runningCounters}
        />

        <nav className="tab-nav">
          <button className={`tab-btn ${tab === 'unreviewed' ? 'active' : ''}`} onClick={() => setTab('unreviewed')}>
            신규 미검토 <span className="count-pill">{counts.unreviewed}</span>
          </button>
          <button className={`tab-btn ${tab === 'status' ? 'active' : ''}`} onClick={() => setTab('status')}>
            검토 상태별 확인 <span className="count-pill">{counts.status}</span>
          </button>
          <button className={`tab-btn ${tab === 'keywords' ? 'active' : ''}`} onClick={() => setTab('keywords')}>
            분야 · 키워드 관리
          </button>
          <button className={`tab-btn ${tab === 'health' ? 'active' : ''}`} onClick={() => setTab('health')}>
            사이트별 수집 상태
          </button>
          <button className={`tab-btn ${tab === 'logs' ? 'active' : ''}`} onClick={() => setTab('logs')}>
            시스템 로그 <span className="count-pill">{counts.logs}</span>
          </button>
        </nav>

        <div className="tab-body">
          {tab === 'unreviewed' && (
            <UnreviewedTab
              postings={postings}
              domains={domains}
              onChangeReview={review.handleChangeReview}
              onChangeReviewBulk={review.handleChangeReviewBulk}
              onOpenDetail={handleOpenDetail}
              removingIds={removingIds}
            />
          )}
          {tab === 'status' && (
            <StatusTab
              postings={postings}
              domains={domains}
              onChangeReview={review.handleChangeReview}
              onChangeReviewBulk={review.handleChangeReviewBulk}
              onOpenDetail={handleOpenDetail}
              removingIds={removingIds}
            />
          )}
          {tab === 'health' && <HealthMonitorTab runs={runs} />}
          {tab === 'keywords' && (
            <KeywordsTab
              domains={domains}
              keywords={keywords}
              postings={postings}
              onDomainCreate={ops.handleDomainCreate}
              onDomainUpdate={ops.handleDomainUpdate}
              onDomainSoftDelete={ops.handleDomainSoftDelete}
              onDomainHardDelete={ops.handleDomainHardDelete}
              onKeywordCreate={ops.handleKeywordCreate}
              onKeywordUpdate={ops.handleKeywordUpdate}
              onKeywordDelete={ops.handleKeywordDelete}
              onKeywordToggle={ops.handleKeywordToggle}
              keywordVersion={keywordVersion}
            />
          )}
          {tab === 'logs' && <LogsTab logs={logs} />}
        </div>
      </main>

      <PostingDetailModal
        posting={detail}
        domains={domains}
        open={!!detail}
        onClose={() => setDetail(null)}
      />
    </div>
  );
}

function Root() {
  return (
    <ToastProvider>
      <App />
    </ToastProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<Root />);
