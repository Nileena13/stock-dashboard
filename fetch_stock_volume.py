"""
fetch_stock_volume.py
──────────────────────────────────────────────────────────────────────
Fetches live stock data from Yahoo Finance and generates dashboard.html
Run:  python3 fetch_stock_volume.py
──────────────────────────────────────────────────────────────────────
"""

import yfinance as yf
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

# ── Watchlist ─────────────────────────────────────────────────────
ALL_MARKET_SYMBOLS = [
    'NVDA','TSLA','AAPL','AMD','PLTR','AMZN','META','MSFT','GOOGL','QCOM',
    'F','INTC','BAC','AAL','NIO','SOFI','RIVN','AMC','GME','PLUG',
    'MARA','RIOT','SNDL','SPCE','TLRY','MU','SMCI','ON','UBER','NFLX'
]
SP500_SYMBOLS = [
    'NVDA','TSLA','AAPL','AMD','PLTR','AMZN','META','MSFT','GOOGL','QCOM',
    'F','INTC','BAC','AAL','WFC','C','JPM','GE','T','VZ',
    'SMCI','MU','ON','UBER','NFLX','CRM','PYPL','CSCO','IBM','GS'
]

# ── Sector Map ────────────────────────────────────────────────────
SECTORS = {
    'NVDA':'Technology','TSLA':'Auto/EV','AAPL':'Technology',
    'AMD':'Technology','PLTR':'Technology','AMZN':'Consumer',
    'META':'Technology','MSFT':'Technology','GOOGL':'Technology',
    'QCOM':'Technology','F':'Auto','INTC':'Technology',
    'BAC':'Finance','AAL':'Airlines','NIO':'Auto/EV',
    'SOFI':'Finance','RIVN':'Auto/EV','AMC':'Entertainment',
    'GME':'Retail','PLUG':'Energy','MARA':'Crypto',
    'RIOT':'Crypto','SNDL':'Cannabis','SPCE':'Aerospace',
    'TLRY':'Cannabis','MU':'Technology','SMCI':'Technology',
    'ON':'Technology','UBER':'Technology','NFLX':'Entertainment',
    'WFC':'Finance','C':'Finance','JPM':'Finance',
    'GE':'Industrial','T':'Telecom','VZ':'Telecom',
    'CRM':'Technology','PYPL':'Finance','CSCO':'Technology',
    'IBM':'Technology','GS':'Finance',
}

# ── Email Config ──────────────────────────────────────────────────
SENDER_EMAIL   = "nileenak77@gmail.com"
RECEIVER_EMAIL = "anugrahpr23@gmail.com"

# ── Helpers ───────────────────────────────────────────────────────
def fmt_vol(n):
    if not n or n == 0: return "-"
    if n >= 1e9:  return f"{n/1e9:.2f}B"
    if n >= 1e6:  return f"{n/1e6:.1f}M"
    if n >= 1e3:  return f"{n/1e3:.0f}K"
    return str(int(n))

def fmt_cap(n):
    if not n or n == 0: return "-"
    if n >= 1e12: return f"${n/1e12:.2f}T"
    if n >= 1e9:  return f"${n/1e9:.2f}B"
    if n >= 1e6:  return f"${n/1e6:.1f}M"
    return f"${n:,.0f}"

def is_market_open():
    et  = timezone(timedelta(hours=-4))
    now = datetime.now(et)
    if now.weekday() >= 5: return False
    open_t  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_t <= now <= close_t

# ── Fetch from Yahoo Finance ──────────────────────────────────────
def fetch_stocks(symbols):
    print(f"  -> Downloading data for {len(symbols)} symbols...")
    try:
        data = yf.download(
            tickers=symbols, period="5d", interval="1d",
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True,
        )
    except Exception as e:
        print(f"  x  Download failed: {e}")
        return []

    stocks = []
    for sym in symbols:
        try:
            df = data[sym] if len(symbols) > 1 else data
            if df is None or df.empty: continue
            clean = df.dropna(subset=["Close"])
            if len(clean) < 2: continue
            row  = clean.iloc[-1]
            prev = clean.iloc[-2]
            price      = float(row["Close"])
            volume     = int(row["Volume"]) if row["Volume"] > 0 else 0
            change_pct = ((price - float(prev["Close"])) / float(prev["Close"])) * 100
            if volume == 0: continue
            try:
                fi         = yf.Ticker(sym).fast_info
                market_cap = getattr(fi, "market_cap", None)
                adv        = getattr(fi, "three_month_average_volume", None)
            except Exception:
                market_cap = None
                adv        = None
            if not adv:
                adv = int(df["Volume"].mean()) if not df["Volume"].empty else None
            try:
                name = yf.Ticker(sym).info.get("shortName", sym)
            except Exception:
                name = sym
            stocks.append({
                "ticker":     sym,
                "name":       name,
                "volume":     volume,
                "price":      round(price, 2),
                "change_pct": round(change_pct, 2),
                "market_cap": market_cap,
                "adv_20d":    int(adv) if adv else 0,
                "sector":     SECTORS.get(sym, "Other"),
            })
        except Exception:
            continue
    return sorted(stocks, key=lambda x: x["volume"], reverse=True)

# ── JS helpers ────────────────────────────────────────────────────
def stocks_to_js(stocks, var_name):
    items = []
    for s in stocks[:10]:
        items.append(
            f'  {{ t:{json.dumps(s["ticker"])}, n:{json.dumps(s["name"])}, '
            f'v:{s["volume"]}, price:{json.dumps("$"+str(s["price"]))}, '
            f'ch:{s["change_pct"]}, cap:{json.dumps(fmt_cap(s["market_cap"]))}, '
            f'adv:{s["adv_20d"]}, sector:{json.dumps(s.get("sector","Other"))} }}'
        )
    return f'const {var_name} = [\n' + ',\n'.join(items) + '\n];'

def gainers_losers_js(stocks):
    valid   = [s for s in stocks if s.get("change_pct") is not None]
    gainers = sorted([s for s in valid if s["change_pct"] > 0],
                     key=lambda x: x["change_pct"], reverse=True)[:5]
    losers  = sorted([s for s in valid if s["change_pct"] < 0],
                     key=lambda x: x["change_pct"])[:5]
    def to_obj(s):
        return (f'{{t:{json.dumps(s["ticker"])},n:{json.dumps(s["name"])},'
                f'ch:{s["change_pct"]},price:{json.dumps("$"+str(s["price"]))},'
                f'sector:{json.dumps(s.get("sector","Other"))}}}')
    return ('const gainers=[' + ','.join(to_obj(s) for s in gainers) + '];' +
            '\nconst losers=['  + ','.join(to_obj(s) for s in losers)  + '];')

# ── Daily History ─────────────────────────────────────────────────
def load_history():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"entries": []}

def save_history(all_stocks, snp_stocks, fetched_at):
    history = load_history()
    today   = fetched_at.strftime("%Y-%m-%d")
    history["entries"] = [e for e in history["entries"] if e.get("date") != today]
    history["entries"].append({
        "date":          today,
        "date_label":    fetched_at.strftime("%b %d"),
        "top_all":       all_stocks[0]["ticker"] if all_stocks else "-",
        "top_all_vol":   all_stocks[0]["volume"]  if all_stocks else 0,
        "top_snp":       snp_stocks[0]["ticker"]  if snp_stocks else "-",
        "top_snp_vol":   snp_stocks[0]["volume"]  if snp_stocks else 0,
        "snp_total_vol": sum(s["volume"] for s in snp_stocks[:10]),
    })
    history["entries"] = sorted(history["entries"], key=lambda x: x["date"])[-30:]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")
    with open(path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"  OK  history.json updated! ({len(history['entries'])} day(s) stored)")
    return history

def history_to_js(history):
    entries = history.get("entries", [])[-7:]
    items   = [json.dumps({
        "date": e["date"], "label": e["date_label"],
        "topAll": e["top_all"], "topAllVol": e["top_all_vol"],
        "topSnp": e["top_snp"], "topSnpVol": e["top_snp_vol"],
        "snpTotalVol": e["snp_total_vol"],
    }) for e in entries]
    return 'const historyData=[' + ','.join(items) + '];'

# ── Email Summary ─────────────────────────────────────────────────
def load_email_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_config.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def build_email_html(all_stocks, snp_stocks, fetched_at, market_open):
    date_str   = fetched_at.strftime("%B %d, %Y")
    time_str   = fetched_at.strftime("%I:%M %p ET")
    status_str = "Market Open" if market_open else "After Market Close"

    valid   = [s for s in all_stocks if s.get("change_pct") is not None]
    gainers = sorted([s for s in valid if s["change_pct"] > 0],
                     key=lambda x: x["change_pct"], reverse=True)[:5]
    losers  = sorted([s for s in valid if s["change_pct"] < 0],
                     key=lambda x: x["change_pct"])[:5]

    def chg_span(pct):
        sign  = "+" if pct >= 0 else ""
        color = "#3B6D11" if pct >= 0 else "#A32D2D"
        bg    = "#EAF3DE" if pct >= 0 else "#FCEBEB"
        return (f'<span style="background:{bg};color:{color};font-weight:700;'
                f'padding:2px 8px;border-radius:4px;font-size:12px;">'
                f'{sign}{pct:.2f}%</span>')

    def vol_row(s, rank):
        is_spike  = s["adv_20d"] > 0 and s["volume"] > 2 * s["adv_20d"]
        spike_tag = ""
        if is_spike:
            ratio     = round(s["volume"] / s["adv_20d"])
            spike_tag = (f' <span style="background:#FEF3C7;color:#92400E;'
                         f'font-size:10px;font-weight:700;padding:1px 5px;'
                         f'border-radius:3px;">x{ratio} avg vol</span>')
        return (f'<tr style="border-bottom:1px solid #f0efed;">'
                f'<td style="padding:9px 12px;color:#aaa;font-size:12px;width:28px;">{rank}</td>'
                f'<td style="padding:9px 12px;">'
                f'<span style="font-weight:700;color:#185FA5;font-size:13px;">{s["ticker"]}</span>'
                f'<span style="color:#999;font-size:11px;margin-left:6px;">{s.get("sector","")}</span>{spike_tag}'
                f'<div style="color:#666;font-size:11px;margin-top:1px;">{s["name"]}</div></td>'
                f'<td style="padding:9px 12px;text-align:right;font-size:12px;color:#444;">{fmt_vol(s["volume"])}</td>'
                f'<td style="padding:9px 12px;text-align:right;font-size:13px;font-weight:600;">${s["price"]}</td>'
                f'<td style="padding:9px 12px;text-align:right;">{chg_span(s["change_pct"])}</td></tr>')

    def gl_rows(stocks, is_gain):
        rows = ""
        for s in stocks:
            pct   = s["change_pct"]
            sign  = "+" if pct >= 0 else ""
            color = "#3B6D11" if is_gain else "#A32D2D"
            bg    = "#EAF3DE" if is_gain else "#FCEBEB"
            rows += (f'<tr style="border-bottom:1px solid #f0efed;">'
                     f'<td style="padding:8px 12px;font-weight:700;color:#1a1a1a;font-size:13px;">{s["ticker"]}</td>'
                     f'<td style="padding:8px 12px;color:#666;font-size:12px;">{s["name"]}</td>'
                     f'<td style="padding:8px 12px;font-size:12px;color:#888;">${s["price"]}</td>'
                     f'<td style="padding:8px 12px;text-align:right;">'
                     f'<span style="background:{bg};color:{color};font-weight:700;'
                     f'padding:2px 8px;border-radius:4px;font-size:12px;">{sign}{pct:.2f}%</span>'
                     f'</td></tr>')
        return rows

    th = 'style="padding:9px 12px;font-size:10px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;border-bottom:2px solid #e8e8e8;"'
    sh = 'style="background:#f8f8f6;padding:14px 20px;font-size:13px;font-weight:700;color:#1a1a1a;border-top:2px solid #e8e8e8;"'

    all_rows  = "".join(vol_row(s, i+1) for i, s in enumerate(all_stocks[:5]))
    snp_rows  = "".join(vol_row(s, i+1) for i, s in enumerate(snp_stocks[:5]))
    gain_rows = gl_rows(gainers, True)
    loss_rows = gl_rows(losers,  False)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:20px;background:#f0efed;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<div style="max-width:620px;margin:0 auto;">
  <div style="background:#185FA5;border-radius:12px 12px 0 0;padding:24px 24px 20px;">
    <div style="font-size:22px;font-weight:700;color:#fff;">Stock Volume Dashboard</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.8);margin-top:6px;">{date_str} &nbsp;·&nbsp; {time_str} &nbsp;·&nbsp; {status_str}</div>
  </div>
  <div style="background:#fff;border-radius:0 0 12px 12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div {sh}>Top Gainers &amp; Top Losers</div>
    <div style="display:table;width:100%;">
      <div style="display:table-cell;width:50%;vertical-align:top;border-right:1px solid #e8e8e8;">
        <div style="padding:4px 0;background:#f9fdf5;">
          <div style="padding:8px 12px;font-size:11px;font-weight:700;color:#3B6D11;text-transform:uppercase;">Top Gainers</div>
          <table style="width:100%;border-collapse:collapse;">{gain_rows}</table>
        </div>
      </div>
      <div style="display:table-cell;width:50%;vertical-align:top;">
        <div style="padding:4px 0;background:#fdf9f9;">
          <div style="padding:8px 12px;font-size:11px;font-weight:700;color:#A32D2D;text-transform:uppercase;">Top Losers</div>
          <table style="width:100%;border-collapse:collapse;">{loss_rows}</table>
        </div>
      </div>
    </div>
    <div {sh}>Top 5 Most Active - All US Stocks</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr>
        <th {th}>#</th><th {th}>Stock</th>
        <th {th} style="text-align:right;">Volume</th>
        <th {th} style="text-align:right;">Price</th>
        <th {th} style="text-align:right;">Change</th>
      </tr></thead>
      <tbody>{all_rows}</tbody>
    </table>
    <div {sh}>Top 5 Most Active - S&amp;P 500</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr>
        <th {th}>#</th><th {th}>Stock</th>
        <th {th} style="text-align:right;">Volume</th>
        <th {th} style="text-align:right;">Price</th>
        <th {th} style="text-align:right;">Change</th>
      </tr></thead>
      <tbody>{snp_rows}</tbody>
    </table>
    <div style="padding:16px 20px;text-align:center;font-size:11px;color:#bbb;border-top:1px solid #f0efed;">
      Not financial advice &nbsp;·&nbsp; Data from Yahoo Finance &nbsp;·&nbsp; Built with Claude AI
    </div>
  </div>
</div>
</body>
</html>"""

def send_email_summary(all_stocks, snp_stocks, fetched_at, market_open):
    print("  --> Sending email summary...")
    config = load_email_config()
    if not config:
        print("  --  Email skipped: email_config.json not found.")
        return
    app_password = config.get("app_password", "").strip()
    if not app_password:
        print("  --  Email skipped: app_password is empty in email_config.json.")
        return

    date_str = fetched_at.strftime("%b %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Stock Dashboard - Top Movers {date_str}"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL
    msg.attach(MIMEText(build_email_html(all_stocks, snp_stocks, fetched_at, market_open), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"  OK  Email summary sent to {RECEIVER_EMAIL}")
    except smtplib.SMTPAuthenticationError:
        print("  x   Email failed: Wrong app password. Check email_config.json.")
    except Exception as e:
        print(f"  x   Email failed: {e}")

# ── Terminal table ────────────────────────────────────────────────
def print_table(title, stocks, badge):
    now_str = datetime.now().strftime("%b %d, %Y  %I:%M %p")
    status  = "Market Open" if is_market_open() else "Closed"
    print()
    print("=" * 105)
    print(f"  {badge}  {title}")
    print(f"  Data as of: {now_str} ET   |   {status}")
    print("=" * 105)
    print(f"  {'#':<4} {'Ticker':<8} {'Company':<28} {'Volume':>10} {'Mkt Cap':>12} {'ADV 20D':>10} {'Price':>9} {'% Change':>9}")
    print("  " + "-" * 101)
    for i, s in enumerate(stocks[:10], 1):
        chg = s.get("change_pct", 0) or 0
        print(
            f"  {i:<4} {s['ticker']:<8} {s['name'][:27]:<28} "
            f"{fmt_vol(s['volume']):>10} {fmt_cap(s['market_cap']):>12} "
            f"{fmt_vol(s['adv_20d']):>10} ${s['price']:>8.2f} "
            f"{'+'if chg>=0 else ''}{chg:.2f}%"
        )
    print("=" * 105)

# ── HTML generator ────────────────────────────────────────────────
def generate_html(all_stocks, snp_stocks, fetched_at, market_open, history=None):
    date_str   = fetched_at.strftime("%b %d, %Y")
    time_str   = fetched_at.strftime("%I:%M %p")
    stamp_text = f"{date_str} · {time_str} ET · {'Live · Market Open' if market_open else 'Market Close (last session)'}"
    pill_text  = f"{date_str} · {'Live' if market_open else 'Market Close'}"

    top_all   = all_stocks[0]["ticker"]  if all_stocks else "-"
    top_all_v = fmt_vol(all_stocks[0]["volume"]) if all_stocks else "-"
    top_snp   = snp_stocks[0]["ticker"] if snp_stocks else "-"
    top_snp_v = fmt_vol(snp_stocks[0]["volume"]) if snp_stocks else "-"
    snp_total = fmt_vol(sum(s["volume"] for s in snp_stocks[:10]))
    snp_caps  = [(s["market_cap"] or 0) for s in snp_stocks]
    big_cap_i = snp_caps.index(max(snp_caps)) if snp_caps else 0
    big_cap   = snp_stocks[big_cap_i]["ticker"] if snp_stocks else "-"
    big_cap_v = fmt_cap(snp_stocks[big_cap_i]["market_cap"]) if snp_stocks else "-"

    all_js  = stocks_to_js(all_stocks, "allStocks")
    snp_js  = stocks_to_js(snp_stocks, "snpStocks")
    gl_js   = gainers_losers_js(all_stocks)
    hist_js = history_to_js(history or {"entries": []})

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Stock Volume Dashboard - {date_str}</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
    :root{{
      --bg:#f5f5f3;--surface:#fff;--surface2:#f0efed;--border:rgba(0,0,0,0.08);
      --text:#1a1a1a;--text2:#6b6b6b;--text3:#aaa;
      --blue1:#185FA5;--blue2:#378ADD;--teal1:#0F6E56;--teal2:#1D9E75;
      --green-bg:#EAF3DE;--green-text:#3B6D11;--red-bg:#FCEBEB;--red-text:#A32D2D;
      --snp-bg:#E1F5EE;--snp-text:#0F6E56;--r:12px;--rs:8px;
    }}
    @media(prefers-color-scheme:dark){{:root{{
      --bg:#111110;--surface:#1c1c1b;--surface2:#242423;--border:rgba(255,255,255,0.08);
      --text:#f0ede8;--text2:#888;--text3:#555;--blue1:#5B9FD8;--blue2:#85B7EB;
      --teal1:#1D9E75;--teal2:#5DCAA5;--green-bg:#1a2e10;--green-text:#7ec850;
      --red-bg:#2e1010;--red-text:#f08080;--snp-bg:#0a2018;--snp-text:#5DCAA5;
    }}}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:2rem 1.5rem;}}
    .page{{max-width:1060px;margin:0 auto;}}
    .hdr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:1.75rem;gap:1rem;flex-wrap:wrap;}}
    .brand{{display:flex;align-items:center;gap:12px;}}
    .bicon{{width:44px;height:44px;border-radius:var(--rs);background:var(--blue1);display:flex;align-items:center;justify-content:center;}}
    .bicon svg{{width:22px;height:22px;fill:none;stroke:#fff;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round;}}
    h1{{font-size:22px;font-weight:700;letter-spacing:-0.4px;}}
    .sub{{font-size:13px;color:var(--text2);margin-top:3px;}}
    .hdr-right{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}
    .pill{{font-size:12px;color:var(--text2);background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:6px 14px;white-space:nowrap;}}
    .pill-dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#1D9E75;margin-right:6px;vertical-align:middle;}}
    .rbtn{{display:flex;align-items:center;gap:7px;padding:10px 20px;font-size:13px;font-weight:600;background:var(--blue1);color:#fff;border:none;border-radius:8px;cursor:pointer;transition:background 0.15s,transform 0.1s;}}
    .rbtn:hover{{background:var(--blue2);}} .rbtn:active{{transform:scale(0.97);}}
    .rbtn svg{{width:15px;height:15px;fill:none;stroke:#fff;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;}}
    .spin{{animation:spin 0.9s linear infinite;}} @keyframes spin{{to{{transform:rotate(360deg);}}}}
    .stamp-bar{{background:var(--surface);border:1px solid var(--border);border-radius:var(--rs);padding:10px 16px;margin-bottom:1.5rem;font-size:12.5px;color:var(--text2);text-align:center;line-height:1.6;}}
    .stamp-bar strong{{color:var(--text);}}
    .metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:1.75rem;}}
    .metric{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;}}
    .ml{{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:0.07em;margin-bottom:5px;}}
    .mv{{font-size:23px;font-weight:700;letter-spacing:-0.5px;}} .ms{{font-size:12px;color:var(--text3);margin-top:3px;}}
    .sec{{margin-top:1.75rem;}}
    .sbadge{{font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;display:inline-block;margin-bottom:6px;}}
    .ball{{background:rgba(55,138,221,0.12);color:var(--blue1);}} .bsnp{{background:var(--snp-bg);color:var(--snp-text);}}
    .sec h2{{font-size:16px;font-weight:600;margin-bottom:3px;}} .sec p{{font-size:12px;color:var(--text2);margin-bottom:12px;}}
    .tcard{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);overflow-x:auto;margin-bottom:12px;}}
    .tcard.snp{{border-color:rgba(29,158,117,0.3);}}
    table{{width:100%;border-collapse:collapse;font-size:13px;min-width:700px;}}
    thead{{background:var(--surface2);}} .tcard.snp thead{{background:var(--snp-bg);}}
    th{{padding:11px 12px;text-align:left;font-size:10.5px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid var(--border);white-space:nowrap;}}
    .tcard.snp th{{color:var(--snp-text);}}
    td{{padding:12px 12px;border-bottom:1px solid var(--border);vertical-align:middle;}}
    tr:last-child td{{border-bottom:none;}} tr:hover td{{background:var(--surface2);}}
    .tbdg{{display:inline-block;font-weight:700;font-size:12px;padding:3px 7px;border-radius:5px;}}
    .tall{{color:var(--blue1);background:rgba(55,138,221,0.12);}} .tsnp{{color:var(--teal1);background:var(--snp-bg);}}
    .vw{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;}}
    .vbg{{flex:1;height:5px;background:var(--border);border-radius:3px;overflow:hidden;min-width:60px;}}
    .vf{{height:100%;border-radius:3px;}}
    .vn{{font-size:11px;color:var(--text2);white-space:nowrap;min-width:48px;text-align:right;font-weight:500;}}
    .bdg{{font-size:12px;font-weight:600;padding:3px 7px;border-radius:5px;white-space:nowrap;}}
    .pos{{color:var(--green-text);background:var(--green-bg);}} .neg{{color:var(--red-text);background:var(--red-bg);}} .neu{{color:var(--text2);background:var(--surface2);}}
    .chcard{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:20px;margin-bottom:4px;}}
    .chcard.snp{{border-color:rgba(29,158,117,0.3);}}
    .chtitle{{font-size:11px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;}}
    .lgnd{{display:flex;gap:14px;margin-bottom:10px;}}
    .li{{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text2);}}
    .ld{{width:10px;height:10px;border-radius:2px;flex-shrink:0;}}
    .chwrap{{position:relative;height:210px;}}
    hr{{border:none;border-top:1px solid var(--border);margin:2rem 0;}}
    .gloss{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;margin-bottom:1.5rem;display:grid;grid-template-columns:1fr 1fr;gap:10px 24px;}}
    .gt{{font-size:12px;font-weight:600;margin-bottom:2px;}} .gd{{font-size:12px;color:var(--text2);line-height:1.5;}}
    .foot{{text-align:center;font-size:12px;color:var(--text3);padding-top:1.25rem;border-top:1px solid var(--border);line-height:1.8;}}
    .foot a{{color:var(--blue2);text-decoration:none;}}
    @media(max-width:680px){{.metrics{{grid-template-columns:1fr 1fr;}}.gloss{{grid-template-columns:1fr;}}}}
    .stag{{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;background:var(--surface2);color:var(--text2);margin-top:3px;}}
    .spk{{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;background:#FEF3C7;color:#92400E;white-space:nowrap;}}
    @media(prefers-color-scheme:dark){{.spk{{background:#3d2b00;color:#FCD34D;}}}}
    .gl-wrap{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:1.75rem;}}
    .gl-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;}}
    .gl-g{{border-color:rgba(59,109,17,0.25);}} .gl-l{{border-color:rgba(163,45,45,0.25);}}
    .gl-head{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:10px;}}
    .gl-g .gl-head{{color:var(--green-text);}} .gl-l .gl-head{{color:var(--red-text);}}
    .gl-row{{display:flex;align-items:center;gap:6px;padding:7px 0;border-bottom:1px solid var(--border);}}
    .gl-row:last-child{{border-bottom:none;}}
    .gl-tk{{font-size:12px;font-weight:700;min-width:42px;}} .gl-nm{{font-size:11px;color:var(--text2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}} .gl-pr{{font-size:11px;color:var(--text2);white-space:nowrap;}}
    @media(max-width:480px){{.gl-wrap{{grid-template-columns:1fr;}}}}
    .hist-empty{{padding:24px;text-align:center;color:var(--text2);font-size:13px;line-height:1.8;}}
    .hist-tcard{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);overflow-x:auto;margin-bottom:12px;}}
    .hist-tcard table{{min-width:560px;}}
    .today-tag{{font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;background:rgba(55,138,221,0.12);color:var(--blue1);margin-left:6px;vertical-align:middle;}}
  </style>
</head>
<body>
<div class="page">
  <div class="hdr">
    <div class="brand">
      <div class="bicon"><svg viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div>
      <div><h1>Volume Dashboard</h1><div class="sub">Daily Trading Volume &middot; All US Stocks &amp; S&amp;P 500</div></div>
    </div>
    <div class="hdr-right">
      <div class="pill"><span class="pill-dot"></span>{pill_text}</div>
      <button class="rbtn" onclick="openRefresh()">
        <svg id="ricon" viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4"/></svg>
        Refresh Data
      </button>
    </div>
  </div>
  <div class="stamp-bar">&#128197; Prices &amp; volumes as of <strong>{stamp_text}</strong> &nbsp;&middot;&nbsp; If market is closed, data reflects last trading session close</div>
  <div class="metrics">
    <div class="metric"><div class="ml">Top All-Market</div><div class="mv">{top_all}</div><div class="ms">{top_all_v} shares</div></div>
    <div class="metric"><div class="ml">Top S&amp;P 500</div><div class="mv">{top_snp}</div><div class="ms">{top_snp_v} shares</div></div>
    <div class="metric"><div class="ml">S&amp;P 500 Total Vol</div><div class="mv">{snp_total}</div><div class="ms">top 10 combined</div></div>
    <div class="metric"><div class="ml">Largest S&amp;P Cap</div><div class="mv">{big_cap}</div><div class="ms">{big_cap_v}</div></div>
  </div>
  <div class="gl-wrap">
    <div class="gl-card gl-g"><div class="gl-head">Top Gainers &middot; All Market</div><div id="glGain"></div></div>
    <div class="gl-card gl-l"><div class="gl-head">Top Losers &middot; All Market</div><div id="glLoss"></div></div>
  </div>
  <div class="sec">
    <span class="sbadge ball">All US Stocks</span>
    <h2>Top 10 by Daily Volume</h2>
    <p>All exchanges &mdash; often dominated by small-cap stocks with news-driven spikes</p>
    <div class="tcard" id="allT"></div>
    <div class="chcard">
      <div class="chtitle">Volume vs ADV &mdash; All Stocks (millions of shares)</div>
      <div class="lgnd">
        <div class="li"><div class="ld" style="background:#378ADD"></div>Today's volume</div>
        <div class="li"><div class="ld" style="background:rgba(160,160,160,0.4);border:1px solid rgba(130,130,130,0.5)"></div>ADV 20D</div>
      </div>
      <div class="chwrap"><canvas id="allC"></canvas></div>
    </div>
  </div>
  <hr/>
  <div class="sec">
    <span class="sbadge bsnp">S&amp;P 500</span>
    <h2>Top 10 S&amp;P 500 Stocks by Daily Volume</h2>
    <p>Large-cap index members only &mdash; blue-chip companies like Apple, NVIDIA, Tesla</p>
    <div class="tcard snp" id="snpT"></div>
    <div class="chcard snp">
      <div class="chtitle">Volume vs ADV &mdash; S&amp;P 500 Stocks (millions of shares)</div>
      <div class="lgnd">
        <div class="li"><div class="ld" style="background:#1D9E75"></div>Today's volume</div>
        <div class="li"><div class="ld" style="background:rgba(160,160,160,0.4);border:1px solid rgba(130,130,130,0.5)"></div>ADV 20D</div>
      </div>
      <div class="chwrap"><canvas id="snpC"></canvas></div>
    </div>
  </div>
  <hr/>
  <div class="sec">
    <span class="sbadge" style="background:rgba(120,80,220,0.12);color:#7c3aed;">History</span>
    <h2>Daily History &mdash; Last 7 Days</h2>
    <p>One row per trading day &mdash; today is highlighted. Grows automatically each morning when the script runs.</p>
    <div class="hist-tcard" id="histT"></div>
    <div class="chcard" style="margin-top:12px;">
      <div class="chtitle">S&amp;P 500 Top 10 &mdash; Total Volume Per Day (millions of shares)</div>
      <div class="chwrap"><canvas id="histC"></canvas></div>
    </div>
  </div>
  <hr/>
  <div class="gloss">
    <div><div class="gt">Volume (daily)</div><div class="gd">Total shares traded today. Resets every morning at market open (9:30 AM ET).</div></div>
    <div><div class="gt">Market Cap</div><div class="gd">Total company value = share price &times; total shares outstanding.</div></div>
    <div><div class="gt">ADV 20D</div><div class="gd">Average Daily Volume over ~20 trading days &mdash; the stock's normal activity level.</div></div>
    <div><div class="gt">% Price Change</div><div class="gd">Price movement today vs yesterday's close. Green = up, Red = down.</div></div>
    <div><div class="gt">Sector</div><div class="gd">Industry the company belongs to, e.g. Technology, Finance, Auto/EV.</div></div>
    <div><div class="gt">Volume Spike</div><div class="gd">Shown when today's volume is more than 2&times; the 20-day average.</div></div>
    <div><div class="gt">Daily History</div><div class="gd">Saved every time the script runs. Keeps the last 30 days.</div></div>
    <div><div class="gt">Email Summary</div><div class="gd">Sent automatically each morning to {RECEIVER_EMAIL} when the script runs.</div></div>
  </div>
  <div class="foot">
    Live data from <a href="https://finance.yahoo.com" target="_blank">Yahoo Finance</a> via yfinance &middot;
    {date_str} &middot; Not financial advice &middot; Built with <a href="https://claude.ai" target="_blank">Claude AI</a>
  </div>
</div>
<script>
{all_js}
{snp_js}
{gl_js}
{hist_js}
const allColors=['#185FA5','#378ADD','#378ADD','#378ADD','#378ADD','#85B7EB','#85B7EB','#85B7EB','#85B7EB','#85B7EB'];
const snpColors=['#0F6E56','#1D9E75','#1D9E75','#1D9E75','#1D9E75','#5DCAA5','#5DCAA5','#5DCAA5','#5DCAA5','#5DCAA5'];
function fmtV(n){{if(!n||n===0)return'-';if(n>=1e9)return(n/1e9).toFixed(2)+'B';if(n>=1e6)return(n/1e6).toFixed(1)+'M';return Math.round(n/1e3)+'K';}}
function buildTable(stocks,cls,colors){{
  const maxV=Math.max(...stocks.map(s=>s.v));
  const rows=stocks.map((s,i)=>{{
    const pct=Math.round((s.v/maxV)*100);
    const chStr=(s.ch>=0?'+':'')+Number(s.ch).toFixed(2)+'%';
    const bc=s.ch>0?'pos':s.ch<0?'neg':'neu';
    const isSpike=s.adv>0&&s.v>2*s.adv;
    const spikeRatio=s.adv>0?Math.round(s.v/s.adv):0;
    const spikeBadge=isSpike?`<div style="margin-top:3px"><span class="spk">&#9889; ${{spikeRatio}}x avg vol</span></div>`:'';
    return `<tr><td style="width:34px;color:var(--text3);font-size:12px">${{i+1}}</td>
      <td style="width:70px"><span class="tbdg t${{cls}}">${{s.t}}</span></td>
      <td style="max-width:160px"><div style="color:var(--text2);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${{s.n}}</div>${{s.sector?`<span class="stag">${{s.sector}}</span>`:''}}</td>
      <td style="width:160px"><div class="vw"><div class="vbg"><div class="vf" style="width:${{pct}}%;background:${{colors[i]}}"></div></div><span class="vn">${{fmtV(s.v)}}</span></div>${{spikeBadge}}</td>
      <td style="width:80px;font-size:12px;color:var(--text2)">${{s.cap}}</td>
      <td style="width:76px;font-size:12px;color:var(--text2)">${{fmtV(s.adv)}}</td>
      <td style="width:76px;font-size:13px;font-weight:500">${{s.price}}</td>
      <td style="width:96px"><span class="bdg ${{bc}}">${{chStr}}</span></td></tr>`;
  }}).join('');
  return `<table><thead><tr><th style="width:34px">#</th><th style="width:70px">Ticker</th><th>Company</th><th style="width:160px">Volume</th><th style="width:80px">Mkt Cap</th><th style="width:76px">ADV 20D</th><th style="width:76px">Price</th><th style="width:96px">% Change</th></tr></thead><tbody>${{rows}}</tbody></table>`;
}}
function buildGLRow(s,isGain){{
  const cls=isGain?'pos':'neg';
  const chStr=(s.ch>=0?'+':'')+Number(s.ch).toFixed(2)+'%';
  return `<div class="gl-row"><span class="gl-tk">${{s.t}}</span><span class="gl-nm">${{s.n}}</span><span class="gl-pr">${{s.price}}</span><span class="bdg ${{cls}}">${{chStr}}</span></div>`;
}}
function buildHistTable(entries){{
  if(!entries||entries.length===0) return '<div class="hist-empty">No history yet. Run the script each morning and a new row will appear here.</div>';
  const sorted=[...entries].reverse();
  const rows=sorted.map((e,i)=>{{
    const isToday=i===0;
    const todayTag=isToday?'<span class="today-tag">Today</span>':'';
    const fw=isToday?'700':'400';
    return `<tr><td style="font-size:12px;font-weight:${{fw}};white-space:nowrap">${{e.label}}${{todayTag}}</td><td style="font-size:12px;font-weight:700;color:var(--blue1)">${{e.topAll}}</td><td style="font-size:12px;color:var(--text2)">${{fmtV(e.topAllVol)}}</td><td style="font-size:12px;font-weight:700;color:var(--teal1)">${{e.topSnp}}</td><td style="font-size:12px;color:var(--text2)">${{fmtV(e.topSnpVol)}}</td><td style="font-size:12px;color:var(--text2)">${{fmtV(e.snpTotalVol)}}</td></tr>`;
  }}).join('');
  return `<table><thead><tr><th>Date</th><th>Top All-Market</th><th>Vol</th><th>Top S&amp;P 500</th><th>Vol</th><th>S&amp;P Total Vol</th></tr></thead><tbody>${{rows}}</tbody></table>`;
}}
const isDark=matchMedia('(prefers-color-scheme:dark)').matches;
const tc=isDark?'rgba(255,255,255,0.4)':'rgba(0,0,0,0.4)';
const gc=isDark?'rgba(255,255,255,0.06)':'rgba(0,0,0,0.05)';
const opts={{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>' '+fmtV(ctx.raw*1e6)+' shares'}}}}}},scales:{{x:{{ticks:{{color:tc,font:{{size:11}},autoSkip:false}},grid:{{display:false}},border:{{display:false}}}},y:{{ticks:{{color:tc,font:{{size:11}},callback:v=>v+'M'}},grid:{{color:gc}},border:{{display:false}}}}}}}};
document.getElementById('allT').innerHTML=buildTable(allStocks,'all',allColors);
document.getElementById('snpT').innerHTML=buildTable(snpStocks,'snp',snpColors);
document.getElementById('glGain').innerHTML=gainers.map(s=>buildGLRow(s,true)).join('');
document.getElementById('glLoss').innerHTML=losers.map(s=>buildGLRow(s,false)).join('');
document.getElementById('histT').innerHTML=buildHistTable(historyData);
if(historyData&&historyData.length>0){{
  const hc=historyData.map((_,i)=>i===historyData.length-1?'#7c3aed':'rgba(120,80,220,0.35)');
  new Chart(document.getElementById('histC'),{{type:'bar',data:{{labels:historyData.map(e=>e.label),datasets:[{{label:'S&P Total Vol',data:historyData.map(e=>parseFloat((e.snpTotalVol/1e6).toFixed(1))),backgroundColor:hc,borderRadius:4,borderSkipped:false}}]}},options:opts}});
}}else{{document.getElementById('histC').parentElement.style.display='none';}}
new Chart(document.getElementById('allC'),{{type:'bar',data:{{labels:allStocks.map(s=>s.t),datasets:[{{label:"Today",data:allStocks.map(s=>parseFloat((s.v/1e6).toFixed(1))),backgroundColor:allColors,borderRadius:4,borderSkipped:false}},{{label:"ADV",data:allStocks.map(s=>parseFloat((s.adv/1e6).toFixed(1))),backgroundColor:'rgba(160,160,160,0.15)',borderRadius:4,borderSkipped:false,borderWidth:1.5,borderColor:'rgba(140,140,140,0.4)'}}]}},options:opts}});
new Chart(document.getElementById('snpC'),{{type:'bar',data:{{labels:snpStocks.map(s=>s.t),datasets:[{{label:"Today",data:snpStocks.map(s=>parseFloat((s.v/1e6).toFixed(1))),backgroundColor:snpColors,borderRadius:4,borderSkipped:false}},{{label:"ADV",data:snpStocks.map(s=>parseFloat((s.adv/1e6).toFixed(1))),backgroundColor:'rgba(160,160,160,0.15)',borderRadius:4,borderSkipped:false,borderWidth:1.5,borderColor:'rgba(140,140,140,0.4)'}}]}},options:opts}});
function openRefresh(){{const icon=document.getElementById('ricon');icon.classList.add('spin');setTimeout(()=>{{icon.classList.remove('spin');alert('To refresh:\\n\\n1. Go to Terminal\\n2. Run: python3 fetch_stock_volume.py\\n3. Refresh this page');  }},600);}}
</script>
</body>
</html>'''

# ── Main ──────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 52)
    print("  Stock Volume Dashboard  -  Yahoo Finance")
    print("=" * 52)

    print("\n  Fetching All-Market stocks...")
    all_stocks = fetch_stocks(ALL_MARKET_SYMBOLS)

    print("\n  Fetching S&P 500 stocks...")
    snp_stocks = fetch_stocks(SP500_SYMBOLS)

    if not all_stocks:
        print("\n  No data returned. Check your internet and try again.\n")
        return

    print_table("Top 10 Most Active US Stocks",      all_stocks, "ALL MARKET")
    print_table("Top 10 Most Active S&P 500 Stocks", snp_stocks, "S&P 500")

    fetched_at  = datetime.now()
    market_open = is_market_open()

    history = save_history(all_stocks, snp_stocks, fetched_at)
    html    = generate_html(all_stocks, snp_stocks, fetched_at, market_open, history)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock_data.json")
    with open(json_path, "w") as f:
        json.dump({
            "fetched_at":       fetched_at.isoformat(),
            "market_open":      market_open,
            "all_market_top10": all_stocks[:10],
            "snp500_top10":     snp_stocks[:10],
        }, f, indent=2, default=str)

    print(f"\n  OK  dashboard.html generated!")
    print(f"  OK  stock_data.json saved!")

    send_email_summary(all_stocks, snp_stocks, fetched_at, market_open)

    print(f"\n  --> Open dashboard.html in your browser to see the dashboard!")
    print(f"  --> File location: {out_path}")
    print(f"\n  Market: {'Open' if market_open else 'Closed - showing last session close'}\n")

if __name__ == "__main__":
    main()
