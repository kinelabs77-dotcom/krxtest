#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
전종목 일봉(OHLCV) + 외국인·기관 수급 수집기 — 조회 전용, 표준 라이브러리만 사용.

기존 PC 수집기(update_ohlcv.py)가 쓰던 KRX 정보데이터시스템(data.krx.co.kr)의
같은 화면(MDCSTAT01501 전종목 시세 / MDCSTAT02401 투자자별 순매수)을 쓰되,
관심종목만이 아니라 코스피·코스닥 "전종목"을 날짜별로 저장한다.
→ 종목을 새로 추가해도 과거 일봉·수급이 이미 있어서 PC 없이 바로 신호를 계산할 수 있다.

  python collect_krx.py probe                 # 접속 점검만(로그인 + 최근 거래일 1일 조회, 아무것도 저장 안 함)
  python collect_krx.py update                # 마지막 저장일 다음 날부터 오늘(또는 어제)까지 이어 붙이기
  python collect_krx.py backfill 20251201     # 지정일부터 다시 받기(처음 한 번)

환경변수 KRX_ID / KRX_PW (GitHub Secrets) 로 로그인한다. 값은 어디에도 출력·저장하지 않는다.

저장 구조
  data/stocks/<종목코드>.json   {"code","name","market","bars":[[날짜,시,고,저,종,거래량]...],"flows":{날짜:{"foreign":원,"inst":원}}}
  data/index.json               {"KOSPI":[[날짜,시,고,저,종,거래대금(백만원)]...],"KOSDAQ":[...]}
  data/listing.json             {"종목코드":{"name","market","last"}}  (이름→코드 찾기용)
  data/status.json              마지막 날짜, 못 받은 날(재시도 대상) 등
"""
import http.cookiejar, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
STOCKS = os.path.join(DATA, "stocks")
START_DEFAULT = "2025-12-01"
SLEEP = float(os.environ.get("KRX_SLEEP", "0.5"))
INVESTORS = {"foreign": "9000", "inst": "7050"}  # 외국인, 기관합계

KRX_JSON_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
KRX_MAIN_URL = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020202"
KRX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
KRX_HEADERS = {"User-Agent": KRX_UA, "Referer": KRX_MAIN_URL, "X-Requested-With": "XMLHttpRequest",
               "Content-Type": "application/x-www-form-urlencoded"}
KRX_LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
KRX_LOGIN_JSP = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
KRX_LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_logged = {"ok": False, "tries": 0}


def login():
    """pykrx 와 같은 순서(세션 쿠키 → login.jsp → 로그인 POST → 중복 로그인이면 skipDup=Y)."""
    kid, kpw = os.environ.get("KRX_ID", ""), os.environ.get("KRX_PW", "")
    if not kid or not kpw:
        print("[오류] KRX_ID / KRX_PW 가 설정되지 않았습니다(저장소 Settings → Secrets).")
        return False
    _logged["tries"] += 1
    try:
        for url, ref in ((KRX_LOGIN_PAGE, None), (KRX_LOGIN_JSP, KRX_LOGIN_PAGE)):
            h = {"User-Agent": KRX_UA}
            if ref:
                h["Referer"] = ref
            with _opener.open(urllib.request.Request(url, headers=h), timeout=20) as r:
                r.read()

        def post(skip=False):
            p = {"mbrNm": "", "telNo": "", "di": "", "certType": "", "mbrId": kid, "pw": kpw}
            if skip:
                p["skipDup"] = "Y"
            req = urllib.request.Request(KRX_LOGIN_URL, data=urllib.parse.urlencode(p).encode(), method="POST",
                                         headers={"User-Agent": KRX_UA, "Referer": KRX_LOGIN_PAGE,
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with _opener.open(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        res = post()
        code = res.get("_error_code", "")
        if code == "CD011":
            res = post(True)
            code = res.get("_error_code", "")
        if code == "CD001":
            _logged["ok"] = True
            print("[완료] KRX 로그인 성공")
            return True
        print(f"[경고] KRX 로그인 실패({code}): {res.get('_error_message', '')}")
    except Exception as e:  # 네트워크·차단 등 — 원인 파악용으로 종류만 출력
        print(f"[경고] KRX 로그인 중 오류: {type(e).__name__}: {e}")
    return False


def krx_post(data, retries=3):
    """KRX JSON 조회. 로그아웃/비JSON 응답이면 한 번 다시 로그인하고 재시도한다. 끝내 실패하면 예외."""
    body = urllib.parse.urlencode(data).encode("utf-8")
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(KRX_JSON_URL, data=body, headers=KRX_HEADERS, method="POST")
            with _opener.open(req, timeout=40) as resp:
                raw = resp.read().decode("utf-8", "replace")
            if raw.strip() == "LOGOUT" or not raw.lstrip().startswith("{"):
                last = RuntimeError("비JSON 응답: " + raw[:80].replace("\n", " "))
                if _logged["tries"] < 3:
                    _logged["ok"] = False
                    login()
                time.sleep(2 * (i + 1))
                continue
            payload = json.loads(raw)
            return (payload.get("OutBlock_1") or payload.get("output") or []) if isinstance(payload, dict) else []
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def num(v):
    s = str(v if v is not None else "").replace(",", "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def iso_of(d):
    return d.strftime("%Y-%m-%d")


# ---------- 저장소 입출력 ----------
def read_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def write_json(path, obj, indent=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":") if indent is None else None, indent=indent)
    os.replace(tmp, path)


def stock_path(code):
    return os.path.join(STOCKS, f"{code}.json")


# ---------- 하루치 수집 ----------
def fetch_bars(dd):
    """그날 전종목 시세. {코드: (이름, 시장, [시,고,저,종,거래량])}. 시장별 실패는 예외로 올림."""
    out = {}
    for mkt in ("STK", "KSQ"):
        rows = krx_post({"bld": "dbms/MDC/STAT/standard/MDCSTAT01501", "mktId": mkt, "trdDd": dd})
        for r in rows:
            code = str(r.get("ISU_SRT_CD", "")).strip()
            o, h, l, c, v = (num(r.get(k)) for k in ("TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "ACC_TRDVOL"))
            if not code or c is None or not v:
                continue
            out[code] = (str(r.get("ISU_ABBRV") or r.get("ISU_NM") or "").strip(), mkt,
                         [int(o or c), int(h or c), int(l or c), int(c), int(v)])
        time.sleep(SLEEP)
    return out


def fetch_flows(dd):
    """그날 전종목 외국인·기관 순매수(원). {코드: {"foreign":..,"inst":..}}. 실패하면 예외."""
    out = {}
    for key, tp in INVESTORS.items():
        for mkt in ("STK", "KSQ"):
            rows = krx_post({"bld": "dbms/MDC/STAT/standard/MDCSTAT02401", "locale": "ko_KR", "mktId": mkt,
                             "invstTpCd": tp, "strtDd": dd, "endDd": dd, "share": "1", "money": "1", "csvxls_isNo": "false"})
            for r in rows:
                code = str(r.get("ISU_SRT_CD", "")).strip()
                val = num(r.get("NETBID_TRDVAL"))
                if code and val is not None:
                    out.setdefault(code, {})[key] = int(val)
            time.sleep(SLEEP)
    return out


def apply_day(iso, bars, flows, listing):
    """하루치 결과를 종목 파일에 반영. bars 가 None 이면 수급만, flows 가 None 이면 일봉만."""
    codes = set()
    if bars:
        codes |= set(bars)
    if flows:
        codes |= set(flows)
    for code in codes:
        p = stock_path(code)
        st = read_json(p, None)
        if st is None:
            if not bars or code not in bars:
                continue  # 상장 정보 없는 종목의 수급만 있는 경우는 건너뜀
            st = {"code": code, "name": bars[code][0], "market": bars[code][1], "bars": [], "flows": {}}
        if bars and code in bars:
            name, mkt, b = bars[code]
            st["name"], st["market"] = name or st.get("name", ""), mkt
            st["bars"] = [x for x in st["bars"] if x[0] != iso] + [[iso] + b]
            st["bars"].sort(key=lambda x: x[0])
            listing[code] = {"name": st["name"], "market": mkt, "last": st["bars"][-1][0]}
        if flows and code in flows:
            st["flows"][iso] = flows[code]
        write_json(p, st)


def update_index(start_iso, end_iso, status):
    idx = read_json(os.path.join(DATA, "index.json"), {})
    for name, (i1, i2) in {"KOSPI": ("1", "001"), "KOSDAQ": ("2", "001")}.items():
        bars = idx.get(name) or []
        s = start_iso if not bars else iso_of(datetime.strptime(max(b[0] for b in bars), "%Y-%m-%d") + timedelta(days=1))
        if s > end_iso:
            continue
        try:
            rows = krx_post({"bld": "dbms/MDC/STAT/standard/MDCSTAT00301", "locale": "ko_KR", "indIdx": i1, "indIdx2": i2,
                             "strtDd": s.replace("-", ""), "endDd": end_iso.replace("-", ""), "share": "2", "money": "3",
                             "csvxls_isNo": "false"})
        except Exception as e:
            print(f"  [경고] {name} 지수 조회 실패: {e}")
            status.setdefault("index_gaps", []).append(name)
            continue
        got = 0
        for r in rows:
            dd = str(r.get("TRD_DD", "")).strip().replace("/", "-").replace(".", "-")
            c = num(r.get("CLSPRC_IDX"))
            if len(dd) != 10 or c is None:
                continue
            o, h, l = (num(r.get(k)) for k in ("OPNPRC_IDX", "HGPRC_IDX", "LWPRC_IDX"))
            val = num(r.get("ACC_TRDVAL"))
            bars = [b for b in bars if b[0] != dd] + [[dd, o or c, h or c, l or c, c, int(val) if val is not None else None]]
            got += 1
        bars.sort(key=lambda b: b[0])
        idx[name] = bars
        print(f"  {name} 지수 {got}일 추가(총 {len(bars)}일)")
        time.sleep(SLEEP)
    write_json(os.path.join(DATA, "index.json"), idx)


# ---------- 명령 ----------
def trading_end(now):
    """오늘 일봉은 15:40 이후에만 넣는다(장중 값이 섞이지 않게)."""
    return now if (now.hour, now.minute) >= (15, 40) else now - timedelta(days=1)


def cmd_probe():
    if not login():
        return 1
    d = trading_end(datetime.now(KST))
    for _ in range(10):
        if d.weekday() < 5:
            dd = d.strftime("%Y%m%d")
            try:
                bars = fetch_bars(dd)
            except Exception as e:
                print(f"[실패] {dd} 시세 조회: {type(e).__name__}: {e}")
                return 1
            if bars:
                print(f"[성공] {dd} 시세 {len(bars)}종목")
                try:
                    fl = fetch_flows(dd)
                    print(f"[성공] {dd} 수급 {len(fl)}종목")
                except Exception as e:
                    print(f"[경고] {dd} 수급 조회 실패: {type(e).__name__}: {e}")
                    return 2
                return 0
        d -= timedelta(days=1)
    print("[실패] 최근 10일 중 시세가 있는 날을 찾지 못했습니다.")
    return 1


def cmd_collect(start_iso=None):
    now = datetime.now(KST)
    end = trading_end(now)
    end_iso = iso_of(end)
    status = read_json(os.path.join(DATA, "status.json"), {})
    listing = read_json(os.path.join(DATA, "listing.json"), {})
    if start_iso is None:
        last = status.get("last_date")
        start_iso = iso_of(datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)) if last else START_DEFAULT
    bar_gaps = set(status.get("bar_gaps", []))
    flow_gaps = set(status.get("flow_gaps", []))
    if not login():
        return 1
    days = []
    d = datetime.strptime(start_iso, "%Y-%m-%d")
    end_naive = end.replace(tzinfo=None)
    while d <= end_naive:
        if d.weekday() < 5:
            days.append(iso_of(d))
        d += timedelta(days=1)
    todo_days = sorted(set(days) | bar_gaps | flow_gaps)
    print(f"처리할 날짜 {len(todo_days)}일 ({todo_days[0] if todo_days else '-'} ~ {todo_days[-1] if todo_days else '-'}), 못 받은 날 재시도 {len(bar_gaps | flow_gaps)}일")
    new_bar_gaps, new_flow_gaps, ok_days, empty = set(), set(), 0, 0
    for iso in todo_days:
        dd = iso.replace("-", "")
        bars = flows = None
        need_bars = iso in days or iso in bar_gaps
        need_flows = iso in days or iso in flow_gaps or iso in bar_gaps
        if need_bars:
            try:
                bars = fetch_bars(dd)
            except Exception as e:
                print(f"  [경고] {iso} 시세 실패(다음 실행에서 재시도): {type(e).__name__}: {e}")
                new_bar_gaps.add(iso)
                continue
            if not bars:
                empty += 1
                print(f"  {iso}: 자료 없음(휴장일)")
                continue
        if need_flows:
            try:
                flows = fetch_flows(dd)
            except Exception as e:
                print(f"  [경고] {iso} 수급 실패(다음 실행에서 재시도): {type(e).__name__}: {e}")
                new_flow_gaps.add(iso)
        apply_day(iso, bars, flows, listing)
        ok_days += 1
        print(f"  {iso}: 시세 {len(bars) if bars else '-'}종목 · 수급 {len(flows) if flows else '-'}종목")
    update_index(START_DEFAULT if status.get("last_date") is None else start_iso, end_iso, status)
    write_json(os.path.join(DATA, "listing.json"), listing)
    ok_dates = [x for x in todo_days if x not in new_bar_gaps]
    status.update({"updated_at": now.isoformat(), "last_date": max([status.get("last_date") or ""] + ok_dates) or None,
                   "bar_gaps": sorted(new_bar_gaps), "flow_gaps": sorted(new_flow_gaps), "stocks": len(listing),
                   "source": "KRX MDCSTAT01501(전종목 시세) + MDCSTAT02401(외국인 9000·기관 7050 순매수, 원) + MDCSTAT00301(지수)"})
    write_json(os.path.join(DATA, "status.json"), status, indent=1)
    print(f"[완료] {ok_days}거래일 반영 · 휴장 {empty}일 · 시세 실패 {len(new_bar_gaps)}일 · 수급 실패 {len(new_flow_gaps)}일 · 전체 {len(listing)}종목")
    return 0 if not new_bar_gaps else 3


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "probe":
        return cmd_probe()
    if cmd == "update":
        return cmd_collect()
    if cmd == "backfill":
        s = sys.argv[2] if len(sys.argv) > 2 else START_DEFAULT.replace("-", "")
        # 처음부터 다시 받을 때는 상태를 초기화하지 않고 지정일부터 덮어쓴다
        return cmd_collect(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
