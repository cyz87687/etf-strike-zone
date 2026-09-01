# -*- coding: utf-8 -*-
"""
ETF 击球区诊断 · 自动生成器
数据来源：腾讯财经公开行情接口（web.ifzq.gtimg.cn 前复权日K），与 WeStock 同源。
仅用 Python 标准库，可在 GitHub Actions (ubuntu-latest, py3.11) 无依赖运行。
输出：index.html（GitHub Pages 入口）
"""
import urllib.request
import json
import math
import datetime
import statistics

# ETF 标的（市场代码, 显示名, 跟踪指数说明）
ETFS = [
    ("sh513310", "中韩半导体", "中证中韩半导体指数"),
    ("sz159316", "港股创新药", "恒生港股通创新药指数（易方达）"),
    ("sh562500", "机器人",     "中证机器人指数（华夏）"),
    ("sh515050", "通信",       "中证5G通信主题指数"),
    ("sh588170", "科创半导体", "上证科创板半导体指数（华夏）"),
]

KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,2024-01-01,2099-12-31,800,qfq"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8")


def load_kline(code):
    """返回 (dates, closes, highs, lows, opens, vols)，前复权日K，按时间升序。"""
    d = json.loads(fetch(KLINE_URL.format(code=code)))
    node = d["data"][code]
    key = "qfqday" if "qfqday" in node else ("day" if "day" in node else list(node.keys())[0])
    rows = node[key]
    dates, opens, closes, highs, lows, vols = [], [], [], [], [], []
    for r in rows:
        dates.append(r[0])
        opens.append(float(r[1]))
        closes.append(float(r[2]))
        highs.append(float(r[3]))
        lows.append(float(r[4]))
        vols.append(float(r[5]))
    return dates, closes, highs, lows, opens, vols


def ma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def ema_series(vals, n):
    k = 2 / (n + 1)
    e = vals[0]
    out = [e]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def rsi(vals, n):
    if len(vals) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(vals)):
        d = vals[i] - vals[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - 100 / (1 + rs)


def macd(vals):
    e12 = ema_series(vals, 12)
    e26 = ema_series(vals, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema_series(dif, 9)
    hist = [2 * (x - y) for x, y in zip(dif, dea)]
    return dif[-1], dea[-1], hist[-1], hist[-2] if len(hist) > 1 else hist[-1]


def boll(closes, n=20):
    window = closes[-n:]
    mid = sum(window) / n
    sd = statistics.pstdev(window)
    return mid, mid + 2 * sd, mid - 2 * sd


def strike_score(c, mas, rsi2, rsi14, hist):
    """击球区评分 0–5，定义=已回撤至MA20以下 + 长线结构未破 + 超卖 + 下跌中企稳。
    仅作相对排序参考，非投资建议。
      · 深度回调(0–1.5)：距52周高点回撤
      · 超卖(0–1.5)：RSI(2) 越低越高
      · 结构未破(0–1.5)：仅当价格已≤MA20(确为回调而非追涨)时，站上MA60(+1.0)且站上MA120(+0.5)
      · 企稳(0–0.5)：MACD柱>0（动量翻正）且价格仍<MA20
    """
    s = 0.0
    # 深度回调
    dd = c / mas["hi52"] - 1
    if dd <= -0.30:
        s += 1.5
    elif dd <= -0.20:
        s += 1.0
    elif dd <= -0.10:
        s += 0.6
    # 超卖
    if rsi2 is not None:
        if rsi2 <= 20:
            s += 1.5
        elif rsi2 <= 35:
            s += 1.0
        elif rsi2 <= 50:
            s += 0.5
    # 结构未破（门控：仅当已回撤至MA20以下才计）
    m20 = mas.get(20)
    dipped = (m20 is not None and c <= m20)
    if dipped:
        if mas.get(60) and c >= mas[60]:
            s += 1.0
        if mas.get(120) and c >= mas[120]:
            s += 0.5
        if hist is not None and hist > 0:
            s += 0.5
    return round(min(s, 5.0), 1)


def analyze(code, name, tracker):
    dates, closes, highs, lows, opens, vols = load_kline(code)
    c = closes[-1]
    prev = closes[-2]
    chg = (c / prev - 1) * 100
    mas = {5: ma(closes, 5), 10: ma(closes, 10), 20: ma(closes, 20),
           30: ma(closes, 30), 60: ma(closes, 60), 120: ma(closes, 120),
           250: ma(closes, 250), "hi52": max(closes[-250:])}
    rsi2 = rsi(closes, 2)
    rsi14 = rsi(closes, 14)
    mid, up, lowb = boll(closes, 20)
    dif, dea, h, h_prev = macd(closes)
    # 跌破均线计数（5/10/20/30/60/120/250）
    broken = []
    for n in (5, 10, 20, 30, 60, 120, 250):
        m = mas.get(n)
        if m and c < m:
            broken.append((n, m))
    above = [n for n in (5, 10, 20, 60) if mas.get(n) and c >= mas[n]]
    ret60 = (c / closes[-61] - 1) * 100 if len(closes) > 60 else None
    ret20 = (c / closes[-21] - 1) * 100 if len(closes) > 20 else None
    dd_hi = (c / mas["hi52"] - 1) * 100
    score = strike_score(c, mas, rsi2, rsi14, h)
    # MACD 定性
    if h > 0 and h >= h_prev:
        macd_txt = "偏多"
    elif h > 0:
        macd_txt = "转多"
    elif h < 0 and dif > dea:
        macd_txt = "走平"
    else:
        macd_txt = "中性"
    dev = {}
    for n in (5, 10, 20, 60):
        m = mas.get(n)
        dev[n] = (c / m - 1) * 100 if m else None
    return dict(
        code=code, name=name, tracker=tracker, date=dates[-1], c=c, prev=prev,
        chg=chg, mas=mas, dev=dev, rsi2=rsi2, rsi14=rsi14, boll=(mid, up, lowb),
        dif=dif, dea=dea, hist=h, broken=broken, above=above, ret60=ret60,
        ret20=ret20, dd_hi=dd_hi, score=score, macd_txt=macd_txt,
        low52=min(closes[-250:]), hi52=mas["hi52"], vol=vols[-1],
    )


def fmt(x, p=2, sign=False):
    if x is None:
        return "—"
    s = f"{x:+.{p}f}" if sign else f"{x:.{p}f}"
    return s


def pct(x, sign=True):
    return fmt(x, 2, sign) + "%"


def cls(x):
    return "up" if x >= 0 else "down"


def score_tag(s):
    if s >= 3.5:
        return '<span class="tag t-hot">', f"★★★★ {s}", "</span>"
    if s >= 3.0:
        return '<span class="tag t-mid">', f"★★★ {s}", "</span>"
    if s >= 2.5:
        return '<span class="tag t-mid">', f"★★½ {s}", "</span>"
    return '<span class="tag t-cold">', f"★★ {s}", "</span>"


def build_html(results, gen_time):
    results_sorted = sorted(results, key=lambda r: r["score"], reverse=True)
    # 全景表
    rows = ""
    for r in results_sorted:
        d = r["dev"]
        ma_cells = ""
        for n in (5, 10, 20, 60):
            v = d[n]
            if v is None:
                ma_cells += "<td>—</td>"
            else:
                ma_cells += f'<td class="{cls(v)}">{pct(v)}</td>'
        r2 = fmt(r["rsi2"], 1) if r["rsi2"] is not None else "—"
        r2_hl = f'<b class="hl">{r2}</b>' if (r["rsi2"] is not None and r["rsi2"] <= 20) else r2
        a, b, c = score_tag(r["score"])
        hl = ' style="background:#fff5f4"' if r["score"] >= 3.5 else ""
        rows += f"""      <tr{hl}>
        <td class="name">{r['code']} {r['name']}</td>
        <td>{fmt(r['c'])}</td><td class="{cls(r['chg'])}">{pct(r['chg'])}</td>
        <td>{pct(r['dd_hi'])}</td><td>{pct(r['ret60'])}</td><td>{pct(r['ret20'])}</td>
        {ma_cells}
        <td>{r2_hl}</td><td>{r['macd_txt']}</td>
        <td>{a}{b}{c}</td>
      </tr>\n"""
    # 排序矩阵
    matrix = ""
    labels = {0: "首选", 1: "次选", 2: "观察", 3: "趋势", 4: "偏弱"}
    for i, r in enumerate(results_sorted):
        a, b, c = score_tag(r["score"])
        width = int(r["score"] / 5 * 100)
        tag = labels.get(i, "")
        tcls = "t-hot" if r["score"] >= 3.5 else ("t-mid" if r["score"] >= 2.5 else "t-cold")
        matrix += f"""      <div class="m-item">
        <div class="nm">{r['code']} {r['name']} <span class="tag {tcls}">{tag}</span></div>
        <div class="bar"><i style="width:{width}%"></i></div>
        <div class="sc">击球区分 {r['score']}/5 · RSI₂={fmt(r['rsi2'],1) if r['rsi2'] is not None else '—'} · 距52w高 {pct(r['dd_hi'])} · 站上均线 {len(r['above'])}/4</div>
      </div>\n"""
    # 159316 专项
    hk = next(r for r in results if r["code"] == "sz159316")
    broken_txt = "、".join(f"MA{n}({fmt(m)})" for n, m in hk["broken"]) or "无（均站上）"
    above_long = [n for n in (60, 120, 250) if hk["mas"].get(n) and hk["c"] >= hk["mas"][n]]
    above_long_txt = "、".join(f"MA{n}" for n in above_long) or "无（长周期均线全破）"
    support_lines = f"""
      <tr><td>BOLL下轨(20,2σ)</td><td>{fmt(hk['boll'][2])}</td><td>超卖反弹需求强，已贴近</td></tr>
      <tr><td>MA60（年线）</td><td>{fmt(hk['mas'][60])}</td><td><b>核心支撑</b>，不破则趋势未坏</td></tr>
      <tr><td>MA120</td><td>{fmt(hk['mas'][120])}</td><td>中期多空分水岭</td></tr>
      <tr><td>52周低位</td><td>{fmt(hk['low52'])}</td><td>下方终极防线</td></tr>
      <tr><td>52周高位</td><td>{fmt(hk['hi52'])}</td><td>距此 {pct(hk['dd_hi'])}</td></tr>"""
    r2 = hk["rsi2"]
    verdict = ("具备抄底条件，但需分档、控仓、设止损" if (r2 is not None and r2 <= 25)
               else "超卖但趋势未确认，等回踩支撑或站稳MA20再加")
    strategy = f"""
      <li><b>激进档：</b>贴近 BOLL下轨({fmt(hk['boll'][2])})～MA60({fmt(hk['mas'][60])}) 区间小仓埋伏，<b>止损破 MA60({fmt(hk['mas'][60])})</b>。</li>
      <li><b>稳健档：</b>等重新站回 MA20({fmt(hk['mas'][20])}) 且放量确认后再跟进，避免下落途中接飞刀。</li>
      <li><b>当前({fmt(hk['c'])}，{pct(hk['chg'])}）：</b>RSI₂={fmt(r2,1) if r2 is not None else '—'}{' 极度超卖' if (r2 is not None and r2<=20) else ''}；MACD{hk['macd_txt']}；已跌破 {len(hk['broken'])} 根均线（{broken_txt}），未见止跌信号前不宜满仓。</li>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF击球区诊断 · {gen_time[:10]}</title>
<style>
  :root{{--up:#d8392b; --down:#1a9e54; --bg:#ffffff; --card:#f7f8fa;
    --line:#e6e8eb; --txt:#1f2329; --sub:#6b7280; --acc:#2563eb;}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--txt);padding:24px;line-height:1.55}}
  .wrap{{max-width:1080px;margin:0 auto}}
  h1{{font-size:22px;margin-bottom:4px}}
  .meta{{color:var(--sub);font-size:13px;margin-bottom:6px}}
  .up{{color:var(--up);font-weight:600}}
  .down{{color:var(--down);font-weight:600}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:16px 18px;margin-bottom:18px}}
  h2{{font-size:16px;margin-bottom:10px;border-left:4px solid var(--acc);padding-left:8px}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}}
  th,td{{border:1px solid var(--line);padding:7px 8px;text-align:center}}
  th{{background:#eef1f4;font-weight:600}}
  td.name{{text-align:left;font-weight:600}}
  .tag{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600}}
  .t-hot{{background:#fde8e6;color:var(--up)}}
  .t-mid{{background:#fef3e0;color:#c97a12}}
  .t-cold{{background:#e8f6ee;color:var(--down)}}
  .matrix{{display:flex;flex-wrap:wrap;gap:12px}}
  .m-item{{flex:1 1 190px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px}}
  .m-item .nm{{font-weight:700;font-size:14px;margin-bottom:6px}}
  .bar{{height:8px;border-radius:4px;background:#e6e8eb;overflow:hidden;margin:6px 0}}
  .bar > i{{display:block;height:100%;background:linear-gradient(90deg,#1a9e54,#d8392b)}}
  .m-item .sc{{font-size:12px;color:var(--sub)}}
  ul{{padding-left:18px;margin:6px 0}}
  li{{margin:4px 0;font-size:13.5px}}
  .note{{font-size:12.5px;color:var(--sub);margin-top:8px}}
  .warn{{background:#fff7e6;border:1px solid #ffd591;border-radius:8px;padding:10px 12px;font-size:13px;margin-top:8px}}
  b.hl{{color:var(--acc)}}
  .verdict{{background:#eef4ff;border:1px solid #bcd2ff;border-radius:8px;padding:10px 12px;font-size:13.5px;margin-top:8px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>ETF 击球区诊断报告</h1>
  <div class="meta">数据日期 {results_sorted[0]['date']}（最近交易日收盘）· 生成于 {gen_time}（北京时间）</div>
  <div class="meta">数据来源：腾讯财经公开行情接口（前复权日K，与 WeStock 同源）· 红涨绿跌 · 本页每日收盘后自动更新</div>

  <div class="card">
    <h2>一、五只ETF全景对比</h2>
    <table>
      <thead><tr>
        <th>ETF</th><th>现价</th><th>今日</th><th>距52w高</th><th>60日</th><th>20日</th>
        <th>MA5</th><th>MA10</th><th>MA20</th><th>MA60</th><th>RSI(2)</th><th>MACD</th><th>击球区</th>
      </tr></thead>
      <tbody>
{rows}      </tbody>
    </table>
    <div class="note">MA列显示「价格相对该均线的偏离%」，绿=价格已跌破该均线。击球区分 0–5（越高越接近可介入的回调支撑位）。评分=深度回调(距52w高回撤) + 超卖(RSI₂) + 结构未破(已≤MA20且站上MA60/MA120) + 企稳(MACD柱翻正)，仅作相对排序参考；处于上升通道(价格>MA20)者不计入击球区。</div>
  </div>

  <div class="card">
    <h2>二、击球区排序（风险/赔率视角，按分数降序）</h2>
    <div class="matrix">
{matrix}    </div>
  </div>

  <div class="card">
    <h2>三、sz159316 港股创新药 · 技术面诊断（规则自动）</h2>
    <ul>
      <li><b>定性：</b>本页仅呈现客观技术面。单日跌幅 {pct(hk['chg'])}，RSI₂={fmt(hk['rsi2'],1) if hk['rsi2'] is not None else '—'}{' 进入极度超卖区（≤20）' if (hk['rsi2'] is not None and hk['rsi2']<=20) else ''}。</li>
      <li><b>均线结构：</b>收盘 {fmt(hk['c'])} 跌破 {len(hk['broken'])} 根均线（{broken_txt}）；长周期中仍站稳 {above_long_txt} 之上。</li>
      <li><b>区间位置：</b>距52周高点 {pct(hk['dd_hi'])}，处于年内中低位；BOLL下轨 {fmt(hk['boll'][2])} 已贴近，短线超卖反弹需求强。</li>
      <li class="note">注：大跌的具体新闻催化（如板块获利了结、外围利率扰动、个股事件等）需结合当日资讯面独立研判，本自动页不臆测原因。</li>
    </ul>
  </div>

  <div class="card">
    <h2>四、sz159316 能否抄底 · 策略（按计算价位分档）</h2>
    <table>
      <thead><tr><th>关键位</th><th>数值</th><th>含义</th></tr></thead>
      <tbody>{support_lines}</tbody>
    </table>
    <ul style="margin-top:10px">{strategy}</ul>
    <div class="verdict">结论：估值/趋势技术面 = <b>{verdict}</b>。优先等回踩 MA60 支撑区或重新站稳 MA20 再加重。</div>
  </div>

  <div class="card">
    <h2>五、数据来源与免责</h2>
    <div class="note">行情/均线/技术指标：腾讯财经公开接口（web.ifzq.gtimg.cn 前复权日K，与 WeStock/腾讯自选股同源），截至最近交易日收盘由 generate.py 自动计算。MA5/10/20/30/60/120/250、RSI(2)/(14) Wilder平滑、BOLL(20,2σ)、MACD(12,26,9) 均由前复权收盘价计算。本报告仅为客观数据分析，不构成投资建议，投资有风险。</div>
  </div>
</div>
</body>
</html>"""
    return html


def main():
    results = []
    for code, name, tracker in ETFS:
        try:
            results.append(analyze(code, name, tracker))
        except Exception as e:
            print(f"[WARN] {code} 获取失败: {e}")
    if not results:
        raise SystemExit("无可用数据，终止生成")
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    gen_time = now.strftime("%Y-%m-%d %H:%M")
    html = build_html(results, gen_time)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成 index.html，数据日期 {results[0]['date']}，{len(results)} 只标的")


if __name__ == "__main__":
    main()
