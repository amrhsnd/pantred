from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

import pandas as pd

from data_collection import CollectionRequest, MarketDataCollector


HOST = "127.0.0.1"
PORT = 8501
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA", "BTC-USD", "ETH-USD", "EURUSD=X"]
DEFAULT_TIMEFRAMES = [
    "1m",
    "2m",
    "5m",
    "15m",
    "30m",
    "60m",
    "90m",
    "1h",
    "1d",
    "5d",
    "1wk",
    "1mo",
    "3mo",
]
DEFAULT_PERIODS = [
    "1d",
    "5d",
    "1mo",
    "3mo",
    "6mo",
    "1y",
    "2y",
    "5y",
    "10y",
    "ytd",
    "max",
]
YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"


class DashboardState:
    def __init__(self) -> None:
        self.last_result: dict | None = None
        self.error: str | None = None


state = DashboardState()


def run_collection(form: dict[str, list[str]]) -> dict:
    symbol_input = get_value(form, "symbols", "AAPL")
    symbols = [symbol.strip() for symbol in symbol_input.replace(",", " ").split() if symbol.strip()]
    timeframe = get_value(form, "timeframe", "1d")
    date_mode = get_value(form, "date_mode", "period")
    output_dir = Path(get_value(form, "output_dir", "data/raw"))
    include_heikin_ashi = get_value(form, "heikin_ashi", "") == "on"
    start = get_value(form, "start", "") or None
    end = get_value(form, "end", "") or None
    period = get_value(form, "period", "6mo")

    request = CollectionRequest(
        symbols=symbols,
        timeframes=[timeframe],
        period=period if date_mode == "period" else None,
        start=start if date_mode == "dates" else None,
        end=end if date_mode == "dates" else None,
        output_dir=output_dir,
        include_heikin_ashi=include_heikin_ashi,
    )

    results = MarketDataCollector().collect(request)
    previews = []
    for result in results:
        if result.output_path and result.output_path.exists():
            df = pd.read_csv(result.output_path)
            previews.append(
                {
                    "symbol": result.symbol,
                    "timeframe": result.timeframe,
                    "rows": result.rows,
                    "output_path": str(result.output_path),
                    "columns": list(df.columns),
                    "records": df.tail(20).to_dict(orient="records"),
                }
            )

    return {
        "request": {
            "symbols": symbols,
            "timeframe": timeframe,
            "date_mode": date_mode,
            "period": request.period,
            "start": request.start,
            "end": request.end,
            "output_dir": str(output_dir),
            "include_heikin_ashi": include_heikin_ashi,
        },
        "results": [
            {
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "rows": result.rows,
                "output_path": str(result.output_path) if result.output_path else None,
            }
            for result in results
        ],
        "previews": previews,
    }


def get_value(form: dict[str, list[str]], key: str, default: str = "") -> str:
    values = form.get(key)
    if not values:
        return default
    return values[0]


def search_symbols(query: str) -> list[dict[str, str]]:
    if len(query.strip()) < 2:
        return [
            {"symbol": symbol, "name": symbol, "exchange": ""}
            for symbol in DEFAULT_SYMBOLS
        ]

    params = urlencode({"q": query, "quotes_count": 10, "news_count": 0})
    request = Request(
        f"{YAHOO_SEARCH_URL}?{params}",
        headers={"User-Agent": "pantred-data-collector/0.1"},
    )

    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results = []
    for item in payload.get("quotes", []):
        symbol = item.get("symbol")
        if not symbol:
            continue

        results.append(
            {
                "symbol": symbol,
                "name": item.get("shortname") or item.get("longname") or symbol,
                "exchange": item.get("exchDisp") or item.get("exchange") or "",
                "type": item.get("quoteType") or "",
            }
        )

    return results


def render_page() -> bytes:
    result = state.last_result or {}
    request = result.get("request", {})
    selected_symbol = " ".join(request.get("symbols", ["AAPL"]))
    selected_timeframe = request.get("timeframe", "1d")
    selected_period = request.get("period", "6mo") or "6mo"
    selected_date_mode = request.get("date_mode", "period")
    selected_output_dir = request.get("output_dir", "data/raw")
    include_heikin_ashi = request.get("include_heikin_ashi", True)

    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pantred Data Collector</title>
  <style>
    :root {{
      --bg: #f7f3ea;
      --panel: #ffffff;
      --ink: #172026;
      --muted: #65727d;
      --line: #d9d5c8;
      --accent: #126a63;
      --accent-2: #274c77;
      --danger: #9d2f2f;
      --shadow: 0 16px 40px rgba(23, 32, 38, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    header {{
      padding: 28px 32px 18px;
      border-bottom: 1px solid var(--line);
      background: #fffaf0;
    }}
    h1 {{
      margin: 0;
      font-size: 28px;
      font-weight: 760;
    }}
    .subtitle {{
      margin: 8px 0 0;
      max-width: 760px;
      color: var(--muted);
      line-height: 1.45;
      font-size: 15px;
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(280px, 380px) minmax(0, 1fr);
      gap: 24px;
      padding: 24px 32px 40px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    form {{
      padding: 18px;
      display: grid;
      gap: 16px;
    }}
    label {{
      display: grid;
      gap: 7px;
      font-size: 13px;
      color: var(--muted);
      font-weight: 650;
    }}
    input, select {{
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      color: var(--ink);
      background: #fff;
      font: inherit;
      font-size: 14px;
    }}
    .row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .radio-row, .check-row {{
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      color: var(--ink);
      font-size: 14px;
    }}
    .radio-row label, .check-row label {{
      display: inline-flex;
      grid-auto-flow: column;
      align-items: center;
      gap: 7px;
      color: var(--ink);
      font-weight: 560;
    }}
    input[type="radio"], input[type="checkbox"] {{
      width: 16px;
      min-height: 16px;
      accent-color: var(--accent);
    }}
    .field-note {{
      min-height: 16px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      min-height: 42px;
      padding: 10px 14px;
      background: var(--accent);
      color: #fff;
      font-weight: 760;
      cursor: pointer;
    }}
    button:hover {{ background: #0e5a54; }}
    .content {{
      display: grid;
      gap: 18px;
      align-content: start;
    }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric {{
      padding: 16px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--panel);
    }}
    .metric .label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .metric .value {{
      margin-top: 8px;
      font-size: 24px;
      font-weight: 780;
      overflow-wrap: anywhere;
    }}
    .section {{
      padding: 18px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 10px 9px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      background: #fbf8f0;
      position: sticky;
      top: 0;
    }}
    .table-wrap {{
      max-height: 430px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .empty, .error {{
      padding: 18px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--muted);
      line-height: 1.45;
    }}
    .error {{
      border-color: #d9a2a2;
      color: var(--danger);
      background: #fff6f4;
    }}
    code {{
      background: #f1eadb;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    @media (max-width: 900px) {{
      header, main {{ padding-left: 18px; padding-right: 18px; }}
      main {{ grid-template-columns: 1fr; }}
      .status-grid {{ grid-template-columns: 1fr; }}
      .row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Pantred Data Collector</h1>
    <p class="subtitle">Choose the market, candle timeframe, and collection window, then export clean OHLCV data for chart generation and trend-image experiments.</p>
  </header>
  <main>
    <aside class="panel">
      <form method="post" action="/collect">
        <label>
          Symbols
          <input id="symbols-input" name="symbols" list="symbols" value="{escape(selected_symbol)}" placeholder="Search ticker or company name">
          <datalist id="symbols">
            {render_options(DEFAULT_SYMBOLS, selected_symbol)}
          </datalist>
          <span id="symbol-search-status" class="field-note">Type at least 2 characters to search Yahoo Finance.</span>
        </label>

        <label>
          Timeframe
          <select name="timeframe">
            {render_select(DEFAULT_TIMEFRAMES, selected_timeframe)}
          </select>
        </label>

        <div class="radio-row">
          <label><input type="radio" name="date_mode" value="period" {checked(selected_date_mode == "period")}> Period</label>
          <label><input type="radio" name="date_mode" value="dates" {checked(selected_date_mode == "dates")}> Dates</label>
        </div>

        <label>
          Period
          <select name="period">
            {render_select(DEFAULT_PERIODS, selected_period)}
          </select>
        </label>

        <div class="row">
          <label>
            Start
            <input name="start" type="date" value="{escape(request.get("start") or "")}">
          </label>
          <label>
            End
            <input name="end" type="date" value="{escape(request.get("end") or "")}">
          </label>
        </div>

        <label>
          Output directory
          <input name="output_dir" value="{escape(selected_output_dir)}">
        </label>

        <div class="check-row">
          <label><input type="checkbox" name="heikin_ashi" {checked(include_heikin_ashi)}> Add Heikin Ashi columns</label>
        </div>

        <button type="submit">Collect data</button>
      </form>
    </aside>

    <section class="content">
      {render_error()}
      {render_results(result)}
    </section>
  </main>
  <script>
    const symbolsInput = document.getElementById("symbols-input");
    const symbolsList = document.getElementById("symbols");
    const symbolStatus = document.getElementById("symbol-search-status");
    let symbolSearchTimer;

    function setSymbolOptions(matches) {{
      symbolsList.innerHTML = "";
      matches.forEach((match) => {{
        const option = document.createElement("option");
        option.value = match.symbol;
        option.label = [match.name, match.exchange, match.type].filter(Boolean).join(" · ");
        symbolsList.appendChild(option);
      }});
    }}

    async function searchSymbols(query) {{
      if (query.trim().length < 2) {{
        setSymbolOptions({json.dumps([{"symbol": item, "name": item, "exchange": "", "type": ""} for item in DEFAULT_SYMBOLS])});
        symbolStatus.textContent = "Type at least 2 characters to search Yahoo Finance.";
        return;
      }}

      symbolStatus.textContent = "Searching symbols...";
      try {{
        const response = await fetch(`/api/symbols?q=${{encodeURIComponent(query)}}`);
        if (!response.ok) {{
          throw new Error("Search failed");
        }}

        const matches = await response.json();
        setSymbolOptions(matches);
        symbolStatus.textContent = matches.length
          ? `${{matches.length}} matches from Yahoo Finance.`
          : "No matches found.";
      }} catch (error) {{
        symbolStatus.textContent = "Could not reach Yahoo symbol search.";
      }}
    }}

    symbolsInput.addEventListener("input", (event) => {{
      clearTimeout(symbolSearchTimer);
      symbolSearchTimer = setTimeout(() => searchSymbols(event.target.value), 250);
    }});
  </script>
</body>
</html>
"""
    return body.encode("utf-8")


def render_options(options: list[str], selected: str) -> str:
    return "\n".join(f'<option value="{escape(option)}"></option>' for option in options)


def render_select(options: list[str], selected: str) -> str:
    return "\n".join(
        f'<option value="{escape(option)}" {selected_attr(option == selected)}>{escape(option)}</option>'
        for option in options
    )


def render_error() -> str:
    if not state.error:
        return ""
    return f'<div class="error">{escape(state.error)}</div>'


def render_results(result: dict) -> str:
    if not result:
        return """
        <div class="empty">
          Pick a symbol and collection window, then collect data. The exported CSV files are saved locally and previewed here.
        </div>
        """

    total_rows = sum(item["rows"] for item in result.get("results", []))
    file_count = sum(1 for item in result.get("results", []) if item.get("output_path"))
    output_dir = result.get("request", {}).get("output_dir", "data/raw")
    previews = result.get("previews", [])

    preview_html = "\n".join(render_preview(preview) for preview in previews)
    if not preview_html:
        preview_html = '<div class="empty">No rows were returned for that request.</div>'

    return f"""
      <div class="status-grid">
        <div class="metric"><div class="label">Rows</div><div class="value">{total_rows}</div></div>
        <div class="metric"><div class="label">Files</div><div class="value">{file_count}</div></div>
        <div class="metric"><div class="label">Output</div><div class="value">{escape(output_dir)}</div></div>
      </div>
      {preview_html}
    """


def render_preview(preview: dict) -> str:
    columns = preview.get("columns", [])
    records = preview.get("records", [])
    headers = "".join(f"<th>{escape(column)}</th>" for column in columns)
    rows = []
    for record in records:
        rows.append(
            "<tr>"
            + "".join(f"<td>{escape(format_cell(record.get(column)))}</td>" for column in columns)
            + "</tr>"
        )

    return f"""
      <div class="panel section">
        <h2>{escape(preview["symbol"])} {escape(preview["timeframe"])} preview</h2>
        <p class="subtitle">{preview["rows"]} rows written to <code>{escape(preview["output_path"])}</code></p>
        <div class="table-wrap">
          <table>
            <thead><tr>{headers}</tr></thead>
            <tbody>{"".join(rows)}</tbody>
          </table>
        </div>
      </div>
    """


def format_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def checked(condition: bool) -> str:
    return "checked" if condition else ""


def selected_attr(condition: bool) -> str:
    return "selected" if condition else ""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/symbols":
            query = parse_qs(parsed_url.query).get("q", [""])[0]
            self.send_json(search_symbols(query))
            return

        self.send_page()

    def do_POST(self) -> None:
        if self.path != "/collect":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        form = parse_qs(raw_body)

        try:
            state.last_result = run_collection(form)
            state.error = None
        except Exception as exc:
            state.error = str(exc)

        self.send_page()

    def send_page(self) -> None:
        payload = render_page()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, data: object) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Pantred dashboard running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
