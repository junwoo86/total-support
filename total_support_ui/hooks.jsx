/* ============================================================
 * hooks.jsx — App에서 분리한 상태 mutation/effect 훅 모음
 *
 * UMD/Babel-standalone 환경이라 ES module 대신 글로벌 스코프에 노출.
 * 각 훅은 호출자가 보유한 state setter · liveMode · toast 를 인자로 받는다.
 * App 안에 인라인되어 있던 로직과 동작은 1:1 동일. (순수 추출, 행동 변화 없음)
 * ============================================================ */

/* -- 0. 서버 페이지네이션 · 필터·정렬 백엔드 위임 ---------------
 * 매 탭(UnreviewedTab, StatusTab) 가 자체 인스턴스 보유.
 * filters 변경 시 page=1 reload, loadMore 시 다음 200건 누적.
 * 정렬은 항상 백엔드(`relevance_score DESC NULLS LAST`)가 처리하므로
 * 상위 200건이 가장 적합한 행임이 보장된다.
 * Mock 모드(non-LIVE) 에선 외부에서 들어온 mockItems 를 사용. */
const PAGE_FETCH_SIZE = 200;

function usePaginatedPostings({ liveMode, initialFilters, mockItems = [] }) {
  const [filters, setFiltersState] = useState(initialFilters || {});
  const [items, setItems] = useState(liveMode ? [] : mockItems);
  const [total, setTotal] = useState(liveMode ? 0 : mockItems.length);
  const [pagesLoaded, setPagesLoaded] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // 필터 직렬화 키 (deps 트리거용)
  const filtersKey = JSON.stringify(filters);

  // 페이지 1 reload (필터 변경 시)
  useEffect(() => {
    if (!liveMode) {
      setItems(mockItems);
      setTotal(mockItems.length);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    window.API.fetchPostings({ ...filters, page: 1, page_size: PAGE_FETCH_SIZE })
      .then(res => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
        setPagesLoaded(1);
      })
      .catch(e => !cancelled && setError(e))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveMode, filtersKey]);

  const setFilters = (patch) => setFiltersState(prev => ({ ...prev, ...patch }));

  const loadMore = () => {
    if (!liveMode || loading || items.length >= total) return;
    setLoading(true);
    const nextPage = pagesLoaded + 1;
    window.API.fetchPostings({ ...filters, page: nextPage, page_size: PAGE_FETCH_SIZE })
      .then(res => {
        setItems(prev => [...prev, ...res.items]);
        setTotal(res.total);
        setPagesLoaded(nextPage);
      })
      .catch(e => setError(e))
      .finally(() => setLoading(false));
  };

  // PATCH 후 외부에서 호출 — 한 row만 인라인 업데이트.
  // 필터에 안 맞는 새 상태가 되면 list 에서 제거 (status 필터의 경우).
  const upsertItem = (id, partial) => {
    setItems(prev => prev.map(p => p.id === id ? { ...p, ...partial } : p));
  };
  const removeItem = (id) => {
    setItems(prev => prev.filter(p => p.id !== id));
    setTotal(t => Math.max(0, t - 1));
  };
  const refetch = () => {
    if (!liveMode) return;
    setLoading(true);
    window.API.fetchPostings({ ...filters, page: 1, page_size: PAGE_FETCH_SIZE })
      .then(res => {
        setItems(res.items);
        setTotal(res.total);
        setPagesLoaded(1);
      })
      .catch(e => setError(e))
      .finally(() => setLoading(false));
  };

  return {
    items,
    total,
    loading,
    error,
    filters,
    setFilters,
    loadMore,
    canLoadMore: items.length < total,
    pagesLoaded,
    pageSize: PAGE_FETCH_SIZE,
    upsertItem,
    removeItem,
    refetch,
  };
}

/* -- 0b. 검토 상태별 카운트 — StatusTab 의 탭/칩 카운트에 사용 ----
 * `GET /api/grant/postings/counts` 를 동일 필터 (status 제외) 로 호출.
 * filters / refreshKey 가 바뀌면 재요청 (작업 후 즉시 반영을 위해 refreshKey
 * 카운터 외부에서 증가시킬 수 있게 노출). Mock 모드는 mockPostings 로컬 집계.
 */
function usePostingCounts({ liveMode, filters = {}, refreshKey = 0, mockPostings = [] }) {
  const empty = { UNREVIEWED: 0, NEEDS_REVIEW: 0, IN_PROGRESS: 0, EXCLUDED: 0, EXPIRED: 0 };
  const [counts, setCounts] = useState(empty);
  const filtersKey = JSON.stringify(filters);

  useEffect(() => {
    if (!liveMode) {
      const c = { ...empty };
      for (const p of mockPostings) {
        if (Object.hasOwn(c, p.review_status)) c[p.review_status] += 1;
      }
      setCounts(c);
      return;
    }
    let cancelled = false;
    window.API.getPostingCounts(filters)
      .then(res => { if (!cancelled) setCounts({ ...empty, ...res }); })
      .catch(() => { /* 카운트는 비치명적 — 실패 시 기존값 유지 */ });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveMode, filtersKey, refreshKey, mockPostings.length]);

  return counts;
}

/* -- 0c. 적합도 미평가 건 재평가 (수동 버튼 + 프로그레스바) ----
 * 대상: UNREVIEWED + 미만료 + (relevance_score NULL OR evaluation_failed).
 * - count: 버튼 옆 "미평가 N건" (마운트 시 fetch).
 * - 트리거 후 백엔드 진행 상태(status)를 2초 간격 폴링 → progress 갱신.
 *   진행률 = processed/total. running=false + finished 면 완료 → 목록 refetch.
 *   (count 감소 폴링은 실패 건이 또 NULL 이라 부정확 — 백엔드 processed 사용.) */
function useEvaluateMissing({ liveMode, toast, onComplete }) {
  const [count, setCount] = useState(0);
  const [progress, setProgress] = useState(null);  // {total, processed, updated, failed} | null
  const [running, setRunning] = useState(false);
  const pollRef = useRef(null);

  const refreshCount = () => {
    if (!liveMode) return;
    window.API.getEvaluateMissingCount()
      .then(r => setCount(r.count))
      .catch(() => {});
  };

  useEffect(() => { refreshCount(); /* eslint-disable-next-line */ }, [liveMode]);
  useEffect(() => () => clearInterval(pollRef.current), []);

  const startPolling = () => {
    clearInterval(pollRef.current);
    let ticks = 0;
    pollRef.current = setInterval(() => {
      ticks += 1;
      window.API.getEvaluateMissingStatus()
        .then(st => {
          setProgress({
            total: st.total, processed: st.processed,
            updated: st.updated, failed: st.failed,
          });
          if (!st.running) {
            clearInterval(pollRef.current);
            setRunning(false);
            refreshCount();
            if (st.total > 0) {
              toast(
                `재평가 완료 — ${st.updated}건 평가, ${st.failed}건 실패`,
                st.failed > 0 ? 'warn' : 'success',
              );
            }
            onComplete && onComplete();
            // 잠시 후 진행바 숨김
            setTimeout(() => setProgress(null), 4000);
          } else if (ticks > 600) {  // 최대 20분(2s*600) 안전장치
            clearInterval(pollRef.current);
            setRunning(false);
          }
        })
        .catch(() => {});
    }, 2000);
  };

  const trigger = () => {
    if (!liveMode) return;
    window.API.triggerEvaluateMissing()
      .then(res => {
        if (!res.started) {
          toast(res.reason || '재평가를 시작할 수 없습니다', 'warn');
          refreshCount();
          return;
        }
        setRunning(true);
        setProgress({ total: res.target_count, processed: 0, updated: 0, failed: 0 });
        toast(`${res.target_count}건 재평가 시작`, 'success');
        startPolling();
      })
      .catch(e => toast(`재평가 트리거 실패: ${e.message}`, 'error'));
  };

  return { count, running, progress, trigger, refreshCount };
}

/* -- 1. LIVE 모드 초기 부트스트랩 ----------------------------- */
function useLiveBootstrap({
  liveMode,
  setPostings, setDomains, setKeywords, setRuns, setLogs,
  setKeywordVersion, setBootstrapped,
  toast,
}) {
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
        toast(
          `LIVE 모드 — ${data.postings.length}건 공고, ${data.domains.length} 분야 로드됨`,
          'success',
        );
      } catch (e) {
        toast(`LIVE 부트스트랩 실패: ${e.message}`, 'error');
      }
    })();
    return () => { cancelled = true; };
  }, [liveMode]);
}

/* -- 2. 공고 검토상태 단건/일괄 변경 -------------------------- */
function usePostingReview({
  postings, setPostings, setLogs, setRemovingIds,
  tab, liveMode, toast,
  paginatedHooks = [],
}) {
  // 두 탭의 hook items 합쳐서 찾기 (LIVE) — id 로 lookup.
  const findRow = (id) => {
    for (const h of paginatedHooks) {
      const found = h.items && h.items.find(x => x.id === id);
      if (found) return found;
    }
    return postings.find(x => x.id === id);
  };

  // 행 한 건이 새 status 로 바뀔 때, 각 hook 에서 보일지 안 보일지 판단해 해당 hook
  // items 에서 제거/유지/삽입을 결정. 가장 단순한 정책: 새 status 가 hook 의 status
  // 필터와 매치하면 inline update, 아니면 hook 에서 제거.
  // (status 필터는 단일 string · 다중 string[] · 미지정 셋 모두 지원.)
  const statusMatches = (wantedStatus, newStatus) => {
    if (!wantedStatus) return true;
    if (Array.isArray(wantedStatus)) {
      return wantedStatus.length === 0 || wantedStatus.includes(newStatus);
    }
    return wantedStatus === newStatus;
  };
  const applyToHooks = (id, newStatus, original) => {
    const oldStatus = original?.review_status;
    for (const h of paginatedHooks) {
      const wantedStatus = h.filters && h.filters.status;
      const wasMatching  = statusMatches(wantedStatus, oldStatus);
      const willMatch    = statusMatches(wantedStatus, newStatus);
      if (willMatch && wasMatching) {
        // 같은 hook 안에 머무름 — in-place update.
        h.upsertItem && h.upsertItem(id, {
          review_status: newStatus,
          last_updated_at: new Date().toISOString(),
        });
      } else if (!willMatch && wasMatching) {
        // 이 hook 에서 빠짐.
        h.removeItem && h.removeItem(id);
      } else if (willMatch && !wasMatching) {
        // 이 hook 으로 새로 들어옴 — partial 만으론 row 못 만드므로 refetch.
        // (정렬·페이지 위치까지 백엔드 기준으로 정확히 맞추는 안전 경로.)
        h.refetch && h.refetch();
      }
      // (!willMatch && !wasMatching) — no-op.
    }
  };

  const handleChangeReview = (id, newStatus) => {
    const p = findRow(id);
    if (!p || p.review_status === newStatus) return;
    const willLeave = (tab === 'unreviewed' && newStatus !== 'UNREVIEWED')
                      || (tab === 'status' && p.review_status !== newStatus);

    const apply = () => {
      setPostings(ps => ps.map(x => x.id === id
        ? { ...x, review_status: newStatus, last_updated_at: new Date().toISOString() }
        : x));
      applyToHooks(id, newStatus, p);
    };
    if (willLeave) {
      setRemovingIds(rids => [...rids, id]);
      setTimeout(() => {
        apply();
        setRemovingIds(rids => rids.filter(x => x !== id));
      }, 320);
    } else {
      apply();
    }

    if (liveMode) {
      window.API.patchReviewStatus(id, newStatus).catch(e => {
        toast(`상태 변경 실패 — 롤백: ${e.message}`, 'error');
        setPostings(ps => ps.map(x =>
          x.id === id ? { ...x, review_status: p.review_status } : x,
        ));
        applyToHooks(id, p.review_status, p);
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
    const allCandidates = ids.map(findRow).filter(Boolean);
    const targets = allCandidates.filter(p => p.review_status !== newStatus);
    if (!targets.length) {
      toast('변경할 항목이 없습니다 (이미 같은 상태)', 'warn');
      return;
    }

    const fadeIds = targets.map(t => t.id);

    const apply = () => {
      const now = new Date().toISOString();
      setPostings(ps => ps.map(p =>
        targets.find(t => t.id === p.id)
          ? { ...p, review_status: newStatus, last_updated_at: now }
          : p
      ));
      for (const t of targets) applyToHooks(t.id, newStatus, t);
    };

    if (fadeIds.length > 0) {
      setRemovingIds(rids => [...rids, ...fadeIds]);
      setTimeout(() => {
        apply();
        setRemovingIds(rids => rids.filter(x => !fadeIds.includes(x)));
      }, 320);
    } else apply();

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

  return { handleChangeReview, handleChangeReviewBulk };
}

/* -- 3. 헬스 패널 폴링 (LIVE) -------------------------------- */
function useHealthPolling({ liveMode, hasRunning, setRuns }) {
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
}

/* -- 4. 수집 트리거 + RUNNING 상태 관리 ----------------------- */
function useRunTrigger({
  liveMode,
  setRuns, setLogs,
  runningSites, setRunningSites, setRunningCounters,
  toast,
}) {
  const handleTriggerRun = (site) => {
    if (runningSites.includes(site)) return;
    setRunningSites(s => [...s, site]);
    setRunningCounters(c => ({ ...c, [site]: 0 }));
    if (!liveMode) toast(`${SITE_LABEL[site]} 수집을 시작했습니다`, 'info');

    if (liveMode) {
      window.API.triggerRun(site)
        .then(res => {
          toast(`${SITE_LABEL[site]} 수집 시작 — job ${res.job_id.slice(0, 8)}`, 'info');
          const poll = setInterval(async () => {
            try {
              const h = await window.API.getHealth();
              const card = h.cards.find(c => c.source_site === site);
              if (card && card.status !== 'RUNNING') {
                clearInterval(poll);
                setRuns(rs => [...rs, card.latest_run].filter(Boolean));
                setRunningSites(s => s.filter(x => x !== site));
                setRunningCounters(c => { const n = { ...c }; delete n[site]; return n; });
                toast(
                  `${SITE_LABEL[site]} → ${card.status}`,
                  card.status === 'OK' ? 'success' : card.status === 'WARN' ? 'warn' : 'error',
                );
              }
            } catch (e) { /* keep polling */ }
          }, 2000);
          setTimeout(() => clearInterval(poll), 180000);
        })
        .catch(e => {
          toast(`수집 트리거 실패: ${e.message}`, 'error');
          setRunningSites(s => s.filter(x => x !== site));
          setRunningCounters(c => { const n = { ...c }; delete n[site]; return n; });
        });
      return;
    }

    // mock 모드: 랜덤 시뮬레이션
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

  return { handleTriggerRun };
}

/* -- 5. RUNNING 카운터 증가 타이머 --------------------------- */
function useRunningTimer(runningSites, setRunningCounters) {
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
}

/* -- 6. 분야/키워드 CRUD (+keyword version bump 부수효과) ----- */
function useDomainKeywordOps({
  liveMode,
  domains, setDomains,
  keywords, setKeywords,
  postings,
  keywordVersion, setKeywordVersion,
  setLogs, toast,
}) {
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

  return {
    handleDomainCreate, handleDomainUpdate,
    handleDomainSoftDelete, handleDomainHardDelete,
    handleKeywordCreate, handleKeywordUpdate,
    handleKeywordDelete, handleKeywordToggle,
  };
}
