/* ==========================================================
 * Mock Data — simulates tb_grant_* tables per PRD §4
 * Today = 2026-05-22 (Asia/Seoul)
 * ========================================================== */

// "Today" anchor for D-Day calculations (PRD scenario date)
const TODAY = new Date('2026-05-22T09:00:00+09:00');

function todayKST() { return TODAY; }
function dateOnly(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}
function dDay(endDateStr) {
  if (!endDateStr) return null;
  const end = dateOnly(new Date(endDateStr + 'T00:00:00+09:00'));
  const today = dateOnly(TODAY);
  return Math.round((end - today) / 86400000);
}
function fmtDateShort(s) {
  if (!s) return '';
  return s.slice(5).replace('-', '-');
}
function fmtDateTime(iso) {
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function relTime(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  // anchor to scenario "today" so labels feel real
  const anchored = (TODAY.getTime() - new Date(iso).getTime()) / 1000;
  const v = Math.max(diff, anchored);
  if (v < 60) return '방금 전';
  if (v < 3600) return `${Math.floor(v / 60)}분 전`;
  if (v < 86400) return `${Math.floor(v / 3600)}시간 전`;
  return `${Math.floor(v / 86400)}일 전`;
}

/* ----- Domains (tb_grant_domains) ----- */
// Domain colors aligned with Design System v2 category palette
const SEED_DOMAINS = [
  { id: 1, code: 'AI',         label_ko: 'AI',       color: '#2563eb', display_order: 1, enabled: true },
  { id: 2, code: 'BIO',        label_ko: '바이오',    color: '#7c3aed', display_order: 2, enabled: true },
  { id: 3, code: 'HEALTHCARE', label_ko: '헬스케어',  color: '#ff5a4e', display_order: 3, enabled: true },
  { id: 4, code: 'WELLNESS',   label_ko: '웰니스',    color: '#e83e8c', display_order: 4, enabled: true },
  { id: 5, code: 'ESG',        label_ko: 'ESG',      color: '#06b6d4', display_order: 5, enabled: false },
];

/* ----- Keywords (tb_grant_keywords) ----- */
const SEED_KEYWORDS = [
  // AI
  { id: 1, domain_id: 1, keyword: 'AI',                match_mode: 'WORD_BOUNDARY', case_sensitive: false, negative_context: ['SAIPA','AICPA','SAI'], enabled: true },
  { id: 2, domain_id: 1, keyword: '인공지능',          match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 3, domain_id: 1, keyword: '머신러닝',          match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 4, domain_id: 1, keyword: '딥러닝',            match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 5, domain_id: 1, keyword: 'Machine Learning',  match_mode: 'SUBSTRING',     case_sensitive: false, negative_context: [], enabled: true },
  { id: 6, domain_id: 1, keyword: 'Deep Learning',     match_mode: 'SUBSTRING',     case_sensitive: false, negative_context: [], enabled: true },
  // BIO
  { id: 7,  domain_id: 2, keyword: '바이오',           match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 8,  domain_id: 2, keyword: '생명공학',         match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 9,  domain_id: 2, keyword: 'Bio',              match_mode: 'WORD_BOUNDARY', case_sensitive: false, negative_context: ['Biography','Biology'], enabled: true },
  { id: 10, domain_id: 2, keyword: 'Biotech',          match_mode: 'WORD_BOUNDARY', case_sensitive: false, negative_context: [], enabled: true },
  // HEALTHCARE
  { id: 11, domain_id: 3, keyword: '헬스케어',         match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 12, domain_id: 3, keyword: '의료',             match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: ['의료보험 가입 의무','의료비 공제'], enabled: true },
  { id: 13, domain_id: 3, keyword: '디지털헬스',       match_mode: 'SUBSTRING',     case_sensitive: false, negative_context: [], enabled: true },
  { id: 14, domain_id: 3, keyword: 'Healthcare',       match_mode: 'SUBSTRING',     case_sensitive: false, negative_context: [], enabled: true },
  { id: 15, domain_id: 3, keyword: 'Medical',          match_mode: 'WORD_BOUNDARY', case_sensitive: false, negative_context: [], enabled: true },
  // WELLNESS
  { id: 16, domain_id: 4, keyword: '웰니스',           match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 17, domain_id: 4, keyword: '건강증진',         match_mode: 'EXACT_HANGUL',  case_sensitive: false, negative_context: [], enabled: true },
  { id: 18, domain_id: 4, keyword: 'Wellness',         match_mode: 'SUBSTRING',     case_sensitive: false, negative_context: [], enabled: true },
];

/* ----- Postings (tb_grant_postings) ----- */
// Mix of sites, statuses, suitabilities, D-Days (incl. NULL end_date)
const SEED_POSTINGS = [
  {
    id: 101, source_site: 'IRIS', source_id: '021878',
    title: '2026년도 바이오분야 인공지능 진단 모델 고도화 국책 과제 공고',
    detail_url: 'https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do',
    summary: '지정 공모 과제로 다중 생체 데이터를 결합한 인공지능 진단 알고리즘 모델 개발 시 과제당 연간 5억 원 이내 연구비 지원 (총 3년). 임상 데이터 기반 딥러닝 모델 학습 및 검증 인프라 구축비 포함.',
    raw_period: '2026-05-15 ~ 2026-05-29',
    start_date: '2026-05-15', end_date: '2026-05-29',
    posting_status: 'ONGOING',
    assigned_fields: ['AI', '헬스케어', '바이오'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-15T04:02:33+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>바이오·헬스 분야의 다중 생체 데이터(EHR, 영상, 유전체)를 결합한 <b>인공지능 진단 알고리즘</b>을 고도화하고, 임상 1·2상 단계까지 적용 가능한 검증 인프라를 구축하는 국책 R&amp;D 과제입니다.</p><h4>지원 규모</h4><ul><li>과제당 연간 5억 원 이내</li><li>총 연구기간 3년 (단계 평가 후 연장)</li><li>총 12개 과제 내외 선정</li></ul><h4>신청 자격</h4><p>국내 의료기관·바이오 기업과 컨소시엄을 구성한 대학 또는 정부출연연. 머신러닝 모델 학습용 임상 데이터 사용권 확보 필수.</p>`
  },
  {
    id: 102, source_site: 'SBA', source_id: '91b23d38-5953-f111-b404-d4f5ef4a1e33',
    title: '서울시 맞춤형 스마트 웰니스 서비스 디바이스 실증 지원',
    detail_url: 'https://www.sba.seoul.kr/Pages/BusinessApply/PostingDetail.aspx?p=0&mid=91b23d38-5953-f111-b404-d4f5ef4a1e33',
    summary: '웰니스/스마트 헬스케어 하드웨어 또는 소프트웨어를 개발 완료한 서울 소재 중소기업 대상 실증 인프라 매칭. 서울시민 100명 규모 베타 테스트 비용 + 인증 컨설팅 지원.',
    raw_period: '2026-05-18 ~ 2026-05-25',
    start_date: '2026-05-18', end_date: '2026-05-25',
    posting_status: 'ONGOING',
    assigned_fields: ['웰니스', '헬스케어'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-18T04:05:21+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>웰니스·스마트 헬스케어 디바이스(웨어러블, 환경 센서, 디지털 코칭 앱 등)를 보유한 서울 소재 중소기업의 시장 진입을 지원합니다.</p><h4>지원 내용</h4><ul><li>서울시민 100명 규모 베타 사용자 모집·운영비</li><li>제품 인증(KC, FDA, CE) 사전 컨설팅</li><li>실증 결과 보고서 작성 지원</li></ul>`
  },
  {
    id: 103, source_site: 'BIZINFO', source_id: 'PBLN_000000000122322',
    title: '충청북도 바이오 스타트업 글로벌 실증 임상시험 지원',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122322',
    summary: '해외 임상 1상/2상 진입을 준비 중인 바이오 의약품 및 의료기기 제조 7년 미만 창업기업 대상 글로벌 컨설팅 및 인증 비용 지원. IND 신청 자문 포함.',
    raw_period: '2026.05.20 ~ 2026.06.15',
    start_date: '2026-05-20', end_date: '2026-06-15',
    posting_status: 'ONGOING',
    assigned_fields: ['바이오'],
    ai_suitability: 'HIGH',
    review_status: 'IN_PROGRESS',
    screened_with_version: 18,
    first_seen_at: '2026-05-20T04:01:09+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>창업 7년 미만 바이오 의약품·의료기기 기업의 해외 임상시험 및 인증 진입을 지원합니다.</p><h4>주요 지원 항목</h4><ul><li>해외 임상 IND 자문 (최대 3,000만 원)</li><li>FDA/EMA 사전 미팅 컨설팅</li><li>국제 인증(GLP, GMP) 심사 비용 50% 매칭</li></ul>`
  },
  {
    id: 104, source_site: 'BIZINFO', source_id: 'PBLN_000000000122401',
    title: '상시 모집 — 웰니스 시제품 컨설팅 바우처',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122401',
    summary: '건강증진·웰니스 분야 시제품 제작 컨설팅을 상시 신청 받음. 예산 소진 시 마감. 디자인·소재·인증·양산성 4개 트랙으로 패키지 운영.',
    raw_period: '상시모집 (예산 소진 시 마감)',
    start_date: null, end_date: null,
    posting_status: 'ONGOING',
    assigned_fields: ['웰니스'],
    ai_suitability: 'HIGH',
    review_status: 'NEEDS_REVIEW',
    screened_with_version: 18,
    first_seen_at: '2026-04-12T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>웰니스·건강증진 분야 시제품의 디자인·소재·인증·양산성을 4개 트랙으로 컨설팅합니다.</p><p>예산 소진 시까지 상시 접수하며, 트랙별 패키지 단가는 200만~600만 원입니다.</p>`
  },
  {
    id: 105, source_site: 'IRIS', source_id: '021890',
    title: '디지털헬스 분야 의료기기 SaaS 상용화 R&D',
    detail_url: 'https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do',
    summary: '디지털헬스 SaaS 형태의 의료기기 소프트웨어(SaMD) 인허가 및 상용화 단계 지원. CDSS, 영상 분석, 원격 모니터링 등 카테고리별 별도 풀.',
    raw_period: '2026.05.22(금) ~ 06.22(월) 18:00 까지',
    start_date: '2026-05-22', end_date: '2026-06-22',
    posting_status: 'ONGOING',
    assigned_fields: ['헬스케어', 'AI'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-22T04:07:55+09:00',
    last_updated_at: '2026-05-22T04:07:55+09:00',
    content_html: `<h4>사업 개요</h4><p>SaMD(Software as a Medical Device)를 상용화 단계로 이끄는 R&amp;D 지원사업입니다. AI 기반 임상의사결정지원시스템(CDSS), 영상 분석 SaaS, 원격 모니터링 플랫폼이 주요 대상입니다.</p>`
  },
  {
    id: 106, source_site: 'BIZINFO', source_id: 'PBLN_000000000122518',
    title: '2026 K-바이오랩허브 입주 기업 모집 (예정 공고)',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122518',
    summary: '인천 송도 소재 K-바이오랩허브 4기 입주 기업 모집. 본 공고는 6월 5일 정식 게재 예정이며 사전 안내 단계입니다.',
    raw_period: '2026.06.05 ~ 2026.06.30 (예정)',
    start_date: '2026-06-05', end_date: '2026-06-30',
    posting_status: 'SCHEDULED',
    assigned_fields: ['바이오'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-21T04:01:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>K-바이오랩허브 4기 입주 기업 모집 사전 공고입니다.</p><p>모집 대상: 창업 5년 미만 바이오·헬스 분야 기업 / 입주 기간 최대 3년 / 보증금·임차료 50% 감면.</p>`
  },
  {
    id: 107, source_site: 'SBA', source_id: '76a14e22-5b41-e211-a345-c4e5f01234ab',
    title: '서울 인공지능 스타트업 글로벌 진출 패키지 (예정)',
    detail_url: 'https://www.sba.seoul.kr/Pages/BusinessApply/PostingDetail.aspx?p=0&mid=76a14e22-5b41-e211-a345-c4e5f01234ab',
    summary: 'AI·머신러닝 기술 보유 서울 소재 스타트업의 미국·EU 진출 패키지. 현지 법인 설립, IR 피칭, GTM 컨설팅 3종 묶음 지원.',
    raw_period: '2026-06-01 ~ 2026-06-27',
    start_date: '2026-06-01', end_date: '2026-06-27',
    posting_status: 'SCHEDULED',
    assigned_fields: ['AI'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-19T04:02:11+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>AI·머신러닝 보유 서울 스타트업 대상 해외 진출 패키지.</p>`
  },
  {
    id: 108, source_site: 'IRIS', source_id: '021855',
    title: '범부처 전주기 의료기기 연구개발 사업 — 3차 공고',
    detail_url: 'https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do',
    summary: '범부처 전주기 의료기기 사업 3차 공고. 신의료기기, 디지털헬스 의료기기, 첨단 의료기기 3개 트랙으로 운영. 트랙별 5~15억/년.',
    raw_period: '2026-05-08 ~ 2026-06-08',
    start_date: '2026-05-08', end_date: '2026-06-08',
    posting_status: 'ONGOING',
    assigned_fields: ['헬스케어'],
    ai_suitability: 'HIGH',
    review_status: 'NEEDS_REVIEW',
    screened_with_version: 18,
    first_seen_at: '2026-05-08T04:01:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>범부처 전주기 의료기기 연구개발 사업 3차 공고로, 의료기기 카테고리별 3개 트랙(신의료기기/디지털헬스/첨단)으로 분리 운영됩니다.</p>`
  },
  {
    id: 109, source_site: 'BIZINFO', source_id: 'PBLN_000000000122100',
    title: '중소기업 수출 바우처 일반 트랙 (마감 임박)',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122100',
    summary: '중소기업 일반 수출 바우처 신청. 분야 무관 일반 지원 사업으로, 통번역·물류·인증·디자인 등 12개 메뉴 선택 가능.',
    raw_period: '2026.04.20 ~ 2026.05.24',
    start_date: '2026-04-20', end_date: '2026-05-24',
    posting_status: 'ONGOING',
    assigned_fields: [],
    ai_suitability: 'NORMAL',
    review_status: 'EXCLUDED',
    screened_with_version: 18,
    first_seen_at: '2026-04-20T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>중소기업 일반 수출 바우처입니다.</p>`
  },
  {
    id: 110, source_site: 'SBA', source_id: '0e6f12b1-7d22-d111-9904-a3b2c4d5e6f7',
    title: '서울형 청년창업 지원 일반 트랙',
    detail_url: 'https://www.sba.seoul.kr/Pages/BusinessApply/PostingDetail.aspx?p=0&mid=0e6f12b1-7d22-d111-9904-a3b2c4d5e6f7',
    summary: '서울 거주 만 39세 이하 청년 창업자 일반 트랙. 분야 무관, 사업화 자금 최대 5,000만 원 + 멘토링.',
    raw_period: '2026-05-10 ~ 2026-06-10',
    start_date: '2026-05-10', end_date: '2026-06-10',
    posting_status: 'ONGOING',
    assigned_fields: [],
    ai_suitability: 'NORMAL',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-10T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>서울형 청년창업 지원 일반 트랙입니다. 분야 무관.</p>`
  },
  {
    id: 111, source_site: 'IRIS', source_id: '021902',
    title: '바이오 빅데이터 플랫폼 구축 R&D — 머신러닝 분석 모듈',
    detail_url: 'https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do',
    summary: '국가 바이오 빅데이터 플랫폼 위 머신러닝 분석 모듈을 개발할 컨소시엄 모집. 연 7억 원 / 3년.',
    raw_period: '2026-05-22 ~ 2026-06-30',
    start_date: '2026-05-22', end_date: '2026-06-30',
    posting_status: 'ONGOING',
    assigned_fields: ['AI', '바이오'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-22T04:07:55+09:00',
    last_updated_at: '2026-05-22T04:07:55+09:00',
    content_html: `<h4>사업 개요</h4><p>국가 바이오 빅데이터 위에서 동작하는 머신러닝 분석 모듈 개발 R&amp;D.</p>`
  },
  {
    id: 112, source_site: 'BIZINFO', source_id: 'PBLN_000000000122733',
    title: '예산 소진 시까지 — AI 솔루션 도입 비용 매칭',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122733',
    summary: '중소기업이 AI 솔루션을 도입할 때 도입비 50%(최대 3,000만 원) 매칭. 예산 소진 시 마감.',
    raw_period: '예산 소진 시까지',
    start_date: null, end_date: null,
    posting_status: 'ONGOING',
    assigned_fields: ['AI'],
    ai_suitability: 'HIGH',
    review_status: 'NEEDS_REVIEW',
    screened_with_version: 18,
    first_seen_at: '2026-03-04T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>AI 솔루션 도입 비용 매칭 사업으로, 예산 소진 시까지 상시 접수합니다.</p>`
  },
  {
    id: 113, source_site: 'SBA', source_id: 'a9f81c47-3e10-4f22-b701-c91d2e3f4a55',
    title: '강서구 헬스케어 디바이스 제조 기업 시제품 매칭',
    detail_url: 'https://www.sba.seoul.kr/Pages/BusinessApply/PostingDetail.aspx?p=0&mid=a9f81c47-3e10-4f22-b701-c91d2e3f4a55',
    summary: '강서구 소재 의료기기·헬스케어 디바이스 제조 기업 시제품 제작 매칭. 금형비 포함 최대 1,500만 원.',
    raw_period: '2026-05-12 ~ 2026-05-29',
    start_date: '2026-05-12', end_date: '2026-05-29',
    posting_status: 'ONGOING',
    assigned_fields: ['헬스케어'],
    ai_suitability: 'HIGH',
    review_status: 'IN_PROGRESS',
    screened_with_version: 18,
    first_seen_at: '2026-05-12T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>강서구 소재 헬스케어 디바이스 제조 기업 시제품 제작 매칭 사업.</p>`
  },
  {
    id: 114, source_site: 'BIZINFO', source_id: 'PBLN_000000000122809',
    title: '소상공인 일반 경영안정자금 (참고)',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122809',
    summary: '소상공인 일반 경영안정자금. 본 모듈 4대 분야와 무관한 일반 지원으로 자동 매칭 0건.',
    raw_period: '2026-05-01 ~ 2026-12-31',
    start_date: '2026-05-01', end_date: '2026-12-31',
    posting_status: 'ONGOING',
    assigned_fields: [],
    ai_suitability: 'NORMAL',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-01T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>소상공인 일반 경영안정자금입니다.</p>`
  },
  {
    id: 115, source_site: 'IRIS', source_id: '021799',
    title: '의료 인공지능 임상 검증 데이터셋 구축 (지난 공고)',
    detail_url: 'https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do',
    summary: '의료 영상·EHR 데이터의 임상 검증용 데이터셋 구축 사업. 마감 처리된 참고용 공고.',
    raw_period: '2026-04-01 ~ 2026-05-20',
    start_date: '2026-04-01', end_date: '2026-05-20',
    posting_status: 'ONGOING',
    assigned_fields: ['AI', '헬스케어'],
    ai_suitability: 'HIGH',
    review_status: 'EXCLUDED',
    screened_with_version: 18,
    first_seen_at: '2026-04-01T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>의료 영상·EHR 데이터 기반 임상 검증 데이터셋 구축 사업.</p>`
  },
  {
    id: 116, source_site: 'SBA', source_id: 'cc3d11ee-22ab-44ff-99cc-1234567890ab',
    title: '서울 디지털헬스 SaMD 인증 컨설팅',
    detail_url: 'https://www.sba.seoul.kr/Pages/BusinessApply/PostingDetail.aspx?p=0&mid=cc3d11ee-22ab-44ff-99cc-1234567890ab',
    summary: '디지털헬스 의료기기 소프트웨어(SaMD) 인증을 준비하는 서울 소재 기업 컨설팅 패키지.',
    raw_period: '2026-05-17 ~ 2026-06-21',
    start_date: '2026-05-17', end_date: '2026-06-21',
    posting_status: 'ONGOING',
    assigned_fields: ['헬스케어'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-17T04:00:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>디지털헬스 SaMD 인증 컨설팅 패키지로, 식약처 인허가 준비 기업을 대상으로 합니다.</p>`
  },
  {
    id: 117, source_site: 'BIZINFO', source_id: 'PBLN_000000000122900',
    title: '딥러닝 기반 첨단바이오 신약 후보물질 발굴 지원',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122900',
    summary: '딥러닝·생성형 AI를 활용한 신약 후보물질 발굴 R&D. 바이오 + AI 융합 트랙.',
    raw_period: '2026.05.21 ~ 2026.06.25',
    start_date: '2026-05-21', end_date: '2026-06-25',
    posting_status: 'ONGOING',
    assigned_fields: ['AI', '바이오'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-21T04:01:00+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>딥러닝·생성형 AI 기술을 활용한 신약 후보물질 발굴 융합 R&amp;D.</p>`
  },
  {
    id: 118, source_site: 'BIZINFO', source_id: 'PBLN_000000000122912',
    title: '국내 웰니스 관광 융합 콘텐츠 사업화',
    detail_url: 'https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122912',
    summary: '웰니스 관광 콘텐츠 + 디지털 코칭 융합 사업화 지원. 건강증진 프로그램 운영사 대상.',
    raw_period: '2026.05.22 ~ 2026.07.10',
    start_date: '2026-05-22', end_date: '2026-07-10',
    posting_status: 'ONGOING',
    assigned_fields: ['웰니스'],
    ai_suitability: 'HIGH',
    review_status: 'UNREVIEWED',
    screened_with_version: 18,
    first_seen_at: '2026-05-22T04:03:12+09:00',
    last_updated_at: '2026-05-22T04:03:12+09:00',
    content_html: `<h4>사업 개요</h4><p>웰니스 관광 + 디지털 코칭 융합 사업화 지원.</p>`
  },
];

/* ----- Collection runs (tb_grant_collection_runs) ----- */
// Generate 30 days of synthetic history per site
function buildCollectionRuns() {
  const runs = [];
  let id = 1;
  const sites = ['BIZINFO', 'IRIS', 'SBA'];
  // hour offsets per site to mimic staggered schedule
  const startMinute = { BIZINFO: 3, IRIS: 7, SBA: 9 };

  for (let d = 30; d >= 0; d--) {
    const day = new Date(TODAY);
    day.setDate(day.getDate() - d);
    for (const site of sites) {
      // tagged outcomes for "today" so latest matches PRD example
      let status = 'OK';
      let err = null;
      let newRec = Math.floor(Math.random() * 6);
      let upd = Math.floor(Math.random() * 4);
      let pages = 2 + Math.floor(Math.random() * 3);
      let duration = 22000 + Math.floor(Math.random() * 40000);
      let earlyBreak = newRec === 0 ? 'ZERO_NEW_PAGE' : null;

      // make latest mirror PRD: BIZINFO OK, IRIS WARN, SBA FAIL (2 days stale)
      if (d === 0) {
        if (site === 'BIZINFO') { status = 'OK'; newRec = 4; upd = 1; duration = 38120; }
        if (site === 'IRIS')    { status = 'WARN'; newRec = 2; upd = 1; duration = 51400; err = '행 #14 ancmId 추출 실패: pattern mismatch'; }
        if (site === 'SBA')     { status = 'FAIL'; newRec = 0; upd = 0; duration = 60000; err = 'ViewState 만료 후 3회 재시도 실패 (HTTP 500)'; pages = 0; earlyBreak = 'ERROR'; }
      } else if (d === 1 && site === 'SBA') {
        status = 'FAIL'; newRec = 0; upd = 0; duration = 60000;
        err = 'ViewState 만료 후 3회 재시도 실패 (HTTP 500)'; pages = 0; earlyBreak = 'ERROR';
      } else {
        // inject occasional WARN/FAIL
        const roll = Math.random();
        if (roll < 0.05) { status = 'FAIL'; err = 'HTTP 503 (Service Unavailable)'; newRec = 0; upd = 0; pages = 0; earlyBreak = 'ERROR'; }
        else if (roll < 0.12) { status = 'WARN'; err = '일부 행 파싱 실패'; }
      }

      const started = new Date(day);
      started.setHours(4, startMinute[site], 0, 0);
      const finished = status === 'FAIL' ? null : new Date(started.getTime() + duration);
      runs.push({
        id: id++,
        source_site: site,
        started_at: started.toISOString(),
        finished_at: finished ? finished.toISOString() : new Date(started.getTime() + 60000).toISOString(),
        status,
        trigger_kind: 'SCHEDULE',
        triggered_by: 'system',
        pages_visited: pages,
        new_records: newRec,
        updated_records: upd,
        early_break_reason: earlyBreak,
        error_message: err,
        duration_ms: duration,
      });
    }
  }
  return runs;
}

const SEED_COLLECTION_RUNS = buildCollectionRuns();

/* ----- System logs (tb_grant_system_logs) ----- */
const SEED_SYSTEM_LOGS = [
  { id: 1, created_at: '2026-05-22T04:09:01+09:00', level: 'ERROR', category: 'SCRAPER', source_site: 'SBA',
    posting_id: null, message: 'ViewState 만료 후 3회 재시도 실패 — SBA 수집 잡 중단', payload: { retries: 3, http_status: 500, viewstate_len: 0 } },
  { id: 2, created_at: '2026-05-22T04:07:55+09:00', level: 'WARN', category: 'SCRAPER', source_site: 'IRIS',
    posting_id: null, message: '행 #14 ancmId 추출 실패: pattern mismatch — 이번 배치에서 1건 건너뜀', payload: { row_index: 14, raw: 'f_bsnsAncmList…' } },
  { id: 3, created_at: '2026-05-22T04:07:55+09:00', level: 'INFO', category: 'SCRAPER', source_site: 'IRIS',
    posting_id: 105, message: '신규 적재: 디지털헬스 분야 의료기기 SaaS 상용화 R&D', payload: { source_id: '021890' } },
  { id: 4, created_at: '2026-05-22T04:07:55+09:00', level: 'INFO', category: 'SCRAPER', source_site: 'IRIS',
    posting_id: 111, message: '신규 적재: 바이오 빅데이터 플랫폼 구축 R&D', payload: { source_id: '021902' } },
  { id: 5, created_at: '2026-05-22T04:03:18+09:00', level: 'INFO', category: 'BACKFILL', source_site: null,
    posting_id: null, message: '키워드 백필 완료 — 14건 재스캔, 분야 매칭 갱신 3건', payload: { from_version: 17, to_version: 18, scanned: 14, updated: 3 } },
  { id: 6, created_at: '2026-05-22T04:03:12+09:00', level: 'INFO', category: 'SCRAPER', source_site: 'BIZINFO',
    posting_id: 118, message: '신규 적재: 국내 웰니스 관광 융합 콘텐츠 사업화', payload: { source_id: 'PBLN_000000000122912' } },
  { id: 7, created_at: '2026-05-22T04:03:12+09:00', level: 'INFO', category: 'SCRAPER', source_site: 'BIZINFO',
    posting_id: null, message: '연속 페이지 신규 0건 — Early Break (3페이지 순회 후 종료)', payload: { pages_visited: 3 } },
  { id: 8, created_at: '2026-05-22T04:02:55+09:00', level: 'WARN', category: 'URL_TRUNCATED', source_site: 'IRIS',
    posting_id: 108, message: 'detail_url이 950자를 초과하여 trim 처리됨', payload: { original_len: 1024, trimmed_len: 950 } },
  { id: 9, created_at: '2026-05-21T04:09:01+09:00', level: 'ERROR', category: 'SCRAPER', source_site: 'SBA',
    posting_id: null, message: 'ViewState 만료 후 3회 재시도 실패', payload: { retries: 3 } },
  { id: 10, created_at: '2026-05-21T04:07:55+09:00', level: 'INFO', category: 'SCRAPER', source_site: 'IRIS',
    posting_id: null, message: 'IRIS 수집 완료 — 신규 3건, 갱신 1건', payload: {} },
  { id: 11, created_at: '2026-05-20T04:08:43+09:00', level: 'WARN', category: 'PARSE_PERIOD', source_site: 'BIZINFO',
    posting_id: 104, message: 'P6 PARSE_UNKNOWN — 자연어 원문만 보존', payload: { raw: '상시모집 (예산 소진 시 마감)' } },
  { id: 12, created_at: '2026-05-19T04:03:12+09:00', level: 'INFO', category: 'API', source_site: null,
    posting_id: null, message: 'PATCH /api/grant/postings/103/review-status → IN_PROGRESS', payload: { user: 'kim@company.kr' } },
];

window.MOCK = {
  TODAY,
  todayKST, dateOnly, dDay, fmtDateShort, fmtDateTime, relTime,
  SEED_DOMAINS, SEED_KEYWORDS, SEED_POSTINGS, SEED_COLLECTION_RUNS, SEED_SYSTEM_LOGS,
};
