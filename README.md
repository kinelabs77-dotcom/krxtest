# KRX 전종목 일봉·수급 저장소 (회사 PC 없이 돌아가는 수집기)

코스피·코스닥 전종목의 일봉(시·고·저·종·거래량)과 외국인·기관 순매수(원), 코스피·코스닥 지수를
평일 장 마감 후 자동으로 받아 `data/` 에 저장합니다. 종목을 새로 추가해도 과거 자료가 이미 있어서
PC 없이 바로 1234 신호를 계산할 수 있습니다.

## 처음 한 번 해야 할 일 (대표님)
1. GitHub 계정이 없으면 만듭니다(무료).
2. **비공개(Private) 저장소**를 하나 만듭니다. 이름 예: `kr-market-data`. 이 폴더의 파일을 그대로 올립니다
   (클로드에 GitHub를 연결해 주시면 제가 올릴 수 있습니다).
3. 저장소 **Settings → Secrets and variables → Actions → New repository secret** 에서 두 개를 만듭니다.
   - `KRX_ID` = data.krx.co.kr 아이디
   - `KRX_PW` = data.krx.co.kr 비밀번호
   (회사 PC 의 `config.json` 에 넣어 두셨던 그 값입니다. 클로드에게 알려 주시면 안 됩니다. GitHub 화면에 직접 입력하세요.)
4. 저장소 **Actions** 탭 → 「KRX 전종목 일봉·수급 수집」 → **Run workflow** → `mode = probe` 로 실행합니다.
   KRX 가 GitHub 서버(해외 IP)를 받아 주는지 확인하는 점검입니다(아무것도 저장하지 않음).
5. 점검이 성공이면 같은 화면에서 `mode = backfill`, `start = 20251201` 로 한 번 실행합니다(약 20~40분).
   이후에는 평일 16:30·18:50(KST)에 자동으로 이어 붙습니다.

## 파일
- `collect_krx.py` 수집기(표준 라이브러리만). `probe` / `update` / `backfill 20251201`.
- `tools/make_master.py` 필요한 종목만 골라 기존 `ohlcv_master.json` 과 같은 모양으로 만듭니다(paper_daily.js 등이 그대로 읽음).
- `data/stocks/<코드>.json` 종목별 일봉·수급, `data/index.json` 지수, `data/listing.json` 이름↔코드, `data/status.json` 마지막 날짜·못 받은 날.
- `.github/workflows/daily.yml` 자동 실행 설정.

## 못 받은 날 처리
KRX 가 중간에 응답하지 않으면 그 날짜를 `status.json` 의 `bar_gaps`/`flow_gaps` 에 적어 두고 다음 실행 때 다시 받습니다
(예전 PC 수집기는 한 번 실패하면 이후 수급을 통째로 건너뛰었습니다).

## 한계
- KRX 가 해외(GitHub) 접속을 막으면 4번 점검이 실패합니다. 그때는 같은 스크립트를 국내 서버(고정 한국 IP)에서 돌리면 됩니다.
- 장중 현재가·보유종목(토스 API)은 이 저장소에 포함되지 않습니다(토스는 등록한 IP 에서만 호출 가능).
- 조회 전용입니다. 주문 기능은 없습니다.
