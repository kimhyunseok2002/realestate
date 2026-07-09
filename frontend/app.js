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
  tab: "summary", fitFor: null, infraFor: null, _toastT: null,
  horizon: 3, _simT: null, _simSeq: 0,
  storesOn: false, storesLayer: null, storesMarkers: [], storesKey: null,
  paid: {}, payKey: null, payThen: "view", reportText: "", reportSrc: "",
  deepReport: null, reportInputs: null,
  compare: [], lastListingId: null,
  theme: "light", tileLayer: null,
};
let CHART_INK = "#191f28";   // 다크모드에서 차트 라벨 색 (테마 전환 시 갱신)

const COLORS = {
  s1: "#3182f6", s2: "#12b886", s1soft: "rgba(49,130,246,0.12)",
  good: "#12b886", warning: "#f08c00", serious: "#f76707", critical: "#e03131",
  ink: "#191f28", muted: "#8b95a1", grid: "#eef1f4",
};
const REDUCE_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------------- 다크모드 ---------------- */
const SUN_SVG = '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const MOON_SVG = '<svg class="icon" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>';
function basemapUrl(t) {
  return t === "dark"
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
}
function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("survimap_theme"); } catch (e) { /* */ }
  const dark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(dark ? "dark" : "light", true);
}
function applyTheme(t, silent) {
  state.theme = t;
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("survimap_theme", t); } catch (e) { /* */ }
  CHART_INK = cssVar("--ink") || CHART_INK;
  if (state.tileLayer) state.tileLayer.setUrl(basemapUrl(t));
  recolorChart();
  updateThemeBtn();
  if (!silent) toast(t === "dark" ? "다크 모드" : "라이트 모드");
}
function toggleTheme() { applyTheme(state.theme === "dark" ? "light" : "dark"); }
function updateThemeBtn() {
  const b = $("theme-btn"); if (!b) return;
  b.innerHTML = state.theme === "dark" ? SUN_SVG : MOON_SVG;
  b.title = state.theme === "dark" ? "라이트 모드로" : "다크 모드로";
  b.setAttribute("aria-label", b.title);
}
function recolorChart() {
  const c = state.chart; if (!c) return;
  const grid = cssVar("--grid"), muted = cssVar("--muted");
  c.options.scales.x.grid.color = grid; c.options.scales.y.grid.color = grid;
  c.options.scales.x.ticks.color = muted; c.options.scales.y.ticks.color = muted;
  c.update("none");
}

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
/* 게이지 막대: width 0 → 목표치로 자라나는 전환 (숨김 탭은 보일 때 재생) */
function playBars(root) {
  (root || document).querySelectorAll("[data-w]").forEach((el) => {
    if (!el.offsetParent) return;
    const w = el.dataset.w;
    delete el.dataset.w;
    requestAnimationFrame(() => { el.style.width = w + "%"; });
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
const shortGu = (gu) => { const s = gu.replace(/(특별자치시|특별자치도|특별시|광역시|구|시|군)$/, ""); return s.length >= 2 ? s : gu; };
const regionLabel = (gu) => (state.regionOf && state.regionOf[gu]) || "서울";
// 표시용 전체 지명 — 광역시(키==시도명)일 때 "부산 부산" 이중표기 방지
const guFull = (gu) => { const r = regionLabel(gu); return (gu && gu.includes(r)) ? gu : `${r} ${gu}`; };

/* ---------------- init ---------------- */
async function init() {
  try { state.meta = await api("/api/meta"); }
  catch (e) { document.body.insertAdjacentHTML("afterbegin", `<div class="err" style="margin:12px">메타 로드 실패: ${esc(e.message)}</div>`); return; }

  initTheme();
  loadPaid();
  loadUser();
  renderAccountBtn();
  state.regionOf = {}; state.macroOf = {};
  state.meta.districts.forEach((d) => { state.regionOf[d.gu] = d.region; state.macroOf[d.gu] = d.macro || d.region; });

  buildIndustryChips();
  buildRegionChips();
  initMap();
  initAsk();
  // 딥링크(?gu=&industry=&lat=&lon=)가 있으면 그 분석을 복원, 없으면 강남역 데모
  const q = new URLSearchParams(location.search);
  const qi = q.get("industry");
  await selectIndustry(qi && state.meta.industries.some((i) => i.key === qi) ? qi : "카페");
  const qlat = parseFloat(q.get("lat")), qlon = parseFloat(q.get("lon")), qgu = q.get("gu");
  if (isFinite(qlat) && isFinite(qlon)) {
    await setLocation(qlat, qlon, qgu && state.regionOf[qgu]
      ? { gu: qgu, address: `${guFull(qgu)}`, skipReverse: true, fly: true, zoom: 14, reveal: true }
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
  wireChipScroll();
}

/* ---------------- 자연어 채팅바 ---------------- */
function initAsk() {
  const form = $("ask-form"), input = $("ask-input");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (q) runAsk(q);
  });
  document.querySelectorAll("#ask-examples button").forEach((b) => {
    b.onclick = () => runAsk(b.dataset.q || b.textContent.trim());
  });
}
function addAskMsg(role, text) {
  const log = $("ask-log");
  const el = document.createElement("div");
  el.className = `ask-msg ${role}`;
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}
async function runAsk(q) {
  const input = $("ask-input"), send = $("ask-send");
  addAskMsg("user", q);
  input.value = "";
  const ex = $("ask-examples"); if (ex) ex.classList.add("hidden");
  const typing = addAskMsg("bot typing", "AI가 분석 중…");
  send.disabled = true; input.disabled = true;
  try {
    // 1) 빠른 파싱(지역·업종) — 지도/분석은 즉시 반영
    const r = await api(`/api/ask?q=${encodeURIComponent(q)}&industry=${encodeURIComponent(state.industry || "")}`);
    if (!r.ok) { typing.remove(); addAskMsg("bot", r.reply); return; }
    const move = (async () => {
      if (r.industry && r.industry !== state.industry) await selectIndustry(r.industry);
      await setLocation(r.lat, r.lon, { gu: r.gu, address: guFull(r.gu), skipReverse: true, fly: true, zoom: 14, reveal: true });
    })();
    // 2) 답변은 LLM(Claude)이 생성 — 예측 수치에 근거해 질문에 직접 답변(실패 시 템플릿 폴백)
    let reply = r.reply, viaClaude = false;
    try {
      const w = await api("/api/whatif", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gu: r.gu, industry: r.industry, lat: r.lat, lon: r.lon, question: q }),
      });
      if (w && w.text) { reply = w.text; viaClaude = (w.source === "llm"); }
    } catch (e) { /* whatif 실패 → r.reply(템플릿) 사용 */ }
    typing.remove();
    const msg = addAskMsg("bot", reply);
    const tag = document.createElement("span");
    tag.className = "ask-src";
    tag.textContent = viaClaude ? "✦ AI" : "규칙 기반";
    msg.appendChild(tag);
    await move;
  } catch (e) {
    typing.remove();
    addAskMsg("bot", "분석 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.");
  } finally {
    send.disabled = false; input.disabled = false; input.focus();
  }
}

/* 칩바 좌우 스크롤 버튼 — 넘치면 화살표 표시, 클릭 시 한 화면씩 이동 */
function wireChipScroll() {
  document.querySelectorAll(".mt-chipscroll").forEach((wrap) => {
    const sc = wrap.querySelector(".mt-chips");
    const prev = wrap.querySelector(".chip-nav.prev");
    const next = wrap.querySelector(".chip-nav.next");
    if (!sc || !prev || !next) return;
    const update = () => {
      const max = sc.scrollWidth - sc.clientWidth - 2;
      const canPrev = sc.scrollLeft > 2;
      const canNext = sc.scrollLeft < max;
      prev.classList.toggle("show", canPrev);
      next.classList.toggle("show", canNext);
      wrap.classList.toggle("can-prev", canPrev);
      wrap.classList.toggle("can-next", canNext);
    };
    if (!wrap._wired) {
      const step = () => Math.max(120, sc.clientWidth * 0.8);
      prev.addEventListener("click", () => sc.scrollBy({ left: -step(), behavior: REDUCE_MOTION ? "auto" : "smooth" }));
      next.addEventListener("click", () => sc.scrollBy({ left: step(), behavior: REDUCE_MOTION ? "auto" : "smooth" }));
      sc.addEventListener("scroll", update, { passive: true });
      wrap._wired = true;
    }
    update();
  });
}
function buildRegionChips() {
  const box = $("region-chips");
  box.innerHTML = "";
  state.meta.districts.forEach((d) => {
    if (state.scope !== "전체" && d.macro !== state.scope) return;
    const el = document.createElement("button");
    el.type = "button"; el.className = "mchip"; el.textContent = shortGu(d.gu); el.dataset.gu = d.gu;
    el.setAttribute("aria-label", d.gu);
    el.onclick = () => selectGu(d.gu);
    box.appendChild(el);
  });
  if (state.loc && state.loc.gu) highlightRegionChip(state.loc.gu);
  wireChipScroll();
}

/* 세그먼트 컨트롤: 활성 배경이 옆으로 미끄러지는 인디케이터 */
function segInd(container, activeSel) {
  if (!container) return;
  let ind = container.querySelector(".seg-ind");
  if (!ind) { ind = document.createElement("span"); ind.className = "seg-ind"; ind.setAttribute("aria-hidden", "true"); container.prepend(ind); }
  const act = container.querySelector(activeSel);
  if (!act) return;
  ind.style.width = `${act.offsetWidth}px`;
  ind.style.height = `${act.offsetHeight}px`;
  ind.style.transform = `translate(${act.offsetLeft}px, ${act.offsetTop}px)`;
}
function refreshSegInds() {
  segInd($("region-scope"), ".scope-btn.active");
  segInd($("ml-horizon"), ".mh.active");
}

/* 지역 범위(전체/서울/경기) 전환 */
function setScope(scope) {
  state.scope = scope;
  document.querySelectorAll("#region-scope .scope-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.scope === scope));
  segInd($("region-scope"), ".scope-btn.active");
  buildRegionChips();
  if (state.overview) renderBubbles(state.overview, state.ovLabel);
  fitScopeBounds();
}
function fitScopeBounds() {
  const pts = state.meta.districts
    .filter((d) => state.scope === "전체" || d.macro === state.scope)
    .map((d) => [d.lat, d.lon]);
  if (!pts.length || !state.map) return;
  state.map.fitBounds(pts, {
    paddingTopLeft: [430, 40], paddingBottomRight: [30, 40],
    maxZoom: 12, animate: !REDUCE_MOTION,
  });
}
function highlightRegionChip(gu) {
  let act = null;
  document.querySelectorAll("#region-chips .mchip").forEach((c) => {
    const on = c.dataset.gu === gu;
    c.classList.toggle("active", on);
    if (on) act = c;
  });
  // 활성 칩이 가로 스크롤 밖에 있으면 보이게 — 지도↔칩 동기화가 눈에 보이도록
  if (act) act.scrollIntoView({ behavior: REDUCE_MOTION ? "auto" : "smooth", inline: "center", block: "nearest" });
}

async function selectIndustry(key) {
  state.industry = key;
  let act = null;
  document.querySelectorAll("#map-industry-chips .mchip").forEach((c) => {
    const on = c.dataset.key === key;
    c.classList.toggle("active", on);
    if (on) act = c;
  });
  if (act) act.scrollIntoView({ behavior: REDUCE_MOTION ? "auto" : "smooth", inline: "center", block: "nearest" });
  updateLegendTitle();
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
  // 톤다운 베이스맵(CARTO) — 라이트/다크 테마에 맞춰 타일 교체
  state.tileLayer = L.tileLayer(basemapUrl(state.theme), {
    maxZoom: 19, subdomains: "abcd", attribution: "© OpenStreetMap © CARTO",
  }).addTo(map);
  map.on("click", (e) => { clearGeo(); setLocation(e.latlng.lat, e.latlng.lng, { reveal: true }); });
  state.bubbleLayer = L.layerGroup().addTo(map);
  state.listingLayer = L.layerGroup().addTo(map);
  state.storesLayer = L.layerGroup().addTo(map);
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
  // 전체 재생성 대신 diff 업데이트 — 기간/업종/범위 전환 시 지도가 깜빡이지 않음
  state.ovLabel = label;
  const seen = new Set();
  let n = 0;
  list.forEach((d) => {
    if (state.scope !== "전체" && state.macroOf[d.gu] !== state.scope) return;
    const val = d["y" + state.horizon];
    const band = bandFor(val);
    const tagHtml = `<span class="gu">${shortGu(d.gu)}</span>${val}%`;
    const tip = `${d.gu} · ${label} ${state.horizon}년 ${val}%`;
    seen.add(d.gu);
    const ex = state.bubbleMarkers[d.gu];
    if (ex && ex._icon) {
      const b = ex._icon.querySelector(".bubble");
      if (b) {
        b.classList.remove("good", "warning", "serious", "critical");
        b.classList.add(band);
        const tag = b.querySelector(".tag");
        if (tag && tag.innerHTML !== tagHtml) {
          tag.innerHTML = tagHtml;                     // 값이 바뀐 버블만 살짝 튀는 펄스
          if (!REDUCE_MOTION) { tag.classList.remove("tick"); void tag.offsetWidth; tag.classList.add("tick"); }
        }
        ex.setTooltipContent(tip);
        return;
      }
    }
    const delay = REDUCE_MOTION ? 0 : (n++ % 10) * 26;    // 물결치듯 순차 등장
    const html = `<div class="bubble ${band}" style="animation-delay:${delay}ms">
      <div class="tag">${tagHtml}</div>
      <div class="tail"></div></div>`;
    const icon = L.divIcon({ html, className: "bubble-wrap", iconSize: [1, 1], iconAnchor: [0, 0] });
    const m = L.marker([d.lat, d.lon], { icon, riseOnHover: true })
      .bindTooltip(tip, { direction: "top", offset: [0, -14] })
      .on("click", () => selectGu(d.gu));
    m.addTo(state.bubbleLayer);
    state.bubbleMarkers[d.gu] = m;
  });
  Object.keys(state.bubbleMarkers).forEach((gu) => {      // 범위 밖 마커만 제거
    if (!seen.has(gu)) { state.bubbleLayer.removeLayer(state.bubbleMarkers[gu]); delete state.bubbleMarkers[gu]; }
  });
  if (state.loc && state.loc.gu) highlightBubble(state.loc.gu);
}

function highlightBubble(gu) {
  Object.entries(state.bubbleMarkers).forEach(([name, m]) => {
    const el = m._icon && m._icon.querySelector(".bubble");
    if (el) el.classList.toggle("selected", name === gu);
  });
}
function updateLegendTitle() {
  const label = (state.meta.industries.find((i) => i.key === state.industry) || {}).label || state.industry || "";
  $("ml-title").textContent = `${label} · ${state.horizon}년 생존율`;
}
function setHorizon(h) {
  state.horizon = h;
  document.querySelectorAll("#ml-horizon .mh").forEach((b) => b.classList.toggle("active", Number(b.dataset.h) === h));
  segInd($("ml-horizon"), ".mh.active");
  updateLegendTitle();
  if (state.overview) renderBubbles(state.overview, state.ovLabel);
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
  await setLocation(d.lat, d.lon, { gu, address: `${guFull(gu)}`, skipReverse: true, fly: true, zoom: 14, reveal: true });
}

async function setLocation(lat, lon, { gu, address, skipReverse, fly, zoom, reveal } = {}) {
  placePin(lat, lon);
  if (fly) {
    const z = zoom || state.map.getZoom();
    if (REDUCE_MOTION) state.map.setView([lat, lon], z, { animate: false });
    else state.map.flyTo([lat, lon], z, { duration: 0.7, easeLinearity: 0.22 });
  }

  if (skipReverse && gu) {
    state.loc = { lat, lon, gu, address: address || `${guFull(gu)}`, snapped: false, in_support: true };
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
  const card = $("loc-card");
  card.classList.remove("hidden");
  if (!loading && !REDUCE_MOTION) { card.classList.remove("flash"); void card.offsetWidth; card.classList.add("flash"); }
  $("loc-gu-text").textContent = state.loc.gu ? `${guFull(state.loc.gu)}` : "위치 확인 중…";
  $("loc-addr").textContent = state.loc.address;
  $("loc-meta").textContent = `${state.loc.lat.toFixed(5)}, ${state.loc.lon.toFixed(5)}`;
  const sn = $("snap-note");
  if (!loading && state.loc.snapped && state.loc.gu) {
    sn.classList.remove("hidden");
    sn.innerHTML = `${ICONS.warn}<span>지원 자치구 밖/경계 지점이라 가장 가까운 지원 상권(${esc(state.loc.gu)}) 기준으로 근사 분석합니다.</span>`;
  } else sn.classList.add("hidden");
}

/* ---------------- search (라이브 검색 + 키보드 탐색) ---------------- */
let searchSeq = 0, searchT = null, searchSel = -1;
async function fetchGeo(q, { quiet } = {}) {
  const seq = ++searchSeq;
  const box = $("geo-results");
  if (!quiet) box.innerHTML = `<div class="geo-item"><span class="loading"><span class="spinner"></span> 검색 중…</span></div>`;
  try {
    const res = await api(`/api/geocode?q=${encodeURIComponent(q)}`);
    return seq === searchSeq ? res.results : null;      // 최신 검색만 반영
  } catch (e) {
    if (seq === searchSeq && !quiet) box.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span></div>`;
    return null;
  }
}
function renderGeo(results) {
  const box = $("geo-results");
  box.innerHTML = "";
  searchSel = -1;
  if (!results) return;
  if (!results.length) { box.innerHTML = `<div class="geo-item g-addr">검색 결과가 없습니다.</div>`; return; }
  results.slice(0, 5).forEach((r, i) => {
    const el = document.createElement("button");
    el.type = "button"; el.className = "geo-item pop-in";
    el.style.animationDelay = REDUCE_MOTION ? "0ms" : `${i * 38}ms`;
    el.innerHTML = `<div class="g-name">${esc(r.name)}</div><div class="g-addr">${esc(r.display_name)}</div>`;
    el.onclick = () => { $("search").value = r.name; clearGeo(); setLocation(r.lat, r.lon, { fly: true, zoom: 15, reveal: true }); };
    box.appendChild(el);
  });
}
function clearGeo() { $("geo-results").innerHTML = ""; searchSel = -1; searchSeq++; clearTimeout(searchT); }
async function doSearch() {
  const q = $("search").value.trim();
  if (!q) return;
  clearTimeout(searchT);
  const results = await fetchGeo(q);
  if (!results) return;
  renderGeo(results);                          // 목록은 유지 — 다른 후보로 바꿔 고를 수 있게
  if (results.length) setLocation(results[0].lat, results[0].lon, { fly: true, zoom: 15, reveal: true });
}
function liveSearch() {
  const q = $("search").value.trim();
  clearTimeout(searchT);
  if (q.length < 2) { clearGeo(); return; }
  searchT = setTimeout(async () => {
    const results = await fetchGeo(q, { quiet: true });
    if (results) renderGeo(results);
  }, 350);
}
function moveGeoSel(dir) {
  const items = Array.from(document.querySelectorAll("#geo-results .geo-item"));
  if (!items.length) return;
  searchSel = (searchSel + dir + items.length) % items.length;
  items.forEach((el, i) => el.classList.toggle("sel", i === searchSel));
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
    if (state.storesOn) loadStores();
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
  const first = body.classList.contains("hidden");   // 최초 공개 여부
  body.classList.remove("hidden");

  $("result-title").innerHTML = `<span>${esc(guFull(p.input.gu))}</span><span class="rt-sep">·</span><span class="rt-ind">${esc(p.input.industry_label)}</span>`;

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
    <div class="s-item"><div class="s-k">전국 평균(3년) 대비</div><div class="s-v ${diffCls}">${diffTxt}</div></div>
    <div class="s-item"><div class="s-k">위험비 (HR)</div><div class="s-v">${p.hazard_ratio}</div></div>
    <div class="s-item"><div class="s-k">실측 코호트</div><div class="s-v">${p.km.n}<span class="u">개 점포</span></div></div>`;

  renderChart(p); renderRisks(p); renderSimilar(p); renderFeatures(p);
  $("prov").innerHTML = `<span class="ico">${ICONS.info}</span><span><b>데이터:</b> ${esc(p.provenance.note)} 출처(연결 예정): ${esc(p.provenance.sources.map((s) => s.name).join(", "))}</span>`;
  state.fitFor = null;
  state.infraFor = null;
  state.deepReport = null;
  state.reportInputs = null;
  if (first) {
    showTab("summary");
    staggerReveal(body);                       // 스태거는 최초 공개에만 — 갱신 때 출렁임 방지
  } else {
    showTab(state.tab);                        // 보던 탭 유지 (탭별 데이터는 캐시키로 자동 재로드)
  }
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
      ctx.fillStyle = cssVar("--surface") || "#fff"; ctx.beginPath(); ctx.arc(px, py, 4.5, 0, 7); ctx.fill();
      ctx.fillStyle = COLORS.s1; ctx.beginPath(); ctx.arc(px, py, 3, 0, 7); ctx.fill();
      ctx.fillStyle = CHART_INK; ctx.fillText(`${Math.round(v)}%`, px, py - 11);
    });
    ctx.restore();
  },
};
function renderChart(p) {
  const months = p.curve.map((c) => c.month);
  const s = p.curve.map((c) => c.s), lo = p.curve.map((c) => c.lo), hi = p.curve.map((c) => c.hi);
  const km = resampleKM(p.km.points);
  state._chartData = { s, lo, hi, km };                    // 툴팁 콜백이 최신 데이터를 참조
  if (state.chart) {
    // destroy→재생성 대신 데이터만 갱신 — 이전 곡선에서 새 곡선으로 morph 전환
    const c = state.chart;
    c.data.labels = months;
    c.data.datasets[0].data = hi;
    c.data.datasets[1].data = lo;
    c.data.datasets[2].data = s;
    c.data.datasets[3].data = km;
    c.update(REDUCE_MOTION ? "none" : undefined);
  } else {
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
          label: (item) => { const i = item.dataIndex, D = state._chartData;
            return [`예측 생존율: ${D.s[i].toFixed(1)}%`, `95% 신뢰구간: ${D.lo[i].toFixed(1)}–${D.hi[i].toFixed(1)}%`, `실측 KM: ${D.km[i].toFixed(1)}%`]; },
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
    state.chart = new Chart($("survival-chart"), { type: "line", data, options: opts, plugins: [horizonLabelPlugin] });
  }
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
    const fill = `<div class="risk-fill ${pos ? "pos" : "neg"}" style="width:0" data-w="${w}"></div>`;
    return `<div class="risk-row" title="${esc(r.desc)}"><div class="r-label">${esc(r.label)}</div>
      <div class="risk-track"><div class="center"></div>${fill}</div>
      <div class="r-val" style="color:${pos ? "var(--pos)" : "var(--neg)"}">${r.effect_pp > 0 ? "+" : ""}${r.effect_pp}%p</div></div>`;
  }).join("");
  playBars($("risk-list"));
  $("risk-note").textContent = p.risk_note || "";
}
function renderSimilar(p) {
  const rows = [{ gu: `이 자리 (${p.input.gu})`, v: p.survival.y3, me: true }]
    .concat(p.similar.map((s) => ({ gu: s.gu, v: s.survival_3y, me: false })));
  const maxv = Math.max(100, ...rows.map((r) => r.v));
  $("sim-list").innerHTML = rows.map((r) => `
    <div class="sim-row"><div class="s-name ${r.me ? "me" : ""}">${esc(r.gu)}</div>
      <div class="sim-bar-track"><div class="sim-bar ${r.me ? "me" : ""}" style="width:0" data-w="${(r.v / maxv) * 100}"></div></div>
      <div class="s-pct">${r.v}%</div></div>`).join("");
  playBars($("sim-list"));
  $("sim-note").innerHTML = `<span class="ico">${ICONS.info}</span><span>위험 프로파일이 가장 비슷한 지역 · 전국 동일업종 평균 3년 ${p.seoul_avg_3y}%</span>`;
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
  if (!state.listingsOn) return;
  const gu = state.loc && state.loc.gu;
  if (!gu) { clearListings(); toast("먼저 지도에서 위치를 선택하세요"); return; }
  const btn = $("listing-toggle"); btn.classList.add("loading-b");
  try {
    const r = await api(`/api/listings?gu=${encodeURIComponent(gu)}`);
    if (!state.listingsOn) return;
    state.listingsGu = gu;
    renderListings(r.listings);
    if (!r.listings.length) toast("이 지역에 등록된 매물이 없어요");
  } catch (e) { clearListings(); toast("매물을 불러오지 못했어요 — 다시 시도해 주세요"); }
  finally { btn.classList.remove("loading-b"); }
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
    if (!REDUCE_MOTION) state.map.flyTo([l.lat, l.lon], Math.max(state.map.getZoom(), 14), { duration: 0.6, easeLinearity: 0.22 });
    state.loc = { lat: l.lat, lon: l.lon, gu: l.gu, address: l.title, snapped: false, in_support: true };
    renderLocCard(false);
    state.lastPred = r.prediction;
    renderResults(r.prediction, true);          // 결과 렌더(매물 카드는 숨겨짐)
    showTab("summary");                          // 매물 분석 카드는 요약 탭에 뜸
    state.lastListingId = l.id;
    renderListingCard(l, r.analysis);            // 그 위에 매물 분석 카드 표시
    state.reportInputs = { area: l.area_pyeong, rent: l.rent_manwon, deposit: l.deposit_manwon, premium: l.premium_manwon, capital: 0, target: 0 };
    highlightBubble(l.gu); highlightRegionChip(l.gu);
    if (state.listingsOn) loadListings();
    if (state.storesOn) loadStores();
    loadReport(seq);
    resetWhatIf();
  } catch (e) {
    if (seq !== state.predictSeq) return;
    $("input-err").innerHTML = `${ICONS.warn}<span>${esc(e.message)}</span>`;
    $("input-err").classList.remove("hidden");
  }
}
function hashInt(str) { let h = 0; for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0; return h; }
// 매물별 결정론적 점포 일러스트 (합성 매물 — 실사진 대체용 예시 이미지)
function listingThumb(l, band) {
  const c = COLORS[band] || "#3182f6";
  const h = hashInt((l.id || "") + (l.gu || ""));
  const stripes = 6 + (h % 5), sw = 300 / stripes;
  let awn = "";
  for (let i = 0; i < stripes; i++)
    awn += `<path d="M${(10 + i * sw).toFixed(1)} 58 h${sw.toFixed(1)} l-7 16 h-${(sw - 7).toFixed(1)} z" fill="${i % 2 ? c : "#ffffff"}"/>`;
  const cols = 3 + (h % 3), uw = 300 / cols;
  let win = "";
  for (let i = 0; i < cols; i++)
    win += `<rect x="${(10 + i * uw + 8).toFixed(1)}" y="18" width="${(uw - 16).toFixed(1)}" height="22" rx="2.5" fill="var(--th-win)"/>`;
  return `<svg class="lc-thumb-svg" viewBox="0 0 320 132" preserveAspectRatio="none" role="img" aria-label="점포 예시 일러스트">
    <rect width="320" height="132" fill="var(--th-sky)"/>
    <rect x="10" y="6" width="300" height="124" rx="6" fill="var(--th-wall)"/>
    ${win}
    <rect x="10" y="52" width="300" height="7" fill="${c}"/>
    ${awn}
    <rect x="10" y="82" width="300" height="48" fill="var(--th-store)"/>
    <rect x="28" y="92" width="104" height="30" rx="3" fill="var(--th-glass)"/>
    <rect x="150" y="90" width="58" height="40" rx="3" fill="var(--th-door)"/>
    <rect x="226" y="92" width="82" height="30" rx="3" fill="var(--th-glass)"/>
    <circle cx="201" cy="110" r="2.6" fill="${c}"/>
  </svg>`;
}
const PHONE_SVG = '<svg class="icon" viewBox="0 0 24 24"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.7A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8.1 9.8a16 16 0 0 0 6 6l1.3-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2Z"/></svg>';

function renderListingCard(l, a) {
  const box = $("listing-card");
  const feats = [l.floor, `전용 ${l.area_pyeong}평`];
  if (l.corner) feats.push("코너");
  if (l.road_facing) feats.push("도로변");
  const won = (v) => v.toLocaleString();
  box.className = `listing-card band-${a.band}`;
  box.innerHTML = `
    <div class="lc-photo">${listingThumb(l, a.band)}<span class="lc-photo-tag">예시 이미지</span></div>
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
      <div class="lc-af-bar"><div class="lc-af-fill f-${a.band}" style="width:0" data-w="${Math.min(100, a.rent_to_sales_pct)}"></div><span class="lc-af-pct">${a.rent_to_sales_pct}%</span></div>
      <div class="lc-note">${esc(a.note)}</div>
    </div>
    ${l.agency ? `<div class="lc-agency">
      <div class="lc-ag-info"><div class="lc-ag-name">${esc(l.agency)}</div><span class="lc-ag-sub">담당 중개사 · 데모 연락처</span></div>
      <a class="lc-ag-call" href="tel:${esc((l.agency_phone || "").replace(/[^0-9]/g, ""))}">${PHONE_SVG}${esc(l.agency_phone || "")}</a>
    </div>` : ""}
    <button type="button" class="lc-cmp" id="lc-cmp"></button>`;
  box.classList.remove("hidden");
  playBars(box);
  const cmpBtn = $("lc-cmp");
  cmpBtn.onclick = () => addToCompare(l, a);
  updateCmpAddBtn(l.id);
}

/* ---------------- 매물 비교함 ---------------- */
const CMP_MAX = 3;
function inCompare(id) { return state.compare.some((c) => c.id === id); }
function updateCmpAddBtn(id) {
  const btn = $("lc-cmp"); if (!btn) return;
  const on = inCompare(id);
  btn.classList.toggle("added", on);
  btn.disabled = !on && state.compare.length >= CMP_MAX;
  btn.innerHTML = on
    ? `<svg class="icon" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg> 비교함에 담김`
    : (btn.disabled ? `비교함 가득참 (최대 ${CMP_MAX})` : `<svg class="icon" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> 비교함에 담기`);
}
function addToCompare(l, a) {
  if (inCompare(l.id)) { removeFromCompare(l.id); return; }   // 토글
  if (state.compare.length >= CMP_MAX) { toast(`비교함은 최대 ${CMP_MAX}개까지예요`); return; }
  const y3 = state.lastPred ? state.lastPred.survival.y3 : null;
  state.compare.push({
    id: l.id, gu: l.gu, floor: l.floor, area: l.area_pyeong,
    rent: l.rent_manwon, deposit: l.deposit_manwon, maint: l.maintenance_manwon, premium: l.premium_manwon,
    corner: l.corner, road: l.road_facing,
    y3, band: y3 != null ? bandFor(y3) : "warning",
    verdict: a.verdict, aband: a.band, rts: a.rent_to_sales_pct, sales: a.expected_sales_manwon,
  });
  renderCmpTray();
  updateCmpAddBtn(l.id);
  toast(`비교함에 담았어요 (${state.compare.length}/${CMP_MAX})`);
}
function removeFromCompare(id) {
  state.compare = state.compare.filter((c) => c.id !== id);
  renderCmpTray();
  updateCmpAddBtn(id);
}
function clearCompare() { state.compare = []; renderCmpTray(); if (state.lastListingId) updateCmpAddBtn(state.lastListingId); }
function renderCmpTray() {
  const tray = $("cmp-tray");
  if (!state.compare.length) { tray.classList.add("hidden"); return; }
  tray.classList.remove("hidden");
  $("cmp-count").textContent = state.compare.length;
  $("cmp-tray-items").innerHTML = state.compare.map((c) => `
    <span class="cmp-chip band-${c.band}">
      <b>${shortGu(c.gu)} ${esc(c.floor)}</b><i>${c.area}평·월${drWon(c.rent)}</i>
      <button type="button" class="cmp-x" data-id="${esc(c.id)}" aria-label="빼기"><svg class="icon" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg></button>
    </span>`).join("");
  document.querySelectorAll("#cmp-tray-items .cmp-x").forEach((el) => {
    el.onclick = () => removeFromCompare(el.dataset.id);
  });
  $("cmp-open").disabled = state.compare.length < 2;
  $("cmp-open").textContent = state.compare.length < 2 ? "매물 2개+ 담기" : `비교하기 (${state.compare.length})`;
}
function openCompare() {
  if (state.compare.length < 2) { toast("비교하려면 매물을 2개 이상 담아주세요"); return; }
  const rows = state.compare;
  const best = {
    y3: Math.max(...rows.map((r) => r.y3 ?? -1)),
    rts: Math.min(...rows.map((r) => r.rts)),
    rent: Math.min(...rows.map((r) => r.rent)),
    deposit: Math.min(...rows.map((r) => r.deposit)),
    sales: Math.max(...rows.map((r) => r.sales)),
  };
  const cell = (v, isBest, sub) => `<td class="${isBest ? "cmp-best" : ""}">${v}${sub ? `<i>${sub}</i>` : ""}</td>`;
  const head = `<tr><th></th>${rows.map((r) => `<th><span class="cmp-h-gu">${esc(guFull(r.gu))}</span><span class="cmp-h-sub">${esc(r.floor)} · ${r.area}평${r.corner ? " · 코너" : ""}</span><button type="button" class="cmp-open-one" data-id="${esc(r.id)}">열기</button></th>`).join("")}</tr>`;
  const body = [
    ["3년 생존율", rows.map((r) => cell(`<b style="color:${bandColor(r.band)}">${r.y3}%</b>`, r.y3 === best.y3))],
    ["예상 월매출", rows.map((r) => cell(`${drWon(r.sales)}만`, r.sales === best.sales))],
    ["월세", rows.map((r) => cell(`${drWon(r.rent)}만`, r.rent === best.rent))],
    ["보증금", rows.map((r) => cell(`${drWon(r.deposit)}만`, r.deposit === best.deposit))],
    ["권리금", rows.map((r) => cell(r.premium ? `${drWon(r.premium)}만` : "무권리", false))],
    ["임대료 부담", rows.map((r) => cell(`<b style="color:${bandColor(r.aband)}">${r.rts}%</b>`, r.rts === best.rts, r.verdict))],
  ].map(([label, cells]) => `<tr><th>${label}</th>${cells.join("")}</tr>`).join("");
  $("compare-body").innerHTML = `<table class="cmp-table">${head}${body}</table>
    <div class="cmp-legend">🟢 항목별 최선값 · 열기를 누르면 그 매물 분석으로 이동합니다</div>`;
  document.querySelectorAll("#compare-body .cmp-open-one").forEach((el) => {
    el.onclick = () => { closeModal("compare-modal"); openListing(el.dataset.id); };
  });
  openModal("compare-modal");
}
function closeCompare() { closeModal("compare-modal"); }

/* ---------------- LLM report ---------------- */
async function loadReport(seq) {
  // 심층 리포트/잠금화면은 Claude 호출을 기다리지 않고 즉시 노출 (AI 총평만 뒤에 채움)
  state.reportText = "";
  state.reportSrc = "";
  renderReportGated();
  const p = state.lastPred;
  try {
    const r = await api("/api/report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gu: p.input.gu, industry: p.input.industry, lat: p.input.lat, lon: p.input.lon }),
    });
    if (seq !== state.predictSeq) return;          // 위치/업종 바뀌면 무시
    state.reportText = r.text;
    state.reportSrc = r.source;
    if (reportUnlocked()) {
      if (state.deepReport) renderDeep(state.deepReport);   // AI 총평 주입 (재조회 없음)
    } else {
      renderReportGated();                                   // 티저 갱신
    }
  } catch (e) {
    if (seq !== state.predictSeq) return;          // 실패해도 심층 리포트는 이미 떠 있음
  }
}

/* ---------------- 리포트 페이월 · 데모 결제 ---------------- */
const LOCK_SVG = '<svg class="icon" viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
function reportKey() {
  const p = state.lastPred && state.lastPred.input;
  return p ? `${p.gu}:${p.industry}:${p.lat}:${p.lon}` : null;
}
function isPaid() { const k = reportKey(); return !!(k && state.paid[k]); }
function loadPaid() { try { state.paid = JSON.parse(localStorage.getItem("survimap_paid") || "{}") || {}; } catch (e) { state.paid = {}; } }
function savePaid() { try { localStorage.setItem("survimap_paid", JSON.stringify(state.paid)); } catch (e) { /* */ } }

function renderReportGated() {
  const box = $("report-box"), srcEl = $("report-src");
  if (!state.lastPred) return;
  updatePdfLock();
  if (reportUnlocked()) {
    srcEl.innerHTML = `<span class="src-badge src-claude">${ICONS.spark} 심층 리포트</span>`;
    box.classList.add("unlocked");
    box.innerHTML = `
      <div class="dr-inputs" id="dr-inputs">
        <div class="dr-inrow">
          <div class="dr-in"><label>면적</label><span class="dr-inw"><input id="dr-area" type="number" min="4"><i>평</i></span></div>
          <div class="dr-in"><label>월세</label><span class="dr-inw"><input id="dr-rent" type="number" min="0"><i>만원</i></span></div>
          <div class="dr-in"><label>보증금</label><span class="dr-inw"><input id="dr-deposit" type="number" min="0"><i>만원</i></span></div>
          <div class="dr-in"><label>권리금</label><span class="dr-inw"><input id="dr-premium" type="number" min="0"><i>만원</i></span></div>
          <div class="dr-in"><label>자기자본</label><span class="dr-inw"><input id="dr-capital" type="number" min="0"><i>만원</i></span></div>
          <div class="dr-in"><label>목표 월순익</label><span class="dr-inw"><input id="dr-target" type="number" min="0"><i>만원</i></span></div>
        </div>
        <button class="btn sm dr-run" id="dr-run" type="button">${ICONS.spark} 내 조건으로 다시 계산</button>
      </div>
      <div class="dr-body" id="dr-body"></div>`;
    $("dr-run").onclick = () => {
      state.reportInputs = {
        area: +$("dr-area").value || 15, rent: +$("dr-rent").value || 0,
        deposit: +$("dr-deposit").value || 0, premium: +$("dr-premium").value || 0,
        capital: +$("dr-capital").value || 0, target: +$("dr-target").value || 0,
      };
      loadDeepReport();
    };
    $("dr-inputs").addEventListener("keydown", (e) => {    // Enter로 바로 재계산
      if (e.key === "Enter" && e.target.tagName === "INPUT") $("dr-run").click();
    });
    loadDeepReport();
  } else {
    srcEl.innerHTML = `<span class="src-badge src-lock">${LOCK_SVG} 유료</span>`;
    box.classList.remove("unlocked");
    const teaser = state.reportText
      ? esc(String(state.reportText).replace(/\s+/g, " ").trim())     // CSS 페이드로 자연스럽게 흐림 (하드 절단 X)
      : "이 자리·업종의 3년 생존율, 손익분기·투자회수, 실패 시나리오와 임대료 협상, 더 나은 대안까지 — 창업 의사결정에 필요한 모든 숫자를 담은 심층 리포트.";
    const feats = [
      ["📊", "손익분기·투자회수 시뮬", "내 예산·목표순익 기준 월 손익과 회수기간"],
      ["🎯", "명확한 판정 + 실행 플레이북", "진입 여부 결론과 살아남는 구체 전략"],
      ["⚠️", "실패 시나리오 3가지 + 대비책", "이 자리가 망하는 경로와 방어법"],
      ["🤝", "적정 임대료 분석", "적정 임대료 vs 제시액 · 협상 목표가"],
      ["📈", "상권 추세 · 더 나은 대안", "뜨는지/지는지 + 더 안전한 자리·업종"],
    ];
    box.innerHTML = `
      <div class="rl-teaser">${teaser}</div>
      <div class="rl-lock">
        <div class="rl-badge">${LOCK_SVG} 프리미엄 심층 리포트</div>
        <ul class="rl-list">
          ${feats.map((f) => `<li><span class="rl-ico">${f[0]}</span><span class="rl-lx"><b>${f[1]}</b><i>${f[2]}</i></span></li>`).join("")}
        </ul>
        <div class="rl-desc">억대가 걸린 결정, <b>숫자로 확인</b>하고 <b>PDF·TXT로 저장</b>해 은행·동업자 설득에 쓰세요.</div>
        <button type="button" class="btn rl-btn" id="report-unlock">₩4,900 결제하고 전체 보기</button>
        <button type="button" class="rl-up" id="report-upgrade">구독 플랜으로 무제한 이용 →</button>
      </div>`;
    $("report-unlock").onclick = () => openCheckout("view");
    $("report-upgrade").onclick = openPlans;
  }
}
function downloadReportTxt() {
  if (!reportUnlocked() || !state.lastPred) return;
  const p = state.lastPred.input;
  const r = state.deepReport;
  let body = `[SurviMap 심층 리포트] ${guFull(p.gu)} · ${p.industry_label}\n${"=".repeat(46)}\n\n`;
  if (r) {
    const f = r.financials, v = r.verdict, rn = r.rent_nego, tr = r.trend;
    body += `■ 종합 판정: ${v.label} — ${v.sub}\n`;
    body += `  3년 생존율 ${r.survival.y3}% (전국 평균 ${r.avg}%, 위험 ${r.hazard_ratio}배)\n\n`;
    body += `■ 손익 (${r.input.area}평 기준)\n`;
    body += `  월 예상매출 ${f.sales}만 / 영업이익 ${f.op_profit}만 (마진 ${f.margin_pct}%)\n`;
    body += `  손익분기 매출 ${f.be_sales}만 (예상매출의 ${f.be_ratio}%)\n`;
    body += `  초기투자 ${f.invest.total}만 / 투자회수 ${f.payback_months == null ? "난망(적자)" : f.payback_months + "개월"}\n`;
    body += `  시나리오 월순익 — 낙관 ${f.scenarios.best.profit} / 기본 ${f.scenarios.base.profit} / 최악 ${f.scenarios.worst.profit}만\n\n`;
    body += `■ 임대료 협상: 제시 ${rn.offered}만 vs 적정 ${rn.fair}만 (${rn.diff_pct > 0 ? "+" : ""}${rn.diff_pct}%) → ${rn.verdict}\n`;
    body += `  임대료/매출 ${rn.rent_to_sales}% (건강선 ${rn.healthy_max}% 이하) · 협상 목표 ${rn.target}만\n\n`;
    body += `■ 상권 추세: ${tr.direction} (최근 2년 유동 ${tr.foot_change_pct}%, 공실 ${tr.vacancy_change_pp}%p)\n\n`;
    body += `■ 실패 시나리오\n${r.failures.map((x, i) => `  ${i + 1}) ${x.title} — ${x.desc}\n     대비책: ${x.guard}`).join("\n")}\n\n`;
    if (r.alternatives.listings.length)
      body += `■ 더 안전한 대안 자리\n${r.alternatives.listings.map((l) => `  · ${guFull(l.gu)} ${l.floor} ${l.area_pyeong}평 / 월 ${l.rent_manwon}만 → 3년 생존 ${l.y3}%`).join("\n")}\n\n`;
    if (r.alternatives.industries.length)
      body += `■ 이 자리에 더 맞는 업종: ${r.alternatives.industries.map((x) => `${x.label}(${x.y3}%)`).join(", ")}\n\n`;
  }
  if (state.reportText) body += `■ AI 총평\n${state.reportText}\n`;
  const blob = new Blob([body], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `SurviMap_${p.gu}_${p.industry_label}.txt`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  toast("심층 리포트를 저장했어요");
}

/* ---------------- 심층 리포트 (유료) ---------------- */
async function loadDeepReport() {
  const p = state.lastPred && state.lastPred.input;
  if (!p) return;
  const body = $("dr-body");
  if (!body) return;
  const ri = state.reportInputs || {};
  const q = new URLSearchParams();
  q.set("gu", p.gu); q.set("industry", p.industry); q.set("lat", p.lat); q.set("lon", p.lon);
  q.set("area", ri.area || 15);
  ["rent", "deposit", "premium"].forEach((k) => { if (ri[k] != null && ri[k] !== "" && ri[k] !== 0) q.set(k, ri[k]); });
  q.set("capital", ri.capital || 0);
  q.set("target", ri.target || 0);
  body.innerHTML = `<div class="dr-load"><span class="spinner"></span> 맥킨지급 심층 리포트를 생성하는 중…</div>`;
  try {
    const r = await api(`/api/deep_report?${q.toString()}`);
    state.deepReport = r;
    state.reportInputs = { area: r.input.area, rent: r.input.rent, deposit: r.input.deposit, premium: r.input.premium, capital: r.input.capital, target: r.input.target };
    ["area", "rent", "deposit", "premium", "capital", "target"].forEach((k) => { const el = $("dr-" + k); if (el) el.value = state.reportInputs[k]; });
    renderDeep(r);
    if (state.pendingPrint) { state.pendingPrint = false; setTimeout(doPrint, 250); }  // 결제→PDF 흐름
  } catch (e) {
    body.innerHTML = `<div class="err">${ICONS.warn}<span>리포트 생성 실패: ${esc(e.message)}</span></div>`;
  }
}

const drWon = (x) => (x == null ? "—" : Number(x).toLocaleString());

function drSpark(series, dir) {
  const w = 240, h = 46, min = Math.min(...series), max = Math.max(...series), rng = (max - min) || 1;
  const pts = series.map((v, i) => `${((i / (series.length - 1)) * w).toFixed(1)},${(h - 4 - ((v - min) / rng) * (h - 8)).toFixed(1)}`).join(" ");
  const col = dir === "상승" ? "var(--good)" : dir === "하락" ? "var(--critical)" : "var(--warning)";
  const last = pts.split(" ").pop().split(",");
  return `<svg class="dr-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${last[0]}" cy="${last[1]}" r="3.2" fill="${col}"/></svg>`;
}

function renderDeep(r) {
  const f = r.financials, v = r.verdict, rn = r.rent_nego, tr = r.trend, co = r.cohort, alt = r.alternatives;
  const w = drWon;
  const opCls = f.op_profit >= 0 ? "pos" : "neg";
  const payback = f.payback_months == null ? "회수 난망" : `${f.payback_months}개월`;
  const plRow = (label, val, kind) => {
    const cls = kind === "total" ? "pl-total" : kind === "base" ? "pl-base" : "";
    const bcls = kind === "total" ? (val >= 0 ? "pos" : "neg") : "";
    return `<div class="pl-row ${cls}"><span>${label}</span><b class="${bcls}">${w(val)}<i>만</i></b></div>`;
  };
  const scen = (label, profit, kind) =>
    `<div class="scen ${kind}"><div class="scen-l">${label}</div><div class="scen-v ${profit >= 0 ? "pos" : "neg"}">${profit > 0 ? "+" : ""}${w(profit)}<i>만</i></div></div>`;
  const failUnit = (x) => (x.title.includes("임대") ? "만원" : "%p");

  const html = `
  <div class="dr-hero v-${v.band}">
    <div class="dr-hero-row">
      <span class="dr-vlabel">${esc(v.label)}</span>
      <span class="dr-vtag">${esc(guFull(r.input.gu))} · ${esc(r.input.industry_label)} · ${r.input.area}평</span>
    </div>
    <div class="dr-vsub">${esc(v.sub)}</div>
    <div class="dr-kpis">
      <div class="dr-kpi"><span>3년 생존율</span><b style="color:${bandColor(r.band)}">${r.survival.y3}%</b></div>
      <div class="dr-kpi"><span>예상 월순익</span><b class="${opCls}">${f.op_profit > 0 ? "+" : ""}${w(f.op_profit)}만</b></div>
      <div class="dr-kpi"><span>투자 회수</span><b class="${f.payback_months == null ? "neg" : ""}">${payback}</b></div>
      <div class="dr-kpi"><span>총 투자금</span><b>${w(f.invest.total)}만</b></div>
    </div>
  </div>

  ${state.reportText ? `<div class="dr-ai"><div class="dr-ai-h">${ICONS.spark} AI 총평</div><div class="dr-ai-t">${esc(state.reportText)}</div></div>` : ""}

  <div class="dr-sec">
    <div class="dr-eyebrow"><span class="dr-no">01</span> 손익분기 · 투자회수 시뮬</div>
    <div class="pl">
      ${plRow("월 예상매출", f.sales, "base")}
      ${plRow("− 원재료·매입", -f.cogs)}
      ${plRow("− 인건비", -f.labor)}
      ${plRow("− 임대료", -f.rent)}
      ${plRow("− 관리비", -f.maint)}
      ${plRow("− 기타(마케팅·공과)", -f.etc)}
      ${plRow("= 영업이익 (월)", f.op_profit, "total")}
    </div>
    <div class="be-wrap">
      <div class="be-labels"><span>손익분기 매출 <b>${w(f.be_sales)}만</b></span><span>영업이익률 <b class="${opCls}">${f.margin_pct}%</b></span></div>
      <div class="be-bar">
        <div class="be-fill ${f.sales >= f.be_sales ? "ok" : "bad"}" style="width:${Math.min(100, (f.sales / Math.max(f.sales, f.be_sales)) * 100).toFixed(1)}%"></div>
        <div class="be-mark" style="left:${Math.min(99, (f.be_sales / Math.max(f.sales, f.be_sales)) * 100).toFixed(1)}%"></div>
      </div>
      <div class="be-cap">${f.sales >= f.be_sales ? `손익분기를 <b class="pos">${w(f.sales - f.be_sales)}만원</b> 넘겨 흑자 구간` : `손익분기까지 매출을 <b class="neg">${w(f.be_sales - f.sales)}만원</b> 더 올려야 함`}</div>
    </div>
    <div class="scen-row">
      ${scen("낙관 (상위 25%)", f.scenarios.best.profit, "good")}
      ${scen("기본", f.scenarios.base.profit, "base")}
      ${scen("최악 (하위 25%)", f.scenarios.worst.profit, "bad")}
    </div>
    <div class="dr-invest">
      <div class="di"><span>초기 투자금</span><b>${w(f.invest.total)}만원</b><i>보증금 ${w(f.invest.deposit)} · 권리금 ${w(f.invest.premium)} · 인테리어 ${w(f.invest.interior)} · 운영자금 ${w(f.invest.opening)}</i></div>
      <div class="di"><span>투자 회수기간</span><b class="${f.payback_months == null ? "neg" : ""}">${payback}</b><i>회수대상 ${w(f.invest.sunk)}만원(권리+인테리어+운영, 보증금 제외)</i></div>
      ${f.target ? `<div class="di"><span>목표 월순익 대비</span><b class="${f.target_gap >= 0 ? "pos" : "neg"}">${f.target_gap > 0 ? "+" : ""}${w(f.target_gap)}만</b><i>목표 ${w(f.target)}만원 · ${f.target_gap >= 0 ? "달성 가능" : "미달"}</i></div>` : ""}
    </div>
  </div>

  <div class="dr-sec">
    <div class="dr-eyebrow"><span class="dr-no">02</span> 살아남는 실행 플레이북</div>
    ${r.playbook.strengths.length ? `<div class="pb-h pos">받쳐주는 강점</div>${r.playbook.strengths.map((s) => `<div class="pb-row"><span class="pb-pp pos">+${s.pp}%p</span><span>${esc(s.label)}</span></div>`).join("")}` : ""}
    <div class="pb-h neg">개선해야 살아남는다</div>
    ${r.playbook.actions.length ? r.playbook.actions.map((a) => `<div class="pb-act"><div class="pb-act-h"><span class="pb-pp neg">${a.pp}%p</span><b>${esc(a.label)}</b></div><div class="pb-act-t">${esc(a.action)}</div></div>`).join("") : `<div class="dr-note">두드러진 약점이 없습니다. 기본기(입지·객단가)만 지키면 안정적입니다.</div>`}
  </div>

  <div class="dr-sec">
    <div class="dr-eyebrow"><span class="dr-no">03</span> 이렇게 망한다 — 실패 시나리오</div>
    ${r.failures.map((x, i) => `<div class="fail"><div class="fail-h"><span class="fail-n">${i + 1}</span><b>${esc(x.title)}</b><span class="fail-imp">${x.impact}${failUnit(x)}</span></div><div class="fail-d">${esc(x.desc)}</div><div class="fail-g"><b>대비책</b> ${esc(x.guard)}</div></div>`).join("")}
  </div>

  <div class="dr-sec">
    <div class="dr-eyebrow"><span class="dr-no">04</span> 적정 임대료 분석</div>
    <div class="rn-head"><span class="rn-verdict v-${rn.band}">${esc(rn.verdict)}</span><span class="rn-sum">제시 <b>${w(rn.offered)}만</b> vs 적정 <b>${w(rn.fair)}만</b> <em class="${rn.diff_pct > 0 ? "neg" : "pos"}">(${rn.diff_pct > 0 ? "+" : ""}${rn.diff_pct}%)</em></span></div>
    <div class="rn-bars">
      <div class="rn-line"><span>제시</span><div class="rn-track"><div class="rn-fill off" style="width:${Math.min(100, (rn.offered / Math.max(rn.offered, rn.fair)) * 100).toFixed(1)}%"></div></div><em>${w(rn.offered)}만</em></div>
      <div class="rn-line"><span>적정</span><div class="rn-track"><div class="rn-fill fair" style="width:${Math.min(100, (rn.fair / Math.max(rn.offered, rn.fair)) * 100).toFixed(1)}%"></div></div><em>${w(rn.fair)}만</em></div>
    </div>
    <div class="dr-note">평당 제시 ${rn.per_pyeong}만 vs 적정 ${rn.fair_per_pyeong}만 · 임대료/매출 <b class="${rn.rent_to_sales > rn.healthy_max ? "neg" : "pos"}">${rn.rent_to_sales}%</b> (건강선 ${rn.healthy_max}% 이하)</div>
    <div class="rn-target">🎯 협상 목표가 <b>월 ${w(rn.target)}만원</b> — 위 적정가·주변 시세를 근거로 제시하세요.</div>
  </div>

  <div class="dr-sec">
    <div class="dr-eyebrow"><span class="dr-no">05</span> 상권 추세 — 뜨는가 지는가</div>
    <div class="tr-head">
      <span class="tr-dir d-${tr.direction === "상승" ? "up" : tr.direction === "하락" ? "down" : "flat"}">${tr.direction}</span>
      ${drSpark(tr.series, tr.direction)}
    </div>
    <div class="tr-stats">
      <div><span>유동인구 (최근 2년)</span><b class="${tr.foot_change_pct >= 0 ? "pos" : "neg"}">${tr.foot_change_pct > 0 ? "+" : ""}${tr.foot_change_pct}%</b></div>
      <div><span>공실률 (최근 2년)</span><b class="${tr.vacancy_change_pp <= 0 ? "pos" : "neg"}">${tr.vacancy_change_pp > 0 ? "+" : ""}${tr.vacancy_change_pp}%p</b></div>
    </div>
    <div class="dr-note">※ 추세는 프로토타입 추정치입니다. 실데이터(생활인구·R-ONE 공실) 연결 시 실측으로 대체됩니다.</div>
  </div>

  <div class="dr-sec">
    <div class="dr-eyebrow"><span class="dr-no">06</span> 더 나은 대안</div>
    ${alt.listings.length ? `<div class="alt-h">예산 안 · 3년 생존율이 더 높은 자리</div>${alt.listings.map((l) => `<button type="button" class="alt-row" data-lid="${esc(l.id)}"><span class="alt-main"><b>${esc(guFull(l.gu))} · ${esc(l.floor)} ${l.area_pyeong}평</b><i>보증 ${w(l.deposit_manwon)} / 월 ${w(l.rent_manwon)}만 · ${esc(l.verdict)}</i></span><span class="alt-y3" style="color:${bandColor(l.band)}">${l.y3}%</span></button>`).join("")}` : `<div class="dr-note">예산 조건에서 이 자리보다 뚜렷이 나은 대안을 찾지 못했습니다 — 현재 자리가 경쟁력 있다는 신호입니다.</div>`}
    ${alt.industries.length ? `<div class="alt-h">이 자리에 더 맞는 업종</div>${alt.industries.map((x) => `<button type="button" class="alt-row alt-ind" data-key="${esc(x.industry)}"><span class="alt-main"><b>${esc(x.label)}</b><i>같은 자리에서 더 오래 살아남는 업종</i></span><span class="alt-y3" style="color:${bandColor(x.band)}">${x.y3}%</span></button>`).join("")}` : ""}
  </div>

  <div class="dr-sec">
    <div class="dr-eyebrow"><span class="dr-no">07</span> 실측 근거 — 유사 점포 이력</div>
    <div class="co-grid">
      <div class="co"><span>실측 코호트</span><b>${w(co.n)}개</b></div>
      <div class="co"><span>3년 생존</span><b style="color:${bandColor(bandFor(co.survival_3y))}">${co.survival_3y}%</b></div>
      <div class="co"><span>중위 생존</span><b>${co.median_reached ? co.median_months + "개월" : "60개월+"}</b></div>
      <div class="co"><span>반경 ${co.radius_m}m 동종</span><b>약 ${co.competition_count}개</b></div>
    </div>
    <div class="dr-note">동일 지역·업종의 유사 점포 생존 이력(Kaplan–Meier)과 반경 내 실제 경쟁 밀도를 근거로 산출했습니다.</div>
  </div>

  <div class="dr-foot">
    <div class="dr-prov">${esc((r.provenance && r.provenance.note) || "")}</div>
    <div class="report-dl">
      <button type="button" class="ract" id="report-txt"><svg class="icon" viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m7 12 5 5 5-5"/><path d="M5 21h14"/></svg> TXT 저장</button>
      <button type="button" class="ract" id="report-pdf2"><svg class="icon" viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m7 12 5 5 5-5"/><path d="M5 21h14"/></svg> PDF 저장</button>
    </div>
  </div>`;

  $("dr-body").innerHTML = html;
  staggerReveal($("dr-body"));                              // 섹션 순차 등장
  $("report-txt").onclick = downloadReportTxt;
  $("report-pdf2").onclick = exportPDF;
  document.querySelectorAll("#dr-body .alt-row[data-lid]").forEach((el) => {
    el.onclick = () => { showTab("summary"); openListing(el.dataset.lid); };
  });
  document.querySelectorAll("#dr-body .alt-ind[data-key]").forEach((el) => {
    el.onclick = () => { selectIndustry(el.dataset.key); };
  });
}
function openCheckout(then) {
  if (!state.lastPred) return;
  state.payThen = then || "view";
  state.payKey = reportKey();
  const p = state.lastPred.input;
  $("pay-item").textContent = `${guFull(p.gu)} · ${p.industry_label} 생존 리포트`;
  setPayMethod("card");
  openModal("pay-modal");
}
function closePay() { closeModal("pay-modal"); }
function setPayMethod(m) {
  document.querySelectorAll("#pay-methods .pm").forEach((b) => b.classList.toggle("active", b.dataset.m === m));
  $("pay-card").classList.toggle("hidden", m !== "card");
}
function payNow() {
  const btn = $("pay-run");
  if (btn.disabled) return;
  const orig = btn.textContent;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner" style="border-color:rgba(255,255,255,.45);border-top-color:#fff"></span> 결제 중…`;
  setTimeout(() => {
    if (state.payKey) { state.paid[state.payKey] = true; savePaid(); }
    btn.disabled = false; btn.textContent = orig;
    closePay();
    if (state.payThen === "pdf") state.pendingPrint = true;  // 심층 리포트 렌더 완료 후 인쇄
    renderReportGated();
    toast("결제 완료 🎉 리포트가 열렸어요");
  }, 1100);
}

/* ---------------- what-if ---------------- */
function resetWhatIf() {
  resetSim();
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
  if (!busyBtn($("whatif-btn"), true, "")) return;         // 중복 질문 방지
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
    const badge = r.source === "llm" ? `<span class="src-badge src-claude" style="margin-top:8px">${ICONS.spark} AI</span>` : `<span class="src-badge src-template" style="margin-top:8px">템플릿</span>`;
    ans.innerHTML = head + `<div>${esc(r.text)}</div><div style="margin-top:8px">${badge}</div>`;
  } catch (e) { ans.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span></div>`; }
  finally { busyBtn($("whatif-btn"), false); }
}

/* ---------------- 모달 공통 (열림/닫힘 애니메이션 + 포커스 관리) ---------------- */
let modalLastFocus = null;
function openModal(id) {
  modalLastFocus = document.activeElement;
  const ov = $(id);
  ov.classList.remove("hidden", "closing");
  const c = ov.querySelector(".modal-close");
  if (c) c.focus();
}
function closeModal(id) {
  const ov = $(id);
  if (ov.classList.contains("hidden") || ov.classList.contains("closing")) return;
  if (REDUCE_MOTION) { ov.classList.add("hidden"); }
  else {
    ov.classList.add("closing");
    setTimeout(() => { ov.classList.add("hidden"); ov.classList.remove("closing"); }, 190);
  }
  if (modalLastFocus && modalLastFocus.focus) modalLastFocus.focus();
}
/* 모든 모달: Tab 포커스 트랩 */
document.querySelectorAll(".modal-overlay").forEach((ov) => {
  ov.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = Array.from(ov.querySelectorAll('button, [href], input, select, [tabindex]:not([tabindex="-1"])'))
      .filter((el) => el.offsetParent !== null && !el.disabled);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
});

/* ---------------- 소개 모달 ---------------- */
function openAbout() {
  openModal("about-modal");
  $("about-btn").setAttribute("aria-expanded", "true");
}
function closeAbout() {
  closeModal("about-modal");
  $("about-btn").setAttribute("aria-expanded", "false");
}
$("about-btn").onclick = openAbout;
$("about-close").onclick = closeAbout;
$("about-modal").addEventListener("click", (e) => { if (e.target === $("about-modal")) closeAbout(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeAbout(); closeBudget(); closePay(); closeAuth(); closePlans(); closeAccount(); closeCompare(); } });

/* ---------------- 분석창 접기/펼치기 ---------------- */
function togglePanel() {
  const hidden = document.body.classList.toggle("panel-hidden");
  const btn = $("panel-toggle");
  btn.setAttribute("aria-expanded", hidden ? "false" : "true");
  btn.title = hidden ? "분석창 펼치기" : "분석창 접기";
}

/* ---------------- 탭 메뉴 ---------------- */
function moveTabIndicator() {
  const bar = $("tabbar");
  let ind = bar.querySelector(".tab-ind");
  if (!ind) { ind = document.createElement("span"); ind.className = "tab-ind"; ind.setAttribute("aria-hidden", "true"); bar.prepend(ind); }
  const act = bar.querySelector(".tab.active");
  if (!act) return;
  ind.style.width = `${act.offsetWidth}px`;
  ind.style.transform = `translateX(${act.offsetLeft}px)`;
}
function showTab(name) {
  state.tab = name;
  document.querySelectorAll("#tabbar .tab").forEach((t) => {
    const on = t.dataset.tab === name;
    t.classList.toggle("active", on);
    t.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll("#tab-panels .tabpane").forEach((p) => p.classList.toggle("is-hidden", p.dataset.pane !== name));
  moveTabIndicator();
  // 탭바가 화면 위로 밀려나 있으면 새 탭 내용이 보이도록 살짝 스크롤 보정
  const pb = $("panel-body"), tb = $("tabbar");
  if (pb && tb) {
    const off = tb.getBoundingClientRect().top - pb.getBoundingClientRect().top;
    if (off < 0) pb.scrollTo({ top: pb.scrollTop + off - 10, behavior: REDUCE_MOTION ? "auto" : "smooth" });
  }
  const pane = document.querySelector(`#tab-panels .tabpane[data-pane="${name}"]`);
  if (pane) playBars(pane);                     // 숨겨져 있던 게이지 막대 재생
  if (name === "curve" && state.chart) requestAnimationFrame(() => state.chart.resize());
  if (name === "fit") loadFit();
  if (name === "risk") loadInfra();
}

/* 스켈레톤 로딩 (스피너 대신 콘텐츠 자리 잡기) */
const skel = (n, h) => Array.from({ length: n }, (_, i) =>
  `<div class="skel" style="height:${h}px;animation-delay:${i * 90}ms"></div>`).join("");

/* ---------------- 업종추천 (이 자리에 뭐가 맞나) ---------------- */
function fitKey() { return state.loc ? `${state.loc.gu}:${state.loc.lat}:${state.loc.lon}` : null; }
async function loadFit() {
  if (!state.loc || !state.loc.gu) return;
  const key = fitKey();
  if (state.fitFor === key) return;                       // 현재 지점 이미 계산됨
  const box = $("fit-list");
  box.innerHTML = skel(6, 42);
  try {
    const r = await api(`/api/industry_fit?gu=${encodeURIComponent(state.loc.gu)}&lat=${state.loc.lat}&lon=${state.loc.lon}`);
    if (fitKey() !== key) return;                          // 응답 오기 전에 위치가 바뀜
    state.fitFor = key;
    renderFit(r.industries);
  } catch (e) {
    box.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span><button type="button" class="ract" id="fit-retry">다시 시도</button></div>`;
    const rb = $("fit-retry"); if (rb) rb.onclick = () => { state.fitFor = null; loadFit(); };
  }
}
function renderFit(list) {
  const cur = state.industry;
  const maxv = Math.max(100, ...list.map((r) => r.y3));
  const curY3 = (list.find((r) => r.industry === cur) || {}).y3;
  const top = list[0];
  const topBeatsCurrent = top && top.industry !== cur && curY3 != null && top.y3 > curY3;
  $("fit-list").innerHTML = list.map((r, i) => {
    const isCur = r.industry === cur;
    const d = (!isCur && curY3 != null) ? Math.round((r.y3 - curY3) * 10) / 10 : null;   // 현재 업종 대비 %p
    const delta = d == null ? "" :
      `<span class="fit-delta ${d > 0 ? "up" : d < 0 ? "down" : ""}">${d > 0 ? "▲" : d < 0 ? "▼" : ""}${Math.abs(d)}%p</span>`;
    const rec = (i === 0 && topBeatsCurrent) ? ' <em class="fit-rec">추천</em>' : "";
    return `<button type="button" class="fit-row ${isCur ? "me" : ""} ${i === 0 && topBeatsCurrent ? "top" : ""}" data-key="${r.industry}">
      <span class="fit-rank">${i + 1}</span>
      <span class="fit-name">${esc(r.label)}${isCur ? ' <em>현재</em>' : rec}</span>
      <span class="fit-bar-track"><span class="fit-bar" style="width:0;background:${bandColor(r.band)}" data-w="${(r.y3 / maxv) * 100}"></span></span>
      <span class="fit-nums"><span class="fit-pct" style="color:${bandColor(r.band)}">${r.y3}%</span>${delta}</span>
    </button>`;
  }).join("");
  playBars($("fit-list"));
  document.querySelectorAll("#fit-list .fit-row").forEach((el) => {
    el.onclick = () => selectIndustry(el.dataset.key);
  });
}

/* ---------------- 입지 인프라 (실측 · OSM) ---------------- */
function infraKey() { return state.loc ? `${state.loc.lat.toFixed(5)}:${state.loc.lon.toFixed(5)}` : null; }
function infraRetryBtn() {
  const rb = $("infra-retry");
  if (rb) rb.onclick = () => { state.infraFor = null; loadInfra(); };
}
async function loadInfra() {
  if (!state.loc) return;
  const key = infraKey();
  if (state.infraFor === key) return;
  const box = $("infra");
  box.innerHTML = `<div class="skel-note">OpenStreetMap 실측 조회 중 — 최대 10초 정도 걸릴 수 있어요</div>` + skel(3, 62);
  try {
    const c = await api(`/api/context?lat=${state.loc.lat}&lon=${state.loc.lon}`);
    if (infraKey() !== key) return;                        // 응답 오기 전에 위치가 바뀜
    state.infraFor = key;
    renderInfra(c);
  } catch (e) {
    box.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span><button type="button" class="ract" id="infra-retry">다시 시도</button></div>`;
    infraRetryBtn();
  }
}
function renderInfra(c) {
  if (!c || !c.available) {
    $("infra").innerHTML = `<div class="so-hint">실측 인프라 조회에 실패했어요. <button type="button" class="ract" id="infra-retry">다시 시도</button></div>`;
    infraRetryBtn();
    return;
  }
  const t = c.transit, a = c.anchors;
  const dist = (m) => (m == null ? "반경 밖" : m < 1000 ? `최단 ${m}m` : `최단 ${(m / 1000).toFixed(1)}km`);
  const transit = [
    { k: "지하철역", v: t.subway.count, s: dist(t.subway.nearest_m) },
    { k: "버스정류장", v: t.bus.count, s: dist(t.bus.nearest_m) },
    { k: "주차장", v: t.parking.count, s: dist(t.parking.nearest_m) },
  ];
  const anchors = [
    { k: "대학", v: a.university }, { k: "병원", v: a.hospital }, { k: "마트·백화점", v: a.mall },
    { k: "영화관", v: a.cinema }, { k: "관공서", v: a.government }, { k: "학교", v: a.school },
  ];
  $("infra").innerHTML = `
    <div class="infra-sub">교통 · 접근성</div>
    <div class="infra-grid">${transit.map((x) => `
      <div class="infra"><div class="if-k">${esc(x.k)}</div>
        <div class="if-v">${x.v}<span>곳</span></div><div class="if-s">${esc(x.s)}</div></div>`).join("")}</div>
    <div class="infra-sub">앵커 · 집객시설</div>
    <div class="anchor-grid">${anchors.map((x) => `
      <div class="anchor ${x.v > 0 ? "has" : ""}"><span class="an-k">${esc(x.k)}</span><span class="an-v">${x.v}</span></div>`).join("")}</div>
    <div class="risk-note">모델의 '유동인구·배후수요' 지수를 실제 교통·집객 시설(OpenStreetMap)로 교차검증하는 참고 지표입니다.</div>`;
}

/* ---------------- 예산 추천 ---------------- */
function openBudget() {
  $("bf-industry").textContent = (state.meta.industries.find((i) => i.key === state.industry) || {}).label || state.industry;
  $("bf-scope").value = state.scope;
  $("rec-list").innerHTML = `<div class="rec-hint">업종 <b>${esc($("bf-industry").textContent)}</b> 기준. 예산을 정하고 <b>추천 받기</b>를 누르세요.</div>`;
  openModal("budget-modal");
}
function closeBudget() { closeModal("budget-modal"); }
async function runRecommend() {
  if (!busyBtn($("bf-run"), true, "탐색 중…")) return;   // 중복 클릭 방지
  const rent = Math.max(0, parseInt($("bf-rent").value, 10) || 100000);
  const dep = Math.max(0, parseInt($("bf-deposit").value, 10) || 100000000);
  const area = Math.max(0, parseInt($("bf-area").value, 10) || 0);
  const scope = $("bf-scope").value;
  const box = $("rec-list");
  box.innerHTML = skel(5, 56);
  try {
    const r = await api(`/api/recommend?industry=${encodeURIComponent(state.industry)}&scope=${encodeURIComponent(scope)}&max_rent=${rent}&max_deposit=${dep}&min_area=${area}`);
    renderRec(r.results);
  } catch (e) { box.innerHTML = `<div class="err">${ICONS.warn}<span>${esc(e.message)}</span></div>`; }
  finally { busyBtn($("bf-run"), false); }
}
function renderRec(list) {
  state._recList = list;
  if (!list.length) { $("rec-list").innerHTML = `<div class="rec-empty">조건에 맞는 매물이 없어요. 예산을 넓혀보세요.</div>`; return; }
  const csvLabel = planHas("csv") ? "CSV 내보내기" : "CSV · 법인 전용 🔒";
  $("rec-list").innerHTML = `<div class="rec-cap"><span>예산 안 · 생존율 높은 순 ${list.length}곳</span><button type="button" class="ract rec-csv" id="rec-csv">${csvLabel}</button></div>` + list.map((r, i) => `
    <button type="button" class="rec-row" data-id="${esc(r.id)}">
      <span class="rec-rank">${i + 1}</span>
      <span class="rec-main">
        <span class="rec-title">${esc(guFull(r.gu))} · ${esc(r.floor)} ${r.area_pyeong}평</span>
        <span class="rec-sub">보증 ${r.deposit_manwon.toLocaleString()} / 월 ${r.rent_manwon.toLocaleString()}만원 · 임대료 ${esc(r.verdict)}</span>
      </span>
      <span class="rec-y3"><b style="color:${bandColor(r.band)}">${r.y3}%</b><i>3년</i></span>
    </button>`).join("");
  document.querySelectorAll("#rec-list .rec-row").forEach((el) => {
    el.onclick = () => { closeBudget(); openListing(el.dataset.id); };
  });
  const csvEl = $("rec-csv"); if (csvEl) csvEl.onclick = exportRecCsv;
}

/* 비동기 버튼 잠금 + 스피너 (중복 클릭 방지) */
function busyBtn(btn, on, label) {
  if (!btn) return;
  if (on) {
    if (btn.disabled) return false;
    btn.dataset.orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner" style="border-color:rgba(255,255,255,.45);border-top-color:#fff"></span> ${label || "처리 중…"}`;
  } else {
    btn.disabled = false;
    if (btn.dataset.orig) { btn.innerHTML = btn.dataset.orig; delete btn.dataset.orig; }
  }
  return true;
}

/* ---------------- 공유 · PDF ---------------- */
function toast(msg) {
  let t = $("toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(state._toastT);
  state._toastT = setTimeout(() => t.classList.remove("show"), 2200);
}
function copyText(txt) {
  if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(txt);
  return new Promise((res, rej) => {                       // 구형/비보안 컨텍스트 폴백
    const i = document.createElement("input");
    i.value = txt; i.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(i); i.select();
    try { document.execCommand("copy") ? res() : rej(new Error("copy 실패")); }
    catch (e) { rej(e); } finally { i.remove(); }
  });
}
function shareLink() {
  if (!state.loc) return;
  const q = new URLSearchParams();
  if (state.loc.gu) q.set("gu", state.loc.gu);
  if (state.industry) q.set("industry", state.industry);
  q.set("lat", state.loc.lat); q.set("lon", state.loc.lon);
  const url = `${location.origin}${location.pathname}?${q.toString()}`;
  copyText(url).then(() => {
    toast("분석 링크가 복사됐어요");
    const b = $("share-btn");                              // 버튼 자체에도 성공 표시
    if (b.dataset.orig) return;
    b.dataset.orig = b.innerHTML;
    b.classList.add("ok");
    b.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg><span>복사됨</span>`;
    setTimeout(() => { b.innerHTML = b.dataset.orig; delete b.dataset.orig; b.classList.remove("ok"); }, 1400);
  }).catch(() => window.prompt("아래 링크를 복사하세요 (Ctrl+C)", url));
}
function exportPDF() {
  if (!reportUnlocked()) { openCheckout("pdf"); return; }   // 리포트 포함 저장은 결제/구독 후
  doPrint();
}
/* 헤더 PDF 버튼: 미결제 시 자물쇠 표시 (클릭하면 결제창) */
const DL_SVG = '<svg class="icon" viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m7 12 5 5 5-5"/><path d="M5 21h14"/></svg>';
function updatePdfLock() {
  const b = $("pdf-btn"); if (!b) return;
  const locked = !reportUnlocked();
  b.classList.toggle("locked", locked);
  b.innerHTML = (locked ? LOCK_SVG : DL_SVG) + `<span>PDF</span>`;
  b.title = locked ? "PDF 저장은 결제·구독 후 열려요 (클릭 시 결제창)" : "PDF로 저장(인쇄)";
}
function doPrint() {
  // 인쇄 CSS가 '리포트 탭'만 문서 흐름으로 펼쳐 출력 — 화면 탭 상태를 건드리지 않음
  requestAnimationFrame(() => window.print());
}

/* ---------------- 실제 점포 (OSM) ---------------- */
function toggleStores() {
  state.storesOn = !state.storesOn;
  const b = $("stores-toggle");
  b.classList.toggle("on", state.storesOn);
  b.setAttribute("aria-pressed", state.storesOn ? "true" : "false");
  if (state.storesOn) loadStores(); else clearStores();
}
async function loadStores() {
  if (!state.storesOn || !state.loc || !state.industry) { clearStores(); return; }
  const key = `${state.industry}:${state.loc.lat.toFixed(4)}:${state.loc.lon.toFixed(4)}`;
  if (state.storesKey === key && state.storesMarkers.length) return;
  const b = $("stores-toggle"); b.classList.add("loading-b");
  try {
    const r = await api(`/api/stores?lat=${state.loc.lat}&lon=${state.loc.lon}&industry=${encodeURIComponent(state.industry)}`);
    if (!state.storesOn) return;
    state.storesKey = key;
    renderStores(r.stores);
    if (!r.stores.length) toast("이 반경엔 지도에 등록된 실제 점포가 없어요");
  } catch (e) { clearStores(); }
  finally { b.classList.remove("loading-b"); }
}
function renderStores(list) {
  state.storesLayer.clearLayers();
  state.storesMarkers = [];
  list.forEach((s) => {
    const icon = L.divIcon({ html: `<div class="store-dot"></div>`, className: "bubble-wrap", iconSize: [12, 12], iconAnchor: [6, 6] });
    const m = L.marker([s.lat, s.lon], { icon, zIndexOffset: 400 })
      .bindTooltip(esc(s.name), { direction: "top", offset: [0, -6] });
    m.addTo(state.storesLayer);
    state.storesMarkers.push(m);
  });
}
function clearStores() {
  if (state.storesLayer) state.storesLayer.clearLayers();
  state.storesMarkers = []; state.storesKey = null;
}

/* ---------------- what-if 시뮬레이터 ---------------- */
/* 슬라이더 트랙: 중앙(0)→현재값 구간을 브랜드색으로 채움 */
function paintSlider(el) {
  const min = +el.min, max = +el.max, v = +el.value;
  const pct = ((v - min) / (max - min)) * 100;
  const lo = Math.min(50, pct), hi = Math.max(50, pct);
  el.style.background = `linear-gradient(90deg,#e9eef4 0%,#e9eef4 ${lo}%,#3182f6 ${lo}%,#3182f6 ${hi}%,#e9eef4 ${hi}%,#e9eef4 100%)`;
}
function runSim() {
  if (!state.lastPred) return;
  const rent = parseInt($("sim-rent").value, 10) || 0;
  const foot = parseInt($("sim-foot").value, 10) || 0;
  const comp = parseInt($("sim-comp").value, 10) || 0;
  $("sim-rent-v").textContent = `${rent > 0 ? "+" : ""}${rent}%`;
  $("sim-foot-v").textContent = `${foot > 0 ? "+" : ""}${foot}%`;
  $("sim-comp-v").textContent = `${comp > 0 ? "+" : ""}${comp}%`;
  ["sim-rent", "sim-foot", "sim-comp"].forEach((id) => paintSlider($(id)));
  clearTimeout(state._simT);
  state._simT = setTimeout(async () => {
    const p = state.lastPred.input;
    const seq = ++state._simSeq;                 // 늦게 온 이전 응답이 최신 결과를 덮지 않게
    const out = $("sim-out"); out.classList.add("pending");
    try {
      const r = await api(`/api/whatif_sim?gu=${encodeURIComponent(p.gu)}&industry=${encodeURIComponent(p.industry)}&lat=${p.lat}&lon=${p.lon}&rent=${rent / 100}&foot=${foot / 100}&comp=${comp / 100}`);
      if (seq !== state._simSeq) return;
      renderSimOut(r);
    } catch (e) {
      if (seq === state._simSeq) out.innerHTML = `<div class="so-hint">계산에 실패했어요 — 슬라이더를 다시 움직여 보세요.</div>`;
    } finally {
      if (seq === state._simSeq) out.classList.remove("pending");
    }
  }, 180);
}
function renderSimOut(r) {
  const rows = [["1년", "y1"], ["3년", "y3"], ["5년", "y5"]];
  $("sim-out").innerHTML = rows.map(([lab, k]) => {
    const b = r.base[k], a = r.adjusted[k], d = Math.round((a - b) * 10) / 10;
    const cls = d > 0 ? "up" : d < 0 ? "down" : "";
    const arrow = d > 0 ? "▲" : d < 0 ? "▼" : "—";
    return `<div class="so-row"><span class="so-k">${lab}</span>
      <span class="so-base">${b}%</span><span class="so-arr">→</span>
      <span class="so-adj" style="color:${bandColor(bandFor(a))}">${a}%</span>
      <span class="so-delta ${cls}">${arrow} ${Math.abs(d)}%p</span></div>`;
  }).join("");
}
function resetSim() {
  ["sim-rent", "sim-foot", "sim-comp"].forEach((id) => { const el = $(id); if (el) { el.value = 0; paintSlider(el); } });
  ["sim-rent-v", "sim-foot-v", "sim-comp-v"].forEach((id) => { const el = $(id); if (el) el.textContent = "0%"; });
  const so = $("sim-out"); if (so) so.innerHTML = `<div class="so-hint">위 3개 슬라이더를 움직이면 생존율이 실시간으로 바뀝니다.</div>`;
}

/* ---------------- 계정 · 플랜 (B2C / B2B) ---------------- */
const PERSON_SVG = '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>';
const PLANS = {
  free:       { key: "free", type: "personal", name: "Free", priceLabel: "₩0",
                perks: ["지도·요약·업종추천 무료", "실제 점포·예산추천(기본)", "리포트는 건당 ₩4,900"],
                feat: { report: false, save: false, whatif: "basic", csv: false, api: false, seats: 1 } },
  pro:        { key: "pro", type: "personal", name: "개인 Pro", priceLabel: "₩9,900/월",
                badge: "가장 인기", highlight: true, sub: "리포트 2건이면 본전",
                perks: ["리포트 무제한 열람", "PDF·TXT 저장", "what-if 시뮬레이터 풀", "예비 창업자용"],
                feat: { report: true, save: true, whatif: "full", csv: false, api: false, seats: 1 } },
  business:   { key: "business", type: "business", name: "Business", priceLabel: "₩99,000/월",
                perks: ["Pro 전체 기능", "팀 5석 공유", "CSV 데이터 내보내기", "브랜딩 리포트·우선지원"],
                feat: { report: true, save: true, whatif: "full", csv: true, api: false, seats: 5 } },
  enterprise: { key: "enterprise", type: "business", name: "Enterprise", priceLabel: "문의",
                perks: ["Business 전체", "생존 스코어 API", "대량·배치 조회", "전용 지원·SLA"],
                feat: { report: true, save: true, whatif: "full", csv: true, api: true, seats: "무제한" } },
};
function usersDB() { try { return JSON.parse(localStorage.getItem("survimap_users") || "{}") || {}; } catch (e) { return {}; } }
function saveUsersDB(db) { try { localStorage.setItem("survimap_users", JSON.stringify(db)); } catch (e) { /* */ } }
function loadUser() { try { const s = localStorage.getItem("survimap_session"); const db = usersDB(); state.user = (s && db[s]) ? db[s] : null; } catch (e) { state.user = null; } }
function currentPlan() { return state.user ? (PLANS[state.user.plan] || PLANS.free) : PLANS.free; }
function planHas(f) { const v = currentPlan().feat[f]; return f === "whatif" ? v : !!v; }
function reportUnlocked() { return planHas("report") || isPaid(); }

function renderAccountBtn() {
  const b = $("account-btn");
  if (state.user) {
    const pl = currentPlan();
    b.classList.add("logged");
    b.innerHTML = `<span class="acc-name">${esc(state.user.name || state.user.email)}</span><span class="acc-plan plan-${pl.key}">${esc(pl.name)}</span>`;
    b.title = "계정 · 플랜";
  } else {
    b.classList.remove("logged");
    b.innerHTML = `${PERSON_SVG}<span>로그인</span>`;
    b.title = "로그인 · 회원가입";
  }
}

/* 회원가입 / 로그인 */
function openAuth(mode) { setAuthTab(mode || "signup"); setSignupType("personal"); $("li-err").classList.add("hidden"); openModal("auth-modal"); }
function closeAuth() { closeModal("auth-modal"); }
function setAuthTab(mode) {
  document.querySelectorAll("#auth-tabs .atab").forEach((t) => t.classList.toggle("active", t.dataset.tab === mode));
  $("signup-pane").classList.toggle("hidden", mode !== "signup");
  $("login-pane").classList.toggle("hidden", mode !== "login");
}
function setSignupType(t) {
  state._suType = t;
  document.querySelectorAll("#su-type .seg-b").forEach((b) => b.classList.toggle("active", b.dataset.t === t));
  $("su-biz").classList.toggle("hidden", t !== "business");
  renderSignupPlans(t);
}
function renderSignupPlans(t) {
  const keys = t === "business" ? ["business", "enterprise"] : ["free", "pro"];
  state._suPlan = keys[0];
  $("su-plans").innerHTML = keys.map((k) => { const p = PLANS[k]; return `
    <button type="button" class="plan-pick ${k === state._suPlan ? "sel" : ""}" data-k="${k}">
      <div class="pp-top"><span class="pp-name">${esc(p.name)}</span><span class="pp-price">${esc(p.priceLabel)}</span></div>
      <div class="pp-perk">${esc(p.perks[0])}</div></button>`; }).join("");
  document.querySelectorAll("#su-plans .plan-pick").forEach((el) => el.onclick = () => {
    state._suPlan = el.dataset.k;
    document.querySelectorAll("#su-plans .plan-pick").forEach((x) => x.classList.toggle("sel", x.dataset.k === el.dataset.k));
  });
}
function doSignup() {
  const t = state._suType || "personal";
  const email = $("su-email").value.trim();
  if (!email) { toast("이메일을 입력하세요"); return; }
  const user = { type: t, name: $("su-name").value.trim() || (t === "business" ? "담당자" : "회원"), email, plan: state._suPlan };
  if (t === "business") { user.company = $("su-company").value.trim(); user.bizNo = $("su-bizno").value.trim(); }
  const db = usersDB(); db[email] = user; saveUsersDB(db);
  try { localStorage.setItem("survimap_session", email); } catch (e) { /* */ }
  state.user = user; closeAuth(); renderAccountBtn(); renderReportGated();
  toast(`${PLANS[user.plan].name} · ${t === "business" ? "법인" : "개인"} 가입 완료 🎉`);
}
function doLogin() {
  const email = $("li-email").value.trim(); const db = usersDB();
  if (!db[email]) { $("li-err").textContent = "가입된 계정이 없어요. 먼저 회원가입 해주세요."; $("li-err").classList.remove("hidden"); return; }
  try { localStorage.setItem("survimap_session", email); } catch (e) { /* */ }
  state.user = db[email]; closeAuth(); renderAccountBtn(); renderReportGated(); toast("로그인되었습니다");
}
function logout() { try { localStorage.removeItem("survimap_session"); } catch (e) { /* */ } state.user = null; closeAccount(); renderAccountBtn(); renderReportGated(); toast("로그아웃되었습니다"); }

/* 계정 메뉴 */
function openAccountMenu() {
  if (!state.user) { openAuth("signup"); return; }
  const pl = currentPlan(), u = state.user;
  $("account-body").innerHTML = `
    <div class="ac-row"><span>유형</span><b>${u.type === "business" ? "법인 (B2B)" : "개인 (B2C)"}</b></div>
    ${u.company ? `<div class="ac-row"><span>회사</span><b>${esc(u.company)}</b></div>` : ""}
    <div class="ac-row"><span>이메일</span><b>${esc(u.email)}</b></div>
    <div class="ac-row"><span>플랜</span><b class="acc-plan plan-${pl.key}">${esc(pl.name)}</b></div>
    ${pl.feat.api ? `<div class="ac-api"><div class="ac-api-k">생존 스코어 API 키 (데모)</div><code>sk_live_${btoa(unescape(encodeURIComponent(u.email))).replace(/[^a-zA-Z0-9]/g, "").slice(0, 16)}</code></div>` : ""}
    <div class="ac-btns"><button class="btn" id="ac-plans" type="button">요금제 보기·변경</button><button class="btn ghost" id="ac-logout" type="button">로그아웃</button></div>`;
  $("ac-plans").onclick = () => { closeAccount(); openPlans(); };
  $("ac-logout").onclick = logout;
  openModal("account-modal");
}
function closeAccount() { closeModal("account-modal"); }

/* 요금제 */
function openPlans() { renderPlans(); openModal("plans-modal"); }
function closePlans() { closeModal("plans-modal"); }
function renderPlans() {
  const cur = state.user ? state.user.plan : null;
  const ghostPlan = (k) => k === "free" || k === "enterprise";   // 무료·문의는 부차 CTA
  const group = (title, keys) => `
    <div class="plan-col">
      <div class="plan-col-h">${title}</div>
      ${keys.map((k) => { const p = PLANS[k]; const isCur = k === cur; return `
        <div class="plan-card ${isCur ? "cur" : ""} ${p.highlight ? "hot" : ""}">
          ${p.badge ? `<div class="pc-badge">${esc(p.badge)}</div>` : ""}
          <div class="pc-name">${esc(p.name)}</div>
          <div class="pc-price">${esc(p.priceLabel)}${p.sub ? `<span class="pc-sub">${esc(p.sub)}</span>` : ""}</div>
          <ul class="pc-perks">${p.perks.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
          <button type="button" class="btn ${isCur || ghostPlan(k) ? "ghost" : ""} pc-btn" data-k="${k}" ${isCur ? "disabled" : ""}>${isCur ? "현재 플랜" : (p.priceLabel === "문의" ? "문의하기" : k === "free" ? "무료로 시작" : "이 플랜 선택")}</button>
        </div>`; }).join("")}
    </div>`;
  $("plans-body").innerHTML = group("개인 · B2C", ["free", "pro"]) + group("법인 · B2B", ["business", "enterprise"]);
  document.querySelectorAll("#plans-body .pc-btn").forEach((el) => el.onclick = () => choosePlan(el.dataset.k));
}
function choosePlan(k) {
  const p = PLANS[k];
  if (!state.user) { closePlans(); openAuth("signup"); setSignupType(p.type); toast("가입하면 이 플랜이 적용됩니다"); return; }
  if (k === "enterprise") toast("Enterprise는 영업팀 문의로 진행됩니다 (데모)");
  state.user.plan = k; const db = usersDB(); db[state.user.email] = state.user; saveUsersDB(db);
  renderPlans(); renderAccountBtn(); renderReportGated(); toast(`${p.name} 플랜으로 변경됐어요`);
}

/* 추천 매물 CSV 내보내기 (법인 전용) */
function exportRecCsv() {
  if (!planHas("csv")) { toast("CSV 내보내기는 법인(Business+) 플랜 전용이에요"); openPlans(); return; }
  const rows = state._recList || [];
  if (!rows.length) { toast("먼저 추천을 받아주세요"); return; }
  const head = ["지역", "층", "면적(평)", "보증금(만원)", "월세(만원)", "3년생존율(%)", "임대료판정"];
  const body = rows.map((r) => [`${guFull(r.gu)}`, r.floor, r.area_pyeong, r.deposit_manwon, r.rent_manwon, r.y3, r.verdict].join(","));
  const blob = new Blob(["﻿" + [head.join(","), ...body].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = "SurviMap_추천매물.csv";
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  toast("CSV로 저장했어요");
}

/* ---------------- events ---------------- */
$("panel-toggle").onclick = togglePanel;
document.querySelectorAll("#region-scope .scope-btn").forEach((b) => { b.onclick = () => setScope(b.dataset.scope); });
document.querySelectorAll("#ml-horizon .mh").forEach((b) => { b.onclick = () => setHorizon(Number(b.dataset.h)); });
$("listing-toggle").onclick = toggleListings;
$("stores-toggle").onclick = toggleStores;
["sim-rent", "sim-foot", "sim-comp"].forEach((id) => { const el = $(id); if (el) el.addEventListener("input", runSim); });
document.querySelectorAll("#tabbar .tab").forEach((t) => { t.onclick = () => showTab(t.dataset.tab); });
$("share-btn").onclick = shareLink;
$("pdf-btn").onclick = exportPDF;
$("theme-btn").onclick = toggleTheme;
$("cmp-open").onclick = openCompare;
$("cmp-clear").onclick = clearCompare;
$("compare-close").onclick = closeCompare;
$("compare-modal").addEventListener("click", (e) => { if (e.target === $("compare-modal")) closeCompare(); });
$("budget-btn").onclick = openBudget;
$("budget-close").onclick = closeBudget;
$("bf-run").onclick = runRecommend;
$("budget-modal").addEventListener("click", (e) => { if (e.target === $("budget-modal")) closeBudget(); });
$("pay-close").onclick = closePay;
$("pay-run").onclick = payNow;
document.querySelectorAll("#pay-methods .pm").forEach((b) => { b.onclick = () => setPayMethod(b.dataset.m); });
$("pay-modal").addEventListener("click", (e) => { if (e.target === $("pay-modal")) closePay(); });
$("account-btn").onclick = openAccountMenu;
document.querySelectorAll("#auth-tabs .atab").forEach((t) => { t.onclick = () => setAuthTab(t.dataset.tab); });
document.querySelectorAll("#su-type .seg-b").forEach((b) => { b.onclick = () => setSignupType(b.dataset.t); });
$("su-run").onclick = doSignup;
$("li-run").onclick = doLogin;
$("go-login").onclick = () => setAuthTab("login");
$("go-signup").onclick = () => setAuthTab("signup");
$("auth-close").onclick = closeAuth;
$("auth-modal").addEventListener("click", (e) => { if (e.target === $("auth-modal")) closeAuth(); });
$("plans-close").onclick = closePlans;
$("plans-modal").addEventListener("click", (e) => { if (e.target === $("plans-modal")) closePlans(); });
$("account-close").onclick = closeAccount;
$("account-modal").addEventListener("click", (e) => { if (e.target === $("account-modal")) closeAccount(); });
$("search").addEventListener("input", liveSearch);
$("search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const sel = document.querySelector("#geo-results .geo-item.sel");
    if (sel) sel.click(); else doSearch();
  } else if (e.key === "ArrowDown") { e.preventDefault(); moveGeoSel(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); moveGeoSel(-1); }
  else if (e.key === "Escape") { clearGeo(); e.target.blur(); }
});
$("whatif-btn").onclick = askWhatIf;
$("whatif-input").addEventListener("keydown", (e) => { if (e.key === "Enter") askWhatIf(); });
/* 탭바 좌우 화살표 이동 */
$("tabbar").addEventListener("keydown", (e) => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  e.preventDefault();
  const tabs = Array.from(document.querySelectorAll("#tabbar .tab"));
  const i = tabs.findIndex((t) => t.classList.contains("active"));
  const ni = (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  tabs[ni].focus(); showTab(tabs[ni].dataset.tab);
});
/* 예산 모달: Enter로 바로 추천 */
["bf-rent", "bf-deposit", "bf-area"].forEach((id) => {
  const el = $(id); if (el) el.addEventListener("keydown", (e) => { if (e.key === "Enter") runRecommend(); });
});
window.addEventListener("resize", () => { moveTabIndicator(); refreshSegInds(); wireChipScroll(); });

init().then(() => { refreshSegInds(); wireChipScroll(); });
