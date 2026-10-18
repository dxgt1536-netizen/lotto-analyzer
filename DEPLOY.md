# 배포 현황

## 완료됨 (2026-08-21)

- **서버**: 152.67.208.226 (Ubuntu 22.04, ubuntu 계정) — 이미 다른 서비스(gnuboard, news-cardgen 등)가
  Caddy 리버스 프록시로 떠 있던 서버라, 새 nginx를 깔지 않고 **기존 Caddy에 새 사이트 블록만 추가**했다.
- **도메인**: [lottostat.kr](https://lottostat.kr) (가비아에서 구매, `www.lottostat.kr`도 함께 연결).
  이전에 임시로 쓰던 `lottoanalysis.duckdns.org`는 `lottostat.kr`로 301 영구 리다이렉트되도록 처리함.
- **앱**: `~/lotto`에 배포, `.venv` + gunicorn(2 워커, 127.0.0.1:8000)
- **상시 실행**: systemd 서비스 `lotto` (`/etc/systemd/system/lotto.service`, `enable`됨 — 재부팅해도 자동 시작)
- **리버스 프록시 + HTTPS**: `/etc/caddy/Caddyfile`에 블록 추가 (`deploy/Caddyfile.snippet` 참고),
  Let's Encrypt 인증서 자동 발급 완료
- **데이터**: 로또 6/45 전체 1237회차 수집 완료, 매주 토요일 21:10 cron으로 자동 갱신
  (`crontab -l`에 `# lotto sync auto`로 등록됨)
- **SEO 기본 태그**: `/robots.txt`, `/sitemap.xml`, canonical, OG 태그, JSON-LD 모두 `lottostat.kr` 기준으로 응답 확인함
- **구글 서치 콘솔 소유권 확인 완료** — 아래 "해킹 의심 오류" 참고. **DNS(도메인 이름 공급업체) 방식**으로 확인됨.
  가비아 DNS의 TXT 레코드(`@`, `google-site-verification=OSNnN1V9DMvqxFodO7rDVgrLGo_x0UYYySGwleRDRCc`)를
  **절대 지우면 안 됨** — 지우면 인증이 풀림.
- **광고 자리**: 코드는 준비됐지만 `ADSENSE_CLIENT_ID`가 비어 있어 아직 꺼져 있는 상태 (아래 참고)

서버에서 상태 확인/재시작이 필요하면:
```bash
ssh -i "ssh-key-2024-02-17 (1).key" ubuntu@152.67.208.226
sudo systemctl status lotto        # 앱 상태
sudo systemctl restart lotto       # .env 수정 후 재시작
sudo journalctl -u lotto -f        # 실시간 로그
sudo systemctl reload caddy        # Caddyfile 수정 후 반영
```

## 겪었던 문제: 구글이 "사이트가 해킹되었을 가능성" 이라며 확인 거부

- **증상**: Search Console에서 "URL 접두어" + "HTML 파일" 방식으로 소유권 확인 시도할 때마다
  `lottoanalysis.duckdns.org`, `lottostat.kr` 도메인을 바꿔가며 시도해도 계속
  "사이트가 해킹되었을 가능성이 있는 것으로 확인되어 웹사이트를 확인하지 못했습니다" 오류 발생.
- **원인 추정**: 서버 자체를 점검했을 때 현재 활성 악성코드/이상 크론잡/변조 파일은 없었음.
  다만 이 서버(152.67.208.226)에서 과거에 gnuboard(그누보드) 게시판처럼 흔히 해킹 표적이 되는
  서비스가 돌았던 이력이 있어, **구글 Safe Browsing이 이 IP 자체를 예전에 위험 이력으로 분류해뒀을
  가능성이 큼**. 도메인을 새로 사도 같은 IP를 쓰는 한 이 낙인이 따라옴.
- **해결**: Search Console에서 "URL 접두어"(HTTP 콘텐츠를 크롤링해서 확인) 대신
  **"도메인" 속성 + DNS TXT 레코드** 방식으로 전환. DNS 인증은 콘텐츠를 크롤링하지 않고 DNS 조회만
  하기 때문에, "해킹 의심" 콘텐츠 스캔 필터를 우회해서 바로 통과됨.
- **참고**: 이 이슈는 우리 로또 사이트 코드 문제가 아니었음. 같은 IP에서 다른(특히 오래되고 관리가
  뜸한) 서비스를 운영 중이라면 앞으로도 같은 문제가 재발할 수 있으니, 새 사이트를 이 서버에 추가로
  띄울 땐 처음부터 "도메인" + DNS 방식으로 인증하는 걸 권장.

## 남은 일 (계정/심사가 필요해서 직접 하셔야 함)

### 1. 사이트맵 제출

Search Console 좌측 메뉴 **Sitemaps**에서 `sitemap.xml` 제출 (`https://lottostat.kr/sitemap.xml`,
이미 자동 생성되고 있음). 색인은 며칠~몇 주 걸릴 수 있음 — 정상.

네이버도 노출하려면 https://searchadvisor.naver.com 에서 동일하게(가능하면 DNS 방식으로) 진행 후
`NAVER_SITE_VERIFICATION` 입력.

### 2. 트래픽을 좀 쌓기

애드센스는 콘텐츠가 너무 적거나 방문자가 없으면 반려되는 경우가 많습니다. 서치콘솔 등록 후
검색 유입이 조금이라도 생길 때까지 기다렸다가 애드센스를 신청하는 걸 추천합니다.

### 3. 구글 애드센스 (광고)

1. https://www.google.com/adsense → `https://lottostat.kr`로 신청
2. 심사 통과 후 발급된 발행자 ID(`ca-pub-...`)를 서버 `.env`의 `ADSENSE_CLIENT_ID`에 입력
3. 애드센스 대시보드에서 디스플레이 광고 단위 2개를 만들어 슬롯 ID를
   `ADSENSE_SLOT_TOP`, `ADSENSE_SLOT_INLINE`에 입력
4. `sudo systemctl restart lotto` — 광고 스크립트와 `/ads.txt`가 자동으로 켜짐
5. 애드센스 "사이트" 메뉴에서 `ads.txt` 상태가 "발견됨"으로 바뀌는지 확인

### 참고

- 이 사이트는 복권 구매·베팅을 대행하지 않고 공개된 당첨 통계만 보여주므로 일반적인
  "도박" 카테고리 규제 대상은 아니지만, 애드센스 정책은 지역/국가마다 다르게 적용될 수
  있습니다. 승인이 안 되면 정책 센터의 반려 사유를 확인하세요.
- 페이지 하단 면책 문구(당첨 보장 안 함)는 정책 준수와 신뢰도를 위해 넣어뒀으니 임의로
  지우지 않는 걸 추천합니다.
- `ssh-key-2024-02-17 (1).key`는 이 VPS의 SSH 개인키입니다. `.gitignore`에 이미 제외 처리했지만,
  이 프로젝트를 다른 곳(특히 공개 저장소)에 올릴 계획이 있다면 이 폴더 밖으로 옮겨서 보관하는 걸
  권장합니다.
