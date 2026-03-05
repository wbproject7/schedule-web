"""
직원 스케줄 웹 생성기 - Flask Backend
=====================================
OR-Tools CP-SAT Solver 기반 스케줄 최적화 API

실행: python3 app.py
접속: http://localhost:5000
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
from ortools.sat.python import cp_model
import pandas as pd
import calendar
from datetime import date
import os
import uuid
import time
import re

app = Flask(__name__, template_folder='templates')

# 임시 파일 저장 디렉토리 (클라우드 환경에서는 /tmp 사용)
import tempfile as _tmpmod
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', os.path.join(os.path.dirname(__file__), 'output'))
if not os.path.exists(OUTPUT_DIR):
    OUTPUT_DIR = os.path.join(_tmpmod.gettempdir(), 'schedule_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 생성된 파일 경로 저장 {file_id: (path, timestamp)}
file_store = {}
FILE_TTL = 3600  # 1시간 후 파일 자동 삭제

# Rate limiting {ip: [timestamps]}
rate_store = {}
RATE_WINDOW = 60   # 60초
RATE_MAX = 10       # 분당 최대 10회


# ============================================================
# 보안 유틸리티
# ============================================================

def validate_input(data):
    """입력 데이터 검증. 오류 문자열 리스트 반환."""
    errors = []

    # year
    try:
        year = int(data.get('year', 0))
        if not (2020 <= year <= 2035):
            errors.append('연도는 2020~2035 범위여야 합니다.')
    except (ValueError, TypeError):
        errors.append('올바른 연도를 입력해주세요.')

    # month
    try:
        month = int(data.get('month', 0))
        if not (1 <= month <= 12):
            errors.append('월은 1~12 범위여야 합니다.')
    except (ValueError, TypeError):
        errors.append('올바른 월을 입력해주세요.')

    # employees
    employees = data.get('employees', [])
    if not isinstance(employees, list):
        errors.append('직원 목록이 올바르지 않습니다.')
    elif len(employees) < 2:
        errors.append('직원은 최소 2명 이상이어야 합니다.')
    elif len(employees) > 50:
        errors.append('직원은 최대 50명까지 지원합니다.')
    else:
        # 이름 검증
        seen = set()
        for emp in employees:
            if not isinstance(emp, str) or len(emp.strip()) == 0:
                errors.append('직원 이름은 비어 있을 수 없습니다.')
                break
            if len(emp) > 20:
                errors.append(f'직원 이름은 20자 이내여야 합니다: {emp[:20]}...')
                break
            if emp in seen:
                errors.append(f'중복된 직원 이름: {emp}')
                break
            seen.add(emp)

    # managers
    managers = data.get('managers', [])
    if not isinstance(managers, list):
        errors.append('관리자 목록이 올바르지 않습니다.')
    elif isinstance(employees, list):
        for m in managers:
            if m not in employees:
                errors.append(f'관리자 "{m}"이(가) 직원 목록에 없습니다.')
                break

    # constraints 범위 검증
    cons = data.get('constraints', {})
    if isinstance(cons, dict):
        n = len(employees) if isinstance(employees, list) else 0
        checks = [
            ('doCount', 1, 28, 'D/O 횟수'),
            ('maxConsecutive', 1, 28, '최대 연속 근무'),
            ('maxConsecutiveOff', 1, 28, '최대 연속 휴무'),
            ('minWeekday', 1, n or 50, '평일 최소 근무'),
            ('minWeekend', 1, n or 50, '주말 최소 근무'),
            ('minWeekdayOff', 0, n or 50, '평일 최소 휴무'),
        ]
        for key, lo, hi, label in checks:
            try:
                v = int(cons.get(key, lo))
                if not (lo <= v <= hi):
                    errors.append(f'{label}은(는) {lo}~{hi} 범위여야 합니다.')
            except (ValueError, TypeError):
                errors.append(f'{label} 값이 올바르지 않습니다.')

    return errors


def check_rate_limit():
    """IP 기반 rate limit 체크. 초과 시 False 반환."""
    ip = request.remote_addr or 'unknown'
    now = time.time()

    if ip not in rate_store:
        rate_store[ip] = []

    # 윈도우 밖의 기록 제거
    rate_store[ip] = [t for t in rate_store[ip] if now - t < RATE_WINDOW]

    if len(rate_store[ip]) >= RATE_MAX:
        return False

    rate_store[ip].append(now)
    return True


def cleanup_files():
    """TTL 초과된 파일 정리"""
    now = time.time()
    expired = [fid for fid, (path, ts) in file_store.items() if now - ts > FILE_TTL]
    for fid in expired:
        path, _ = file_store.pop(fid, (None, 0))
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


# ============================================================
# 라우트
# ============================================================

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


@app.route('/api/solve', methods=['POST'])
def api_solve():
    """스케줄 생성 API"""
    # Rate limiting
    if not check_rate_limit():
        return jsonify({'success': False, 'error': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'}), 429

    # 파일 정리 (요청마다 트리거)
    cleanup_files()

    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': '요청 데이터가 비어있습니다.'}), 400

        # 입력 검증
        validation_errors = validate_input(data)
        if validation_errors:
            return jsonify({'success': False, 'error': ' / '.join(validation_errors)}), 400

        result = run_full_pipeline(data)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 내부 에러 메시지를 클라이언트에 노출하지 않음
        return jsonify({'success': False, 'error': '스케줄 생성 중 서버 오류가 발생했습니다. 조건을 확인 후 다시 시도해주세요.'}), 500


@app.route('/api/download/<file_id>')
def download(file_id):
    """생성된 파일 다운로드"""
    # file_id 형식 검증 (uuid_type 형태만 허용)
    if not re.match(r'^[a-f0-9]{8}_(excel|csv)$', file_id):
        return jsonify({'error': '잘못된 파일 ID입니다.'}), 400
    if file_id not in file_store:
        return jsonify({'error': '파일을 찾을 수 없습니다. (만료되었을 수 있습니다)'}), 404
    path, _ = file_store[file_id]
    if not os.path.exists(path):
        return jsonify({'error': '파일이 삭제되었습니다.'}), 404
    return send_file(path, as_attachment=True)


# ============================================================
# 메인 파이프라인
# ============================================================

def run_full_pipeline(data):
    """입력 데이터를 받아 전체 파이프라인 실행"""

    year = int(data['year'])
    month = int(data['month'])
    employees = data['employees']
    holidays = [int(d) for d in data.get('holidays', [])]
    constraints = data['constraints']
    pre_requests = data['preRequests']
    fair_weekend = data.get('fairWeekend', True)
    managers = data.get('managers', [])

    # 달력 정보 구성
    num_days = calendar.monthrange(year, month)[1]
    days = list(range(1, num_days + 1))
    day_of_week = {d: date(year, month, d).weekday() for d in days}

    weekend_or_holiday = set()
    for d in days:
        if day_of_week[d] >= 5 or d in holidays:
            weekend_or_holiday.add(d)

    # pre_requests 정규화 (문자열 키 → 정수 리스트)
    normalized_req = {}
    for emp in employees:
        req = pre_requests.get(emp, {'DO': [], 'MO': []})
        normalized_req[emp] = {
            'DO': [int(d) for d in req.get('DO', [])],
            'MO': [int(d) for d in req.get('MO', [])],
        }

    # constraints 정규화
    cons = {
        'do_count': int(constraints.get('doCount', 8)),
        'max_consec': int(constraints.get('maxConsecutive', 5)),
        'min_weekday': int(constraints.get('minWeekday', 4)),
        'min_weekend': int(constraints.get('minWeekend', 6)),
        'min_weekday_off': int(constraints.get('minWeekdayOff', 2)),
        'max_consec_off': int(constraints.get('maxConsecutiveOff', 4)),
    }

    # 1) 충돌 검증
    conflicts = detect_conflicts(
        employees, days, weekend_or_holiday, normalized_req, cons, year, month
    )

    # 2) 충돌 해결
    resolved_req = resolve_conflicts(
        employees, conflicts, normalized_req
    )

    # 3) 솔버 실행
    schedule = solve(
        employees, days, num_days, weekend_or_holiday,
        resolved_req, cons, fair_weekend, managers
    )

    if schedule is None:
        # 실패 원인 분석
        hints = []
        num_emp = len(employees)
        if cons['min_weekend'] >= num_emp:
            hints.append(f'주말 최소 근무({cons["min_weekend"]}명)가 전체 인원({num_emp}명) 이상입니다.')
        if cons['min_weekday'] >= num_emp:
            hints.append(f'평일 최소 근무({cons["min_weekday"]}명)가 전체 인원({num_emp}명) 이상입니다.')
        total_mo = sum(len(normalized_req[e]['MO']) for e in employees)
        if total_mo > num_days * (num_emp - cons['min_weekday']):
            hints.append('연차(M/O) 신청이 너무 많아 최소 근무 인원을 채울 수 없습니다.')
        if len(managers) >= 2 and cons['do_count'] * len(managers) > num_days:
            hints.append(f'관리자({len(managers)}명)의 D/O 합계가 총 일수를 초과합니다. 관리자 수를 줄이거나 D/O를 줄여주세요.')
        hint_msg = ' '.join(hints) if hints else '제약 조건 간의 충돌이 있습니다.'
        return {
            'success': False,
            'error': f'스케줄을 찾을 수 없습니다. {hint_msg}',
            'conflicts': conflicts,
        }

    # 4) 검증
    verification = verify(schedule, employees, days, weekend_or_holiday, day_of_week, cons, managers)

    # 5) 파일 생성
    file_id = str(uuid.uuid4())[:8]
    excel_id, csv_id = save_files(
        schedule, employees, year, month, days, day_of_week,
        weekend_or_holiday, cons, file_id
    )

    # 6) 응답 구성
    # schedule을 문자열 키로 변환 (JSON 호환)
    schedule_json = {}
    for emp in employees:
        schedule_json[emp] = {str(d): v for d, v in schedule[emp].items()}

    day_name_kr = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    cal_info = {
        'numDays': num_days,
        'dayOfWeek': {str(d): dow for d, dow in day_of_week.items()},
        'dayNames': day_name_kr,
        'weekendOrHoliday': sorted(weekend_or_holiday),
    }

    return {
        'success': True,
        'schedule': schedule_json,
        'calendarInfo': cal_info,
        'conflicts': conflicts,
        'verification': verification,
        'files': {
            'excel': f'/api/download/{excel_id}',
            'csv': f'/api/download/{csv_id}',
        },
    }


# ============================================================
# 충돌 검증
# ============================================================

def detect_conflicts(employees, days, weekend_or_holiday, pre_requests, constraints, year, month):
    """사전 신청 충돌 감지"""
    day_name_kr = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    num_employees = len(employees)
    conflicts = []

    for d in days:
        absent = []
        for emp in employees:
            req = pre_requests.get(emp, {'DO': [], 'MO': []})
            if d in req['DO'] or d in req['MO']:
                absent.append(emp)

        if d in weekend_or_holiday:
            max_absent = num_employees - constraints['min_weekend']
        else:
            max_absent = num_employees - constraints['min_weekday']

        if len(absent) > max_absent:
            dow = date(year, month, d).weekday()
            conflicts.append({
                'day': d,
                'dayStr': f"{month}월 {d}일({day_name_kr[dow]})",
                'employees': absent,
                'maxAbsent': max_absent,
                'actual': len(absent),
            })

    return conflicts


def resolve_conflicts(employees, conflicts, pre_requests):
    """충돌을 선착순으로 해결"""
    resolved = {}
    for emp in employees:
        req = pre_requests.get(emp, {'DO': [], 'MO': []})
        resolved[emp] = {'DO': list(req['DO']), 'MO': list(req['MO'])}

    rejected = []
    for c in conflicts:
        d = c['day']
        approved = 0
        for emp in employees:
            req = resolved[emp]
            if d in req['DO'] or d in req['MO']:
                if approved < c['maxAbsent']:
                    approved += 1
                else:
                    if d in req['DO']:
                        req['DO'].remove(d)
                    if d in req['MO']:
                        req['MO'].remove(d)
                    rejected.append({'employee': emp, 'day': d})

    return resolved


# ============================================================
# OR-Tools 솔버
# ============================================================

def solve(employees, days, num_days, weekend_or_holiday, pre_requests, constraints, fair_weekend, managers=None):
    """OR-Tools CP-SAT Solver로 스케줄 최적화"""

    num_employees = len(employees)
    do_count = constraints['do_count']
    max_consec = constraints['max_consec']
    min_weekday = constraints['min_weekday']
    min_weekend = constraints['min_weekend']
    min_weekday_off = constraints.get('min_weekday_off', 2)
    max_consec_off = constraints.get('max_consec_off', 4)
    if managers is None:
        managers = []
    manager_indices = [i for i, e in enumerate(employees) if e in managers]

    # M/O 집합
    mo_set = set()
    for e_idx, emp in enumerate(employees):
        req = pre_requests.get(emp, {'DO': [], 'MO': []})
        for d in req['MO']:
            mo_set.add((e_idx, d))

    model = cp_model.CpModel()

    # 결정 변수
    dayoff = {}
    for e_idx in range(num_employees):
        for d in days:
            dayoff[(e_idx, d)] = model.new_bool_var(f'do_{e_idx}_{d}')

    # [Hard] M/O인 날은 D/O 불가
    for (e_idx, d) in mo_set:
        model.add(dayoff[(e_idx, d)] == 0)

    # [Hard] 사전 신청 D/O 고정
    for e_idx, emp in enumerate(employees):
        req = pre_requests.get(emp, {'DO': [], 'MO': []})
        for d in req['DO']:
            model.add(dayoff[(e_idx, d)] == 1)

    # [Hard] 월 D/O 합계
    for e_idx in range(num_employees):
        model.add(sum(dayoff[(e_idx, d)] for d in days) == do_count)

    # [Hard] 최소 근무 인원
    for d in days:
        mo_today = sum(1 for e in range(num_employees) if (e, d) in mo_set)
        do_sum = sum(dayoff[(e, d)] for e in range(num_employees))
        min_w = min_weekend if d in weekend_or_holiday else min_weekday
        max_do = num_employees - mo_today - min_w

        if max_do < 0:
            return None

        model.add(do_sum <= max_do)

    # [Hard] 최대 연속 근무
    for e_idx in range(num_employees):
        for start in range(1, num_days - max_consec + 1):
            end = start + max_consec
            if end > num_days:
                break
            window = range(start, end + 1)
            rest = []
            for d in window:
                if (e_idx, d) in mo_set:
                    rest.append(1)
                else:
                    rest.append(dayoff[(e_idx, d)])
            model.add(sum(rest) >= 1)

    # [Hard] 평일 최소 휴무 인원 (D/O + M/O 합산)
    weekdays = [d for d in days if d not in weekend_or_holiday]
    if min_weekday_off > 0:
        for d in weekdays:
            mo_today = sum(1 for e in range(num_employees) if (e, d) in mo_set)
            do_sum = sum(dayoff[(e, d)] for e in range(num_employees))
            needed_do = min_weekday_off - mo_today
            if needed_do > 0:
                model.add(do_sum >= needed_do)

    # [Hard] 관리자 휴무 겹침 방지 (하루에 최대 1명만 쉴 수 있음)
    if len(manager_indices) >= 2:
        for d in days:
            off_vars = []
            for m_idx in manager_indices:
                if (m_idx, d) in mo_set:
                    off_vars.append(1)  # M/O인 날은 항상 쉼
                else:
                    off_vars.append(dayoff[(m_idx, d)])
            model.add(sum(off_vars) <= 1)

    # [Hard] 최대 연속 휴무 (D/O + M/O 합산)
    if max_consec_off > 0:
        window_size = max_consec_off + 1
        for e_idx in range(num_employees):
            for start in range(1, num_days - max_consec_off + 1):
                end = start + max_consec_off
                if end > num_days:
                    break
                window = range(start, end + 1)
                work_in_window = []
                for d in window:
                    if (e_idx, d) in mo_set:
                        work_in_window.append(0)  # M/O = 쉬는 날
                    else:
                        # dayoff=1이면 쉬는 것, work = 1 - dayoff
                        work_in_window.append(1 - dayoff[(e_idx, d)])
                model.add(sum(work_in_window) >= 1)

    # [형평성] 주말/공휴일 D/O 분배
    wh_days = sorted(weekend_or_holiday)

    if fair_weekend and wh_days:
        for e_idx, emp in enumerate(employees):
            req = pre_requests.get(emp, {'DO': [], 'MO': []})
            pre_wk_do = sum(1 for d in req['DO'] if d in weekend_or_holiday)
            max_wk = max(1, pre_wk_do) if pre_wk_do <= 2 else pre_wk_do
            model.add(sum(dayoff[(e_idx, d)] for d in wh_days) <= max_wk)

        for e_idx in range(num_employees):
            has_mo_wk = any((e_idx, d) in mo_set for d in wh_days)
            if not has_mo_wk:
                model.add(sum(dayoff[(e_idx, d)] for d in wh_days) >= 1)

    # [Soft] 평일 D/O 균등 분산
    if weekdays:
        max_wd = model.new_int_var(0, num_employees, 'max_wd')
        min_wd = model.new_int_var(0, num_employees, 'min_wd')
        for d in weekdays:
            s = sum(dayoff[(e, d)] for e in range(num_employees))
            model.add(s <= max_wd)
            model.add(s >= min_wd)
        model.minimize(max_wd - min_wd)

    # 솔버 실행
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_workers = 4

    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # 결과 추출
    schedule = {}
    for e_idx, emp in enumerate(employees):
        schedule[emp] = {}
        for d in days:
            if (e_idx, d) in mo_set:
                schedule[emp][d] = 'M/O'
            elif solver.value(dayoff[(e_idx, d)]) == 1:
                schedule[emp][d] = 'D/O'
            else:
                schedule[emp][d] = 'W'

    return schedule


# ============================================================
# 검증
# ============================================================

def verify(schedule, employees, days, weekend_or_holiday, day_of_week, constraints, managers=None):
    """스케줄 제약 조건 검증"""
    if managers is None:
        managers = []
    day_name_kr = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    results = []

    # D/O 횟수
    do_ok = True
    for emp in employees:
        cnt = sum(1 for d in days if schedule[emp][d] == 'D/O')
        if cnt != constraints['do_count']:
            do_ok = False
    results.append({
        'name': f"D/O {constraints['do_count']}회/인",
        'pass': do_ok,
    })

    # 최소 근무 인원
    min_ok = True
    for d in days:
        w = sum(1 for e in employees if schedule[e][d] == 'W')
        req = constraints['min_weekend'] if d in weekend_or_holiday else constraints['min_weekday']
        if w < req:
            min_ok = False
    results.append({
        'name': '최소 근무 인원',
        'pass': min_ok,
    })

    # 연속 근무
    max_c = 0
    consec_ok = True
    for emp in employees:
        c = 0
        for d in days:
            if schedule[emp][d] == 'W':
                c += 1
                if c > constraints['max_consec']:
                    consec_ok = False
                max_c = max(max_c, c)
            else:
                c = 0
    results.append({
        'name': f"연속 근무 {constraints['max_consec']}일 이하",
        'pass': consec_ok,
        'detail': f"최대 {max_c}일",
    })

    # 주말 D/O 분배
    wh_do = {}
    for e in employees:
        wh_do[e] = sum(1 for d in days if d in weekend_or_holiday and schedule[e][d] == 'D/O')
    results.append({
        'name': '주말/공휴일 D/O 분배',
        'pass': True,
        'detail': wh_do,
    })

    # 평일 최소 휴무
    weekdays = [d for d in days if d not in weekend_or_holiday]
    min_off = constraints.get('min_weekday_off', 2)
    if weekdays and min_off > 0:
        off_ok = True
        for d in weekdays:
            off_cnt = sum(1 for e in employees if schedule[e][d] != 'W')
            if off_cnt < min_off:
                off_ok = False
        results.append({
            'name': f"평일 최소 {min_off}명 휴무",
            'pass': off_ok,
        })

    # 연속 휴무
    max_consec_off = constraints.get('max_consec_off', 4)
    if max_consec_off > 0:
        consec_off_ok = True
        max_co = 0
        for emp in employees:
            c = 0
            for d in days:
                if schedule[emp][d] != 'W':
                    c += 1
                    if c > max_consec_off:
                        consec_off_ok = False
                    max_co = max(max_co, c)
                else:
                    c = 0
        results.append({
            'name': f"연속 휴무 {max_consec_off}일 이하",
            'pass': consec_off_ok,
            'detail': f"최대 {max_co}일",
        })

    # 관리자 휴무 겹침
    if managers:
        mgr_ok = True
        for d in days:
            off_mgrs = [m for m in managers if schedule[m][d] != 'W']
            if len(off_mgrs) > 1:
                mgr_ok = False
        results.append({
            'name': '관리자 휴무 비겹침',
            'pass': mgr_ok,
        })

    # 평일 분산
    if weekdays:
        wd_counts = [sum(1 for e in employees if schedule[e][d] == 'D/O') for d in weekdays]
        results.append({
            'name': '평일 D/O 분산',
            'pass': True,
            'detail': f"{min(wd_counts)}~{max(wd_counts)}명/일",
        })

    return results


# ============================================================
# 파일 생성
# ============================================================

def save_files(schedule, employees, year, month, days, day_of_week,
               weekend_or_holiday, constraints, file_id):
    """Excel/CSV 파일 생성 및 저장"""
    day_name_kr = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    col_labels = [f"{d}({day_name_kr[day_of_week[d]]})" for d in days]

    df = pd.DataFrame(index=employees, columns=col_labels)
    for emp in employees:
        for i, d in enumerate(days):
            df.loc[emp, col_labels[i]] = schedule[emp][d]

    # 통계 열
    for emp in employees:
        vals = list(schedule[emp].values())
        df.loc[emp, '근무(W)'] = vals.count('W')
        df.loc[emp, '휴무(D/O)'] = vals.count('D/O')
        df.loc[emp, '연차(M/O)'] = vals.count('M/O')

    # 근무 인원 행
    row = []
    for d in days:
        row.append(sum(1 for e in employees if schedule[e][d] == 'W'))
    row += ['', '', '']
    df.loc['[근무인원]'] = row

    # CSV
    csv_name = f"schedule_{year}{month:02d}_{file_id}.csv"
    csv_path = os.path.join(OUTPUT_DIR, csv_name)
    df.to_csv(csv_path, encoding='utf-8-sig')
    csv_id = f"{file_id}_csv"
    file_store[csv_id] = (csv_path, time.time())

    # Excel
    excel_name = f"schedule_{year}{month:02d}_{file_id}.xlsx"
    excel_path = os.path.join(OUTPUT_DIR, excel_name)
    try:
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f'{year}년{month}월')
            _style_excel(writer, f'{year}년{month}월')
        excel_id = f"{file_id}_excel"
        file_store[excel_id] = (excel_path, time.time())
    except Exception:
        excel_id = f"{file_id}_excel"
        file_store[excel_id] = (csv_path, time.time())  # fallback

    return excel_id, csv_id


def _style_excel(writer, sheet_name):
    """Excel 셀 서식 적용"""
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    ws = writer.sheets[sheet_name]

    fill_do = PatternFill(start_color='B4D7FF', end_color='B4D7FF', fill_type='solid')
    fill_mo = PatternFill(start_color='FFD6D6', end_color='FFD6D6', fill_type='solid')
    fill_header = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    font_header = Font(color='FFFFFF', bold=True, size=10)
    font_cell = Font(size=10)
    border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    center = Alignment(horizontal='center', vertical='center')

    for cell in ws[1]:
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = center
        cell.border = border

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
        for cell in row:
            cell.font = font_cell
            cell.alignment = center
            cell.border = border
            if cell.value == 'D/O':
                cell.fill = fill_do
            elif cell.value == 'M/O':
                cell.fill = fill_mo

    ws.column_dimensions['A'].width = 10
    for col_idx in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 8


# ============================================================
# 실행
# ============================================================

if __name__ == '__main__':
    import sys
    is_dev = '--dev' in sys.argv
    print("=" * 50)
    print("  직원 스케줄 웹 생성기")
    print(f"  http://localhost:5000 에서 접속하세요")
    if is_dev:
        print("  [개발 모드]")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=is_dev)
