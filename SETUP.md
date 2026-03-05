# 직원 스케줄 생성기 - 설치 및 마이그레이션 가이드

> 이 문서는 직원 스케줄 생성기를 새로운 환경(집 iMac 등)으로 옮기고 실행하는 방법을 설명합니다.

---

## 목차

1. [필요 환경](#1-필요-환경)
2. [집 iMac으로 옮기는 방법](#2-집-imac으로-옮기는-방법)
3. [개인 계정 설정](#3-개인-계정-설정)
4. [집에서 실행하는 방법](#4-집에서-실행하는-방법)
5. [비밀번호 변경 방법](#5-비밀번호-변경-방법)
6. [Render.com 배포 방법](#6-rendercom-배포-방법)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. 필요 환경

| 항목 | 요구 사항 |
|------|-----------|
| Python | 3.9 이상 (권장: 3.11) |
| pip | Python과 함께 설치됨 |
| 운영체제 | macOS, Windows, Linux 모두 가능 |
| 브라우저 | Chrome, Safari, Edge 등 최신 브라우저 |
| 디스크 | 약 500MB (Python 패키지 포함) |

### macOS에서 Python 확인

```bash
# Python 버전 확인
python3 --version

# pip 확인
pip3 --version
```

Python이 설치되어 있지 않다면:

```bash
# Homebrew가 없는 경우 먼저 설치
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 설치
brew install python
```

또는 [python.org](https://www.python.org/downloads/)에서 직접 다운로드하여 설치할 수 있습니다.

---

## 2. 집 iMac으로 옮기는 방법

아래 3가지 방법 중 편한 것을 선택하세요.

### 방법 A: USB 또는 에어드롭으로 폴더 복사 (가장 간단)

1. **현재 Mac에서**: `schedule-web` 폴더 전체를 USB에 복사하거나 에어드롭으로 전송
2. **집 iMac에서**: 원하는 위치에 폴더를 붙여넣기 (예: 데스크톱)

```bash
# 예시: 데스크톱에 놓았다면
cd ~/Desktop/schedule-web
ls -la
# app.py, templates/, requirements.txt 등이 보이면 성공
```

> 에어드롭 방법: Finder에서 `schedule-web` 폴더를 선택 > 우클릭 > 공유 > AirDrop > 집 iMac 선택

### 방법 B: GitHub 개인 계정으로 Fork/Clone

현재 회사 계정의 GitHub 레포(`https://github.com/sam4827/schedule-web`)에서 개인 계정으로 옮기는 방법입니다.

**순서:**

1. 웹 브라우저에서 `https://github.com/sam4827/schedule-web` 접속
2. 우측 상단 **Fork** 버튼 클릭
3. 개인 계정을 선택하여 Fork 완료
4. 집 iMac에서 Fork한 레포를 Clone:

```bash
# 개인 계정 이름이 예를 들어 "my-personal"이라면:
cd ~/Desktop
git clone https://github.com/my-personal/schedule-web.git
cd schedule-web
```

> 레포가 Private으로 전환된 경우 Fork가 안 될 수 있습니다. 그 경우 방법 A 또는 C를 사용하세요.

### 방법 C: 파일 압축 후 이메일/클라우드로 전송

1. **현재 Mac에서** 폴더를 압축:

```bash
cd ~/Desktop
zip -r schedule-web.zip schedule-web/
```

2. 압축 파일을 아래 중 하나로 전송:
   - 이메일에 첨부하여 자신에게 전송
   - Google Drive / iCloud Drive / Dropbox에 업로드
   - 카카오톡 나에게 보내기

3. **집 iMac에서** 파일을 다운로드하고 압축 해제:

```bash
cd ~/Desktop
unzip schedule-web.zip
cd schedule-web
```

---

## 3. 개인 계정 설정

### 3-1. GitHub 개인 계정 만들기 + 레포 생성 + 푸시

이미 개인 GitHub 계정이 있다면 **레포 생성**부터 진행하세요.

#### 계정 생성

1. [github.com](https://github.com) 접속
2. **Sign up** 클릭
3. 개인 이메일로 계정 생성

#### 새 레포 생성 및 코드 푸시

```bash
# 1. schedule-web 폴더로 이동
cd ~/Desktop/schedule-web

# 2. 기존 git 정보 초기화 (회사 계정 연결 제거)
rm -rf .git

# 3. 새로 git 초기화
git init
git add .
git commit -m "Initial commit: 직원 스케줄 생성기"

# 4. GitHub에서 새 레포 생성 후 연결
#    (GitHub 웹사이트에서 "New repository" > 이름: schedule-web > Create)
git remote add origin https://github.com/본인계정/schedule-web.git
git branch -M main
git push -u origin main
```

> Private 레포로 만들면 다른 사람이 코드를 볼 수 없습니다. (권장)

#### Git 사용자 정보 설정

```bash
git config --global user.name "본인 이름"
git config --global user.email "본인 이메일@example.com"
```

### 3-2. ngrok 개인 계정 만들기

ngrok을 사용하면 로컬에서 실행 중인 서버를 외부에서 접속할 수 있습니다.

1. [ngrok.com](https://ngrok.com) 접속
2. **Sign up for free** 클릭 > 개인 이메일로 가입
3. 가입 후 대시보드에서 **Your Authtoken** 확인

#### ngrok 설치 및 설정

```bash
# Homebrew로 설치
brew install ngrok

# 또는 직접 다운로드: https://ngrok.com/download

# authtoken 설정 (대시보드에서 복사한 토큰)
ngrok config add-authtoken 본인의_AUTH_TOKEN
```

#### ngrok으로 외부 공유

```bash
# 앱이 실행 중인 상태에서 새 터미널 창을 열고:
ngrok http 5000
```

터미널에 표시되는 `https://xxxxx.ngrok-free.app` 주소를 상대방에게 전달하면 됩니다.

> 무료 계정은 접속 시 ngrok 경고 페이지가 한 번 표시됩니다. "Visit Site"를 누르면 진행됩니다.

### 3-3. Render.com 개인 계정으로 배포

Render.com에 배포하면 항상 접속 가능한 공개 URL을 받을 수 있습니다.
자세한 배포 절차는 아래 [6. Render.com 배포 방법](#6-rendercom-배포-방법)을 참고하세요.

---

## 4. 집에서 실행하는 방법

### Step 1: 터미널 열기

Spotlight(Cmd + Space)에서 "터미널" 입력 후 실행

### Step 2: 프로젝트 폴더로 이동

```bash
cd ~/Desktop/schedule-web
```

### Step 3: 가상 환경 생성 (최초 1회만)

```bash
python3 -m venv venv
```

### Step 4: 가상 환경 활성화

```bash
source venv/bin/activate
```

> 프롬프트 앞에 `(venv)`가 표시되면 성공입니다.

### Step 5: 패키지 설치 (최초 1회만)

```bash
pip install -r requirements.txt
```

### Step 6: 앱 실행

```bash
python3 app.py
```

### Step 7: 브라우저에서 접속

브라우저를 열고 주소창에 입력:

```
http://localhost:5000
```

### 앱 종료

터미널에서 `Ctrl + C`를 누르면 종료됩니다.

### 매번 실행할 때 (2회차 이후)

```bash
cd ~/Desktop/schedule-web
source venv/bin/activate
python3 app.py
```

또는 실행 스크립트를 사용:

```bash
cd ~/Desktop/schedule-web
source venv/bin/activate
bash start.sh         # 프로덕션 모드 (Gunicorn)
bash start.sh dev     # 개발 모드 (디버그 활성화)
```

---

## 5. 비밀번호 변경 방법

기본 비밀번호는 `schedule2026`입니다.

### 방법 1: 환경변수로 변경 (권장)

앱을 실행할 때 환경변수를 설정합니다:

```bash
# 일회성 변경
ACCESS_PASSWORD=새비밀번호 python3 app.py

# 또는 export로 세션 동안 유지
export ACCESS_PASSWORD=새비밀번호
python3 app.py
```

### 방법 2: .env 파일 만들기

프로젝트 폴더에 `.env` 파일을 만들면 편리합니다 (직접 터미널에서):

```bash
echo 'export ACCESS_PASSWORD=새비밀번호' > ~/Desktop/schedule-web/.env
```

실행 시:

```bash
source .env
python3 app.py
```

### 방법 3: Render.com에서 변경

Render 대시보드 > 해당 서비스 > **Environment** 탭 > `ACCESS_PASSWORD` 값 수정 > **Save Changes**

변경 후 서비스가 자동으로 재시작됩니다.

---

## 6. Render.com 배포 방법

Render.com을 사용하면 24시간 접속 가능한 웹 URL을 무료로 받을 수 있습니다.

### Step 1: 사전 준비

- GitHub 개인 계정에 `schedule-web` 레포가 Push되어 있어야 합니다.
  ([3-1 참고](#3-1-github-개인-계정-만들기--레포-생성--푸시))

### Step 2: Render.com 가입

1. [render.com](https://render.com) 접속
2. **Get Started for Free** 클릭
3. **GitHub 계정으로 로그인** 선택 (가장 편리)

### Step 3: 새 웹 서비스 생성

1. 대시보드에서 **New +** > **Web Service** 클릭
2. GitHub 레포 목록에서 `schedule-web` 선택
   - 목록에 안 보이면 "Configure account"를 눌러 레포 접근 권한 허용
3. 아래 설정 입력:

| 항목 | 값 |
|------|-----|
| Name | `schedule-generator` (또는 원하는 이름) |
| Region | `Oregon` 또는 `Singapore` |
| Branch | `main` |
| Runtime | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60` |
| Plan | `Free` |

### Step 4: 환경변수 설정

1. **Environment** 섹션에서 **Add Environment Variable** 클릭
2. 다음을 추가:

| Key | Value |
|-----|-------|
| `PYTHON_VERSION` | `3.11.11` |
| `ACCESS_PASSWORD` | 원하는 비밀번호 |

### Step 5: 배포

**Create Web Service** 클릭 후 빌드가 자동으로 시작됩니다. (약 3~5분 소요)

배포 완료 후 제공되는 URL (예: `https://schedule-generator-xxxx.onrender.com`)로 접속하면 됩니다.

### 이후 업데이트 방법

GitHub에 코드를 Push하면 Render.com이 자동으로 감지하여 재배포합니다:

```bash
git add .
git commit -m "업데이트 내용"
git push origin main
# Render.com이 자동으로 재배포 시작
```

> **참고**: 무료 플랜은 15분간 접속이 없으면 서비스가 자동으로 휴면(sleep)됩니다.
> 다시 접속하면 약 30초~1분 후 자동으로 깨어납니다.

---

## 7. 트러블슈팅

### 포트 충돌 (Address already in use)

```
OSError: [Errno 48] Address already in use
```

**해결 방법:**

```bash
# 5000번 포트를 사용 중인 프로세스 확인
lsof -i :5000

# 해당 프로세스 종료 (PID 번호 확인 후)
kill -9 PID번호

# 또는 다른 포트로 실행
python3 app.py  # app.py 내 port=5000을 다른 번호로 변경
```

> macOS Monterey 이상에서는 AirPlay 수신이 5000번 포트를 사용할 수 있습니다.
> 시스템 설정 > 일반 > AirDrop 및 Handoff > AirPlay 수신 모드 해제로 해결됩니다.

### 패키지 설치 에러

```bash
# pip 업그레이드 후 재시도
pip install --upgrade pip
pip install -r requirements.txt

# 특정 패키지만 문제가 되는 경우
pip install flask
pip install ortools
pip install pandas openpyxl
```

### OR-Tools 설치 실패

OR-Tools는 일부 환경에서 설치가 어려울 수 있습니다:

```bash
# Apple Silicon(M1/M2/M3) Mac의 경우
pip install ortools

# 버전을 지정하여 설치
pip install ortools==9.12.4544

# 그래도 안 되면 Rosetta 모드로 시도
arch -x86_64 pip3 install ortools
```

### "python3: command not found"

```bash
# Python 설치 여부 확인
which python3

# 없으면 Homebrew로 설치
brew install python

# 또는 python으로 실행 가능할 수 있음
python --version
```

### 가상 환경 관련 문제

```bash
# 가상 환경 삭제 후 재생성
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 브라우저에서 접속이 안 되는 경우

1. 터미널에서 앱이 정상 실행 중인지 확인 (에러 메시지 없는지)
2. `http://localhost:5000` 주소를 정확히 입력했는지 확인
3. 방화벽이 5000번 포트를 차단하고 있지 않은지 확인
4. 다른 브라우저로 시도

### ngrok 연결 문제

```bash
# authtoken이 설정되어 있는지 확인
ngrok config check

# authtoken 재설정
ngrok config add-authtoken 본인의_AUTH_TOKEN

# ngrok 버전 확인 (v3 이상 권장)
ngrok version
```

### Render.com 배포 실패

1. **Build Command**가 `pip install -r requirements.txt`로 정확히 설정되어 있는지 확인
2. **Start Command**가 올바른지 확인
3. Render 대시보드의 **Logs** 탭에서 에러 메시지 확인
4. `PYTHON_VERSION` 환경변수가 `3.11.11`로 설정되어 있는지 확인

### 솔버 타임아웃 (30초 초과)

- 직원 수가 20명 이상이면 솔버 시간이 길어질 수 있습니다.
- 제약 조건을 완화하거나 (D/O 횟수, 최소 근무 인원 등) 직원 수를 줄여보세요.

---

## 참고: 프로젝트 파일 구조

```
schedule-web/
  app.py              # Flask 백엔드 (OR-Tools 솔버 포함)
  templates/
    index.html         # 프론트엔드 (채팅 스타일 UI)
  requirements.txt     # Python 패키지 목록
  start.sh             # 실행 스크립트
  render.yaml          # Render.com 배포 설정
  Procfile             # Gunicorn 설정
  SETUP.md             # 이 문서
  USER_GUIDE.md        # 사용자 가이드
```
