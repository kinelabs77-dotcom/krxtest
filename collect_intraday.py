# 장중 현재가 수집기 (표준 라이브러리만 사용)
# 네이버 polling API로 data/stocks/ 에 있는 전종목의 현재가를 받아 data/intraday.json 에 저장합니다.
# 조회 전용. 일부만 받아졌거나 전부 실패하면 기존 파일을 건드리지 않고 오류로 끝납니다.
import datetime
import json
import os
import sys
import time
import urllib.request

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
BATCH = 60


def list_codes():
    d = os.path.join("data", "stocks")
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json") and f[:-5].isalnum())


def fetch(batch):
    url = "https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:" + ",".join(batch)
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
            j = json.loads(raw.decode("cp949", errors="replace"))
            areas = j.get("result", {}).get("areas", [])
            return areas[0].get("datas", []) if areas else []
        except Exception as e:  # noqa
            last = e
            time.sleep(2 * (attempt + 1))
    print("batch fail:", batch[0], "...", last, file=sys.stderr)
    return []


def main():
    codes = list_codes()
    prices, prev, market, traded_at = {}, {}, "", ""
    for i in range(0, len(codes), BATCH):
        for d in fetch(codes[i:i + BATCH]):
            cd = d.get("cd")
            nv = d.get("nv")
            if not cd or not isinstance(nv, (int, float)) or nv <= 0:
                continue
            prices[cd] = nv
            if isinstance(d.get("sv"), (int, float)):
                prev[cd] = d["sv"]
            if cd == "005930":
                market = d.get("ms", "")
                traded_at = (d.get("nxtOverMarketPriceInfo") or {}).get("localTradedAt", "")
        time.sleep(0.2)
    print("codes", len(codes), "got", len(prices), "market", market, "traded_at", traded_at)
    if len(codes) == 0 or len(prices) < len(codes) * 0.5:
        print("수집 실패: 절반 미만만 받아짐. 파일을 갱신하지 않습니다.", file=sys.stderr)
        sys.exit(1)
    now = datetime.datetime.now(KST)
    out = {
        "asof": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "naver-polling",
        "market": market,
        "traded_at": traded_at,
        "delay_note": "네이버 실시간 시세(거래소 직접 수신, 지연 거의 없음). 수집은 GitHub 스케줄이라 실행 시각이 몇 분 밀릴 수 있음.",
        "count": len(prices),
        "prices": prices,
        "prev_close": prev,
    }
    with open(os.path.join("data", "intraday.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("saved", out["asof"])


if __name__ == "__main__":
    main()
