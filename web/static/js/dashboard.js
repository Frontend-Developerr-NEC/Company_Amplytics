(function () {
  const el = document.getElementById("chart-data");
  if (!el) return;
  const data = JSON.parse(el.textContent);

  // ---------- helpers ----------
  function parseISODate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  function toISODate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }
  function mmdd(d) {
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${m}-${day}`;
  }

  // ---------- period & series ----------
  const start = parseISODate(data.period_start);
  const end = parseISODate(data.period_end);
  const asOf = data.as_of ? parseISODate(data.as_of) : end;
  const target = data.target;

  const dates = [];
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    dates.push(new Date(d));
  }
  const days = dates.length;
  const pace = target / days;

  const byDate = {};
  for (const r of data.records) byDate[r.date] = r;

  const labels = dates.map(mmdd);
  const todayIso = toISODate(asOf);

  // Daily series (null when not in that source)
  const actualDaily = dates.map((d) => {
    const r = byDate[toISODate(d)];
    if (!r || r.source === "predicted") return null;
    return r.units;
  });
  const predictedDaily = dates.map((d) => {
    const r = byDate[toISODate(d)];
    if (!r || r.source !== "predicted") return null;
    return r.units;
  });

  // Bar colors: differentiate actual vs predicted, highlight "today"
  const actualColors = dates.map((d) => {
    const iso = toISODate(d);
    return iso === todayIso ? "rgba(5,150,105,0.95)" : "rgba(16,185,129,0.72)";
  });
  const actualBorders = dates.map((d) => {
    const iso = toISODate(d);
    return iso === todayIso ? "rgb(4,120,87)" : "rgb(5,150,105)";
  });
  const predictedColors = dates.map(() => "rgba(139,92,246,0.55)");
  const predictedBorders = dates.map(() => "rgb(124,58,237)");

  // Cumulative series (up to asOf)
  let running = 0;
  const cumulative = dates.map((d) => {
    if (d > asOf) return null;
    const r = byDate[toISODate(d)];
    if (!r) return null;
    running += r.units;
    return running;
  });
  const cumulativeSource = dates.map((d) => {
    const r = byDate[toISODate(d)];
    return r ? r.source : null;
  });

  // Pace (cumulative target) and final target
  const paceLine = dates.map((_, i) => pace * (i + 1));
  const targetLine = dates.map(() => target);

  // Headroom band: pace line (upper) and cumulative (lower) only where cumulative exists.
  // Draw as two datasets with fill between them.
  const headroomUpper = dates.map((d, i) => {
    if (d > asOf) return null;
    return Math.max(paceLine[i], cumulative[i] ?? paceLine[i]);
  });
  const headroomLower = dates.map((d, i) => {
    if (d > asOf) return null;
    const c = cumulative[i];
    return c == null ? paceLine[i] : Math.min(paceLine[i], c);
  });

  // "Behind pace" flag per point (cumulative > pace at asOf-so-far)
  const behindSegments = dates.map((d, i) => {
    if (d > asOf) return false;
    const c = cumulative[i];
    return c != null && c > paceLine[i];
  });

  const commonOpts = {
    color: document.documentElement.dataset.theme === "black" ? "#d4d4d8" : "#475467",
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "bottom",
        labels: { boxWidth: 10, usePointStyle: true },
      },
      tooltip: {
        callbacks: {
          title: (items) => items[0]?.label ?? "",
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
      },
      y: {
        beginAtZero: true,
        grid: { color: "rgba(148,163,184,0.18)" },
        title: { display: true, text: "kWh" },
      },
    },
  };

  // ==================== DAILY CHART ====================
  const dailyEl = document.getElementById("dailyChart");
  if (dailyEl) {
    new Chart(dailyEl, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Actual",
            data: actualDaily,
            backgroundColor: actualColors,
            borderColor: actualBorders,
            borderWidth: 1,
            borderRadius: 4,
            maxBarThickness: 18,
            order: 2,
          },
          {
            label: "Predicted (missing)",
            data: predictedDaily,
            backgroundColor: predictedColors,
            borderColor: predictedBorders,
            borderWidth: 1,
            borderDash: [4, 3],
            borderRadius: 4,
            maxBarThickness: 18,
            order: 2,
          },
          {
            type: "line",
            label: "Pace",
            data: dates.map(() => pace),
            borderColor: "rgb(234,179,8)",
            borderDash: [6, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            order: 1,
          },
        ],
      },
      options: {
        ...commonOpts,
        plugins: {
          ...commonOpts.plugins,
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const i = ctx.dataIndex;
                const ds = ctx.dataset.label;
                const v = ctx.parsed.y;
                if (v == null) return null;
                if (ds === "Pace") return `Pace: ${v.toFixed(2)} kWh`;
                const r = byDate[toISODate(dates[i])];
                const src = r && r.source === "predicted" ? " (predicted)" : "";
                const diff = v - pace;
                const sign = diff >= 0 ? "+" : "";
                return `${ds}: ${v.toFixed(2)} kWh${src} · ${sign}${diff.toFixed(2)} vs pace`;
              },
            },
          },
        },
      },
    });
  }

  // ==================== CUMULATIVE CHART ====================
  const cumEl = document.getElementById("cumulativeChart");
  if (cumEl) {
    new Chart(cumEl, {
      type: "line",
      data: {
        labels,
        datasets: [
          // Headroom band (fill between upper & lower)
          {
            label: "Headroom",
            data: headroomUpper,
            borderWidth: 0,
            pointRadius: 0,
            fill: "-1", // fill to previous dataset
            backgroundColor: "rgba(16,185,129,0.12)",
            spanGaps: false,
            order: 4,
          },
          {
            label: "Headroom floor",
            data: headroomLower,
            borderWidth: 0,
            pointRadius: 0,
            fill: false,
            spanGaps: false,
            order: 5,
          },

          // Cumulative used
          {
            label: "Cumulative used",
            data: cumulative,
            borderColor: "rgb(79,70,229)",
            backgroundColor: "rgba(79,70,229,0.10)",
            borderWidth: 2,
            tension: 0.2,
            spanGaps: false,
            fill: true,
            pointRadius: dates.map((d, i) => {
              if (d > asOf) return 0;
              const iso = toISODate(d);
              if (iso === todayIso) return 5;
              const r = byDate[iso];
              return r && r.source === "predicted" ? 3 : 0;
            }),
            pointHoverRadius: 5,
            pointBackgroundColor: dates.map((d, i) => {
              const iso = toISODate(d);
              if (iso === todayIso) return "rgb(67,56,202)";
              const r = byDate[iso];
              return r && r.source === "predicted"
                ? "rgb(124,58,237)"
                : "rgb(79,70,229)";
            }),
            segment: {
              borderDash: (ctx) => {
                const i = ctx.p1DataIndex;
                return cumulativeSource[i] === "predicted" ? [6, 4] : undefined;
              },
              borderColor: (ctx) => {
                const i = ctx.p1DataIndex;
                if (cumulativeSource[i] === "predicted") return "rgb(124,58,237)";
                return behindSegments[i] ? "rgb(220,38,38)" : "rgb(79,70,229)";
              },
            },
            order: 1,
          },

          // Pace (cumulative target progression)
          {
            label: "Target pace",
            data: paceLine,
            borderColor: "rgb(234,179,8)",
            borderDash: [6, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            order: 2,
          },

          // Final target
          {
            label: "Target",
            data: targetLine,
            borderColor: "rgb(220,38,38)",
            borderDash: [3, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            order: 3,
          },
        ],
      },
      options: {
        ...commonOpts,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              boxWidth: 10,
              usePointStyle: true,
              filter: (item) =>
                item.text !== "Headroom floor" && item.text !== "Headroom",
            },
          },
          tooltip: {
            filter: (item) =>
              item.dataset.label !== "Headroom floor" &&
              item.dataset.label !== "Headroom",
            callbacks: {
              label: (ctx) => {
                const v = ctx.parsed.y;
                if (v == null) return null;
                return `${ctx.dataset.label}: ${v.toFixed(2)} kWh`;
              },
            },
          },
        },
        scales: {
          ...commonOpts.scales,
          y: {
            ...commonOpts.scales.y,
            title: { display: true, text: "Cumulative kWh" },
          },
        },
      },
    });
  }

  document.addEventListener("amplytics-theme-change", (event) => {
    const color = event.detail.theme === "black" ? "#d4d4d8" : "#475467";
    document.querySelectorAll("canvas").forEach((canvas) => {
      const chart = Chart.getChart(canvas);
      if (!chart) return;
      chart.options.color = color;
      chart.update("none");
    });
  });
})();