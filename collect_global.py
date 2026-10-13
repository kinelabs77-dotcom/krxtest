#!/usr/bin/env python3
"""글로벌 지표 수집 -> data/global.json (표준 라이브러리만). 일부 실패해도 받은 것만 저장, 절반 미만이면 파일을 건드리지 않고 실패 종료."""
import json, sys, time, datetime, urllib.request, urllib.parse, os
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json,*/*"}
# key, 이름, 묶음, 야후 심볼, 변동 표시(pct=퍼센트, bp=금리 포인트차)
ITEMS = [
 ("spx","S&P500","us","^GSPC","pct"), ("ixic","나스닥","us","^IXIC","pct"), ("dji","다우","us","^DJI","pct"), ("sox","필라델피아반도체","us","^SOX","pct"),
 ("es","S&P500 선물","fut","ES=F","pct"), ("nq","나스닥 선물","fut","NQ=F","pct"),
 ("vix","VIX","risk","^VIX","pct"), ("tnx","미 10년물 금리","risk","^TNX","bp"), ("dxy","달러인덱스","risk","DX-Y.NYB","pct"),
 ("krw","원/달러","fx","KRW=X","pct"), ("wti","WTI 유가","com","CL=F","pct"), ("gold","금","com","GC=F","pct"), ("btc","비트코인","com","BTC-USD","pct"),
 ("ewy","EWY(한국ETF)","kr","EWY","pct"), ("kospi","코스피","kr","^KS11","pct"), ("kosdaq","코스닥","kr","^KQ11","pct"),
 ("n225","닛케이225","asia","^N225","pct"), ("hsi","항셍","asia","^HSI","pct"), ("sh","상해종합","asia","000001.SS","pct"),
 ("nvda","엔비디아","stk","NVDA","pct"), ("tsm","TSMC(ADR)","stk","TSM","pct"),
]
def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e; time.sleep(1.5 * (i + 1))
    raise last
def chart(sym):
    for host in ("query1", "query2"):
        try:
            j = get("https://%s.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=10d" % (host, urllib.parse.quote(sym)))
            c = j["chart"]["result"][0]; m = c["meta"]
            cl = [x for x in c["indicators"]["quote"][0]["close"] if x is not None]
            price = m.get("regularMarketPrice") or (cl[-1] if cl else None)
            if price is None or len(cl) < 2: continue
            prev = cl[-2]  # 일봉 마지막이 오늘(장중 잠정 포함)이므로 직전 일봉 종가가 기준
            return {"price": round(price, 4), "prev": round(prev, 4), "t": datetime.datetime.fromtimestamp(m["regularMarketTime"], datetime.timezone.utc).isoformat(timespec="minutes")}
        except Exception as e:
            err = e
    return None
def fng():
    try:
        j = get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")
        f = j["fear_and_greed"]
        return {"score": round(f["score"], 1), "rating": f["rating"], "prev_close": round(f.get("previous_close", 0), 1), "week": round(f.get("previous_1_week", 0), 1), "month": round(f.get("previous_1_month", 0), 1), "t": f.get("timestamp")}
    except Exception as e:
        print("fng 실패:", e); return None
def main():
    out = {}; ok = 0
    for key, name, grp, sym, kind in ITEMS:
        d = chart(sym)
        if not d: print("실패", sym); continue
        ok += 1
        row = {"name": name, "group": grp, "sym": sym, "price": d["price"], "t": d["t"]}
        if kind == "bp": row["chg"] = round((d["price"] - d["prev"]) * 100, 1); row["unit"] = "bp"
        else: row["chg"] = round((d["price"] / d["prev"] - 1) * 100, 2); row["unit"] = "%"
        out[key] = row
    print("받은 지표 %d/%d" % (ok, len(ITEMS)))
    if ok < len(ITEMS) // 2: sys.exit("절반 미만 — 파일을 갱신하지 않습니다")
    kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    res = {"asof": kst.isoformat(timespec="minutes"), "count": ok, "items": out, "fng": fng()}
    os.makedirs("data", exist_ok=True)
    with open("data/global.json", "w", encoding="utf-8") as f: json.dump(res, f, ensure_ascii=False, indent=1)
if __name__ == "__main__": main()
