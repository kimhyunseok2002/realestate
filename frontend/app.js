/* =====================================================================
   상권 생존 예측 — 프론트엔드 (v3 · 호갱노노식 지도 우선)
   ===================================================================== */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = `요청 실패 (${r.status})`;
    try { const j = await r.json(); if (j.detail) msg = typeof j.detail === "string" ? j.detail : msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
};

// Lucide-style 인라인 SVG (이모지 대신 — ui-ux-pro-max 권고)
const ICONS = {
  dot: '<svg class="icon" viewBox="0 0 24 24" fill="currentColor" stroke="none"><circle cx="12" cy="12" r="6"/></svg>',
  info: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>',
  arrow: '<svg class="icon" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>',
  spark: '<svg class="icon" viewBox="0 0 24 24"><path d="m12 4 1.4 3.6L17 9l-3.6 1.4L12 14l-1.4-3.6L7 9l3.6-1.4L12 4Z"/></svg>',
  users: '<svg class="icon" viewBox="0 0 24 24"><circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0"/><path d="M16 5.5a3 3 0 0 1 0 5.5"/><path d="M21 20a6 6 0 0 0-4-5.6"/></svg>',
  activity: '<svg class="icon" viewBox="0 0 24 24"><path d="M3 12h4l2.5 6L14 6l2 6h5"/></svg>',
  door: '<svg class="icon" viewBox="0 0 24 24"><path d="M4 21h16"/><path d="M6 21V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17"/><path d="M14 12h.01"/></svg>',
  coins: '<svg class="icon" viewBox="0 0 24 24"><circle cx="8.5" cy="8.5" r="5"/><path d="M15 4.5a5 5 0 0 1 0 9.8"/><path d="M13.5 20a5 5 0 0 0 4-8"/></svg>',
  home: '<svg class="icon" viewBox="0 0 24 24"><path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/></svg>',
  wallet: '<svg class="icon" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h13v4"/><path d="M3 7v10a2 2 0 0 0 2 2h16V9H5"/><path d="M16 13h.01"/></svg>',
  warn: '<svg class="icon" viewBox="0 0 24 24"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  compare: '<svg class="icon" viewBox="0 0 24 24"><path d="M16 3h5v5"/><path d="M8 21H3v-5"/><path d="M21 3l-7.5 7.5"/><path d="M3 21l7.5-7.5"/></svg>',
};

const state = {
  meta: null, map: null,
  bubbleLayer: null, bubbleMarkers: {},
  pinMarker: null, circle: null,
  loc: null, industry: null,
  overview: null, chart: null, lastPred: null,
  reverseSeq: 0, predictSeq: 0,
  scope: "전체", regionOf: {}, ovLabel: "",
  listingsOn: false, listingLayer: null, listingMarkers: {}, listingsGu: null,
  tab: "summary", fitFor: null, _toastT: null,
};

const COLORS = {
  s1: "#3182f6", s2: "#12b886", s1soft: "rgba(49,130,246,0.12)",
  good: "#12b886", warning: "#f08c00", serious: "#f76707", critical: "#e03131",
  ink: "#191f28", muted: "#8b95a1", grid: "#eef1f4",
};
const REDUCE_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* 숫자 카운트업 (토스식) */
function countUp(el, to, decimals = 0, dur = 750) {
  if (REDUCE_MOTION) { el.textContent = to.toFixed(decimals); return; }
  const start = performance.now();
  (function tick(now) {
    const t = Math.min(1, (now - start) / dur);
    const e = 1 - Math.pow(1 - t, 3);           // easeOutCubic
    el.textContent = (to * e).toFixed(decimals);
    if (t < 1) requestAnimationFrame(tick); else el.textContent = to.toFixed(decimals);
  })(start);
}
/* 결과 섹션 스태거 등장 */
function staggerReveal(container) {
  Array.from(container.children).forEach((el, i) => {
    el.classList.remove("reveal"); void el.offsetWidth;
    el.style.animationDelay = REDUCE_MOTION ? "0ms" : `${i * 55}ms`;
    el.classList.add("reveal");
  });
}
/* 지도 클릭 → 결과 영역으로 살짝 스크롤 */
function scrollToResults() {
  const pb = $("panel-body"), rb = $("result-body");
  if (!pb || !rb || rb.classList.contains("hidden")) return;
  const delta = rb.getBoundingClientRect().top - pb.getBoundingClientRect().top;
  pb.scrollTo({ top: pb.scrollTop + delta - 16, behavior: REDUCE_MOTION ? "auto" : "smooth" });
}
function bandFor(pct) {
  if (pct >= 55) return "good";
  if (pct >= 40) return "warning";
  if (pct >= 28) return "serious";
  return "critical";
}
const BAND_KO = { good: "안정적", warning: "평균 수준", serious: "취약", critical: "매우 취약" };
const bandColor = (b) => COLORS[b];
const shortGu = (gu) => gu.replace(/(특별시|광역시|구|시|군)$/, "");
const regionLabel = (gu) => (state.regionOf && state.regionOf[gu]) || "서울";

/* ---------------- init ---------------- */
async function init() {
  try { state.meta = await api("/api/meta"); }
  catch (e) { document.body.insertAdjacentHTML("afterbegin", `<div class="err" style="margin:12px">메타 로드 실패: ${esc(e.message)}</div>`); return; }

  state.regionOf = {};
  state.meta.districts.forEach((d) => { state.regionOf[d.gu] = d.region; });

  buildIndustryChips();
  buildRegionChips();
  initMap();
  // 딥링크(?gu=&industry=&lat=&lon=)가 있으면 그 분석을 복원, 없으면 강남역 데모
  const q = new URLSearchParams(location.search);
  const qi = q.get("industry");
  await selectIndustry(qi && state.meta.industries.some((i) => i.key === qi) ? qi : "카페");
  const qlat = parseFloat(q.get("lat")), qlon = parseFloat(q.get("lon")), qgu = q.get("gu");
  if (isFinite(qlat) && isFinite(qlon)) {
    await setLocation(qlat, qlon, qgu && state.regionOf[qgu]
      ? { gu: qgu, address: `${regionLabel(qgu)} ${qgu}`, skipReverse: true, fly: true, zoom: 14, reveal: true }
      : { fly: true, zoom: 14, reveal: true });
  } else {
    await setLocation(37.4979, 127.0276, { fly: true, zoom: 12 });   // 강남역 데모
  }
}

function buildIndustryChips() {
  const box = $("map-industry-chips");
  box.innerHTML = "";
  state.meta.industries.forEach((it) => {
    const el = document.createElement("button");
    el.type = "button"; el.className = "mchip"; el.textContent = it.label; el.dataset.key = it.key;
    el.onclick = () => selectIndustry(it.key);
    box.appendChild(el);
  });
}
function buildRegionChips() {
  const box = $("region-chips");
  box.innerHTML = "";
  state.meta.districts.forEach((d) => {
    if (state.scope !== "전체" && d.region !== state.scope) return;
    const el = document.createElement("button");
    el.type = "button"; el.className = "mchip"; el.textContent = shortGu(d.gu); el.dataset.gu = d.gu;
    el.setAttribute("aria-label", d.gu);
    el.onclick = () => selectGu(d.gu);
    box.appendChild(el);
  });
  if (state.loc && state.loc.gu) highlightRegionChip(state.loc.gu);
}

/* 지역 범위(전체/서울/경기) 전환 */
function setScope(scope) {
  state.scope = scope;
  document.querySelectorAll("#region-scope .scope-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.scope === scope));
  buildRegionChips();
  if (state.overview) renderBubbles(state.overview, state.ovLabel);
  fitScopeBounds();
}
function fitScopeBounds() {
  const pts = state.meta.districts
    .filter((d) => state.scope === "전체" || d.region === state.scope)
    .map((d) => [d.lat, d.lon]);
  if (!pts.length || !state.map) return;
  state.map.fitBounds(pts, {
    paddingTopLeft: [430, 40], paddingBottomRight: [30, 40],
    maxZoom: 12, animate: !REDUCE_MOTION,
  });
}
function highlightRegionChip(gu) {
  document.querySelectorAll("#region-chips .mchip").forEach((c) =>
    c.classList.toggle("active", c.dataset.gu === gu));
}

async function selectIndustry(key) {
  state.industry = key;
  document.querySelectorAll("#map-industry-chips .mchip").forEach((c) =>
    c.classList.toggle("active", c.dataset.key === key));
  const label = (state.meta.industries.find((i) => i.key === key) || {}).label || key;
  $("ml-title").textContent = `${label} · 3년 생존율`;
  await loadOverview(key);
  if (state.loc) predict();                     // 업종 바꾸면 현재 위치 재분석
}

/* ---------------- map ---------------- */
function initMap() {
  delete L.Icon.Default.prototype._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
    shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  });
  const c = state.meta.default_center;
  const map = L.map("map", { zoomControl: false, minZoom: 10 }).setView([c.lat, c.lon], 11);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  // 톤다운 베이스맵(CARTO Positron) — 데이터 버블이 배경보다 도드라지도록
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    maxZoom: 19, subdomains: "abcd", attribution: "© OpenStreetMap © CARTO",
  }).addTo(map);
  map.on("click", (e) => setLocation(e.latlng.lat, e.latlng.lng, { reveal: true }));
  state.bubbleLayer = L.layerGroup().addTo(map);
  state.listingLayer = L.layerGroup().addTo(map);
  state.map = map;
}

async function loadOverview(industry) {
  try {
    const r = await api(`/api/overview?industry=${encodeURIComponent(industry)}`);
    state.overview = r.districts;
    renderBubbles(r.districts, r.industry_label);
  } catch (e) { /* 버블 없이도 동작 */ }
}

function renderBubbles(list, label) {
  state.bubbleLayer.clearLayers();
  state.bubbleMarkers = {};
  state.ovLabel = label;
  list.forEach((d) => {
    if (state.scope !== "전체" && state.regionOf[d.gu] !== state.scope) return;
    const html = `<div class="bubble ${d.band}">
      <div class="tag"><span class="gu">${shortGu(d.gu)}</span>${d.y3}%</div>
      <div class="tail"></div></div>`;
    const icon = L.divIcon({ html, className: "bubble-wrap", iconSize: [1, 1], iconAnchor: [0, 0] });
    const m = L.marker([d.lat, d.lon], { icon, riseOnHover: true })
      .bindTooltip(`${d.gu} · ${label} 3년 ${d.y3}%`, { direction: "top", offset: [0, -14] })
      .on("click", () => selectGu(d.gu));
    m.addTo(state.bubbleLayer);
    state.bubbleMarkers[d.gu] = m;
  });
  if (state.loc && state.loc.gu) highlightBubble(state.loc.gu);
}

function highlightBubble(gu) {
  Object.entries(state.bubbleMarkers).forEach(([name, m]) => {
    const el = m._icon && m._icon.querySelector(".bubble");
    if (el) el.classList.toggle("selected", name === gu);
  });
}

function placePin(lat, lon) {
  if (!state.pinMarker) {
    const icon = L.divIcon({ html: '<div class="pin-dot"></div>', className: "bubble-wrap", iconSize: [18, 18], iconAnchor: [9, 9] });
    state.pinMarker = L.marker([lat, lon], { icon, zIndexOffset: 1000 }).addTo(state.map);
    state.circle = L.circle([lat, lon], { radius: 200, color: COLORS.s1, weight: 1.5, fillColor: COLORS.s1, fillOpacity: 0.08 }).addTo(state.map);
  } else {
    state.pinMarker.setLatLng([lat, lon]);
    state.circle.setLatLng([lat, lon]);
  }
}

/* 자치구 버블 클릭 → 그 구 중심으로 분석 */
async function selectGu(gu) {
  const d = (state.overview || []).find((x) => x.gu === gu)
    || (state.meta.districts.find((x) => x.gu === gu));
  if (!d) return;
  await setLocation(d.lat, d.lon, { gu, address: `${regionLabel(gu)} ${gu}`, skipReverse: true, fly: true, zoom: 14, reveal: true });
}

async function setLocation(lat, lon, { gu, address, skipReverse, fly, zoom, reveal } = {}) {
  placePin(lat, lon);
  if (fly) state.map.setView([lat, lon], zoom || state.map.getZoom(), { animate: !REDUCE_MOTION });
  $("geo-results").innerHTML = "";

  if (skipReverse && gu) {
    state.loc = { lat, lon, gu, address: address || `${regionLabel(gu)} ${gu}`, snapped: false, in_support: true };
    renderLocCard(false);
  } else {
    const seq = ++state.reverseSeq;
    state.loc = { lat, lon, gu: null, address: "조회 중…", snapped: false };
    renderLocCard(true);
    try {
      const rv = await api(`/api/reverse?lat=${lat}&lon=${lon}`);
      if (seq !== state.reverseSeq) return;
      state.loc = { lat, lon, gu: rv.gu, address: rv.address || "(주소 미확인)", snapped: rv.snapped, in_support: rv.in_support };
    } catch (e) {
      if (seq !== state.reverseSeq) return;
      state.loc = { lat, lon, gu: null, address: "(주소 조회 실패)", snapped: false };
    }
    renderLocCard(false);
  }
  if (state.loc.gu) { highlightBubble(state.loc.gu); highlightRegionChip(state.loc.gu); }
  if (state.industry) { state.revealNext = !!reveal; predict(); }
}

function renderLocCard(loading) {
  $("loc-card").classList.remove("hidden");
  $("loc-gu-text").textContent = state.loc.gu ? `${regionLabel(state.loc.gu)} ${state.loc.gu}` : "위치 확인 중…";
  $("loc-addr").textContent = state.loc.address;
  $("loc-meta").textContent = `${state.loc.lat.toFixed(5)}, ${state.loc.lon.toFixed(5)}`;
  const sn = $("snap-note");
  if (!loading && state.loc.snapped && state.loc.gu) {
    sn.classList.remove("hidden");
    sn.innerHTML = `${ICONS.warn}<span>지원 자치구 밖/경계 지점이라 가장 가까운 지원 상권(${esc(state.loc.gu)}) 기준으로 근사 분석합니다.</span>`;
  } else sn.classList.add("hidden");
}

/* ---------------- search ---------------- */
async function doSearch() {
  const q = $("search").value.trim();
  if (!q) return;
  const box = $("geo-results");
  box.innerHTML = `<div class="geo-item"><span class="loading"><span class="spinner"></span> 검색 중…</span></div>`;
  try {
    const res = await api(`/api/geocode?q=${encodeURIComponent(q)}`);
    box.innerHTML = "";
    if (!res.results.length) { box.innerHTML = `<div class="geo-item g-addr">검색 결과가 없습니다.</div>`; return; }
    res.results.slice(0, 5).forEach((r) => {
      const el = document.createElement("button");
      el.type = "button"; el.className = "geo-item";
      el.innerHTML = `<div class="g-name">${esc(r.name)}</div><div class="g-addr">${esc(r.display_name)}</div>`;
      el.onclick = () => { $("search").value = r.name; box.innerHTML = ""; setLocation(r.lat, r.lon, { fly: true, zoom: 15, reveal: true }); };
      box.appendChild(el);
    });
  } catch (e) { box.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}

/* ---------------- predict ---------------- */
async function predict() {
  if (!state.loc || !state.industry) return;
  const reveal = state.revealNext; state.revealNext = false;   // reveal 의도를 요청 단위로 소비
  const seq = ++state.predictSeq;
  $("input-err").classList.add("hidden");
  try {
    const pred = await api("/api/predict", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ industry: state.industry, lat: state.loc.lat, lon: state.loc.lon, gu: state.loc.gu, address: state.loc.address }),
    });
    if (seq !== state.predictSeq) return;         // 최신 예측만 렌더
    state.lastPred = pred;
    renderResults(pred, reveal);
    highlightBubble(pred.input.gu);
    highlightRegionChip(pred.input.gu);
    if (state.listingsOn && state.listingsGu !== pred.input.gu) loadListings();
    loadReport(seq);
    resetWhatIf();
  } catch (e) {
    if (seq !== state.predictSeq) return;
    $("input-err").innerHTML = `${ICONS.warn}<span>${esc(e.message)}</span>`;
    $("input-err").classList.remove("hidden");
  }
}

function renderResults(p, reveal) {
  $("placeholder").classList.add("hidden");
  $("listing-card").classList.add("hidden");   // 일반 예측에선 매물 카드 숨김
  const body = $("result-body");
  body.classList.remove("hidden");

  $("result-title").innerHTML = `<span>${regionLabel(p.input.gu)} ${esc(p.input.gu)}</span><span class="rt-sep">·</span><span class="rt-ind">${esc(p.input.industry_label)}</span>`;

  const tiles = [
    { k: "1년", v: p.survival.y1 }, { k: "3년", v: p.survival.y3, hero: true }, { k: "5년", v: p.survival.y5 },
  ];
  $("tiles").innerHTML = tiles.map((t) => {
    const b = bandFor(t.v), col = bandColor(b);
    const pill = t.hero ? `<div class="band-pill band-${b}">${ICONS.dot} ${BAND_KO[b]}</div>` : "";
    return `<div class="tile ${t.hero ? "hero" : ""}"><div class="t-label">${t.k} 생존율</div>
      <div class="t-val" style="color:${col}"><span class="t-num" data-to="${t.v}">0</span><span class="t-unit">%</span></div>${pill}
      <div class="t-bar"><i style="width:0;background:${col}" data-w="${t.v}"></i></div></div>`;
  }).join("");
  $("tiles").querySelectorAll(".t-num").forEach((el) =>
    countUp(el, parseFloat(el.dataset.to), String(el.dataset.to).includes(".") ? 1 : 0));
  requestAnimationFrame(() => $("tiles").querySelectorAll(".t-bar > i").forEach((i) => { i.style.width = i.dataset.w + "%"; }));

  const diff = p.vs_seoul_avg_3y;
  const diffCls = diff > 0 ? "delta-pos" : diff < 0 ? "delta-neg" : "";
  const diffTxt = `${diff > 0 ? "▲" : diff < 0 ? "▼" : ""} ${Math.abs(diff)}%p`;
  const med = p.median_capped ? `60<span class="u">개월+</span>` : `${Math.round(p.median_months)}<span class="u">개월</span>`;
  $("summary").innerHTML = `
    <div class="s-item"><div class="s-k">예상 중위 생존기간</div><div class="s-v">${med}</div></div>
    <div class="s-item"><div class="s-k">수도권 평균(3년) 대비</div><div class="s-v ${diffCls}">${diffTxt}</div></div>
    <div class="s-item"><div class="s-k">위험비 (HR)</div><div class="s-v">${p.hazard_ratio}</div></div>
    <div class="s-item"><div class="s-k">실측 코호트</div><div class="s-v">${p.km.n}<span class="u">개 점포</span></div></div>`;

  renderChart(p); renderRisks(p); renderSimilar(p); renderFeatures(p);
  $("prov").innerHTML = `<span class="ico">${ICONS.info}</span><span><b>데이터:</b> ${esc(p.provenance.note)} 출처(연결 예정): ${esc(p.provenance.sources.map((s) => s.name).join(", "))}</span>`;
  state.fitFor = null;
  showTab("summary");
  staggerReveal(body);
  if (reveal) requestAnimationFrame(scrollToResults);
}

/* ---------------- chart ---------------- */
function resampleKM(points) {
  const out = new Array(61).fill(100);
  let last = 100, idx = 0;
  const pts = points.slice().sort((a, b) => a.month - b.month);
  for (let m = 0; m <= 60; m++) { while (idx < pts.length && pts[idx].month <= m) { last = pts[idx].s; idx++; } out[m] = last; }
  return out;
}
const horizonLabelPlugin = {
  id: "horizonLabels",
  afterDatasetsDraw(chart) {
    const ds = chart.data.datasets.find((d) => d._main); if (!ds) return;
    const { ctx, scales: { x, y } } = chart; ctx.save();
    ctx.font = "700 11px 'Fira Code', monospace"; ctx.textAlign = "center";
    [12, 36, 60].forEach((m) => {
      const v = ds.data[m]; const px = x.getPixelForValue(m), py = y.getPixelForValue(v);
      ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(px, py, 4.5, 0, 7); ctx.fill();
      ctx.fillStyle = COLORS.s1; ctx.beginPath(); ctx.arc(px, py, 3, 0, 7); ctx.fill();
      ctx.fillStyle = COLORS.ink; ctx.fillText(`${Math.round(v)}%`, px, py - 11);
    });
    ctx.restore();
  },
};
function renderChart(p) {
  const months = p.curve.map((c) => c.month);
  const s = p.curve.map((c) => c.s), lo = p.curve.map((c) => c.lo), hi = p.curve.map((c) => c.hi);
  const km = resampleKM(p.km.points);
  const data = { labels: months, datasets: [
    { label: "hi", data: hi, borderColor: "transparent", pointRadius: 0, fill: false, tension: 0.25 },
    { label: "lo", data: lo, borderColor: "transparent", pointRadius: 0, fill: "-1", backgroundColor: COLORS.s1soft, tension: 0.25 },
    { label: "예측 생존곡선", _main: true, data: s, borderColor: COLORS.s1, borderWidth: 2, pointRadius: 0, fill: false, tension: 0.25 },
    { label: "실측 KM", data: km, borderColor: COLORS.s2, borderWidth: 1.75, borderDash: [5, 4], pointRadius: 0, fill: false, stepped: true },
  ] };
  const opts = {
    responsive: true, maintainAspectRatio: false, animation: REDUCE_MOTION ? false : undefined,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { display: false }, tooltip: {
      backgroundColor: "#191f28", padding: 10, cornerRadius: 8, titleFont: { family: "Fira Code" }, bodyFont: { family: "Fira Sans" },
      filter: (item) => item.dataset._main === true,
      callbacks: {
        title: (items) => { const m = Number(items[0].label); return `${m}개월${m % 12 === 0 && m > 0 ? ` (${m / 12}년)` : ""}`; },
        label: (item) => { const i = item.dataIndex; return [`예측 생존율: ${s[i].toFixed(1)}%`, `95% 신뢰구간: ${lo[i].toFixed(1)}–${hi[i].toFixed(1)}%`, `실측 KM: ${km[i].toFixed(1)}%`]; },
      },
    } },
    scales: {
      x: { grid: { color: COLORS.grid, drawTicks: false }, border: { color: "#c8d4d2" },
        ticks: { color: COLORS.muted, maxRotation: 0, autoSkip: false, font: { family: "Fira Code", size: 10 },
          callback: (val, idx) => (idx === 0 ? "0" : idx % 12 === 0 ? `${idx / 12}년` : "") } },
      y: { min: 0, max: 100, grid: { color: COLORS.grid, drawTicks: false }, border: { display: false },
        ticks: { color: COLORS.muted, callback: (v) => `${v}%`, stepSize: 25, font: { family: "Fira Code", size: 10 } } },
    },
  };
  if (state.chart) state.chart.destroy();
  state.chart = new Chart($("survival-chart"), { type: "line", data, options: opts, plugins: [horizonLabelPlugin] });
  $("chart-legend").innerHTML = `
    <span class="lg"><span class="sw" style="background:${COLORS.s1}"></span>예측 생존곡선</span>
    <span class="lg"><span class="sw band" style="background:${COLORS.s1}"></span>95% 신뢰구간</span>
    <span class="lg"><span class="sw dash"></span>실측 KM (n=${p.km.n})</span>`;
}

/* ---------------- risk / similar / features ---------------- */
function renderRisks(p) {
  const maxAbs = Math.max(1, ...p.risks.map((r) => Math.abs(r.effect_pp)));
  $("risk-list").innerHTML = p.risks.map((r) => {
    const w = (Math.abs(r.effect_pp) / maxAbs) * 50, pos = r.effect_pp >= 0;
    const fill = `<div class="risk-fill ${pos ? "pos" : "neg"}" style="width:${w}%"></div>`;
    return `<div class="risk-row" title="${esc(r.desc)}"><div class="r-label">${esc(r.label)}</div>
      <div class="risk-track"><div class="center"></div>${fill}</div>
      <div class="r-val" style="color:${pos ? "var(--pos)" : "var(--neg)"}">${r.effect_pp > 0 ? "+" : ""}${r.effect_pp}%p</div></div>`;
  }).join("");
  $("risk-note").textContent = p.risk_note || "";
}
function renderSimilar(p) {
  const rows = [{ gu: `이 자리 (${p.input.gu})`, v: p.survival.y3, me: true }]
    .concat(p.similar.map((s) => ({ gu: s.gu, v: s.survival_3y, me: false })));
  const maxv = Math.max(100, ...rows.map((r) => r.v));
  $("sim-list").innerHTML = rows.map((r) => `
    <div class="sim-row"><div class="s-name ${r.me ? "me" : ""}">${esc(r.gu)}</div>
      <div class="sim-bar-track"><div class="sim-bar ${r.me ? "me" : ""}" style="width:${(r.v / maxv) * 100}%"></div></div>
      <div class="s-pct">${r.v}%</div></div>`).join("");
  $("sim-note").innerHTML = `<span class="ico">${ICONS.info}</span><span>위험 프로파일이 가장 비슷한 지역 · 수도권 동일업종 평균 3년 ${p.seoul_avg_3y}%</span>`;
}
function renderFeatures(p) {
  const f = p.features;
  const items = [
    { k: `경쟁 (반경 ${f.radius_m}m)`, v: f.competition_count, u: "개", i: ICONS.users },
    { k: "유동인구 지수", v: f.foot_traffic, u: "/100", i: ICONS.activity },
    { k: "공실률", v: f.vacancy, u: "%", i: ICONS.door },
    { k: "임대료 지수", v: f.rent, u: "/100", i: ICONS.coins },
    { k: "배후수요 지수", v: f.resident, u: "/100", i: ICONS.home },
    { k: "소득 지수", v: f.income, u: "/100", i: ICONS.wallet },
  ];
  $("feat-grid").innerHTML = items.map((it) => `
    <div class="feat"><div class="f-k"><span class="ico">${it.i}</span>${it.k}</div>
      <div class="f-v">${it.v}<span class="f-u"> ${it.u}</span></div></div>`).join("");
}

/* ---------------- 매물 ---------------- */
function toggleListings() {
  state.listingsOn = !state.listingsOn;
  const btn = $("listing-toggle");
  btn.classList.toggle("on", state.listingsOn);
  btn.setAttribute("aria-pressed", state.listingsOn ? "true" : "false");
  if (state.listingsOn) loadListings();
  else clearListings();
}
async function loadListings() {
  const gu = state.loc && state.loc.gu;
  if (!state.listingsOn || !gu) { clearListings(); return; }
  try {
    const r = await api(`/api/listings?gu=${encodeURIComponent(gu)}`);
    if (!state.listingsOn) return;
    state.listingsGu = gu;
    renderListings(r.listings);
  } catch (e) { clearListings(); }
}
function renderListings(list) {
  state.listingLayer.clearLayers();
  state.listingMarkers = {};
  list.forEach((l) => {
    const html = `<div class="lst-pin"><span class="lst-rent">월 ${l.rent_manwon}</span></div>`;
    const icon = L.divIcon({ html, className: "bubble-wrap", iconSize: [1, 1], iconAnchor: [0, 0] });
    const m = L.marker([l.lat, l.lon], { icon, riseOnHover: true, zIndexOffset: 600 })
      .bindTooltip(`${esc(l.title)} · 보증 ${l.deposit_manwon}/월 ${l.rent_manwon}만원`,
        { direction: "top", offset: [0, -14] })
      .on("click", () => openListing(l.id));
    m.addTo(state.listingLayer);
    state.listingMarkers[l.id] = m;
  });
}
function clearListings() {
  if (state.listingLayer) state.listingLayer.clearLayers();
  state.listingMarkers = {};
  state.listingsGu = null;
}
async function openListing(lid) {
  const seq = ++state.predictSeq;
  $("input-err").classList.add("hidden");
  try {
    const r = await api(`/api/listing/${encodeURIComponent(lid)}?industry=${encodeURIComponent(state.industry)}`);
    if (seq !== state.predictSeq) return;
    const l = r.listing;
    placePin(l.lat, l.lon);
    if (!REDUCE_MOTION) state.map.setView([l.lat, l.lon], Math.max(state.map.getZoom(), 14), { animate: true });
    state.loc = { lat: l.lat, lon: l.lon, gu: l.gu, address: l.title, snapped: false, in_support: true };
    renderLocCard(false);
    state.lastPred = r.prediction;
    renderResults(r.prediction, true);          // 결과 렌더(매물 카드는 숨겨짐)
    renderListingCard(l, r.analysis);            // 그 위에 매물 분석 카드 표시
    highlightBubble(l.gu); highlightRegionChip(l.gu);
    if (state.listingsOn) loadListings();
    loadReport(seq);
    resetWhatIf();
  } catch (e) {
    if (seq !== state.predictSeq) return;
    $("input-err").innerHTML = `${ICONS.warn}<span>${esc(e.message)}</span>`;
    $("input-err").classList.remove("hidden");
  }
}
function renderListingCard(l, a) {
  const box = $("listing-card");
  const feats = [l.floor, `전용 ${l.area_pyeong}평`];
  if (l.corner) feats.push("코너");
  if (l.road_facing) feats.push("도로변");
  const won = (v) => v.toLocaleString();
  box.className = `listing-card band-${a.band}`;
  box.innerHTML = `
    <div class="lc-head">
      <span class="lc-ico">${ICONS.home}</span>
      <div class="lc-title">${esc(l.title)}</div>
      <span class="lc-verdict v-${a.band}">임대료 ${esc(a.verdict)}</span>
    </div>
    <div class="lc-feats">${feats.map((f) => `<span>${esc(f)}</span>`).join("")}</div>
    <div class="lc-grid">
      <div class="lc-item"><div class="lc-k">보증금</div><div class="lc-v">${won(l.deposit_manwon)}<span>만원</span></div></div>
      <div class="lc-item"><div class="lc-k">월세</div><div class="lc-v">${won(l.rent_manwon)}<span>만원</span></div></div>
      <div class="lc-item"><div class="lc-k">관리비</div><div class="lc-v">${l.maintenance_manwon}<span>만원</span></div></div>
      <div class="lc-item"><div class="lc-k">권리금</div><div class="lc-v">${l.premium_manwon ? won(l.premium_manwon) + '<span>만원</span>' : '무권리'}</div></div>
    </div>
    <div class="lc-afford">
      <div class="lc-af-row"><span>예상 월매출</span><b>${won(a.expected_sales_manwon)}만원</b></div>
      <div class="lc-af-row"><span>고정비 (월세+관리비)</span><b>${won(a.monthly_fixed_manwon)}만원</b></div>
      <div class="lc-af-bar"><div class="lc-af-fill f-${a.band}" style="width:${Math.min(100, a.rent_to_sales_pct)}%"></div><span class="lc-af-pct">${a.rent_to_sales_pct}%</span></div>
      <div class="lc-note">${esc(a.note)}</div>
    </div>`;
  box.classList.remove("hidden");
}

/* ---------------- LLM report ---------------- */
async function loadReport(seq) {
  const box = $("report-box"), srcEl = $("report-src");
  srcEl.innerHTML = "";
  box.innerHTML = `<span class="loading"><span class="spinner"></span> AI가 리포트를 작성하는 중… (Claude 호출)</span>`;
  const p = state.lastPred;
  try {
    const r = await api("/api/report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gu: p.input.gu, industry: p.input.industry, lat: p.input.lat, lon: p.input.lon }),
    });
    if (seq !== state.predictSeq) return;          // 위치/업종 바뀌면 무시
    box.textContent = r.text;
    srcEl.innerHTML = r.source === "claude"
      ? `<span class="src-badge src-claude">${ICONS.spark} Claude</span>`
      : `<span class="src-badge src-template">템플릿</span>`;
  } catch (e) {
    if (seq !== state.predictSeq) return;
    box.innerHTML = `<div class="err">${ICONS.warn}<span>리포트 생성 실패: ${esc(e.message)}</span></div>`;
  }
}

/* ---------------- what-if ---------------- */
function resetWhatIf() {
  $("whatif-answer").classList.add("hidden");
  $("whatif-input").value = "";
  const p = state.lastPred;
  const others = state.meta.industries.filter((i) => i.key !== p.input.industry).slice(0, 3);
  const chips = others.map((o) => `${o.label} 업종이면?`).concat(["임대료 부담을 줄이면?"]);
  $("whatif-suggest").innerHTML = chips.map((c) => `<button type="button" class="suggest">${ICONS.compare}${esc(c)}</button>`).join("");
  document.querySelectorAll("#whatif-suggest .suggest").forEach((el) => {
    el.onclick = () => { $("whatif-input").value = el.textContent.trim(); askWhatIf(); };
  });
}
async function askWhatIf() {
  const q = $("whatif-input").value.trim(); if (!q) return;
  const p = state.lastPred, ans = $("whatif-answer");
  ans.classList.remove("hidden");
  ans.innerHTML = `<span class="loading"><span class="spinner"></span> 시나리오 재계산 + 설명 생성 중…</span>`;
  try {
    const r = await api("/api/whatif", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gu: p.input.gu, industry: p.input.industry, lat: p.input.lat, lon: p.input.lon, question: q }),
    });
    let head = "";
    if (r.alt_survival && r.base_survival) {
      head = `<div class="wa-compare">
        <div class="wa-chip">${esc(p.input.industry_label)} 3년<b>${r.base_survival.y3}%</b></div>
        <span class="wa-arrow">${ICONS.arrow}</span>
        <div class="wa-chip">${esc(r.compared_industry)} 3년<b style="color:${bandColor(bandFor(r.alt_survival.y3))}">${r.alt_survival.y3}%</b></div></div>`;
    }
    const badge = r.source === "claude" ? `<span class="src-badge src-claude" style="margin-top:8px">${ICONS.spark} Claude</span>` : `<span class="src-badge src-template" style="margin-top:8px">템플릿</span>`;
    ans.innerHTML = head + `<div>${esc(r.text)}</div><div style="margin-top:8px">${badge}</div>`;
  } catch (e) { ans.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span></div>`; }
}

/* ---------------- 소개 모달 ---------------- */
let aboutLastFocus = null;
function openAbout() {
  aboutLastFocus = document.activeElement;
  $("about-modal").classList.remove("hidden");
  $("about-btn").setAttribute("aria-expanded", "true");
  $("about-close").focus();
}
function closeAbout() {
  if ($("about-modal").classList.contains("hidden")) return;
  $("about-modal").classList.add("hidden");
  $("about-btn").setAttribute("aria-expanded", "false");
  if (aboutLastFocus && aboutLastFocus.focus) aboutLastFocus.focus();
}
$("about-btn").onclick = openAbout;
$("about-close").onclick = closeAbout;
$("about-modal").addEventListener("click", (e) => { if (e.target === $("about-modal")) closeAbout(); });
$("about-modal").addEventListener("keydown", (e) => {   // Tab 포커스 트랩
  if (e.key !== "Tab") return;
  const f = $("about-modal").querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])');
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeAbout(); closeBudget(); } });

/* ---------------- 탭 메뉴 ---------------- */
function showTab(name) {
  state.tab = name;
  document.querySelectorAll("#tabbar .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll("#tab-panels .tabpane").forEach((p) => p.classList.toggle("is-hidden", p.dataset.pane !== name));
  if (name === "curve" && state.chart) requestAnimationFrame(() => state.chart.resize());
  if (name === "fit") loadFit();
}

/* ---------------- 업종추천 (이 자리에 뭐가 맞나) ---------------- */
async function loadFit() {
  if (!state.loc || !state.loc.gu) return;
  const key = `${state.loc.gu}:${state.loc.lat}:${state.loc.lon}`;
  if (state.fitFor === key) return;                       // 현재 지점 이미 계산됨
  const box = $("fit-list");
  box.innerHTML = `<div class="loading"><span class="spinner"></span> 업종별 생존율 계산 중…</div>`;
  try {
    const r = await api(`/api/industry_fit?gu=${encodeURIComponent(state.loc.gu)}&lat=${state.loc.lat}&lon=${state.loc.lon}`);
    state.fitFor = key;
    renderFit(r.industries);
  } catch (e) { box.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span></div>`; }
}
function renderFit(list) {
  const cur = state.industry;
  const maxv = Math.max(100, ...list.map((r) => r.y3));
  $("fit-list").innerHTML = list.map((r, i) => `
    <button type="button" class="fit-row ${r.industry === cur ? "me" : ""}" data-key="${r.industry}">
      <span class="fit-rank">${i + 1}</span>
      <span class="fit-name">${esc(r.label)}${r.industry === cur ? ' <em>현재</em>' : ""}</span>
      <span class="fit-bar-track"><span class="fit-bar" style="width:${(r.y3 / maxv) * 100}%;background:${bandColor(r.band)}"></span></span>
      <span class="fit-pct" style="color:${bandColor(r.band)}">${r.y3}%</span>
    </button>`).join("");
  document.querySelectorAll("#fit-list .fit-row").forEach((el) => {
    el.onclick = () => selectIndustry(el.dataset.key);
  });
}

/* ---------------- 예산 추천 ---------------- */
function openBudget() {
  $("bf-industry").textContent = (state.meta.industries.find((i) => i.key === state.industry) || {}).label || state.industry;
  $("bf-scope").value = state.scope;
  $("rec-list").innerHTML = `<div class="rec-hint">업종 <b>${esc($("bf-industry").textContent)}</b> 기준. 예산을 정하고 <b>추천 받기</b>를 누르세요.</div>`;
  $("budget-modal").classList.remove("hidden");
}
function closeBudget() { $("budget-modal").classList.add("hidden"); }
async function runRecommend() {
  const rent = Math.max(0, parseInt($("bf-rent").value, 10) || 100000);
  const dep = Math.max(0, parseInt($("bf-deposit").value, 10) || 100000000);
  const area = Math.max(0, parseInt($("bf-area").value, 10) || 0);
  const scope = $("bf-scope").value;
  const box = $("rec-list");
  box.innerHTML = `<div class="loading"><span class="spinner"></span> 예산 안 매물 탐색 중…</div>`;
  try {
    const r = await api(`/api/recommend?industry=${encodeURIComponent(state.industry)}&scope=${encodeURIComponent(scope)}&max_rent=${rent}&max_deposit=${dep}&min_area=${area}`);
    renderRec(r.results);
  } catch (e) { box.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span></div>`; }
}
function renderRec(list) {
  if (!list.length) { $("rec-list").innerHTML = `<div class="rec-empty">조건에 맞는 매물이 없어요. 예산을 넓혀보세요.</div>`; return; }
  $("rec-list").innerHTML = `<div class="rec-cap">예산 안 · 생존율 높은 순 ${list.length}곳</div>` + list.map((r, i) => `
    <button type="button" class="rec-row" data-id="${esc(r.id)}">
      <span class="rec-rank">${i + 1}</span>
      <span class="rec-main">
        <span class="rec-title">${regionLabel(r.gu)} ${esc(r.gu)} · ${esc(r.floor)} ${r.area_pyeong}평</span>
        <span class="rec-sub">보증 ${r.deposit_manwon.toLocaleString()} / 월 ${r.rent_manwon.toLocaleString()}만원 · 임대료 ${esc(r.verdict)}</span>
      </span>
      <span class="rec-y3"><b style="color:${bandColor(r.band)}">${r.y3}%</b><i>3년</i></span>
    </button>`).join("");
  document.querySelectorAll("#rec-list .rec-row").forEach((el) => {
    el.onclick = () => { closeBudget(); openListing(el.dataset.id); };
  });
}

/* ---------------- 공유 · PDF ---------------- */
function toast(msg) {
  let t = $("toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(state._toastT);
  state._toastT = setTimeout(() => t.classList.remove("show"), 2200);
}
function shareLink() {
  if (!state.loc) return;
  const q = new URLSearchParams();
  if (state.loc.gu) q.set("gu", state.loc.gu);
  if (state.industry) q.set("industry", state.industry);
  q.set("lat", state.loc.lat); q.set("lon", state.loc.lon);
  const url = `${location.origin}${location.pathname}?${q.toString()}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(() => toast("분석 링크가 복사됐어요")).catch(() => toast(url));
  } else { toast(url); }
}
function exportPDF() {
  document.querySelectorAll("#tab-panels .tabpane").forEach((p) => p.classList.remove("is-hidden"));  // 인쇄용 전체 표시
  if (state.chart) state.chart.resize();
  const restore = () => { showTab(state.tab); window.removeEventListener("afterprint", restore); };
  window.addEventListener("afterprint", restore);
  requestAnimationFrame(() => window.print());
}

/* ---------------- events ---------------- */
document.querySelectorAll("#region-scope .scope-btn").forEach((b) => { b.onclick = () => setScope(b.dataset.scope); });
$("listing-toggle").onclick = toggleListings;
document.querySelectorAll("#tabbar .tab").forEach((t) => { t.onclick = () => showTab(t.dataset.tab); });
$("share-btn").onclick = shareLink;
$("pdf-btn").onclick = exportPDF;
$("budget-btn").onclick = openBudget;
$("budget-close").onclick = closeBudget;
$("bf-run").onclick = runRecommend;
$("budget-modal").addEventListener("click", (e) => { if (e.target === $("budget-modal")) closeBudget(); });
$("search").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
$("whatif-btn").onclick = askWhatIf;
$("whatif-input").addEventListener("keydown", (e) => { if (e.key === "Enter") askWhatIf(); });

init();
