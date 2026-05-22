/* ============================================================
 * App · root state + tab routing + mutations
 * ============================================================ */

function App() {
  // ----- Core state -----
  // LIVE 모드면 실제 API에서 로드, 아니면 mock 시드 사용.
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

  // ----- LIVE mode bootstrap: 백엔드에서 초기 데이터 일괄 로드 -----
  useEffect(() => {
    if (!liveMode) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await window.API.loadAll();
        if (cancelled) return;
        setPostings(data.postings);
        setDomains(data.domains);
        setKeywords(data.keywords);
        setRuns(data.runs);
        setLogs(data.logs);
        setKeywordVersion(data.keywordVersion);
        setBootstrapped(true);
        toast(`LIVE 모드 — ${data.postings.length}건 공고, ${data.domains.length} 분야 로드됨`, 'success');
      } catch (e) {
        toast(`LIVE 부트스트랩 실패: ${e.message}`, 'error');
      }
    })();
    return () => { cancelled = true; };
  }, [liveMode]);

  // running timer
  useEffect(() => {
    if (runningSites.length === 0) return;
    const t = setInterval(() => {
      setRunningCounters(c => {
        const next = { ...c };
        for (const s of runningSites) next[s] = (next[s] || 0) + 1;
        return next;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [runningSites]);

  // counts for tab badges
  const counts = useMemo(() => ({
    unreviewed: postings.filter(p => p.review_status === 'UNREVIEWED').length,
    status:     postings.filter(p => p.review_status !== 'UNREVIEWED').length,
    logs:       logs.length,
  }), [postings, logs]);

  // ===== Mutations =====
  const handleChangeReview = (id, newStatus) => {
    const p = postings.find(x => x.id === id);
    if (!p || p.review_status === newStatus) return;
    const willLeave = (tab === 'unreviewed' && newStatus !== 'UNREVIEWED');

    const apply = () => {
      setPostings(ps => ps.map(x => x.id === id
        ? { ...x, review_status: newStatus, last_updated_at: new Date().toISOString() }
        : x));
    };
    if (willLeave) {
      setRemovingIds(rids => [...rids, id]);
      setTimeout(() => { apply(); setRemovingIds(rids => rids.filter(x => x !== id)); }, 320);
    } else {
      apply();
    }

    // LIVE: 실 PATCH 호출 (실패 시 롤백)
    if (liveMode) {
      window.API.patchReviewStatus(id, newStatus).catch(e => {
        toast(`상태 변경 실패 — 롤백: ${e.message}`, 'error');
        setPostings(ps => ps.map(x => x.id === id ? { ...x, review_status: p.review_status } : x));
      });
    }

    setLogs(L => [{
      id: Date.now(), created_at: new Date().toISOString(), level: 'INFO',
      category: 'API', source_site: null, posting_id: id,
      message: `PATCH /api/grant/postings/${id}/review-status → ${newStatus}`,
      payload: { from: p.review_status, to: newStatus },
    }, ...L]);
    toast(`"${p.title.slice(0, 22)}…" → ${REVIEW_LABEL[newStatus]}`, 'success');
  };

  const handleChangeReviewBulk = (ids, newStatus) => {
    if (!ids || !ids.length) return;
    const targets = postings.filter(p => ids.includes(p.id) && p.review_status !== newStatus);
    if (!targets.length) { toast('변경할 항목이 없습니다 (이미 같은 상태)', 'warn'); return; }

    const fadeIds = (tab === 'unreviewed' && newStatus !== 'UNREVIEWED')
      ? targets.map(t => t.id)
      : (tab === 'status' ? targets.map(t => t.id) : []);

    const apply = () => {
      const now = new Date().toISOString();
      setPostings(ps => ps.map(p =>
        targets.find(t => t.id === p.id)
          ? { ...p, review_status: newStatus, last_updated_at: now }
          : p
      ));
    };

    if (fadeIds.length > 0) {
      setRemovingIds(rids => [...rids, ...fadeIds]);
      setTimeout(() => {
        apply();
        setRemovingIds(rids => rids.filter(x => !fadeIds.includes(x)));
      }, 320);
    } else apply();

    // G3 · LIVE: 병렬 PATCH (실패한 id는 롤백 토스트)
    if (liveMode) {
      Promise.allSettled(
        targets.map(t => window.API.patchReviewStatus(t.id, newStatus))
      ).then(results => {
        const failed = results.filter(r => r.status === 'rejected');
        if (failed.length) {
          toast(`${failed.length}건 일괄 변경 실패 — 새로고침 권장`, 'error');
        }
      });
    }

    setLogs(L => [{
      id: Date.now(), created_at: new Date().toISOString(), level: 'INFO',
      category: 'API', source_site: null, posting_id: null,
      message: `BULK PATCH /api/grant/postings (×${targets.length}) → ${newStatus}`,
      payload: { count: targets.length, to: newStatus, ids: targets.map(t => t.id) },
    }, ...L]);
    toast(`${targets.length}건 → ${REVIEW_LABEL[newStatus]} 일괄 변경됨`, 'success');
  };

  // ===== G2 · LIVE 모드 detail 모달 — content_html 보강 =====
  const handleOpenDetail = (p) => {
    if (!liveMode) { setDetail(p); return; }
    // 1차로 list item을 일단 보여주고 content_html은 백그라운드 로드
    setDetail(p);
    window.API.getPostingDetail(p.id)
      .then(full => setDetail(d => d && d.id === full.id ? { ...d, ...full } : d))
      .catch(e => toast(`상세 로드 실패: ${e.message}`, 'error'));
  };

  // ===== G6 · LIVE 모드 헬스 패널 폴링 =====
  // RUNNING 중인 사이트가 있으면 5초, 없으면 30초.
  // RUNNING run row의 progress 필드(pages_visited/new_records)는 base.py가
  // 매 페이지 후 incremental update하므로, 같은 id라도 새 값으로 교체해야 한다.
  const hasRunning = runningSites.length > 0;
  useEffect(() => {
    if (!liveMode) return;
    const interval = hasRunning ? 5000 : 30000;
    const t = setInterval(() => {
      window.API.getHealth()
        .then(h => {
          const newRuns = h.cards.map(c => c.latest_run).filter(Boolean);
          if (newRuns.length === 0) return;
          setRuns(prev => {
            const map = new Map(prev.map(r => [r.id, r]));
            let changed = false;
            for (const r of newRuns) {
              const existing = map.get(r.id);
              if (!existing) {
                map.set(r.id, r); changed = true;
              } else if (
                existing.status !== r.status ||
                existing.pages_visited !== r.pages_visited ||
                existing.new_records !== r.new_records ||
                existing.finished_at !== r.finished_at
              ) {
                // RUNNING 중인 run의 progress 필드 변경 → 교체
                map.set(r.id, r); changed = true;
              }
            }
            return changed ? Array.from(map.values()) : prev;
          });
        })
        .catch(() => { /* 일시적 오류는 무시 */ });
    }, interval);
    return () => clearInterval(t);
  }, [liveMode, hasRunning]);

  // ----- Manual run trigger -----
  const handleTriggerRun = (site) => {
    if (runningSites.includes(site)) return;
    setRunningSites(s => [...s, site]);
    setRunningCounters(c => ({ ...c, [site]: 0 }));
    // LIVE 모드는 서버 응답 확인 후 toast (워커 없으면 503 → 부정확한 정보 방지)
    if (!liveMode) toast(`${SITE_LABEL[site]} 수집을 시작했습니다`, 'info');

    // LIVE: 실 POST 호출 후 폴링으로 헬스 갱신
    if (liveMode) {
      window.API.triggerRun(site)
        .then(res => {
          toast(`${SITE_LABEL[site]} 수집 시작 — job ${res.job_id.slice(0, 8)}`, 'info');
          // 2초마다 health 폴링하여 status 변화 감지
          const poll = setInterval(async () => {
            try {
              const h = await window.API.getHealth();
              const card = h.cards.find(c => c.source_site === site);
              if (card && card.status !== 'RUNNING') {
                clearInterval(poll);
                setRuns(rs => [...rs, card.latest_run].filter(Boolean));
                setRunningSites(s => s.filter(x => x !== site));
                setRunningCounters(c => { const n = { ...c }; delete n[site]; return n; });
                toast(`${SITE_LABEL[site]} → ${card.status}`, card.status === 'OK' ? 'success' : card.status === 'WARN' ? 'warn' : 'error');
              }
            } catch (e) { /* keep polling */ }
          }, 2000);
          // 안전 상한: 3분
          setTimeout(() => clearInterval(poll), 180000);
        })
        .catch(e => {
          toast(`수집 트리거 실패: ${e.message}`, 'error');
          setRunningSites(s => s.filter(x => x !== site));
          setRunningCounters(c => { const n = { ...c }; delete n[site]; return n; });
        });
      return;
    }

    const duration = 6000 + Math.floor(Math.random() * 4000);
    setTimeout(() => {
      const roll = Math.random();
      let status = 'OK', err = null;
      let newRec = 1 + Math.floor(Math.random() * 4);
      let upd = Math.floor(Math.random() * 3);
      let pages = 2 + Math.floor(Math.random() * 2);
      let earlyBreak = newRec === 0 ? 'ZERO_NEW_PAGE' : null;

      if (roll < 0.08) {
        status = 'FAIL'; err = 'HTTP 503 (Service Unavailable)';
        newRec = 0; upd = 0; pages = 0; earlyBreak = 'ERROR';
      } else if (roll < 0.18) {
        status = 'WARN'; err = '일부 행 파싱 예외 (1건)';
      }

      const newRun = {
        id: Date.now(),
        source_site: site,
        started_at: new Date(Date.now() - duration).toISOString(),
        finished_at: new Date().toISOString(),
        status, trigger_kind: 'MANUAL', triggered_by: 'me@company.kr',
        pages_visited: pages, new_records: newRec, updated_records: upd,
        early_break_reason: earlyBreak, error_message: err, duration_ms: duration,
      };
      setRuns(rs => [...rs, newRun]);
      setRunningSites(s => s.filter(x => x !== site));
      setRunningCounters(c => { const n = { ...c }; delete n[site]; return n; });

      setLogs(L => [{
        id: Date.now() + 1, created_at: new Date().toISOString(),
        level: status === 'OK' ? 'INFO' : status === 'WARN' ? 'WARN' : 'ERROR',
        category: 'SCRAPER', source_site: site, posting_id: null,
        message: status === 'OK'
          ? `${SITE_LABEL[site]} 수동 수집 완료 — 신규 ${newRec}건, 갱신 ${upd}건`
          : `${SITE_LABEL[site]} 수동 수집 ${status} — ${err || ''}`,
        payload: { trigger: 'MANUAL', duration_ms: duration },
      }, ...L]);

      toast(
        status === 'OK'  ? `${SITE_LABEL[site]} 수집 완료 — 신규 ${newRec}건` :
        status === 'WARN' ? `${SITE_LABEL[site]} 일부 예외 발생` :
                            `${SITE_LABEL[site]} 수집 실패`,
        status === 'OK' ? 'success' : status === 'WARN' ? 'warn' : 'error',
      );
    }, duration);
  };

  // ----- Domain / Keyword CRUD + version bump -----
  const bumpKeywordVersion = (label) => {
    const next = keywordVersion + 1;
    setKeywordVersion(next);
    const target = postings.filter(p => p.screened_with_version < next).length;
    setLogs(L => [{
      id: Date.now(), created_at: new Date().toISOString(), level: 'INFO',
      category: 'BACKFILL', source_site: null, posting_id: null,
      message: `keyword_version v${keywordVersion} → v${next} (${label}) — 백필 대기 ${target}건`,
      payload: { from: keywordVersion, to: next, target },
    }, ...L]);
    if (target > 0) toast(`재스캔 대기: ${target}건 (백그라운드 진행 중)`, 'info');
  };

  const handleDomainCreate = (payload) => {
    if (domains.find(d => d.code === payload.code)) {
      toast(`코드 "${payload.code}"가 이미 존재합니다`, 'error');
      return;
    }
    if (liveMode) {
      window.API.createDomain(payload)
        .then(created => {
          setDomains(d => [...d, created]);
          bumpKeywordVersion(`분야 추가: ${payload.label_ko}`);
          toast(`분야 "${payload.label_ko}" 추가됨`, 'success');
        })
        .catch(e => toast(`분야 추가 실패: ${e.message}`, 'error'));
      return;
    }
    const id = Math.max(0, ...domains.map(d => d.id)) + 1;
    setDomains(d => [...d, { id, ...payload, enabled: true, created_at: new Date().toISOString() }]);
    bumpKeywordVersion(`분야 추가: ${payload.label_ko}`);
    toast(`분야 "${payload.label_ko}" 추가됨`, 'success');
  };
  const handleDomainUpdate = (id, payload) => {
    if (liveMode) {
      window.API.patchDomain(id, payload)
        .then(updated => {
          setDomains(ds => ds.map(d => d.id === id ? updated : d));
          bumpKeywordVersion(`분야 편집: ${payload.label_ko}`);
          toast(`분야 "${payload.label_ko}" 수정됨`, 'success');
        })
        .catch(e => toast(`분야 수정 실패: ${e.message}`, 'error'));
      return;
    }
    setDomains(ds => ds.map(d => d.id === id ? { ...d, ...payload } : d));
    bumpKeywordVersion(`분야 편집: ${payload.label_ko}`);
    toast(`분야 "${payload.label_ko}" 수정됨`, 'success');
  };
  const handleDomainSoftDelete = (id) => {
    const d = domains.find(x => x.id === id);
    if (liveMode) {
      const next = !d.enabled;
      // 백엔드 DELETE는 soft delete(enabled=false)만, 활성화는 PATCH
      const op = next ? window.API.patchDomain(id, { enabled: true }) : window.API.deleteDomain(id, false);
      op
        .then(() => {
          setDomains(ds => ds.map(x => x.id === id ? { ...x, enabled: next } : x));
          bumpKeywordVersion(`분야 ${d.enabled ? '비활성화' : '활성화'}: ${d.label_ko}`);
          toast(`"${d.label_ko}" ${d.enabled ? '비활성화' : '활성화'}됨`, 'info');
        })
        .catch(e => toast(`상태 변경 실패: ${e.message}`, 'error'));
      return;
    }
    setDomains(ds => ds.map(x => x.id === id ? { ...x, enabled: !x.enabled } : x));
    bumpKeywordVersion(`분야 ${d.enabled ? '비활성화' : '활성화'}: ${d.label_ko}`);
    toast(`"${d.label_ko}" ${d.enabled ? '비활성화' : '활성화'}됨`, 'info');
  };
  const handleDomainHardDelete = (id) => {
    const d = domains.find(x => x.id === id);
    if (liveMode) {
      window.API.deleteDomain(id, true)
        .then(() => {
          setDomains(ds => ds.filter(x => x.id !== id));
          setKeywords(ks => ks.filter(k => k.domain_id !== id));
          bumpKeywordVersion(`분야 영구삭제 (CASCADE): ${d.label_ko}`);
          toast(`"${d.label_ko}" 영구 삭제 — 자식 키워드 CASCADE`, 'warn');
        })
        .catch(e => toast(`영구 삭제 실패: ${e.message}`, 'error'));
      return;
    }
    setDomains(ds => ds.filter(x => x.id !== id));
    setKeywords(ks => ks.filter(k => k.domain_id !== id));
    bumpKeywordVersion(`분야 영구삭제 (CASCADE): ${d.label_ko}`);
    toast(`"${d.label_ko}" 영구 삭제 — 자식 키워드 CASCADE`, 'warn');
  };

  const handleKeywordCreate = (payload) => {
    if (liveMode) {
      window.API.createKeyword(payload.domain_id, payload)
        .then(created => {
          setKeywords(ks => [...ks, created]);
          bumpKeywordVersion(`키워드 추가: ${payload.keyword}`);
          toast(`키워드 "${payload.keyword}" 추가됨`, 'success');
        })
        .catch(e => toast(`키워드 추가 실패: ${e.message}`, 'error'));
      return;
    }
    const id = Math.max(0, ...keywords.map(k => k.id)) + 1;
    setKeywords(ks => [...ks, { id, ...payload }]);
    bumpKeywordVersion(`키워드 추가: ${payload.keyword}`);
    toast(`키워드 "${payload.keyword}" 추가됨`, 'success');
  };
  const handleKeywordUpdate = (id, payload) => {
    const existing = keywords.find(k => k.id === id);
    if (liveMode && existing) {
      window.API.patchKeyword(existing.domain_id, id, payload)
        .then(updated => {
          setKeywords(ks => ks.map(k => k.id === id ? updated : k));
          bumpKeywordVersion(`키워드 편집: ${payload.keyword}`);
          toast(`키워드 "${payload.keyword}" 수정됨`, 'success');
        })
        .catch(e => toast(`키워드 수정 실패: ${e.message}`, 'error'));
      return;
    }
    setKeywords(ks => ks.map(k => k.id === id ? { ...k, ...payload } : k));
    bumpKeywordVersion(`키워드 편집: ${payload.keyword}`);
    toast(`키워드 "${payload.keyword}" 수정됨`, 'success');
  };
  const handleKeywordDelete = (id) => {
    const k = keywords.find(x => x.id === id);
    if (liveMode && k) {
      window.API.deleteKeyword(k.domain_id, id)
        .then(() => {
          setKeywords(ks => ks.filter(x => x.id !== id));
          bumpKeywordVersion(`키워드 삭제: ${k.keyword}`);
          toast(`키워드 "${k.keyword}" 삭제됨`, 'info');
        })
        .catch(e => toast(`키워드 삭제 실패: ${e.message}`, 'error'));
      return;
    }
    setKeywords(ks => ks.filter(x => x.id !== id));
    bumpKeywordVersion(`키워드 삭제: ${k && k.keyword}`);
    toast(`키워드 "${k && k.keyword}" 삭제됨`, 'info');
  };
  const handleKeywordToggle = (id) => {
    const k = keywords.find(x => x.id === id);
    if (liveMode && k) {
      window.API.patchKeyword(k.domain_id, id, { enabled: !k.enabled })
        .then(updated => {
          setKeywords(ks => ks.map(x => x.id === id ? updated : x));
          bumpKeywordVersion(`키워드 ${k.enabled ? '비활성화' : '활성화'}: ${k.keyword}`);
        })
        .catch(e => toast(`토글 실패: ${e.message}`, 'error'));
      return;
    }
    setKeywords(ks => ks.map(x => x.id === id ? { ...x, enabled: !x.enabled } : x));
    bumpKeywordVersion(`키워드 ${k.enabled ? '비활성화' : '활성화'}: ${k.keyword}`);
  };

  // ===== Render =====
  return (
    <div className="app">
      {/* Promo banner — black strip at the very top */}
      <div className="promo-banner">
        <span className="dot" />
        <span>매일 새벽 <code>04:00 KST</code> 자동 수집 · 기업마당 · IRIS · SBA</span>
        <span style={{ opacity: 0.6 }}>·</span>
        <span style={{ opacity: 0.85 }}>PRD v9.0 · Engineering-Ready</span>
      </div>

      {/* Top nav */}
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
        {/* Health panel — always visible */}
        <HealthPanel
          runs={runs}
          onTriggerRun={handleTriggerRun}
          runningSites={runningSites}
          runningCounters={runningCounters}
        />

        {/* Tabs */}
        <nav className="tab-nav">
          <button className={`tab-btn ${tab === 'unreviewed' ? 'active' : ''}`} onClick={() => setTab('unreviewed')}>
            신규 미검토 <span className="count-pill">{counts.unreviewed}</span>
          </button>
          <button className={`tab-btn ${tab === 'status' ? 'active' : ''}`} onClick={() => setTab('status')}>
            상태별 모니터링 <span className="count-pill">{counts.status}</span>
          </button>
          <button className={`tab-btn ${tab === 'health' ? 'active' : ''}`} onClick={() => setTab('health')}>
            헬스 모니터
          </button>
          <button className={`tab-btn ${tab === 'keywords' ? 'active' : ''}`} onClick={() => setTab('keywords')}>
            분야 · 키워드 관리
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
              onChangeReview={handleChangeReview}
              onChangeReviewBulk={handleChangeReviewBulk}
              onOpenDetail={handleOpenDetail}
              removingIds={removingIds}
            />
          )}
          {tab === 'status' && (
            <StatusTab
              postings={postings}
              domains={domains}
              onChangeReview={handleChangeReview}
              onChangeReviewBulk={handleChangeReviewBulk}
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
              onDomainCreate={handleDomainCreate}
              onDomainUpdate={handleDomainUpdate}
              onDomainSoftDelete={handleDomainSoftDelete}
              onDomainHardDelete={handleDomainHardDelete}
              onKeywordCreate={handleKeywordCreate}
              onKeywordUpdate={handleKeywordUpdate}
              onKeywordDelete={handleKeywordDelete}
              onKeywordToggle={handleKeywordToggle}
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
