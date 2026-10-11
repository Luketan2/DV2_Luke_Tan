# Open for Business: Australia's 2.8 million businesses

FIT3179 Data Visualisation 2, Semester 2 2026, by Luke Tan.

A single-page data story about how many businesses operate in Australia, where they are, which industries are growing, and how many open, close and fail each year. All charts and maps are built with Vega-Lite.

## Structure

| Path | What it is |
|---|---|
| `index.html` | The story page |
| `css/style.css` | Layout and typography (Newsreader + Public Sans) |
| `js/main.js` | Shared chart theme and the code that embeds every spec |
| `specs/*.vl.json` | One human-readable Vega-Lite spec per chart |
| `data/` | Small, web-ready CSV/GeoJSON files used by the charts (~0.8 MB in total) |
| `data_prep/build_data.py` | Rebuilds everything in `data/` from the raw ABS and ASIC downloads |
| `raw/` | Original downloads (not committed; see the script header for URLs) |

To preview locally, run `python -m http.server` in this folder and open <http://localhost:8000>. Opening the file directly will not work, because browsers block data loading from `file://`.

## Chart inventory

| # | Spec | Idiom | Basic or advanced | Data |
|---|---|---|---|---|
| 1 | `01_waffle` | Waffle (unit) chart | Advanced | ABS business counts by employment size |
| 2 | `02_size_matrix` | Transition matrix heatmap | Advanced | ABS size changes 2025 to 2026 |
| 3 | `03_choropleth` | **Choropleth map** with city insets and an industry filter | Advanced (map) | ABS SA2 counts aggregated to SA4, plus ABS population |
| 4 | `04_dot_density` | **Dot density map** | Advanced (map) | ABS SA4 counts |
| 5 | `05_growth_symbols` | **Proportional symbol map** with city insets | Advanced (map) | ABS SA4 counts, 2023 to 2025 |
| 6 | `06_state_tiles` | **Tile grid map** with sparklines | Advanced (map) | ASIC insolvencies and ABS state counts |
| 7 | `07_quarterly` | Line and area chart with brush zoom | Basic | ABS quarterly time series |
| 8 | `08_waterfall` | Waterfall chart with year selector | Advanced | ABS entries and exits |
| 9 | `09_industry_heatmap` | Diverging heatmap | Advanced | ABS industry counts 2019 to 2026 |
| 10 | `10_marimekko` | Marimekko (mosaic) chart | Advanced | ABS industry by size |
| 11 | `11_churn_dumbbell` | Dumbbell chart with year selector | Advanced* | ABS entry and exit rates |
| 12 | `12_survival` | Highlighted multi-line chart with selector | Basic | ABS survival of 2022-23 entrants |
| 13 | `13_insolvency_history` | Annotated bar chart | Basic | ASIC 1999 to 2026 |
| 14 | `14_insolvency_calendar` | Calendar heatmap | Advanced | ASIC monthly |
| 15 | `15_insolvency_share` | Scatterplot with reference line | Basic | ASIC + ABS combined |

That is 15 charts in total: 11 advanced (including 4 map idioms) and 4 basic. *Ask your tutor whether a dumbbell chart counts as advanced or as a dot plot.

## Data sources

See the "About this visualisation" section of the page, or the header of `data_prep/build_data.py`. ABS and ASIC data are © Commonwealth of Australia and licensed under CC BY 4.0.
