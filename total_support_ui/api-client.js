/* ============================================================
 * api-client.js — 실 API 어댑터 (PRD §9)
 *
 * 사용:
 *   ?live=1 쿼리 파라미터가 있으면 실 백엔드 (http://localhost:8000) 사용.
 *   없으면 기존 mockdata.js로 동작 (개발/디자인 확인 모드).
 *
 *   ?api=http://other:9000 으로 base URL override 가능.
 * ============================================================ */

(function (global) {
  const params = new URLSearchParams(global.location.search);

  // 모드 결정 우선순위:
  //   1) ?mock=1 → 강제 MOCK
  //   2) ?live=1 → 강제 LIVE
  //   3) 백엔드와 같은 origin에서 호스팅 (FastAPI StaticFiles `/ui/` 마운트) → 자동 LIVE
  //   4) file:// 또는 다른 정적 호스팅 → MOCK
  const isSameOriginHosted =
    global.location.protocol.startsWith('http') &&
    global.location.pathname.startsWith('/ui');

  const FORCE_MOCK = params.has('mock');
  const FORCE_LIVE = params.has('live');
  const LIVE_MODE = !FORCE_MOCK && (FORCE_LIVE || isSameOriginHosted);

  // base URL: ?api 명시 > 동일 origin(상대 경로) > localhost:8000 fallback
  let API_BASE;
  if (params.get('api')) {
    API_BASE = params.get('api');
  } else if (LIVE_MODE && isSameOriginHosted) {
    API_BASE = global.location.origin; // 동일 origin
  } else {
    API_BASE = 'http://localhost:8000';
  }

  // 백엔드 ↔ 프론트 데이터 모양 정합성 매핑
  // - posting.assigned_fields: 백엔드는 list[str], 프론트는 그대로 list[str] (OK)
  // - posting.first_seen_at / last_updated_at: ISO 문자열 (OK)
  // - collection_runs.started_at / finished_at: ISO 문자열 (OK)
  async function jget(path, qs) {
    const url = new URL(API_BASE + path);
    if (qs) Object.entries(qs).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
    const r = await fetch(url, { headers: { 'Accept': 'application/json' } });
    if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
    return r.json();
  }
  async function jsend(method, path, body) {
    const r = await fetch(API_BASE + path, {
      method,
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`${method} ${path} → ${r.status}: ${txt.slice(0, 200)}`);
    }
    if (r.status === 204) return null;
    return r.json();
  }

  // ----- Public API client -----
  const API = {
    LIVE_MODE,
    API_BASE,

    // ----- 초기 데이터 로드 -----
    async loadAll() {
      const [postingsRes, domains, runs, logs, health] = await Promise.all([
        jget('/api/grant/postings', { page_size: 200 }),
        jget('/api/grant/domains'),
        jget('/api/grant/collection/runs', { days: 30 }),
        jget('/api/grant/logs', { limit: 200 }),
        jget('/api/grant/collection/health'),
      ]);

      // 도메인별 키워드 로드 (병렬)
      const keywordLists = await Promise.all(
        domains.map(d => jget(`/api/grant/domains/${d.id}/keywords`))
      );
      const keywords = keywordLists.flat();
      const keywordVersion = Math.max(0, ...keywords.map(k => k.id)) || 0;

      // 백엔드의 d_day는 헬퍼이므로 mockdata.dDay()와 호환되게 raw 그대로 사용
      return {
        postings: postingsRes.items.map(normalizePosting),
        domains,
        keywords,
        runs,
        logs,
        keywordVersion,
        health,
      };
    },

    // ----- Postings -----
    /** 서버 페이지네이션 + 백엔드 필터·정렬.
     *  opts 예: { status, suitability, site, domain, relevance_bucket, q,
     *           hide_expired, page, page_size }
     *  - 배열 값 (다중 선택 칩) → CSV 로 직렬화 (backend 의 _csv_tuple 와 정합).
     *  - 'ALL' / 'NONE' 같은 단일 모드 pseudo 옵션은 그대로 보냄 (NONE 은 LIKE
     *    '%NONE%' 매치되지 않으므로 결과 0 — 미매칭 의도). */
    async fetchPostings(opts = {}) {
      const params = _serializeFilters(opts);
      const res = await jget('/api/grant/postings', params);
      // {items, total, page, page_size}
      return { ...res, items: res.items.map(normalizePosting) };
    },
    /** GET /postings/counts — { UNREVIEWED, NEEDS_REVIEW, IN_PROGRESS, EXCLUDED }
     *  status 는 보내지 않음 (4개 모두 항상 반환). 나머지 필터는 동일. */
    async getPostingCounts(opts = {}) {
      const { status: _ignored, page: _p, page_size: _ps, ...rest } = opts;
      const params = _serializeFilters(rest);
      return jget('/api/grant/postings/counts', params);
    },
    async patchReviewStatus(id, status) {
      return jsend('PATCH', `/api/grant/postings/${id}/review-status`, { status });
    },
    async getPostingDetail(id) {
      return jget(`/api/grant/postings/${id}/detail`);
    },

    // ----- Domains -----
    async createDomain(payload) {
      return jsend('POST', '/api/grant/domains', payload);
    },
    async patchDomain(id, payload) {
      return jsend('PATCH', `/api/grant/domains/${id}`, payload);
    },
    async deleteDomain(id, hard = false) {
      return jsend('DELETE', `/api/grant/domains/${id}?hard=${hard ? 'true' : 'false'}`);
    },

    // ----- Keywords -----
    async createKeyword(domainId, payload) {
      return jsend('POST', `/api/grant/domains/${domainId}/keywords`, payload);
    },
    async patchKeyword(domainId, kwId, payload) {
      return jsend('PATCH', `/api/grant/domains/${domainId}/keywords/${kwId}`, payload);
    },
    async deleteKeyword(domainId, kwId) {
      return jsend('DELETE', `/api/grant/domains/${domainId}/keywords/${kwId}`);
    },
    async previewKeyword(payload) {
      return jsend('POST', '/api/grant/keywords/preview', payload);
    },

    // ----- Collection -----
    async triggerRun(site) {
      return jsend('POST', '/api/grant/collection/run', { site });
    },
    async getHealth() {
      return jget('/api/grant/collection/health');
    },
    async getRuns(opts = {}) {
      return jget('/api/grant/collection/runs', opts);
    },

    // ----- Logs -----
    async getLogs(opts = {}) {
      return jget('/api/grant/logs', opts);
    },

    // ----- Company guideline (회사 적합도 평가용 시스템 지침) -----
    async getGuideline() {
      return jget('/api/grant/company-guideline');
    },
    async putGuideline(content_md, opts = {}) {
      const reevaluate = opts.reevaluate !== false;  // 기본 true
      return jsend('PUT', '/api/grant/company-guideline', { content_md, reevaluate });
    },
    async getGuidelineHistory() {
      return jget('/api/grant/company-guideline/history');
    },
  };

  // UI 필터 객체 → 쿼리스트링 파라미터.
  // - 배열은 CSV 직렬화 (빈 배열은 파라미터 자체 생략 = 전체).
  // - true → 'true', false/null/'' → 생략.
  // - 'ALL' pseudo 값 → 생략 (단일 모드용).
  function _serializeFilters(opts) {
    const params = {};
    for (const [k, v] of Object.entries(opts)) {
      if (v == null || v === '' || v === false) continue;
      if (v === true) { params[k] = 'true'; continue; }
      if (Array.isArray(v)) {
        if (v.length === 0) continue;
        params[k] = v.join(',');
        continue;
      }
      if (v === 'ALL') continue;
      params[k] = v;
    }
    return params;
  }

  // 백엔드 PostingListItem → 프론트 posting shape으로 (assigned_fields list/string 호환)
  function normalizePosting(p) {
    return {
      ...p,
      // 백엔드는 list, mockdata도 list — 그대로
      assigned_fields: Array.isArray(p.assigned_fields) ? p.assigned_fields : [],
      // detail은 별도 요청
      content_html: null,
      // 사업 상세 요약 — 백엔드 본문 selector 적용 후 title fallback (LLM 요약 X)
      summary: p.title.length > 120 ? p.title.slice(0, 120) + '…' : p.title,
    };
  }

  global.API = API;
  // 사용자 알림
  if (LIVE_MODE) {
    console.info(`%c[total-support] LIVE → ${API_BASE}`, 'color:#0284c7;font-weight:bold');
  } else {
    console.info('%c[total-support] MOCK (URL에 ?live=1 또는 /ui/ 경로로 호스팅 시 자동 LIVE)', 'color:#64748b');
  }
})(window);
