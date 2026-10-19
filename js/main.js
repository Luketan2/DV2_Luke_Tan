// Embeds every Vega-Lite spec in /specs into its matching <div> on the page.
// All charts share one editorial theme, defined once here.

const INK = "#1d1d1b";
const INK_2 = "#52514e";
const MUTED = "#898781";
const GRID = "#e6e3db";
const BASELINE = "#c3c2b7";

const theme = {
  background: null,
  font: "Public Sans",
  padding: {top: 4, right: 0, bottom: 4, left: 0},
  view: {stroke: null},
  axis: {
    labelFont: "Public Sans", titleFont: "Public Sans",
    labelColor: INK_2, titleColor: INK_2,
    labelFontSize: 11, titleFontSize: 11.5, titleFontWeight: 600, titlePadding: 10,
    gridColor: GRID, gridWidth: 1, domainColor: BASELINE, tickColor: BASELINE
  },
  legend: {
    labelFont: "Public Sans", titleFont: "Public Sans",
    labelColor: INK_2, titleColor: INK, labelFontSize: 11, titleFontSize: 11.5, titleFontWeight: 600,
    symbolStrokeWidth: 0
  },
  title: {font: "Newsreader", color: INK, fontWeight: 600, subtitleFont: "Public Sans", subtitleColor: INK_2},
  header: {labelFont: "Public Sans", titleFont: "Public Sans"},
  text: {font: "Public Sans", color: INK_2},
  range: {category: ["#2a78d6", "#eb6834", "#1baf7a"]}
};

const charts = [
  ["#vis-waffle", "specs/01_waffle.vl.json"],
  ["#vis-matrix", "specs/02_size_matrix.vl.json"],
  ["#vis-choropleth", "specs/03_choropleth.vl.json"],
  ["#vis-dots", "specs/04_dot_density.vl.json"],
  ["#vis-growth", "specs/05_growth_symbols.vl.json"],
  ["#vis-tiles", "specs/06_state_tiles.vl.json"],
  ["#vis-quarterly", "specs/07_quarterly.vl.json"],
  ["#vis-waterfall", "specs/08_waterfall.vl.json"],
  ["#vis-heatmap", "specs/09_industry_heatmap.vl.json"],
  ["#vis-marimekko", "specs/10_marimekko.vl.json"],
  ["#vis-churn", "specs/11_churn_dumbbell.vl.json"],
  ["#vis-survival", "specs/12_survival.vl.json"],
  ["#vis-insolv-history", "specs/13_insolvency_history.vl.json"],
  ["#vis-insolv-calendar", "specs/14_insolvency_calendar.vl.json"],
  ["#vis-insolv-share", "specs/15_insolvency_share.vl.json"]
];

const embedOptions = {
  config: theme,
  renderer: "svg",
  actions: {export: true, source: true, compiled: false, editor: true},
  tooltip: {theme: "custom"}
};

// Wait for the web fonts so text is measured correctly, then draw every chart.
document.fonts.ready.then(() => {
  for (const [el, spec] of charts) {
    vegaEmbed(el, spec, embedOptions).catch((err) => {
      console.error(spec, err);
      document.querySelector(el).innerHTML = `<p class="chart-error">Chart failed to load: ${spec}</p>`;
    });
  }
});
