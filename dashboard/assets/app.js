/* global Chart */
(function () {
  const RATE_LABELS = {
    fed_funds: "Fed Funds",
    sofr: "SOFR",
    treasury_10y: "10Y Treasury",
    mortgage_30y: "30Y Mortgage",
    prime_rate: "Prime",
  };

  const COLORS = ["#5b8cff", "#2dd4bf", "#a78bfa", "#fbbf24", "#f472b6", "#34d399", "#60a5fa"];
  Chart.defaults.color = "#8b9bb8";
  Chart.defaults.borderColor = "rgba(148,163,184,0.12)";
  Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";

  const fmtPct = (v) => (v == null || Number.isNaN(v) ? "—" : `${Number(v).toFixed(2)}%`);
  const fmtNum = (v, d = 2) => (v == null || Number.isNaN(v) ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));
  const fmtMoney = (v) => {
    if (v == null || Number.isNaN(v)) return "—";
    const n = Number(v);
    const abs = Math.abs(n);
    if (abs >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
    return `$${n.toLocaleString()}`;
  };

  async function load() {
    const res = await fetch(`data/kpis.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`Failed to load kpis.json (${res.status})`);
    return res.json();
  }

  function renderRateCards(rates) {
    const el = document.getElementById("rate-cards");
    const order = ["fed_funds", "sofr", "treasury_10y", "mortgage_30y", "prime_rate"];
    el.innerHTML = order
      .map((k) => {
        const r = rates[k];
        return `<div class="kpi">
          <div class="label">${RATE_LABELS[k] || k}</div>
          <div class="value">${r ? fmtPct(r.value) : "—"}</div>
          <div class="hint">${r ? r.date : "no data"}</div>
        </div>`;
      })
      .join("");
  }

  function renderRatesChart(history) {
    const bySeries = {};
    (history || []).forEach((row) => {
      (bySeries[row.series_name] ||= []).push(row);
    });
    const datasets = Object.keys(bySeries).map((name, i) => ({
      label: RATE_LABELS[name] || name,
      data: bySeries[name].map((r) => ({ x: r.date, y: r.value })),
      borderColor: COLORS[i % COLORS.length],
      backgroundColor: "transparent",
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 2,
    }));
    new Chart(document.getElementById("ratesChart"), {
      type: "line",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, usePointStyle: true } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtPct(c.parsed.y)}` } },
        },
        scales: {
          x: { type: "category", ticks: { maxTicksLimit: 8 }, grid: { display: false } },
          y: { ticks: { callback: (v) => `${v}%` }, grid: { color: "rgba(148,163,184,0.08)" } },
        },
      },
    });
  }

  function renderFx(latest, history) {
    const pills = document.getElementById("fx-pills");
    pills.innerHTML = (latest || [])
      .map((r) => `<span class="pill">${r.currency} ${Number(r.rate).toFixed(r.currency === "JPY" ? 2 : 4)}</span>`)
      .join("");

    // Group history; keep chronological order per currency
    const byCcy = {};
    (history || []).forEach((row) => {
      (byCcy[row.currency] ||= []).push(row);
    });
    Object.values(byCcy).forEach((rows) => rows.sort((a, b) => String(a.date).localeCompare(String(b.date))));

    // Index each series to 100 at first observation so EUR/GBP (~0.8) stay
    // visible alongside INR/JPY (~90–160) on one chart.
    const preferred = ["EUR", "GBP", "INR", "JPY"];
    const order = preferred.filter((c) => byCcy[c]).concat(Object.keys(byCcy).filter((c) => !preferred.includes(c)).sort());
    const baseRate = {};
    const datasets = order.map((ccy, i) => {
      const rows = byCcy[ccy];
      const base = Number(rows[0]?.rate);
      baseRate[ccy] = base > 0 ? base : null;
      return {
        label: ccy,
        data: rows.map((r) => ({
          x: r.date,
          y: baseRate[ccy] ? (Number(r.rate) / baseRate[ccy]) * 100 : null,
          raw: Number(r.rate),
        })),
        borderColor: COLORS[i % COLORS.length],
        tension: 0.25,
        pointRadius: 0,
        borderWidth: 2,
      };
    });

    new Chart(document.getElementById("fxChart"), {
      type: "line",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, usePointStyle: true } },
          tooltip: {
            callbacks: {
              label: (c) => {
                const raw = c.raw?.raw;
                const idx = c.parsed.y;
                const rawTxt =
                  raw == null || Number.isNaN(raw)
                    ? ""
                    : ` · ${Number(raw).toFixed(c.dataset.label === "JPY" || c.dataset.label === "INR" ? 2 : 4)}`;
                return `${c.dataset.label}: ${idx == null ? "—" : idx.toFixed(2)} (idx)${rawTxt}`;
              },
            },
          },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 6 }, grid: { display: false } },
          y: {
            title: { display: true, text: "Index (start = 100)", color: "#8b9bb8", font: { size: 11 } },
            grid: { color: "rgba(148,163,184,0.08)" },
            ticks: { callback: (v) => Number(v).toFixed(0) },
          },
        },
      },
    });
  }

  function renderBanks(sys, top) {
    document.getElementById("bank-asof").textContent = sys?.as_of_date
      ? `Call report as of ${sys.as_of_date}`
      : "Latest call report slice";
    document.getElementById("bank-kpis").innerHTML = [
      ["Banks in slice", fmtNum(sys?.bank_count, 0)],
      ["Total assets", fmtMoney(sys?.total_assets)],
      ["Total deposits", fmtMoney(sys?.total_deposits)],
      ["Net income", fmtMoney(sys?.total_net_income)],
      ["Avg ROA", fmtPct(sys?.avg_roa)],
      ["Avg NPL", fmtPct(sys?.avg_npl_ratio)],
    ]
      .map(([l, v]) => `<div class="stat"><div class="s-label">${l}</div><div class="s-value">${v}</div></div>`)
      .join("");

    document.getElementById("top-banks-body").innerHTML = (top || [])
      .map(
        (b) => `<tr>
        <td>${escapeHtml(b.name || "—")}</td>
        <td class="num">${fmtMoney(b.assets)}</td>
        <td class="num">${fmtPct(b.roa)}</td>
        <td class="num">${b.npl_ratio == null ? "—" : fmtPct(b.npl_ratio)}</td>
      </tr>`
      )
      .join("") || `<tr><td colspan="4" class="muted">No bank rows</td></tr>`;
  }

  function renderWbAndTreasury(wb, treasury) {
    const labels = {
      bank_capital_to_assets: "Bank capital / assets",
      npl_ratio: "NPL ratio (WB)",
      domestic_credit_pct_gdp: "Domestic credit % GDP",
    };
    document.getElementById("wb-kpis").innerHTML = (wb || [])
      .map((r) => {
        const label = labels[r.indicator_name] || r.indicator_name;
        return `<div class="stat"><div class="s-label">${label} · ${r.year}</div><div class="s-value">${fmtNum(r.value, 2)}</div></div>`;
      })
      .join("") || `<div class="stat"><div class="s-label">World Bank</div><div class="s-value">—</div></div>`;

    const sample = (treasury || []).slice(0, 12).reverse();
    new Chart(document.getElementById("treasuryChart"), {
      type: "bar",
      data: {
        labels: sample.map((t) => (t.security_desc || "").slice(0, 28)),
        datasets: [
          {
            label: "Avg interest %",
            data: sample.map((t) => t.avg_interest_rate_amt),
            backgroundColor: "rgba(91, 140, 255, 0.55)",
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { callback: (v) => `${v}%` }, grid: { color: "rgba(148,163,184,0.08)" } },
          y: { grid: { display: false }, ticks: { font: { size: 10 } } },
        },
      },
    });
  }

  function renderQuality(q) {
    const badge = document.getElementById("quality-badge");
    const status = q?.status || "unknown";
    badge.textContent = `Quality ${q?.overall_score ?? "—"} · ${status.toUpperCase()}`;
    badge.className = `badge ${status === "pass" ? "ok" : status === "warn" ? "warn" : "fail"}`;

    document.getElementById("quality-grid").innerHTML = (q?.datasets || [])
      .map((d) => {
        const f = d.freshness || {};
        const miss = Object.values(d.missing_values || {}).reduce((a, b) => a + b, 0);
        return `<div class="q-card">
          <h3>${escapeHtml(d.dataset)}</h3>
          <div class="q-score">${d.quality_score}</div>
          <div class="q-meta">
            Rows: ${fmtNum(d.row_count, 0)} · Dupes: ${fmtNum(d.duplicate_rows, 0)} · Missing cells: ${fmtNum(miss, 0)}<br/>
            Freshness: ${f.status || "—"} (${f.latest_date || "n/a"}${f.days_stale != null ? `, ${f.days_stale}d` : ""})
          </div>
        </div>`;
      })
      .join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  load()
    .then((data) => {
      document.getElementById("updated-at").textContent = `Updated ${data.generated_at || "—"}`;
      document.getElementById("run-meta").textContent = data.quality
        ? `overall DQ ${data.quality.overall_score} (${data.quality.status})`
        : "";
      renderRateCards(data.rates || {});
      renderRatesChart(data.rate_history || []);
      renderFx(data.fx_latest || [], data.fx_history || []);
      renderBanks(data.bank_system || {}, data.top_banks || []);
      renderWbAndTreasury(data.world_bank || [], data.treasury_sample || []);
      renderQuality(data.quality || {});
    })
    .catch((err) => {
      document.getElementById("updated-at").textContent = String(err.message || err);
      document.getElementById("quality-badge").className = "badge fail";
      document.getElementById("quality-badge").textContent = "Load error";
    });
})();
