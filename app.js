// Gráficos do painel. Chama as APIs do Flask e desenha com Chart.js.
const COURT = "#10243B";
const BALL = "#C6F24E";
const WIN = "#1F8A4C";
const LOSS = "#E4572E";
const GRID = "rgba(16,36,59,.08)";

function brDate(iso) {
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}` : `${m}/${y}`;
}

const baseOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false }, ticks: { color: "#5E6E74", font: { size: 11 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 6 } },
    y: { grid: { color: GRID }, ticks: { color: "#5E6E74", font: { size: 11 } } },
  },
};

async function drawRank() {
  const el = document.getElementById("rankChart");
  if (!el) return;
  const data = await fetch("/api/ranking-series").then((r) => r.json());
  if (!data.length) return;
  new Chart(el, {
    type: "line",
    data: {
      labels: data.map((p) => brDate(p.date)),
      datasets: [{
        data: data.map((p) => p.rank),
        borderColor: COURT, backgroundColor: "rgba(16,36,59,.06)",
        borderWidth: 2.5, fill: true, tension: .3,
        pointBackgroundColor: BALL, pointBorderColor: COURT, pointRadius: 4,
      }],
    },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        // Ranking: menor é melhor, então invertemos o eixo.
        y: { ...baseOpts.scales.y, reverse: true },
      },
    },
  });
}

async function drawMatches() {
  const el = document.getElementById("matchChart");
  if (!el) return;
  const d = await fetch("/api/partidas-series").then((r) => r.json());
  new Chart(el, {
    type: "bar",
    data: {
      labels: d.labels.map(brDate),
      datasets: [
        { label: "Vitórias", data: d.wins, backgroundColor: WIN, borderRadius: 4, stack: "s" },
        { label: "Derrotas", data: d.losses, backgroundColor: LOSS, borderRadius: 4, stack: "s" },
      ],
    },
    options: {
      ...baseOpts,
      plugins: { legend: { display: true, labels: { boxWidth: 12, font: { size: 11 }, color: "#5E6E74" } } },
      scales: {
        x: { ...baseOpts.scales.x, stacked: true },
        y: { ...baseOpts.scales.y, stacked: true, ticks: { ...baseOpts.scales.y.ticks, precision: 0 } },
      },
    },
  });
}

async function drawTraining() {
  const el = document.getElementById("trainChart");
  if (!el) return;
  const d = await fetch("/api/treinos-series").then((r) => r.json());
  new Chart(el, {
    type: "bar",
    data: {
      labels: d.labels.map(brDate),
      datasets: [{ data: d.minutes, backgroundColor: COURT, borderRadius: 4 }],
    },
    options: baseOpts,
  });
}

function initDashboard(hasRanking) {
  if (window.Chart && Chart.defaults) {
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  }
  if (hasRanking) drawRank();
  drawMatches();
  drawTraining();
}
window.initDashboard = initDashboard;

/* Menu mobile: tab "Mais" abre bottom-sheet; só visual, sem rotas. */
(function () {
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }
  ready(function () {
    if (window.Chart && Chart.defaults) Chart.defaults.maintainAspectRatio = false;
    var sheet = document.getElementById("moreSheet");
    var scrim = document.getElementById("scrim");
    var openBtn = document.getElementById("moreTab");
    var closeBtn = document.getElementById("sheetClose");
    if (!sheet || !openBtn) return;
    function open() {
      sheet.classList.add("open");
      sheet.setAttribute("aria-hidden", "false");
      if (scrim) scrim.hidden = false;
      document.body.style.overflow = "hidden";
      openBtn.classList.add("on");
    }
    function close() {
      sheet.classList.remove("open");
      sheet.setAttribute("aria-hidden", "true");
      if (scrim) scrim.hidden = true;
      document.body.style.overflow = "";
      openBtn.classList.remove("on");
      openBtn.focus({ preventScroll: true });
    }
    var isOpen = function () { return sheet.classList.contains("open"); };
    openBtn.addEventListener("click", function () { isOpen() ? close() : open(); });
    if (closeBtn) closeBtn.addEventListener("click", close);
    if (scrim) scrim.addEventListener("click", close);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && isOpen()) close(); });
    sheet.querySelectorAll("a").forEach(function (a) { a.addEventListener("click", close); });
  });
})();
