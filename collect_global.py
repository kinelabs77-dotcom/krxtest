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
EXTRA = {"es": ["@SP.1", "@ES.1", "ES.1"], "nq": ["@ND.1", "@NQ.1", "NQ.1"]}  # CNBC 선물 심볼 후보
def pick(Q, key, sym):
    for s in [sym] + EXTRA.get(key, []):
        if s in Q: return Q[s]
    return None
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
def cnbc_fetch(symbols):
    url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=" + urllib.request.quote("|".join(symbols), safe="") + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1"
    j = json.loads(raw(url)); out = {}
    q = j["FormattedQuoteResult"]["FormattedQuote"]
    for r in (q if isinstance(q, list) else [q]):
        if str(r.get("code")) not in ("0", "None"): continue
        out[r.get("symbol")] = r
    return out
def cnbc():
    return cnbc_fetch([s for _, _, _, s, _ in ITEMS if s] + [x for v in EXTRA.values() for x in v])
# 미국 테마 섹터(임의 구성 — 모닝레터와 다를 수 있음). 평균은 구성 종목 전일 등락률의 단순평균
THEMES = [
 ("기계·농기계", ["CAT","DE","CNH","AGCO","PCAR","CMI"]),
 ("대형 기술주", ["AAPL","MSFT","GOOGL","AMZN","META","NFLX"]),
 ("제약·바이오", ["LLY","JNJ","MRK","PFE","REGN","VRTX","ABBV","AMGN"]),
 ("금융·가상자산", ["JPM","BAC","C","GS","MS","COIN","MSTR","HOOD"]),
 ("AI반도체·아날로그 반도체", ["NVDA","AMD","AVGO","ARM","TSM","TXN","ADI","MRVL"]),
 ("자동차·2차전지", ["TSLA","GM","F","RIVN","QS","ALB"]),
 ("사이버보안", ["CRWD","PANW","FTNT","ZS","S","NET","OKTA"]),
 ("AI서버·데이터센터 구축", ["SMCI","DELL","VRT","ANET","HPE","CRWV","ORCL"]),
 ("원전·전력장비", ["OKLO","SMR","CEG","VST","GEV","CCJ","NNE","ETN"]),
 ("메모리", ["MU","SNDK","WDC","STX"]),
 ("우주항공·양자·로봇", ["RKLB","ASTS","LUNR","IONQ","RGTI","QBTS","JOBY"]),
]
KO = {"CAT":"캐터필러","DE":"디어","CNH":"CNH 인더스트리얼","AGCO":"AGCO","PCAR":"패카","CMI":"커민스","AAPL":"애플","MSFT":"마이크로소프트","GOOGL":"알파벳","AMZN":"아마존","META":"메타","NFLX":"넷플릭스",
 "LLY":"일라이 릴리","JNJ":"존슨앤드존슨","MRK":"머크","PFE":"화이자","REGN":"리제네론","VRTX":"버텍스","ABBV":"애브비","AMGN":"암젠",
 "JPM":"JP모건","BAC":"뱅크오브아메리카","C":"씨티그룹","GS":"골드만삭스","MS":"모건스탠리","COIN":"코인베이스","MSTR":"스트래티지","HOOD":"로빈후드",
 "NVDA":"엔비디아","AMD":"AMD","AVGO":"브로드컴","ARM":"암 홀딩스","TSM":"TSMC","TXN":"텍사스 인스트루먼트","ADI":"아날로그 디바이시스","MRVL":"마벨",
 "TSLA":"테슬라","GM":"GM","F":"포드","RIVN":"리비안","QS":"퀀텀스케이프","ALB":"앨버말",
 "CRWD":"크라우드스트라이크","PANW":"팔로알토","FTNT":"포티넷","ZS":"지스케일러","S":"센티넬원","NET":"클라우드플레어","OKTA":"옥타",
 "SMCI":"슈퍼 마이크로 컴퓨터","DELL":"델","VRT":"버티브","ANET":"아리스타","HPE":"HPE","CRWV":"코어위브","ORCL":"오라클",
 "OKLO":"오클로","SMR":"뉴스케일","CEG":"컨스텔레이션","VST":"비스트라","GEV":"GE 버노바","CCJ":"카메코","NNE":"나노뉴클리어","ETN":"이튼",
 "MU":"마이크론","SNDK":"샌디스크","WDC":"웨스턴디지털","STX":"시게이트",
 "RKLB":"로켓랩","ASTS":"AST 스페이스모바일","LUNR":"인튜이티브 머신스","IONQ":"아이온큐","RGTI":"리게티","QBTS":"디웨이브","JOBY":"조비"}
def themes():
    try:
        Q = cnbc_fetch(sorted({s for _, l in THEMES for s in l}))
    except Exception as e:
        print("테마 실패:", repr(e)[:120]); return None
    out = []
    for name, lst in THEMES:
        mem = []
        for sy in lst:
            r = Q.get(sy); c = num(r.get("change_pct")) if r else None
            if c is not None: mem.append([sy, KO.get(sy, sy), round(c, 2)])
        if len(mem) < 3: print("테마 종목 부족", name, len(mem)); continue
        avg = sum(m[2] for m in mem) / len(mem)
        mem.sort(key=lambda m: m[2], reverse=avg >= 0)  # 평균과 같은 방향의 극단 종목이 맨 앞(주도 종목)
        out.append({"name": name, "avg": round(avg, 2), "n": len(mem), "members": mem})
    out.sort(key=lambda t: -t["avg"])
    print("테마 %d/%d" % (len(out), len(THEMES)))
    return out or None
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
        hist = []
        for p in (j.get("fear_and_greed_historical") or {}).get("data", []):
            try: hist.append([datetime.datetime.fromtimestamp(p["x"] / 1000, datetime.timezone.utc).strftime("%Y-%m-%d"), round(p["y"], 1)])
            except Exception: pass
        return {"score": round(f["score"], 1), "rating": f["rating"], "prev_close": round(f.get("previous_close", 0), 1), "week": round(f.get("previous_1_week", 0), 1), "month": round(f.get("previous_1_month", 0), 1), "year": round(f.get("previous_1_year", 0), 1), "t": f.get("timestamp"), "hist": hist[-380:]}
    except Exception as e:
        print("fng 실패:", repr(e)[:150]); return None
def probe_charts():
    H = dict(UA, Origin="https://www.cnbc.com", Referer="https://www.cnbc.com/")
    for u in ("https://ts-api.cnbc.com/harmony/app/charts/1D.json?symbol=.DJI",
              "https://ts-api.cnbc.com/harmony/app/bars/.DJI/5M/20261012/20261013/adjusted/EXTENDED.json",
              "https://ts-api.cnbc.com/harmony/app/bars/.DJI/1D/20260701/20261013/adjusted/EXTENDED.json",
              "https://ts-api.cnbc.com/harmony/app/bars/.SPX/1D/20260701/20261013/adjusted/EXTENDED.json",
              "https://api.stock.naver.com/chart/foreign/index/.DJI?periodType=dayCandle&range=3m",
              "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400"):
        try:
            req = urllib.request.Request(u, headers=H)
            with urllib.request.urlopen(req, timeout=20) as r: print("차트진단 OK", u[:90], r.read(500))
        except Exception as e:
            print("차트진단 실패", u[:90], repr(e)[:100])
CHART_KEYS = ["spx","ixic","dji","sox","es","nq","vix","tnx","dxy","krw","wti","gold","kospi","kosdaq","n225","hsi","sh"]
CH = dict(UA, Origin="https://www.cnbc.com", Referer="https://www.cnbc.com/")
def _bars(j):
    pb = (j.get("barData") or {}).get("priceBars")
    if not pb: raise ValueError(str(j.get("statusMessage") or list(j.keys()))[:140])
    return pb
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
TZ = {"spx": ("America/New_York", "뉴욕시간"), "ixic": ("America/New_York", "뉴욕시간"), "dji": ("America/New_York", "뉴욕시간"), "sox": ("America/New_York", "뉴욕시간"), "vix": ("America/New_York", "뉴욕시간"), "tnx": ("America/New_York", "뉴욕시간"), "kospi": ("Asia/Seoul", "한국시간"), "kosdaq": ("Asia/Seoul", "한국시간"), "n225": ("Asia/Tokyo", "도쿄시간"), "hsi": ("Asia/Hong_Kong", "홍콩시간"), "sh": ("Asia/Shanghai", "상하이시간")}
def charts(Q):
    out = {}
    now = datetime.datetime.now(datetime.timezone.utc)
    s14 = (now - datetime.timedelta(days=210)).strftime("%Y%m%d") + "000000"
    e14 = (now + datetime.timedelta(days=2)).strftime("%Y%m%d") + "000000"
    for key in CHART_KEYS:
        base = next((s for k, _, _, s, _ in ITEMS if k == key), None)
        r = pick(Q, key, base) if base else None
        csym = (r or {}).get("symbol") or base
        if not csym: continue
        qs = urllib.request.quote(csym, safe="@.=")
        try:
            ib = _bars(json.loads(raw("https://ts-api.cnbc.com/harmony/app/charts/1D.json?symbol=" + qs, CH, tries=2)))
            db = _bars(json.loads(raw("https://ts-api.cnbc.com/harmony/app/bars/%s/1D/%s/%s/adjusted/EXTENDED.json" % (qs, s14, e14), CH, tries=2)))
        except Exception as e:
            print("차트 실패", key, csym, repr(e)[:150]); continue
        try:
            tzn, tzl = TZ.get(key, ("Asia/Seoul", "한국시간")); tzo = ZoneInfo(tzn); us = key in ("spx", "ixic", "dji", "sox")
            pts = []
            for b in ib:
                t = datetime.datetime.strptime(b["tradeTime"][:12], "%Y%m%d%H%M").replace(tzinfo=ET).astimezone(tzo)
                if t.minute % 5: continue
                hm = t.strftime("%H%M")
                if us and not ("0930" <= hm <= "1600"): continue
                pts.append((t, hm, round(float(b["close"]), 2)))
            inter = [[hm, c] for _, hm, c in pts]
            d0 = pts[0][0].strftime("%Y%m%d")
            wd = "월화수목금토일"[pts[0][0].weekday()]
            cl = [float(b["close"]) for b in db]
            def ma(n): return [round(sum(cl[i - n + 1:i + 1]) / n, 2) if i >= n - 1 else None for i in range(len(cl))]
            m20, m60 = ma(20), ma(60)
            k = 66
            daily = [[b["tradeTime"][:8], round(float(b["open"]), 2), round(float(b["high"]), 2), round(float(b["low"]), 2), round(float(b["close"]), 2)] for b in db][-k:]
            prev = num((r or {}).get("previous_day_closing"))
            out[key] = {"sym": csym, "prev": prev, "ses": "%s/%s(%s)" % (int(d0[4:6]), int(d0[6:8]), wd), "tz": tzl, "i": inter, "d": daily, "m20": m20[-k:], "m60": m60[-k:]}
            print("차트 OK", key, csym, "분봉", len(inter), "일봉", len(daily), "원본", len(ib), len(db))
        except Exception as e:
            print("차트 변환 실패", key, repr(e)[:150], str(ib[:1])[:200])
    return out or None
def main():
    try: Q = cnbc()
    except Exception as e: print("CNBC 실패:", repr(e)[:150]); Q = {}
    fb = {"spx": ".INX", "ixic": ".IXIC", "dji": ".DJI"}
    out = {}
    for key, name, grp, sym, kind in ITEMS:
        d = None
        try:
            if key == "btc": d = btc()
            elif pick(Q, key, sym) is not None:
                r = pick(Q, key, sym); p = num(r.get("last")); pct = num(r.get("change_pct")); ch = num(r.get("change"))
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
    res = {"asof": kst.isoformat(timespec="minutes"), "count": len(out), "items": out, "fng": fng(), "themes": themes(), "charts": charts(Q)}
    os.makedirs("data", exist_ok=True)
    with open("data/global.json", "w", encoding="utf-8") as f: json.dump(res, f, ensure_ascii=False, indent=1)
if __name__ == "__main__": main()

