#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
저장소의 전종목 자료에서, 필요한 종목만 골라 기존 ohlcv_master.json 과 같은 모양으로 만든다.
(paper_daily.js · stock_review.js · 시뮬레이터가 그대로 읽는 형식: stocks[이름]={code,bars}, flows[이름]={날짜:{foreign,inst}}, index)

  python tools/make_master.py --codes 107640,078600 --out ohlcv_master.json
  python tools/make_master.py --names-file names.json --out ohlcv_master.json   # {"이름":"코드", ...} 또는 [{"name","code"}...]

이름은 입력한 이름을 그대로 키로 쓴다(밸런스아카데미의 종목명과 맞추기 위함). 이름만 주면 listing.json 에서 이름으로 찾는다.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")


def load(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="")
    ap.add_argument("--names-file", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    listing = load(os.path.join(DATA, "listing.json"), {})
    by_name = {v["name"].replace(" ", "").upper(): k for k, v in listing.items()}
    want = {}  # 키 이름 -> 코드
    for c in [x.strip() for x in a.codes.split(",") if x.strip()]:
        want[listing.get(c, {}).get("name", c)] = c
    if a.names_file:
        raw = load(a.names_file, {})
        items = raw.items() if isinstance(raw, dict) else [(x["name"], x.get("code", "")) for x in raw]
        for n, c in items:
            c = str(c).strip() or by_name.get(n.replace(" ", "").upper(), "")
            if c:
                want[n] = c
            else:
                print(f"[경고] {n}: 코드를 찾지 못했습니다", file=sys.stderr)
    stocks, flows, miss = {}, {}, []
    for n, c in want.items():
        st = load(os.path.join(DATA, "stocks", f"{c}.json"), None)
        if not st or not st.get("bars"):
            miss.append(f"{n}({c})")
            continue
        stocks[n] = {"code": c, "bars": st["bars"]}
        flows[n] = st.get("flows", {})
    status = load(os.path.join(DATA, "status.json"), {})
    out = {"stocks": stocks, "flows": flows, "index": load(os.path.join(DATA, "index.json"), {}),
           "source": status.get("source", ""), "bar_fields": ["date", "open", "high", "low", "close", "volume"],
           "updated_at": status.get("updated_at", ""), "last_date": status.get("last_date")}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{len(stocks)}종목 저장 → {a.out} (마지막 날짜 {status.get('last_date')})" + (f" · 자료 없음: {', '.join(miss)}" if miss else ""))
    return 0 if not miss else 2


if __name__ == "__main__":
    sys.exit(main())
