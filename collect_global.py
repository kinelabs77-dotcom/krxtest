#!/usr/bin/env python3
"""글로벌 지표 수집 -> data/global.json (표준 라이브러리만).
출처: CNBC 시세(주 출처, 한 번에 전 종목) · 네이버 해외지수/환율(보조) · 코인베이스(비트코인) · CNN(공포탐욕).
야후는 GitHub 서버에서 429로 막혀 쓰지 않는다(2026-10-13 확인). 일부만 받아도 저장하고, 절반 미만이면 파일을 건드리지 않고 실패 종료."""
import json, sys, time, datetime, urllib.request, os
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
CNN_H = dict(UA, Origin="https://edition.cnn.com", Referer="https://edition.cnn.com/")
# key, 표시 이름, 묶음, CNBC 심볼, 변동 표기(pct=퍼센트, bp=금리 포인트차)
ITEMS = [
 ("spx","S&P500","us",".SPX","pct"), ("ixic","나스닥","us",".IXIC","pct"), ("dji","다우","us",".DJI","pct"), ("sox","필라델피아반도체","us",".SOX","pct"),
 ("es","S&P500 선물","fut","@ES.1","pct"), ("nq","나스닥 선물","fut","@NQ.1","pct"),
 ("vix","VIX","risk",".VIX","pct"), ("tnx","미 10년물 금리","risk","US10Y","bp"), ("dxy","달러인덱스","risk",".DXY","pct"),
 ("krw","원/달러","fx","KRW=","pct"), ("wti","WTI 유가","com","@CL.1","pct"), ("gold","금","com","@GC.1","pct"), ("btc","비트코인(24시간)","com",None,"pct"),
 ("ewy","EWY(한국ETF)","kr","EWY","pct"), ("kospi","코스피","kr",".KS11","pct"), ("kosdaq","코스닥","kr",".KQ11","pct"),
 ("n225","닛케이225","asia",".N225","pct"), ("hsi","항셍","asia",".HSI","pct"), ("sh","상해종합","asia",".SSEC","pct"),
 ("nvda","엔비디아","stk","NVDA","pct"), ("tsm","TSMC(ADR)","stk","TSM","pct"),
]
def raw(url, headers=None, tries=3, timeout=20):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers or UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last = e; print("  오류", url[:80], repr(e)[:100]); time.sleep(2 * (i + 1))
    raise last
def num(x):
    try: return float(str(x).replace(",", "").replace("%", "").replace("+", "").strip())
    except Exception: return None
def cnbc():
    syms = "|".join(s for _, _, _, s, _ in ITEMS if s)
    url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=" + urllib.request.quote(syms, safe="") + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1"
    j = json.loads(raw(url)); out = {}
    q = j["FormattedQuoteResult"]["FormattedQuote"]
    for r in (q if isinstance(q, list) else [q]):
        if str(r.get("code")) not in ("0", "None") : continue
        out[r.get("symbol")] = r
    return out
def naver_idx(code):
    j = json.loads(raw("https://api.stock.naver.com/index/%s/basic" % code, tries=2))
    p = num(j["closePrice"]); pct = num(j["fluctuationsRatio"])
    return {"price": p, "pct": pct, "chg": num(j.get("compareToPreviousClosePrice")), "t": j.get("localTradedAt")}
def naver_fx():
    j = json.loads(raw("https://m.stock.naver.com/front-api/marketIndex/productDetail?category=exchange&reutersCode=FX_USDKRW", tries=2))["result"]
    return {"price": num(j["closePrice"]), "pct": num(j["fluctuationsRatio"]) * (-1 if j.get("fluctuationsType", {}).get("name") == "FALLING" else 1), "chg": None, "t": j.get("localTradedAt")}
def btc():
    j = json.loads(raw("https://api.exchange.coinbase.com/products/BTC-USD/stats", tries=2))
    last, op = num(j["last"]), num(j["open"])
    return {"price": last, "pct": (last / op - 1) * 100, "chg": last - op, "t": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")}
def fng():
    try:
        j = json.loads(raw("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", CNN_H, tries=2))
        f = j["fear_and_greed"]
        return {"score": round(f["score"], 1), "rating": f["rating"], "prev_close": round(f.get("previous_close", 0), 1), "week": round(f.get("previous_1_week", 0), 1), "month": round(f.get("previous_1_month", 0), 1), "t": f.get("timestamp")}
    except Exception as e:
        print("fng 실패:", repr(e)[:150]); return None
def main():
    try: Q = cnbc()
    except Exception as e: print("CNBC 실패:", repr(e)[:150]); Q = {}
    fb = {"spx": ".INX", "ixic": ".IXIC", "dji": ".DJI"}
    out = {}
    for key, name, grp, sym, kind in ITEMS:
        d = None
        try:
            if key == "btc": d = btc()
            elif sym in Q:
                r = Q[sym]; p = num(r.get("last")); pct = num(r.get("change_pct")); ch = num(r.get("change"))
                if p is not None and pct is not None: d = {"price": p, "pct": pct, "chg": ch, "t": r.get("last_time")}
            if d is None and key in fb: d = naver_idx(fb[key])
            if d is None and key == "krw": d = naver_fx()
        except Exception as e: print("실패", key, repr(e)[:100])
        if not d or d["price"] is None: print("없음", key); continue
        row = {"name": name, "group": grp, "sym": sym or "BTC-USD", "price": round(d["price"], 4), "t": d["t"]}
        if kind == "bp" and d.get("chg") is not None: row["chg"] = round(d["chg"] * 100, 1); row["unit"] = "bp"
        else: row["chg"] = round(d["pct"], 2); row["unit"] = "%"
        out[key] = row
        print("OK", key, row["price"], row["chg"], row["unit"], row["t"])
    print("받은 지표 %d/%d" % (len(out), len(ITEMS)))
    if len(out) < len(ITEMS) // 2: sys.exit("절반 미만 — 파일을 갱신하지 않습니다")
    kst = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    res = {"asof": kst.isoformat(timespec="minutes"), "count": len(out), "items": out, "fng": fng()}
    os.makedirs("data", exist_ok=True)
    with open("data/global.json", "w", encoding="utf-8") as f: json.dump(res, f, ensure_ascii=False, indent=1)
if __name__ == "__main__": main()
