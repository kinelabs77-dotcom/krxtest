# 장중 현재가 수집기 (표준 라이브러리만 사용)
# 출처를 순서대로 시도하고, 절반 이상 받아지는 첫 출처를 씁니다(막히면 자동으로 다음 출처로 전환).
#   1) 네이버 polling(실시간)  2) 야후 chart(약 15~20분 지연)  3) 다음 금융  4) 네이버 모바일(종목별)  5) KRX 당일 조회(로그인, 장중 지원 불확실)
# data/stocks/ 의 전종목 현재가 + 코스피·코스닥 지수를 data/intraday.json 에 저장합니다.
# 지수: 네이버 모바일 지수 -> 야후(^KS11, ^KQ11). 지수가 실패해도 종목 시세는 저장합니다.
# 모든 출처가 절반 미만이면 기존 파일을 건드리지 않고 오류로 끝납니다. 조회 전용.
import concurrent.futures
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
BATCH = 60
BUDGET = 100  # 출처 하나당 최대 초


def get(url, timeout=20, decode="utf-8", headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(decode, errors="replace")


def num(x):
    return float(str(x).replace(",", "").replace("+", ""))


def list_codes():
    d = os.path.join("data", "stocks")
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json") and f[:-5].isalnum())


def clock_market():
    k = datetime.datetime.now(KST)
    return "OPEN" if (k.weekday() < 5 and datetime.time(9, 0) <= k.time() <= datetime.time(15, 30)) else "CLOSE"


# ---------- 1) 네이버 polling ----------
def naver_batch(batch):
    url = "https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:" + ",".join(batch)
    last = None
    for attempt in range(3):
        try:
            j = json.loads(get(url, decode="cp949"))
            areas = j.get("result", {}).get("areas", [])
            return areas[0].get("datas", []) if areas else []
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (attempt + 1))
    print("naver batch fail:", batch[0], "...", last, file=sys.stderr)
    return []


def src_naver_polling(codes):
    prices, prev, market, traded_at = {}, {}, "", ""
    fails = 0
    t0 = time.time()
    for i in range(0, len(codes), BATCH):
        if time.time() - t0 > BUDGET * 2:
            break
        got = naver_batch(codes[i:i + BATCH])
        if not got:
            fails += 1
            if fails >= 3 and not prices:
                break
        for d in got:
            cd, nv = d.get("cd"), d.get("nv")
            if not cd or not isinstance(nv, (int, float)) or nv <= 0:
                continue
            prices[cd] = nv
            if isinstance(d.get("sv"), (int, float)):
                prev[cd] = d["sv"]
            if cd == "005930":
                market = d.get("ms", "")
                traded_at = (d.get("nxtOverMarketPriceInfo") or {}).get("localTradedAt", "")
        time.sleep(0.2)
    return prices, prev, market, traded_at


# ---------- 종목별 조회 공통(스레드) ----------
def per_code_all(codes, one, workers=12, budget=BUDGET):
    deadline = time.time() + budget
    stop = [False]
    prices, prev, latest = {}, {}, [0]

    def wrap(c):
        if stop[0] or time.time() > deadline:
            return c, None
        try:
            return c, one(c)
        except Exception:  # noqa
            return c, None

    done = ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for c, r in ex.map(wrap, codes):
            done += 1
            if r and isinstance(r.get("price"), (int, float)) and r["price"] > 0:
                ok += 1
                prices[c] = r["price"]
                if isinstance(r.get("prev"), (int, float)) and r["prev"] > 0:
                    prev[c] = r["prev"]
                if isinstance(r.get("time"), (int, float)) and r["time"] > latest[0]:
                    latest[0] = r["time"]
            if done >= 40 and ok == 0:
                stop[0] = True
    return prices, prev, latest[0]


# ---------- 2) 야후 chart ----------
def yahoo_chart(symbol):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=1d" % symbol
    for attempt in range(3):
        try:
            j = json.loads(get(url))
            res = (j.get("chart") or {}).get("result")
            if not res:
                return None
            m = res[0].get("meta", {})
            px = m.get("regularMarketPrice")
            if isinstance(px, (int, float)) and px > 0:
                return {"price": px, "prev": m.get("chartPreviousClose"), "time": m.get("regularMarketTime")}
            return None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (attempt + 1))
        except Exception:  # noqa
            time.sleep(1 + attempt)
    return None


def yahoo_one(code):
    for suf in (".KS", ".KQ"):
        r = yahoo_chart(code + suf)
        if r:
            return r
    return None


def src_yahoo(codes):
    prices, prev, latest = per_code_all(codes, yahoo_one)
    fresh = latest and (time.time() - latest) < 40 * 60
    market = "OPEN" if (clock_market() == "OPEN" and fresh) else "CLOSE"
    traded_at = datetime.datetime.fromtimestamp(latest, KST).isoformat() if latest else ""
    return prices, prev, market, traded_at


# ---------- 3) 다음 금융 ----------
def daum_one(code):
    j = json.loads(get("https://finance.daum.net/api/quotes/A%s" % code,
                       headers={"Referer": "https://finance.daum.net/quotes/A%s" % code}))
    return {"price": j.get("tradePrice"), "prev": j.get("prevClosingPrice"), "time": None}


def src_daum(codes):
    prices, prev, _ = per_code_all(codes, daum_one)
    return prices, prev, clock_market(), ""


# ---------- 4) 네이버 모바일(종목별) ----------
def naver_m_one(code):
    j = json.loads(get("https://m.stock.naver.com/api/stock/%s/basic" % code))
    close = num(j["closePrice"])
    chg = num(j.get("compareToPreviousClosePrice", "0"))
    return {"price": close, "prev": close - chg, "time": None}


def src_naver_mobile(codes):
    prices, prev, _ = per_code_all(codes, naver_m_one)
    return prices, prev, clock_market(), ""


# ---------- 5) KRX 당일 조회 ----------
def src_krx(codes):
    import collect_krx as K  # 같은 저장소의 KRX 수집기 재사용(KRX_ID/KRX_PW 환경변수 사용, 값은 출력하지 않음)
    if not K.login():
        raise RuntimeError("KRX 로그인 실패")
    dd = datetime.datetime.now(KST).strftime("%Y%m%d")
    bars = K.fetch_bars(dd)
    prices = {c: v[2][3] for c, v in bars.items() if c in set(codes)}
    return prices, {}, clock_market(), ""


SOURCES = [
    ("naver-polling", src_naver_polling, "네이버 실시간 시세(거래소 직접 수신, 지연 거의 없음). 수집은 GitHub 스케줄이라 실행 시각이 몇 분 밀릴 수 있음."),
    ("yahoo-chart", src_yahoo, "야후 지연 시세(약 15~20분 늦을 수 있음). 네이버가 막혀 자동 전환됨."),
    ("daum-quotes", src_daum, "다음 금융 시세(지연 여부 미확인). 네이버·야후가 막혀 자동 전환됨."),
    ("naver-mobile", src_naver_mobile, "네이버 모바일 종목별 시세. 네이버 polling·야후·다음이 막혀 자동 전환됨."),
    ("krx-mdcstat01501", src_krx, "KRX 당일 조회(장중 값이 실시간이 아닐 수 있음). 다른 출처가 모두 막혀 자동 전환됨."),
]


# ---------- 지수 ----------
def index_naver(name):
    j = json.loads(get("https://m.stock.naver.com/api/index/%s/basic" % name))
    close = num(j["closePrice"])
    if not (close > 0):
        raise ValueError("close<=0")
    out = {"close": round(close, 2), "traded_at": j.get("localTradedAt", ""), "source": "naver"}
    try:
        out["change"] = round(num(j.get("compareToPreviousClosePrice", "0")), 2)
        out["change_pct"] = round(num(j.get("fluctuationsRatio", "0")), 2)
    except Exception:  # noqa
        pass
    return out


def index_yahoo(sym):
    r = yahoo_chart(sym)
    if not r:
        raise ValueError("yahoo none")
    out = {"close": round(float(r["price"]), 2), "source": "yahoo"}
    if isinstance(r.get("prev"), (int, float)) and r["prev"] > 0:
        out["change"] = round(r["price"] - r["prev"], 2)
        out["change_pct"] = round((r["price"] / r["prev"] - 1) * 100, 2)
    return out


def fetch_index(name, ysym):
    for fn, arg in ((index_naver, name), (index_yahoo, ysym)):
        for attempt in range(2):
            try:
                return fn(arg)
            except Exception as e:  # noqa
                print("index fail:", fn.__name__, arg, e, file=sys.stderr)
                time.sleep(2)
    return None


def main():
    codes = list_codes()
    need = len(codes) * 0.5
    chosen, tried = None, {}
    for name, fn, note in SOURCES:
        try:
            prices, prev, market, traded_at = fn(codes)
        except Exception as e:  # noqa
            print("source error:", name, e, file=sys.stderr)
            tried[name] = "error"
            continue
        tried[name] = len(prices)
        print("source", name, "got", len(prices), "of", len(codes), "market", market)
        if len(codes) > 0 and len(prices) >= need:
            chosen = (name, prices, prev, market, traded_at, note)
            break
    if not chosen:
        print("수집 실패: 모든 출처가 절반 미만", json.dumps(tried), file=sys.stderr)
        sys.exit(1)
    name, prices, prev, market, traded_at, note = chosen
    index = {}
    for nm, ysym, key in (("KOSPI", "^KS11", "kospi"), ("KOSDAQ", "^KQ11", "kosdaq")):
        r = fetch_index(nm, ysym)
        if r:
            index[key] = r
    print("index", json.dumps(index, ensure_ascii=False))
    now = datetime.datetime.now(KST)
    out = {
        "asof": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": name,
        "market": market,
        "traded_at": traded_at,
        "delay_note": note,
        "tried": tried,
        "count": len(prices),
        "index": index,
        "prices": prices,
        "prev_close": prev,
    }
    with open(os.path.join("data", "intraday.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("saved", out["asof"], "source", name)


if __name__ == "__main__":
    main()
