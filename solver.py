"""
OR-Tools CP-SAT Solver (강화 버전)
===================================
개선사항:
- 직원별 D/O 횟수 커스텀
- 전월 연속근무 연계 (cross-month continuity)
- 상세한 실패 분석 힌트
- 솔버 파이프라인 모듈화
"""

from ortools.sat.python import cp_model
import calendar
from datetime import date


def solve_schedule(employees, year, month, holidays, constraints, pre_requests,
                   fair_weekend=True, managers=None, employee_do_counts=None,
                   prev_month_tail=None):
    """
    메인 솔버 함수.

    Args:
        employees: list[str] - 직원 이름 목록
        year, month: int - 대상 연월
        holidays: list[int] - 공휴일 날짜(일)
        constraints: dict - 제약 조건
        pre_requests: dict - {직원명: {'DO': [일], 'MO': [일]}}
        fair_weekend: bool - 주말 형평성 적용
        managers: list[str] - 관리자 목록
        employee_do_counts: dict - {직원명: int} 직원별 D/O 횟수 (None이면 기본값)
        prev_month_tail: dict - {직원명: int} 전월 말 연속근무일수

    Returns:
        dict with 'success', 'schedule', 'verification', 'conflicts', 'hints'
    """
    if managers is None:
        managers = []
    if employee_do_counts is None:
        employee_do_counts = {}
    if prev_month_tail is None:
        prev_month_tail = {}

    num_employees = len(employees)
    num_days = calendar.monthrange(year, month)[1]
    days = list(range(1, num_days + 1))
    day_of_week = {d: date(year, month, d).weekday() for d in days}

    weekend_or_holiday = set()
    for d in days:
        if day_of_week[d] >= 5 or d in holidays:
            weekend_or_holiday.add(d)

    # 제약 조건 정규화
    default_do = int(constraints.get('doCount', 8))
    max_consec = int(constraints.get('maxConsecutive', 5))
    min_weekday = int(constraints.get('minWeekday', 4))
    min_weekend = int(constraints.get('minWeekend', 6))
    min_weekday_off = int(constraints.get('minWeekdayOff', 2))
    max_consec_off = int(constraints.get('maxConsecutiveOff', 4))
    manager_indices = [i for i, e in enumerate(employees) if e in managers]

    # 직원별 D/O 횟수
    do_counts = {}
    for e in employees:
        do_counts[e] = employee_do_counts.get(e, default_do)

    # pre_requests 정규화
    normalized_req = {}
    for emp in employees:
        req = pre_requests.get(emp, {'DO': [], 'MO': []})
        normalized_req[emp] = {
            'DO': [int(d) for d in req.get('DO', [])],
            'MO': [int(d) for d in req.get('MO', [])],
        }

    # M/O 집합
    mo_set = set()
    for e_idx, emp in enumerate(employees):
        for d in normalized_req[emp]['MO']:
            mo_set.add((e_idx, d))

    # 1) 충돌 검증
    conflicts = _detect_conflicts(
        employees, days, weekend_or_holiday, normalized_req,
        min_weekday, min_weekend, year, month
    )

    # 2) 충돌 해결
    resolved_req = _resolve_conflicts(employees, conflicts, normalized_req)

    # M/O 집합 재계산 (충돌 해결 후)
    mo_set = set()
    for e_idx, emp in enumerate(employees):
        for d in resolved_req[emp]['MO']:
            mo_set.add((e_idx, d))

    # 3) 솔버 실행
    schedule = _solve(
        employees, days, num_days, weekend_or_holiday, resolved_req,
        do_counts, max_consec, min_weekday, min_weekend,
        min_weekday_off, max_consec_off, fair_weekend,
        manager_indices, mo_set, prev_month_tail
    )

    if schedule is None:
        hints = _analyze_failure(
            employees, num_days, do_counts, min_weekday, min_weekend,
            managers, normalized_req, weekend_or_holiday
        )
        return {
            'success': False,
            'error': f'스케줄을 찾을 수 없습니다. {" ".join(hints)}',
            'conflicts': conflicts,
            'hints': hints,
        }

    # 4) 검증
    verification = _verify(
        schedule, employees, days, weekend_or_holiday, day_of_week,
        do_counts, max_consec, min_weekday, min_weekend,
        min_weekday_off, max_consec_off, managers
    )

    # 5) 캘린더 정보
    day_name_kr = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    cal_info = {
        'numDays': num_days,
        'dayOfWeek': {str(d): dow for d, dow in day_of_week.items()},
        'dayNames': day_name_kr,
        'weekendOrHoliday': sorted(weekend_or_holiday),
    }

    # schedule을 JSON 호환 형태로
    schedule_json = {}
    for emp in employees:
        schedule_json[emp] = {str(d): v for d, v in schedule[emp].items()}

    return {
        'success': True,
        'schedule': schedule_json,
        'calendarInfo': cal_info,
        'conflicts': conflicts,
        'verification': verification,
    }


def _detect_conflicts(employees, days, weekend_or_holiday, pre_requests,
                       min_weekday, min_weekend, year, month):
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
            max_absent = num_employees - min_weekend
        else:
            max_absent = num_employees - min_weekday

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


def _resolve_conflicts(employees, conflicts, pre_requests):
    resolved = {}
    for emp in employees:
        req = pre_requests.get(emp, {'DO': [], 'MO': []})
        resolved[emp] = {'DO': list(req['DO']), 'MO': list(req['MO'])}

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

    return resolved


def _solve(employees, days, num_days, weekend_or_holiday, pre_requests,
           do_counts, max_consec, min_weekday, min_weekend,
           min_weekday_off, max_consec_off, fair_weekend,
           manager_indices, mo_set, prev_month_tail):

    num_employees = len(employees)
    model = cp_model.CpModel()

    # 결정 변수: dayoff[(e_idx, d)] = 1이면 D/O
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

    # [Hard] 직원별 월 D/O 합계
    for e_idx, emp in enumerate(employees):
        emp_do = do_counts.get(emp, 8)
        model.add(sum(dayoff[(e_idx, d)] for d in days) == emp_do)

    # [Hard] 최소 근무 인원
    for d in days:
        mo_today = sum(1 for e in range(num_employees) if (e, d) in mo_set)
        do_sum = sum(dayoff[(e, d)] for e in range(num_employees))
        min_w = min_weekend if d in weekend_or_holiday else min_weekday
        max_do = num_employees - mo_today - min_w
        if max_do < 0:
            return None
        model.add(do_sum <= max_do)

    # [Hard] 최대 연속 근무 (전월 연계 포함)
    for e_idx, emp in enumerate(employees):
        tail = prev_month_tail.get(emp, 0)

        # 월초: 전월 연속근무 + 이번달 초반
        if tail > 0:
            remaining = max_consec - tail
            if remaining <= 0:
                # 전월만으로 이미 최대치 → 1일은 반드시 휴무
                if (e_idx, 1) in mo_set:
                    pass  # M/O라서 이미 쉼
                else:
                    model.add(dayoff[(e_idx, 1)] == 1)
            else:
                window_end = min(remaining + 1, num_days)
                window = range(1, window_end + 1)
                rest = []
                for d in window:
                    if (e_idx, d) in mo_set:
                        rest.append(1)
                    else:
                        rest.append(dayoff[(e_idx, d)])
                model.add(sum(rest) >= 1)

        # 일반 연속근무 제약
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

    # [Hard] 평일 최소 휴무 인원
    weekdays = [d for d in days if d not in weekend_or_holiday]
    if min_weekday_off > 0:
        for d in weekdays:
            mo_today = sum(1 for e in range(num_employees) if (e, d) in mo_set)
            do_sum = sum(dayoff[(e, d)] for e in range(num_employees))
            needed_do = min_weekday_off - mo_today
            if needed_do > 0:
                model.add(do_sum >= needed_do)

    # [Hard] 관리자 휴무 겹침 방지
    if len(manager_indices) >= 2:
        for d in days:
            off_vars = []
            for m_idx in manager_indices:
                if (m_idx, d) in mo_set:
                    off_vars.append(1)
                else:
                    off_vars.append(dayoff[(m_idx, d)])
            model.add(sum(off_vars) <= 1)

    # [Hard] 최대 연속 휴무
    if max_consec_off > 0:
        for e_idx in range(num_employees):
            for start in range(1, num_days - max_consec_off + 1):
                end = start + max_consec_off
                if end > num_days:
                    break
                window = range(start, end + 1)
                work_in_window = []
                for d in window:
                    if (e_idx, d) in mo_set:
                        work_in_window.append(0)
                    else:
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


def _verify(schedule, employees, days, weekend_or_holiday, day_of_week,
            do_counts, max_consec, min_weekday, min_weekend,
            min_weekday_off, max_consec_off, managers):
    day_name_kr = {0: '월', 1: '화', 2: '수', 3: '목', 4: '금', 5: '토', 6: '일'}
    results = []

    # D/O 횟수 (직원별)
    do_ok = True
    do_details = {}
    for emp in employees:
        cnt = sum(1 for d in days if schedule[emp][d] == 'D/O')
        expected = do_counts.get(emp, 8)
        do_details[emp] = f'{cnt}/{expected}'
        if cnt != expected:
            do_ok = False
    results.append({
        'name': 'D/O 횟수 (직원별)',
        'pass': do_ok,
        'detail': do_details,
    })

    # 최소 근무 인원
    min_ok = True
    min_detail = None
    for d in days:
        w = sum(1 for e in employees if schedule[e][d] == 'W')
        req = min_weekend if d in weekend_or_holiday else min_weekday
        if w < req:
            min_ok = False
            min_detail = f'{d}일: {w}명 (필요 {req}명)'
    results.append({
        'name': '최소 근무 인원',
        'pass': min_ok,
        'detail': min_detail,
    })

    # 연속 근무
    max_c = 0
    consec_ok = True
    for emp in employees:
        c = 0
        for d in days:
            if schedule[emp][d] == 'W':
                c += 1
                if c > max_consec:
                    consec_ok = False
                max_c = max(max_c, c)
            else:
                c = 0
    results.append({
        'name': f'연속 근무 {max_consec}일 이하',
        'pass': consec_ok,
        'detail': f'최대 {max_c}일',
    })

    # 주말 D/O 분배
    wh_do = {}
    for e in employees:
        wh_do[e] = sum(1 for d in days if d in weekend_or_holiday and schedule[e][d] == 'D/O')
    vals = list(wh_do.values())
    results.append({
        'name': '주말/공휴일 D/O 분배',
        'pass': True,
        'detail': f'{min(vals) if vals else 0}~{max(vals) if vals else 0}회/인',
    })

    # 평일 최소 휴무
    weekdays = [d for d in days if d not in weekend_or_holiday]
    if weekdays and min_weekday_off > 0:
        off_ok = True
        for d in weekdays:
            off_cnt = sum(1 for e in employees if schedule[e][d] != 'W')
            if off_cnt < min_weekday_off:
                off_ok = False
        results.append({
            'name': f'평일 최소 {min_weekday_off}명 휴무',
            'pass': off_ok,
        })

    # 연속 휴무
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
            'name': f'연속 휴무 {max_consec_off}일 이하',
            'pass': consec_off_ok,
            'detail': f'최대 {max_co}일',
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
            'detail': f'{min(wd_counts)}~{max(wd_counts)}명/일',
        })

    return results


def _analyze_failure(employees, num_days, do_counts, min_weekday, min_weekend,
                     managers, pre_requests, weekend_or_holiday):
    """실패 원인 분석 (상세 힌트)"""
    hints = []
    num_emp = len(employees)

    if min_weekend >= num_emp:
        hints.append(f'주말 최소 근무({min_weekend}명)가 전체 인원({num_emp}명) 이상입니다.')
    if min_weekday >= num_emp:
        hints.append(f'평일 최소 근무({min_weekday}명)가 전체 인원({num_emp}명) 이상입니다.')

    # D/O 합계 vs 가용 슬롯
    total_do = sum(do_counts.get(e, 8) for e in employees)
    weekdays_cnt = num_days - len(weekend_or_holiday)
    max_daily_do_wd = num_emp - min_weekday
    max_daily_do_wk = num_emp - min_weekend
    total_slots = weekdays_cnt * max_daily_do_wd + len(weekend_or_holiday) * max_daily_do_wk

    total_mo = sum(len(pre_requests.get(e, {}).get('MO', [])) for e in employees)
    if total_do + total_mo > total_slots:
        hints.append(f'총 휴무 요청({total_do + total_mo}일)이 가용 슬롯({total_slots}일)을 초과합니다.')

    if len(managers) >= 2:
        mgr_total_do = sum(do_counts.get(m, 8) for m in managers)
        if mgr_total_do > num_days:
            hints.append(f'관리자({len(managers)}명)의 D/O 합계({mgr_total_do}일)가 총 일수({num_days}일)를 초과합니다.')

    # 직원별 D/O가 너무 많은 경우
    for emp in employees:
        emp_do = do_counts.get(emp, 8)
        emp_mo = len(pre_requests.get(emp, {}).get('MO', []))
        if emp_do + emp_mo > num_days:
            hints.append(f'{emp}의 D/O({emp_do}) + M/O({emp_mo})가 총 일수({num_days})를 초과합니다.')

    if not hints:
        hints.append('제약 조건 간의 충돌이 있습니다. D/O 횟수, 최소 근무 인원, 또는 사전 신청을 조정해보세요.')

    return hints


def get_prev_month_tail(schedule_data, employees):
    """전월 스케줄에서 월말 연속근무일수 계산"""
    tail = {}
    if not schedule_data:
        return tail

    for emp in employees:
        emp_data = schedule_data.get(emp, {})
        if not emp_data:
            tail[emp] = 0
            continue

        # 날짜 키를 정수로 변환하고 정렬
        days_sorted = sorted([int(d) for d in emp_data.keys()])
        consec = 0
        for d in reversed(days_sorted):
            if emp_data.get(str(d)) == 'W':
                consec += 1
            else:
                break
        tail[emp] = consec

    return tail
