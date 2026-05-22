/* ============================================================
 * Health Monitor Tab + System Logs Tab
 * ============================================================ */

function HealthMonitorTab({ runs }) {
  const stats = useMemo(() => {
    const out = {};
    for (const site of ['BIZINFO', 'IRIS', 'SBA']) {
      const siteRuns = runs.filter(r => r.source_site === site);
      const last30 = siteRuns.slice(-30);
      const okCount = last30.filter(r => r.status === 'OK').length;
      const failCount = last30.filter(r => r.status === 'FAIL').length;
      const warnCount = last30.filter(r => r.status === 'WARN').length;
      const okRuns = last30.filter(r => r.status === 'OK' && r.duration_ms);
      const avgMs = okRuns.length ? Math.round(okRuns.reduce((a, r) => a + r.duration_ms, 0) / okRuns.length) : 0;
      const totalNew = last30.reduce((a, r) => a + (r.new_records || 0), 0);
      out[site] = { last30, okCount, failCount, warnCount, avgMs, totalNew };
    }
    return out;
  }, [runs]);

  const recent = useMemo(() =>
    [...runs].sort((a, b) => new Date(b.started_at) - new Date(a.started_at)).slice(0, 18),
    [runs]
  );

  return (
    <div>
      <SectionHead
        title="헬스 모니터"
        sub="사이트별 최근 30일 수집 이력 — 평균 소요 · 실패율 · 신규 적재량"
      />
      <div className="runs-grid">
        {['BIZINFO', 'IRIS', 'SBA'].map(site => {
          const s = stats[site];
          const failRate = s.last30.length ? Math.round((s.failCount / s.last30.length) * 100) : 0;
          return (
            <div key={site} className="run-stat-card">
              <h4>{SITE_FULL[site]} · 최근 {s.last30.length}회</h4>
              <div className="kpi-row">
                <div className="kpi">
                  <div className="k">정상 / 주의 / 실패</div>
                  <div className="v">
                    <span className="green">{s.okCount}</span>
                    <span className="sep">/</span>
                    <span className="yellow">{s.warnCount}</span>
                    <span className="sep">/</span>
                    <span className="red">{s.failCount}</span>
                  </div>
                  <div className="sub">실패율 {failRate}%</div>
                </div>
                <div className="kpi">
                  <div className="k">평균 소요 (OK)</div>
                  <div className="v">{(s.avgMs / 1000).toFixed(1)}<span style={{ fontSize: 13, fontWeight: 500, color: 'var(--steel)', letterSpacing: 0, marginLeft: 2 }}>초</span></div>
                  <div className="sub">신규 누적 {s.totalNew}건</div>
                </div>
              </div>
              <div className="timeline" title="좌→우 = 30일 전 → 오늘">
                {s.last30.map(r => (
                  <div
                    key={r.id}
                    className={`timeline-cell ${r.status === 'WARN' ? 'warn' : r.status === 'FAIL' ? 'fail' : ''}`}
                    data-tip={`${r.started_at.slice(0,10)} · ${r.status} · 신규 ${r.new_records}`}
                  />
                ))}
              </div>
              <div className="timeline-axis">
                <span>−30D</span><span>오늘</span>
              </div>
            </div>
          );
        })}
      </div>

      <SectionHead title="최근 수집 실행 이력" sub="최근 18회 · 시간 역순" />
      <div className="recent-runs">
        <table>
          <thead>
            <tr>
              <th style={{ width: 160 }}>시작 시각</th>
              <th style={{ width: 100 }}>사이트</th>
              <th style={{ width: 90 }}>상태</th>
              <th style={{ width: 110 }}>트리거</th>
              <th style={{ width: 150 }}>신규 / 갱신 / 페이지</th>
              <th style={{ width: 90 }}>소요</th>
              <th>비고</th>
            </tr>
          </thead>
          <tbody>
            {recent.map(r => (
              <tr key={r.id}>
                <td className="log-ts">{MOCK.fmtDateTime(r.started_at)}</td>
                <td><SiteBadge site={r.source_site} /></td>
                <td><RunStatusBadge value={r.status} /></td>
                <td style={{ fontSize: 12, color: 'var(--steel)' }}>
                  {r.trigger_kind === 'MANUAL' ? '👤 수동' : '🕓 자동'}
                  <span style={{ color: 'var(--muted)', marginLeft: 4 }}>· {r.triggered_by}</span>
                </td>
                <td>{r.new_records} / {r.updated_records} / {r.pages_visited}</td>
                <td>{(r.duration_ms / 1000).toFixed(1)}초</td>
                <td style={{ fontSize: 12.5 }}>
                  {r.error_message
                    ? <span style={{ color: 'var(--coral)' }}>{r.error_message}</span>
                    : r.early_break_reason
                      ? <code>{r.early_break_reason}</code>
                      : <span style={{ color: 'var(--muted)' }}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ============================================================
 * Tab 5 · System Logs
 * ============================================================ */
function LogsTab({ logs }) {
  const [level, setLevel] = useState('ALL');
  const [category, setCategory] = useState('ALL');
  const [site, setSite] = useState('ALL');

  const rows = useMemo(() => logs.filter(l =>
    (level === 'ALL' || l.level === level) &&
    (category === 'ALL' || l.category === category) &&
    (site === 'ALL' || l.source_site === site)
  ), [logs, level, category, site]);

  return (
    <div>
      <SectionHead
        title="시스템 로그"
        sub="파싱 · 스크래퍼 · 백필 · API 이벤트 — 시간 역순"
      />
      <Toolbar>
        <Toolbar.Label>레벨</Toolbar.Label>
        <ChipGroup
          value={level}
          onChange={setLevel}
          options={[
            { value: 'ALL', label: '전체' },
            { value: 'INFO', label: 'INFO' },
            { value: 'WARN', label: 'WARN' },
            { value: 'ERROR', label: 'ERROR' },
          ]}
        />
        <Toolbar.Divider />
        <Toolbar.Label>카테고리</Toolbar.Label>
        <SelectInput value={category} onChange={setCategory} style={{ height: 36, padding: '6px 32px 6px 14px', fontSize: 13 }}>
          <option value="ALL">전체</option>
          <option value="SCRAPER">SCRAPER</option>
          <option value="PARSE_PERIOD">PARSE_PERIOD</option>
          <option value="URL_TRUNCATED">URL_TRUNCATED</option>
          <option value="BACKFILL">BACKFILL</option>
          <option value="API">API</option>
        </SelectInput>
        <Toolbar.Divider />
        <Toolbar.Label>사이트</Toolbar.Label>
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
        <Toolbar.Spacer />
        <Toolbar.Count n={rows.length} suffix="건" />
      </Toolbar>

      <div className="data-table">
        {rows.length === 0 ? (
          <div className="empty-state">
            <div className="icon">📜</div>
            <div className="head">조건에 맞는 로그가 없습니다</div>
          </div>
        ) : (
          <table className="log-table">
            <thead>
              <tr>
                <th style={{ width: 160 }}>시각</th>
                <th style={{ width: 80 }}>레벨</th>
                <th style={{ width: 150 }}>카테고리</th>
                <th style={{ width: 110 }}>사이트</th>
                <th>메시지</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(l => (
                <tr key={l.id}>
                  <td className="log-ts">{MOCK.fmtDateTime(l.created_at)}</td>
                  <td><span className={`log-level ${l.level}`}>{l.level}</span></td>
                  <td><span className="log-cat">{l.category}</span></td>
                  <td>{l.source_site ? <SiteBadge site={l.source_site} /> : <span style={{ color: 'var(--muted)' }}>—</span>}</td>
                  <td>
                    <div className="log-message">{l.message}</div>
                    {l.payload && Object.keys(l.payload).length > 0 && (
                      <div className="log-payload">{JSON.stringify(l.payload)}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { HealthMonitorTab, LogsTab });
