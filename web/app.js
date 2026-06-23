/* ============================================================
   Observatório da Violência — consumo ao vivo das consultas
   Q1–Q7 (src/queries.py) via MongoDB. Toda cor de dado vem da
   mesma rampa "brasa" (rateColor): o painel é um só instrumento.
   ============================================================ */
"use strict";

const EMBER = ["#F4E9C8", "#E0A23C", "#CC5A2B", "#8E2C2C", "#4A1518"];
// Domínio fixo (0–60) para que a cor signifique a mesma intensidade em todo ano.
const rateColor = d3.scaleLinear()
  .domain([0, 15, 30, 45, 60])
  .range(EMBER)
  .clamp(true)
  .interpolate(d3.interpolateRgb);

const REGIAO_NOME = { 1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste" };

const state = {
  meta: null,
  anos: [],          // anos com taxa disponível
  ano: 2022,
  geo: null,
  capitais: {},      // codIBGE -> [lon, lat]
  munSel: 2507507,   // João Pessoa
};

const $ = (sel) => document.querySelector(sel);
const fmt = (v, d = 1) => (v == null || Number.isNaN(v)) ? "—" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtInt = (v) => (v == null) ? "—" : Number(v).toLocaleString("pt-BR");

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

/* ---------------- Tooltip compartilhado ---------------- */
const tip = $("#mapTip");
function showTip(html, evt) {
  tip.innerHTML = html;
  tip.hidden = false;
  const pad = 14;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  if (x + w > window.innerWidth) x = evt.clientX - w - pad;
  if (y + h > window.innerHeight) y = evt.clientY - h - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
function hideTip() { tip.hidden = true; }

/* ============================================================
   BOOT
   ============================================================ */
async function boot() {
  try {
    const [meta, geo, caps] = await Promise.all([
      api("/api/meta"),
      fetch("assets/br-regioes.geojson").then((r) => r.json()),
      fetch("assets/capitais.json").then((r) => r.json()),
    ]);
    state.meta = meta;
    state.anos = meta.anosTaxa;
    state.geo = geo;
    state.capitais = caps;

    setStatus(true, `${meta.db} · ${fmtInt(meta.totalMunicipios)} municípios · ${meta.fontes.length} fontes`);
    renderScaleRamp();
    setupYear();
    setupMunSelect();
    setupThresholds();
    setupPeeks();

    await refreshByYear();
    await Promise.all([loadEvolucao(), loadFontes(), loadFiltro()]);
  } catch (err) {
    console.error(err);
    setStatus(false, "falha ao conectar — o MongoDB está no ar? (docker compose up -d)");
  }
}

function setStatus(live, text) {
  const el = $("#dbstatus");
  el.classList.toggle("is-live", live);
  el.classList.toggle("is-error", !live);
  $("#dbstatusText").textContent = text;
}

/* ---------------- Controle de ANO (índice → ano, pula 2021 ausente) ---------------- */
function setupYear() {
  const slider = $("#ano");
  slider.min = 0;
  slider.max = state.anos.length - 1;
  slider.step = 1;
  const startIdx = Math.max(0, state.anos.indexOf(2022));
  slider.value = startIdx;
  state.ano = state.anos[startIdx];
  $("#anoOut").textContent = state.ano;
  $("#pulseAno").textContent = state.ano;

  let timer;
  slider.addEventListener("input", () => {
    state.ano = state.anos[+slider.value];
    $("#anoOut").textContent = state.ano;
    $("#pulseAno").textContent = state.ano;
    clearTimeout(timer);
    timer = setTimeout(refreshByYear, 120);
  });
}

function setupMunSelect() {
  const sel = $("#munSel");
  sel.innerHTML = state.meta.capitais
    .map((c) => `<option value="${c.codIBGE}" ${c.codIBGE === state.munSel ? "selected" : ""}>${c.nome} — ${c.siglaUF}</option>`)
    .join("");
  sel.addEventListener("change", () => {
    state.munSel = +sel.value;
    loadEvolucao();
    loadFontes();
  });
}

function setupThresholds() {
  const tMin = $("#taxaMin"), eMax = $("#escMax");
  let timer;
  const sync = () => {
    $("#taxaMinOut").textContent = tMin.value;
    $("#escMaxOut").textContent = eMax.value;
    clearTimeout(timer);
    timer = setTimeout(loadFiltro, 140);
  };
  tMin.addEventListener("input", sync);
  eMax.addEventListener("input", sync);
}

/* ============================================================
   Atualizações dirigidas pelo ANO: Q1, Q3(mapa), Q4, Q6, pulso
   ============================================================ */
async function refreshByYear() {
  const ano = state.ano;
  $("#pulseAno").textContent = ano;
  const [q1, q3, q4, q6] = await Promise.all([
    api(`/api/q1?ano=${ano}&limite=27`),
    api(`/api/q3?ano=${ano}`),
    api(`/api/q4?ano=${ano}`),
    api(`/api/q6?ano=${ano}`),
  ]);
  setPeek("q1", q1);
  setPeek("q3", q3);
  setPeek("q4", q4);
  setPeek("q6", q6);

  renderPulse(q1.resultado);
  renderMap(q3.resultado, q1.resultado);
  renderHeroStats(q1.resultado, q3.resultado);
  renderRanking(q1.resultado.slice(0, 10));
  renderScatter(q4.resultado);
  renderBucket(q6.resultado);
  // a série Q7 acompanha o ano global
  loadFontes();
}

/* ---------------- Pulso nacional ---------------- */
function renderPulse(rows) {
  const max = 60;
  $("#pulseBars").innerHTML = rows
    .slice().sort((a, b) => a.taxaHomicidiosPor100k - b.taxaHomicidiosPor100k)
    .map((d) => {
      const h = Math.max(6, (d.taxaHomicidiosPor100k / max) * 100);
      return `<span class="pulse__bar" style="height:${h}%;background:${rateColor(d.taxaHomicidiosPor100k)};opacity:.86"
        data-tip="${d.municipio}/${d.uf}|${fmt(d.taxaHomicidiosPor100k)}"></span>`;
    }).join("");
  $("#pulseBars").querySelectorAll(".pulse__bar").forEach((b) => {
    b.addEventListener("mousemove", (e) => {
      const [nome, taxa] = b.dataset.tip.split("|");
      showTip(`<div class="tt__name">${nome}</div><div class="tt__row">taxa <b>${taxa}</b> / 100 mil</div>`, e);
    });
    b.addEventListener("mouseleave", hideTip);
  });
}

/* ---------------- Q3 · Mapa coroplético + capitais ---------------- */
function renderMap(q3rows, q1rows) {
  const svg = d3.select("#map");
  svg.selectAll("*").remove();
  const W = 520, H = 540;
  // geoIdentity (projeção planar) evita o bug de winding do d3-geo esférico, que
  // faz o malha do IBGE preencher o globo inteiro. reflectY: lat cresce p/ cima.
  const proj = d3.geoIdentity().reflectY(true).fitSize([W, H - 10], state.geo);
  const path = d3.geoPath(proj);

  const byReg = new Map(q3rows.map((r) => [String(r.codRegiao), r]));

  svg.append("g").selectAll("path")
    .data(state.geo.features)
    .join("path")
    .attr("class", "map__region")
    .attr("d", path)
    .attr("fill", (f) => {
      const r = byReg.get(String(f.properties.codarea));
      return r ? rateColor(r.mediaTaxa) : "#23202B";
    })
    .on("mousemove", (e, f) => {
      const r = byReg.get(String(f.properties.codarea));
      const nome = REGIAO_NOME[f.properties.codarea] || "Região";
      showTip(
        `<div class="tt__name">${nome}</div>` +
        (r ? `<div class="tt__row">taxa média <b>${fmt(r.mediaTaxa)}</b></div><div class="tt__row">capitais: <b>${r.municipios}</b></div>` : `<div class="tt__row">sem dados</div>`),
        e);
    })
    .on("mouseleave", hideTip);

  // capitais: raio = nº de homicídios, cor = taxa
  const rmax = d3.max(q1rows, (d) => d.homicidiosTotais) || 1;
  const rscale = d3.scaleSqrt().domain([0, rmax]).range([2.5, 16]);

  svg.append("g").selectAll("circle")
    .data(q1rows.filter((d) => state.capitais[d.codIBGE]))
    .join("circle")
    .attr("class", "map__dot")
    .attr("cx", (d) => proj(state.capitais[d.codIBGE])[0])
    .attr("cy", (d) => proj(state.capitais[d.codIBGE])[1])
    .attr("r", (d) => rscale(d.homicidiosTotais))
    .attr("fill", (d) => rateColor(d.taxaHomicidiosPor100k))
    .attr("fill-opacity", 0.92)
    .on("mousemove", (e, d) => showTip(
      `<div class="tt__name">${d.municipio} — ${d.uf}</div>` +
      `<div class="tt__row">taxa <b>${fmt(d.taxaHomicidiosPor100k)}</b> / 100 mil</div>` +
      `<div class="tt__row">homicídios <b>${fmtInt(d.homicidiosTotais)}</b></div>`, e))
    .on("mouseleave", hideTip);
}

function renderHeroStats(q1, q3) {
  const top = q1[0];
  const regTop = q3[0];
  const items = [
    { k: `Capital mais violenta · ${state.ano}`, v: top ? `${fmt(top.taxaHomicidiosPor100k)}` : "—", sub: top ? `${top.municipio}/${top.uf} · ${fmtInt(top.homicidiosTotais)} homicídios` : "" },
    { k: "Maior média regional", v: regTop ? fmt(regTop.mediaTaxa) : "—", sub: regTop ? `${regTop.regiao} · ${regTop.municipios} capitais` : "" },
    { k: "Amplitude entre capitais", v: q1.length ? `${fmt(q1[q1.length - 1].taxaHomicidiosPor100k)}–${fmt(q1[0].taxaHomicidiosPor100k)}` : "—", sub: "taxa / 100 mil hab." },
  ];
  $("#heroStats").innerHTML = items.map((i) =>
    `<li class="stat__item"><span class="stat__k">${i.k}</span><span class="stat__v">${i.v}</span><span class="stat__sub">${i.sub}</span></li>`
  ).join("");
}

/* ---------------- Q1 · Ranking ---------------- */
function renderRanking(rows) {
  const max = d3.max(rows, (d) => d.taxaHomicidiosPor100k) || 1;
  $("#ranking").innerHTML = rows.map((d, i) => `
    <div class="rk">
      <span class="rk__pos">${String(i + 1).padStart(2, "0")}</span>
      <div class="rk__bar-area">
        <div class="rk__label">
          <span class="rk__name">${d.municipio} <span class="rk__uf">${d.uf}</span></span>
        </div>
        <div class="rk__track"><div class="rk__fill" style="width:${(d.taxaHomicidiosPor100k / max) * 100}%;background:${rateColor(d.taxaHomicidiosPor100k)}"></div></div>
      </div>
      <span class="rk__val">${fmt(d.taxaHomicidiosPor100k)}</span>
    </div>`).join("");
}

/* ---------------- Q4 · Dispersão ---------------- */
function renderScatter(rows) {
  const svg = d3.select("#scatter");
  svg.selectAll("*").remove();
  const W = 560, H = 360, m = { t: 16, r: 16, b: 44, l: 48 };
  const x = d3.scaleLinear().domain([20, 90]).range([m.l, W - m.r]);
  const y = d3.scaleLinear().domain([0, 65]).range([H - m.b, m.t]);
  const rmax = d3.max(rows, (d) => d.populacaoTotal) || 1;
  const r = d3.scaleSqrt().domain([0, rmax]).range([3, 15]);

  // grades
  const g = svg.append("g");
  y.ticks(6).forEach((t) => g.append("line").attr("class", "gridline").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(t)).attr("y2", y(t)));

  // eixos
  const ax = svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(7).tickFormat((d) => d + "%"));
  const ay = svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(6));
  ax.select(".domain").remove(); ay.select(".domain").remove();
  svg.append("text").attr("class", "axis__label").attr("x", W / 2).attr("y", H - 6).attr("text-anchor", "middle").text("% com ensino médio ou mais →");
  svg.append("text").attr("class", "axis__label").attr("transform", "rotate(-90)").attr("x", -H / 2).attr("y", 13).attr("text-anchor", "middle").text("taxa / 100 mil →");

  svg.append("g").selectAll("circle").data(rows).join("circle")
    .attr("class", "dot")
    .attr("cx", (d) => x(d.pctEnsinoMedioOuMais))
    .attr("cy", (d) => y(d.taxaHomicidiosPor100k))
    .attr("r", (d) => r(d.populacaoTotal))
    .attr("fill", (d) => rateColor(d.taxaHomicidiosPor100k))
    .attr("fill-opacity", 0.85)
    .on("mousemove", (e, d) => showTip(
      `<div class="tt__name">${d.municipio} — ${d.uf}</div>` +
      `<div class="tt__row">taxa <b>${fmt(d.taxaHomicidiosPor100k)}</b> · escol. <b>${fmt(d.pctEnsinoMedioOuMais)}%</b></div>`, e))
    .on("mouseleave", hideTip);
}

/* ---------------- Q6 · Bucket ---------------- */
function renderBucket(rows) {
  const order = ["Pequeno - até 20 mil hab.", "Médio - 20 a 100 mil hab.", "Grande - acima de 100 mil hab."];
  const byName = new Map(rows.map((r) => [r.portePopulacional, r]));
  const max = d3.max(rows, (d) => d.mediaTaxa) || 1;
  $("#bucket").innerHTML = order.map((name) => {
    const r = byName.get(name);
    const has = r && r.mediaTaxa != null;
    const w = has ? (r.mediaTaxa / max) * 100 : 0;
    return `<div class="bk">
      <div class="bk__top">
        <span class="bk__name">${name}</span>
        <span class="bk__count">${r ? r.municipios + " mun." : "sem capitais nesta faixa"}</span>
      </div>
      <div class="bk__track"><div class="bk__fill" style="width:${w}%;background:${has ? rateColor(r.mediaTaxa) : "transparent"}"></div></div>
      <div class="bk__top" style="margin-top:4px"><span></span><span class="bk__val">${has ? fmt(r.mediaTaxa) : "—"}</span></div>
    </div>`;
  }).join("");
}

/* ---------------- Q2 · Evolução (linha) ---------------- */
async function loadEvolucao() {
  const res = await api(`/api/q2?cod=${state.munSel}&ini=2012&fim=2022`);
  setPeek("q2", res);
  const doc = res.resultado[0];
  const series = (doc ? doc.seriesAnuais : []).slice().sort((a, b) => a.ano - b.ano);
  renderLine(series, doc ? doc.nome : "");
}

function renderLine(series, nome) {
  const svg = d3.select("#line");
  svg.selectAll("*").remove();
  const W = 880, H = 320, m = { t: 22, r: 56, b: 38, l: 52 };
  if (!series.length) return;

  const x = d3.scalePoint().domain(series.map((d) => d.ano)).range([m.l, W - m.r]).padding(0.4);
  const yCount = d3.scaleLinear().domain([0, d3.max(series, (d) => d.homicidiosTotais) * 1.1 || 1]).range([H - m.b, m.t]);
  const taxaVals = series.filter((d) => d.taxaHomicidiosPor100k != null);
  const yRate = d3.scaleLinear().domain([0, d3.max(taxaVals, (d) => d.taxaHomicidiosPor100k) * 1.2 || 1]).range([H - m.b, m.t]);

  yCount.ticks(5).forEach((t) => svg.append("line").attr("class", "gridline").attr("x1", m.l).attr("x2", W - m.r).attr("y1", yCount(t)).attr("y2", yCount(t)));

  const axB = svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x));
  const axL = svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(yCount).ticks(5));
  const axR = svg.append("g").attr("class", "axis").attr("transform", `translate(${W - m.r},0)`).call(d3.axisRight(yRate).ticks(5));
  [axB, axL, axR].forEach((a) => a.select(".domain").remove());

  svg.append("text").attr("class", "axis__label").attr("transform", "rotate(-90)").attr("x", -H / 2).attr("y", 14).attr("text-anchor", "middle").text("homicídios");
  svg.append("text").attr("class", "axis__label").attr("transform", "rotate(-90)").attr("x", -H / 2).attr("y", W - 8).attr("text-anchor", "middle").text("taxa / 100 mil");

  // barras de contagem (aço)
  svg.append("g").selectAll("rect").data(series).join("rect")
    .attr("x", (d) => x(d.ano) - 9).attr("width", 18)
    .attr("y", (d) => yCount(d.homicidiosTotais)).attr("height", (d) => H - m.b - yCount(d.homicidiosTotais))
    .attr("fill", "#33485C").attr("rx", 1)
    .on("mousemove", (e, d) => showTip(`<div class="tt__name">${nome} · ${d.ano}</div><div class="tt__row">homicídios <b>${fmtInt(d.homicidiosTotais)}</b></div>${d.taxaHomicidiosPor100k != null ? `<div class="tt__row">taxa <b>${fmt(d.taxaHomicidiosPor100k)}</b></div>` : ""}`, e))
    .on("mouseleave", hideTip);

  // linha de taxa (brasa)
  const line = d3.line().defined((d) => d.taxaHomicidiosPor100k != null).x((d) => x(d.ano)).y((d) => yRate(d.taxaHomicidiosPor100k)).curve(d3.curveMonotoneX);
  svg.append("path").datum(series).attr("fill", "none").attr("stroke", "#CC5A2B").attr("stroke-width", 2.5).attr("d", line);
  svg.append("g").selectAll("circle").data(taxaVals).join("circle")
    .attr("cx", (d) => x(d.ano)).attr("cy", (d) => yRate(d.taxaHomicidiosPor100k)).attr("r", 4)
    .attr("fill", (d) => rateColor(d.taxaHomicidiosPor100k)).attr("stroke", "#100E15").attr("stroke-width", 1)
    .on("mousemove", (e, d) => showTip(`<div class="tt__name">${nome} · ${d.ano}</div><div class="tt__row">taxa <b>${fmt(d.taxaHomicidiosPor100k)}</b> / 100 mil</div>`, e))
    .on("mouseleave", hideTip);

  // legenda mínima
  svg.append("rect").attr("x", m.l).attr("y", 4).attr("width", 10).attr("height", 10).attr("fill", "#33485C");
  svg.append("text").attr("x", m.l + 15).attr("y", 13).attr("class", "axis__label").style("text-transform", "none").text("homicídios");
  svg.append("rect").attr("x", m.l + 96).attr("y", 4).attr("width", 10).attr("height", 10).attr("fill", "#CC5A2B");
  svg.append("text").attr("x", m.l + 111).attr("y", 13).attr("class", "axis__label").style("text-transform", "none").text("taxa");
}

/* ---------------- Q5 · Filtro $elemMatch ---------------- */
async function loadFiltro() {
  const tMin = +$("#taxaMin").value, eMax = +$("#escMax").value;
  const res = await api(`/api/q5?taxa_min=${tMin}&esc_max=${eMax}`);
  setPeek("q5", res);
  const rows = res.resultado;
  const list = $("#filterlist");
  if (!rows.length) {
    list.innerHTML = `<div class="fl__empty">Nenhum município cruzou taxa &gt; ${tMin} e escolaridade &lt; ${eMax}% em nenhum ano.</div>`;
    return;
  }
  list.innerHTML = rows.map((d) => {
    const s = d.seriesAnuais[0];
    return `<div class="fl">
      <span class="fl__name">${d.nome} <span>${d.siglaUF} · ${d.nomeRegiao || ""}</span></span>
      <span class="fl__metric">taxa <b>${fmt(s.taxaHomicidiosPor100k)}</b></span>
      <span class="fl__metric">escol. <b>${fmt(s.pctEnsinoMedioOuMais)}%</b> · ${s.ano}</span>
    </div>`;
  }).join("");
}

/* ---------------- Q7 · Proveniência $lookup ---------------- */
async function loadFontes() {
  const res = await api(`/api/q7?cod=${state.munSel}&ano=${state.ano}`);
  setPeek("q7", res);
  const doc = res.resultado[0];
  const box = $("#provenance");
  if (!doc) {
    box.innerHTML = `<div class="fl__empty">Sem registro para ${state.ano}.</div>`;
    return;
  }
  const ind = doc.indicadores;
  const metrics = [
    ["Homicídios totais", fmtInt(ind.homicidiosTotais)],
    ["Taxa / 100 mil", ind.taxaHomicidiosPor100k != null ? fmt(ind.taxaHomicidiosPor100k) : "—"],
    ["Ensino médio ou +", ind.pctEnsinoMedioOuMais != null ? fmt(ind.pctEnsinoMedioOuMais) + "%" : "—"],
  ];
  box.innerHTML = `
    <div class="prov__indic">
      <span class="eyebrow">${doc.municipio} · ${doc.ano}</span>
      ${metrics.map(([k, v]) => `<div class="prov__metric"><span class="prov__k">${k}</span><span class="prov__v">${v}</span></div>`).join("")}
    </div>
    <div class="prov__sources">
      <span class="eyebrow">Fontes resolvidas via $lookup</span>
      ${doc.fontes.map((f) => `<div class="src">
        <div class="src__name">${f.nome}</div>
        <div class="src__origin">${f.origem || ""}</div>
        ${f.portal ? `<a class="src__link" href="${f.portal}" target="_blank" rel="noopener">${f.portal}</a>` : ""}
      </div>`).join("")}
    </div>`;
}

/* ============================================================
   "Ver consulta executada" — mostra o pipeline real do MongoDB
   ============================================================ */
function setupPeeks() {
  document.querySelectorAll(".qpeek__toggle").forEach((btn) => {
    btn.setAttribute("aria-expanded", "false");
    btn.addEventListener("click", () => {
      const pre = $("#peek-" + btn.dataset.peek);
      const open = pre.hidden;
      pre.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
      btn.textContent = open ? "ocultar consulta" : "ver consulta executada";
    });
  });
}

function highlight(s) {
  return s
    .replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))
    .replace(/"(\$[a-zA-Z]+)"/g, '"<span class="qpeek__op">$1</span>"')
    .replace(/: (".*?")/g, ': <span class="qpeek__str">$1</span>');
}

function setPeek(q, res) {
  const pre = $("#peek-" + q);
  if (!pre) return;
  const head = `<span class="qpeek__meta">db.${res.colecao}.${res.operacao}( … )  →  ${res.n} documento(s)</span>`;
  pre.innerHTML = head + highlight(res.consulta);
}

function renderScaleRamp() {
  $("#scaleRamp").style.background =
    `linear-gradient(90deg, ${EMBER[0]}, ${EMBER[1]} 30%, ${EMBER[2]} 58%, ${EMBER[3]} 82%, ${EMBER[4]})`;
}

boot();
