"""
calendar_html.py - 캘린더 HTML 생성 믹스인
IndieBiz OS Core

CalendarManager에서 HTML 달력 생성 관련 메서드를 분리한 믹스인 클래스입니다.
generate_calendar_html, _build_html, open_in_browser 등의 메서드를 포함합니다.
"""

import json
import subprocess
import platform
import calendar
from datetime import datetime, date
from typing import Dict, List

from runtime_utils import get_base_path

BASE_PATH = get_base_path()
OUTPUTS_PATH = BASE_PATH / "outputs"


class CalendarHtmlMixin:
    """캘린더 HTML 생성 관련 메서드 믹스인"""

    def get_events_for_month(self, year: int, month: int) -> Dict[int, List[dict]]:
        """특정 월의 이벤트를 날짜별로 정리 (반복 이벤트 확장 포함)"""
        events = self.config.get("events", [])
        _, days_in_month = calendar.monthrange(year, month)
        result: Dict[int, List[dict]] = {}

        for evt in events:
            evt_date_str = evt.get("date", "")
            if not evt_date_str:
                continue

            try:
                evt_date = datetime.strptime(evt_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            repeat = evt.get("repeat", "none")

            if repeat == "none":
                if evt_date.year == year and evt_date.month == month:
                    result.setdefault(evt_date.day, []).append(evt)

            elif repeat == "yearly":
                if evt_date.month == month and evt_date.day <= days_in_month:
                    result.setdefault(evt_date.day, []).append(evt)

            elif repeat == "monthly":
                if evt_date.day <= days_in_month:
                    result.setdefault(evt_date.day, []).append(evt)

            elif repeat == "weekly":
                target_weekday = evt_date.weekday()
                for d in range(1, days_in_month + 1):
                    if date(year, month, d).weekday() == target_weekday:
                        result.setdefault(d, []).append(evt)

            elif repeat == "daily":
                for d in range(1, days_in_month + 1):
                    result.setdefault(d, []).append(evt)

        return result

    def generate_calendar_html(self, year: int = None, month: int = None) -> str:
        """월간 달력 HTML 생성"""
        today = date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        all_events = self.config.get("events", [])
        month_events = self.get_events_for_month(year, month)

        cal = calendar.Calendar(firstweekday=0)
        month_days = cal.monthdayscalendar(year, month)

        month_names = [
            "", "1월", "2월", "3월", "4월", "5월", "6월",
            "7월", "8월", "9월", "10월", "11월", "12월"
        ]
        weekday_names = ["월", "화", "수", "목", "금", "토", "일"]

        html = self._build_html(
            year, month, today, all_events, month_events,
            month_days, month_names, weekday_names
        )

        OUTPUTS_PATH.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUTS_PATH / "calendar.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return str(output_path)

    def _build_html(self, year, month, today, all_events, month_events,
                    month_days, month_names, weekday_names) -> str:
        """HTML 달력 생성"""
        from calendar_manager import EVENT_TYPE_COLORS, EVENT_TYPE_EMOJI, EVENT_TYPE_LABELS

        events_json = json.dumps(all_events, ensure_ascii=False)

        cells_html = ""
        for week in month_days:
            cells_html += "<tr>"
            for i, day_num in enumerate(week):
                if day_num == 0:
                    cells_html += '<td class="empty"></td>'
                else:
                    is_today = (year == today.year and month == today.month and day_num == today.day)
                    day_class = "today" if is_today else ""
                    if i >= 5:
                        day_class += " weekend"
                    if i == 6:
                        day_class += " sunday"

                    day_events = month_events.get(day_num, [])
                    events_html = ""
                    for evt in day_events[:3]:
                        evt_type = evt.get("type", "other")
                        emoji = EVENT_TYPE_EMOJI.get(evt_type, "")
                        color = EVENT_TYPE_COLORS.get(evt_type, "#607d8b")
                        evt_time = evt.get("time", "")
                        time_str = f"{evt_time} " if evt_time else ""
                        title = evt.get("title", "")
                        events_html += f'<div class="event" style="border-left: 3px solid {color};" title="{time_str}{title}">{emoji} {title}</div>'
                    if len(day_events) > 3:
                        events_html += f'<div class="event-more">+{len(day_events) - 3}개 더</div>'

                    cells_html += f'<td class="{day_class}"><div class="day-number">{day_num}</div>{events_html}</td>'
            cells_html += "</tr>"

        all_events_sorted = sorted(all_events, key=lambda e: e.get("date", "") or "9999")
        sidebar_html = ""
        for evt in all_events_sorted:
            evt_type = evt.get("type", "other")
            emoji = EVENT_TYPE_EMOJI.get(evt_type, "")
            color = EVENT_TYPE_COLORS.get(evt_type, "#607d8b")
            label = EVENT_TYPE_LABELS.get(evt_type, "기타")
            repeat = evt.get("repeat", "none")
            repeat_label = {"none": "", "yearly": "매년", "monthly": "매월", "weekly": "매주", "daily": "매일", "interval": "간격"}.get(repeat, "")
            evt_time = evt.get("time", "")
            action = evt.get("action")
            action_label = ""
            if action:
                action_label = f'<span class="event-action">{action}</span>'

            sidebar_html += f'''
            <div class="event-card">
                <div class="event-card-header">
                    <span class="event-emoji">{emoji}</span>
                    <span class="event-title">{evt.get("title", "")}</span>
                </div>
                <div class="event-card-meta">
                    <span class="event-date">{evt.get("date", "") or "매일"}</span>
                    {f'<span class="event-time">{evt_time}</span>' if evt_time else ''}
                    <span class="event-badge" style="background: {color}22; color: {color};">{label}</span>
                    {f'<span class="event-repeat">{repeat_label}</span>' if repeat_label else ''}
                    {action_label}
                </div>
                {f'<div class="event-desc">{evt.get("description", "")}</div>' if evt.get("description") else ''}
            </div>'''

        return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IndieBiz 캘린더 - {year}년 {month_names[month]}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
            background: #f5f0eb;
            color: #333;
        }}
        .container {{
            display: flex;
            height: 100vh;
            gap: 0;
        }}
        .calendar-main {{
            flex: 1;
            display: flex;
            flex-direction: column;
            padding: 24px;
            min-width: 0;
        }}
        .calendar-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }}
        .calendar-title {{
            font-size: 24px;
            font-weight: 700;
            color: #4a3f35;
        }}
        .nav-buttons {{
            display: flex;
            gap: 8px;
        }}
        .nav-btn {{
            padding: 8px 16px;
            border: 1px solid #d4c9bc;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            color: #6b5b4f;
            transition: all 0.2s;
        }}
        .nav-btn:hover {{
            background: #ede7df;
            border-color: #b8a99c;
        }}
        .nav-btn.today-btn {{
            background: #6b5b4f;
            color: white;
            border-color: #6b5b4f;
        }}
        .nav-btn.today-btn:hover {{
            background: #5a4a3f;
        }}
        .calendar-table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            flex: 1;
        }}
        .calendar-table th {{
            padding: 10px 4px;
            text-align: center;
            font-size: 13px;
            font-weight: 600;
            color: #8b7d72;
            border-bottom: 2px solid #d4c9bc;
        }}
        .calendar-table th:nth-child(6) {{ color: #2196f3; }}
        .calendar-table th:nth-child(7) {{ color: #e91e63; }}
        .calendar-table td {{
            border: 1px solid #e8e0d8;
            vertical-align: top;
            padding: 4px 6px;
            height: 100px;
            background: white;
            transition: background 0.15s;
        }}
        .calendar-table td:hover {{ background: #faf8f5; }}
        .calendar-table td.empty {{ background: #f9f5f0; }}
        .calendar-table td.today {{ background: #fff8e1; border-color: #ffb74d; }}
        .calendar-table td.weekend {{ background: #fafafa; }}
        .day-number {{
            font-size: 14px;
            font-weight: 600;
            color: #4a3f35;
            margin-bottom: 4px;
        }}
        .today .day-number {{
            background: #ff9800;
            color: white;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .sunday .day-number {{ color: #e91e63; }}
        .event {{
            font-size: 11px;
            padding: 2px 4px;
            margin-bottom: 2px;
            border-radius: 3px;
            background: #f8f5f1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: default;
        }}
        .event-more {{ font-size: 10px; color: #999; padding: 1px 4px; }}
        .sidebar {{
            width: 320px;
            background: white;
            border-left: 1px solid #e0d8d0;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        .sidebar-header {{
            padding: 20px 20px 16px;
            border-bottom: 1px solid #eee;
        }}
        .sidebar-header h3 {{ font-size: 16px; font-weight: 700; color: #4a3f35; }}
        .sidebar-header p {{ font-size: 12px; color: #999; margin-top: 4px; }}
        .sidebar-body {{ flex: 1; overflow-y: auto; padding: 12px; }}
        .event-card {{
            padding: 12px;
            border: 1px solid #eee;
            border-radius: 8px;
            margin-bottom: 8px;
            transition: box-shadow 0.2s;
        }}
        .event-card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .event-card-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }}
        .event-emoji {{ font-size: 16px; }}
        .event-title {{ font-size: 14px; font-weight: 600; color: #333; }}
        .event-card-meta {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
        .event-date {{ font-size: 12px; color: #888; }}
        .event-time {{ font-size: 12px; color: #666; font-weight: 500; }}
        .event-badge {{ font-size: 10px; padding: 1px 6px; border-radius: 10px; font-weight: 500; }}
        .event-repeat {{ font-size: 10px; color: #999; background: #f5f5f5; padding: 1px 6px; border-radius: 10px; }}
        .event-action {{ font-size: 10px; color: #4caf50; background: #e8f5e9; padding: 1px 6px; border-radius: 10px; }}
        .event-desc {{ font-size: 12px; color: #777; margin-top: 6px; line-height: 1.4; }}
        .no-events {{ text-align: center; color: #999; padding: 40px 20px; font-size: 14px; }}
        @media (max-width: 900px) {{
            .container {{ flex-direction: column; height: auto; }}
            .sidebar {{ width: 100%; border-left: none; border-top: 1px solid #e0d8d0; }}
            .calendar-table td {{ height: 80px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="calendar-main">
            <div class="calendar-header">
                <div class="calendar-title" id="calendarTitle">{year}년 {month_names[month]}</div>
                <div class="nav-buttons">
                    <button class="nav-btn" onclick="changeMonth(-1)">&larr; 이전</button>
                    <button class="nav-btn today-btn" onclick="goToday()">오늘</button>
                    <button class="nav-btn" onclick="changeMonth(1)">다음 &rarr;</button>
                </div>
            </div>
            <table class="calendar-table">
                <thead>
                    <tr>
                        {''.join(f'<th>{d}</th>' for d in weekday_names)}
                    </tr>
                </thead>
                <tbody id="calendarBody">
                    {cells_html}
                </tbody>
            </table>
        </div>
        <div class="sidebar">
            <div class="sidebar-header">
                <h3>등록된 일정</h3>
                <p>{len(all_events)}개의 일정</p>
            </div>
            <div class="sidebar-body" id="sidebarBody">
                {sidebar_html if sidebar_html else '<div class="no-events">등록된 일정이 없습니다.<br><br>시스템 AI에게 기념일이나 약속을 알려주세요.</div>'}
            </div>
        </div>
    </div>

    <script>
        const allEvents = {events_json};
        let currentYear = {year};
        let currentMonth = {month};
        const todayDate = new Date();

        const monthNames = ["", "1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];
        const typeEmojis = {json.dumps(EVENT_TYPE_EMOJI, ensure_ascii=False)};
        const typeColors = {json.dumps(EVENT_TYPE_COLORS, ensure_ascii=False)};

        function changeMonth(delta) {{
            currentMonth += delta;
            if (currentMonth > 12) {{ currentMonth = 1; currentYear++; }}
            if (currentMonth < 1) {{ currentMonth = 12; currentYear--; }}
            renderCalendar();
        }}

        function goToday() {{
            currentYear = todayDate.getFullYear();
            currentMonth = todayDate.getMonth() + 1;
            renderCalendar();
        }}

        function getDaysInMonth(y, m) {{ return new Date(y, m, 0).getDate(); }}

        function getFirstDayOfMonth(y, m) {{
            let d = new Date(y, m - 1, 1).getDay();
            return d === 0 ? 6 : d - 1;
        }}

        function getEventsForDay(y, m, d) {{
            const result = [];
            const targetDate = new Date(y, m - 1, d);
            const targetWeekday = targetDate.getDay() === 0 ? 6 : targetDate.getDay() - 1;

            allEvents.forEach(evt => {{
                if (!evt.date) {{
                    if (evt.repeat === 'daily') result.push(evt);
                    return;
                }}
                const parts = evt.date.split('-');
                const ey = parseInt(parts[0]);
                const em = parseInt(parts[1]);
                const ed = parseInt(parts[2]);
                const repeat = evt.repeat || 'none';

                if (repeat === 'none') {{
                    if (ey === y && em === m && ed === d) result.push(evt);
                }} else if (repeat === 'yearly') {{
                    if (em === m && ed === d) result.push(evt);
                }} else if (repeat === 'monthly') {{
                    if (ed === d) result.push(evt);
                }} else if (repeat === 'weekly') {{
                    const evtDate = new Date(ey, em - 1, ed);
                    const evtWeekday = evtDate.getDay() === 0 ? 6 : evtDate.getDay() - 1;
                    if (evtWeekday === targetWeekday) result.push(evt);
                }} else if (repeat === 'daily') {{
                    result.push(evt);
                }}
            }});
            return result;
        }}

        function renderCalendar() {{
            document.getElementById('calendarTitle').textContent = currentYear + '년 ' + monthNames[currentMonth];
            const daysInMonth = getDaysInMonth(currentYear, currentMonth);
            const firstDay = getFirstDayOfMonth(currentYear, currentMonth);

            let html = '';
            let dayCount = 1;
            const totalCells = Math.ceil((firstDay + daysInMonth) / 7) * 7;

            for (let i = 0; i < totalCells; i++) {{
                if (i % 7 === 0) html += '<tr>';
                if (i < firstDay || dayCount > daysInMonth) {{
                    html += '<td class="empty"></td>';
                }} else {{
                    const d = dayCount;
                    const isToday = (currentYear === todayDate.getFullYear() && currentMonth === todayDate.getMonth() + 1 && d === todayDate.getDate());
                    const weekdayIdx = i % 7;
                    let cls = '';
                    if (isToday) cls += ' today';
                    if (weekdayIdx >= 5) cls += ' weekend';
                    if (weekdayIdx === 6) cls += ' sunday';

                    const dayEvents = getEventsForDay(currentYear, currentMonth, d);
                    let evtHtml = '';
                    dayEvents.slice(0, 3).forEach(evt => {{
                        const t = evt.type || 'other';
                        const emoji = typeEmojis[t] || '';
                        const color = typeColors[t] || '#607d8b';
                        const timeStr = evt.time ? evt.time + ' ' : '';
                        evtHtml += '<div class="event" style="border-left: 3px solid ' + color + ';" title="' + timeStr + evt.title + '">' + emoji + ' ' + evt.title + '</div>';
                    }});
                    if (dayEvents.length > 3) {{
                        evtHtml += '<div class="event-more">+' + (dayEvents.length - 3) + '개 더</div>';
                    }}
                    html += '<td class="' + cls + '"><div class="day-number">' + d + '</div>' + evtHtml + '</td>';
                    dayCount++;
                }}
                if (i % 7 === 6) html += '</tr>';
            }}
            document.getElementById('calendarBody').innerHTML = html;
        }}
    </script>
</body>
</html>'''

    def open_in_browser(self, year: int = None, month: int = None) -> str:
        """캘린더 HTML 생성 후 브라우저에서 열기"""
        file_path = self.generate_calendar_html(year, month)

        system = platform.system()
        try:
            if system == 'Darwin':
                subprocess.run(['open', file_path], check=True)
            elif system == 'Windows':
                import os
                os.startfile(file_path)
            else:
                subprocess.run(['xdg-open', file_path], check=True)
        except Exception as e:
            print(f"[CalendarManager] 브라우저 열기 실패: {e}")

        return file_path
