# ShiftMaker 배포 가이드

## 아키텍처
```
[사용자 브라우저] → HTTPS → [Render.com Flask 서버] → [Supabase PostgreSQL]
                                    (무료)                    (무료)
```
유지비용: **0원**

---

## 1단계: Supabase 데이터베이스 생성 (5분)

1. https://supabase.com 접속 → **Start your project** (GitHub 로그인)
2. **New Project** 클릭
   - Organization: 기본값
   - Name: `shiftmaker`
   - Database Password: 강력한 비밀번호 입력 (**반드시 메모**)
   - Region: `Northeast Asia (Seoul)` 선택
   - Plan: Free
3. 프로젝트 생성 완료 대기 (~2분)
4. **Settings** → **Database** → **Connection string** 섹션
   - `URI` 탭 선택
   - 연결 문자열 복사 (형식: `postgresql://postgres.[ref]:[YOUR-PASSWORD]@...`)
   - `[YOUR-PASSWORD]` 부분을 2번에서 입력한 비밀번호로 교체
   - **이 문자열을 메모장에 저장**

> Supabase 무료 티어: 500MB DB, 무제한 API 요청, 50K MAU

---

## 2단계: GitHub 저장소 Push (3분)

```bash
cd schedule-web
git add -A
git commit -m "ShiftMaker commercial edition"
git remote add origin https://github.com/YOUR_USERNAME/shiftmaker.git
git push -u origin main
```

> 이미 remote가 있다면 `git remote set-url origin ...` 사용

---

## 3단계: Render.com 배포 (5분)

1. https://render.com 접속 → **Get Started** (GitHub 로그인)
2. **New** → **Web Service**
3. GitHub 저장소 연결 → `shiftmaker` 선택
4. 설정:
   - **Name**: `shiftmaker` (URL이 `shiftmaker.onrender.com`이 됨)
   - **Region**: Singapore 또는 Oregon
   - **Branch**: `main`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60`
   - **Plan**: `Free`
5. **Environment Variables** 추가:
   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | 1단계에서 복사한 Supabase 연결 문자열 |
   | `SECRET_KEY` | (Generate 버튼 클릭) |
   | `RENDER` | `true` |
   | `PYTHON_VERSION` | `3.11.11` |
6. **Deploy Web Service** 클릭
7. 빌드 완료 대기 (~3분)

---

## 4단계: 접속 확인

배포 완료 후 `https://shiftmaker.onrender.com` 접속

1. 랜딩 페이지 확인
2. 매장 등록 테스트
3. 직원 추가 → 스케줄 생성 테스트

---

## 보안 체크리스트

| 항목 | 상태 |
|------|------|
| HTTPS 강제 (Render 자동) | ✅ |
| HSTS 헤더 | ✅ |
| Content-Security-Policy | ✅ |
| X-Frame-Options: DENY | ✅ |
| X-Content-Type-Options: nosniff | ✅ |
| XSS Protection | ✅ |
| 비밀번호 SHA-256 + Salt 해싱 | ✅ |
| 토큰 기반 인증 (7일 TTL) | ✅ |
| Rate Limiting (IP 기반) | ✅ |
| SQL Injection 방지 (Parameterized) | ✅ |
| CORS 설정 | ✅ |
| DB 직접 노출 없음 | ✅ |

---

## 로컬 개발

```bash
# DATABASE_URL 없이 실행하면 자동으로 SQLite 사용
python app.py --dev
```

## 커스텀 도메인 (선택)

Render.com 대시보드 → Settings → Custom Domains → 도메인 추가
→ DNS에 CNAME 레코드 설정

---

## 문제 해결

### Render 빌드 실패
- Python 버전 확인: `PYTHON_VERSION=3.11.11`
- ortools는 3.11에서 안정적

### DB 연결 오류
- `DATABASE_URL`이 정확한지 확인
- Supabase 프로젝트가 활성 상태인지 확인 (무료 티어는 7일 미사용 시 일시정지)
- 일시정지된 경우 Supabase 대시보드에서 Resume 클릭

### 서버 슬립 (Render 무료)
- 15분 미활동 시 서버 슬립 → 첫 접속 시 ~30초 대기
- 해결: UptimeRobot (무료) 등으로 5분마다 ping
