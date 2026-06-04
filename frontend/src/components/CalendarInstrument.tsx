/**
 * CalendarInstrument — 일정 캘린더 "계기(instrument)" (앱 모드)
 *
 * 월간 그리드 + 일자별 일정 + 정기 일정 목록. 읽기 중심(LLM 없음, 0 토큰).
 * 데이터: GET /scheduler/calendar/events?year&month → { events, count }.
 *
 * 이벤트 스키마(backend/calendar_manager.add_event): id,title,date("YYYY-MM-DD"),
 *   type,repeat(none|daily|weekly|monthly|yearly|interval),description,time?,enabled,weekdays?,month?,day?
 * 날짜가 명확한 것(none/monthly/yearly)은 그리드에, 주기성(daily/weekly/interval)은 정기 목록에 둔다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

const API = 'http://127.0.0.1:8765';

interface CalEvent {
  id?: string; title?: string; date?: string; type?: string;
  repeat?: string; description?: string; time?: string; enabled?: boolean;
  month?: number; day?: number;
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const REPEAT_LABEL: Record<string, string> = {
  daily: '매일', weekly: '매주', monthly: '매월', yearly: '매년', interval: '주기',
};
// 타입별 색 (점/배지)
const TYPE_COLOR: Record<string, string> = {
  birthday: 'bg-pink-400', anniversary: 'bg-rose-400', holiday: 'bg-red-400',
  meeting: 'bg-blue-400', task: 'bg-amber-400', report: 'bg-violet-400',
};
const colorOf = (e: CalEvent) => TYPE_COLOR[e.type || ''] || 'bg-stone-400';

const pad = (n: number) => String(n).padStart(2, '0');
// 입력 폼 선택지
const REPEAT_OPTS: [string, string][] = [['none', '한 번'], ['weekly', '매주'], ['monthly', '매월'], ['yearly', '매년'], ['daily', '매일']];
const TYPE_OPTS: [string, string][] = [['other', '기타'], ['meeting', '회의/약속'], ['task', '할 일'], ['birthday', '생일'], ['anniversary', '기념일'], ['holiday', '휴일']];

interface AddForm { title: string; date: string; time: string; repeat: string; type: string; description: string }
const EMPTY_FORM: AddForm = { title: '', date: '', time: '', repeat: 'none', type: 'other', description: '' };

export function CalendarInstrument() {
  const today = useMemo(() => new Date(), []);
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1); // 1-12
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selDay, setSelDay] = useState<number | null>(today.getDate());
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState<AddForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (y: number, m: number) => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/scheduler/calendar/events?year=${y}&month=${m}`);
      const d = await res.json();
      setEvents(Array.isArray(d.events) ? d.events : []);
    } catch {
      setError('일정을 불러올 수 없습니다.');
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(year, month); }, [year, month, load]);

  const go = (delta: number) => {
    let m = month + delta, y = year;
    if (m < 1) { m = 12; y -= 1; } else if (m > 12) { m = 1; y += 1; }
    setYear(y); setMonth(m); setSelDay(null);
  };
  const goToday = () => {
    setYear(today.getFullYear()); setMonth(today.getMonth() + 1); setSelDay(today.getDate());
  };

  // ── 일정 추가/삭제: [self:manage_events] IBL 경유 (백엔드 변경 없음) ──
  const runManage = useCallback(async (code: string): Promise<boolean> => {
    try {
      const res = await fetch(`${API}/ibl/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, project_id: '앱모드' }),
      });
      const d = await res.json();
      let r = (d && typeof d === 'object' && 'result' in d) ? d.result : d;
      if (typeof r === 'string') { try { r = JSON.parse(r); } catch { /* keep */ } }
      return !(r && r.success === false);
    } catch {
      return false;
    }
  }, []);

  const openAdd = () => {
    const d = selDay ? `${year}-${pad(month)}-${pad(selDay)}` : `${year}-${pad(month)}-${pad(today.getDate())}`;
    setForm({ ...EMPTY_FORM, date: d });
    setShowAdd(true);
  };

  const submitAdd = async () => {
    const esc = (s: string) => (s || '').replace(/"/g, "'").replace(/[\r\n]+/g, ' ').trim();
    if (!form.title.trim() || !form.date) return;
    setSaving(true);
    const parts = [
      'action: "add"',
      `title: "${esc(form.title)}"`,
      `date: "${form.date}"`,
      `repeat: "${form.repeat || 'none'}"`,
      `type: "${form.type || 'other'}"`,
    ];
    if (form.time) parts.push(`time: "${form.time}"`);
    if (form.description.trim()) parts.push(`description: "${esc(form.description)}"`);
    const ok = await runManage(`[self:manage_events]{${parts.join(', ')}}`);
    setSaving(false);
    if (ok) {
      setShowAdd(false);
      const [, mm, dd] = form.date.split('-').map(Number);
      if (mm === month) setSelDay(dd);
      load(year, month);
    } else {
      setError('일정 추가에 실패했습니다.');
    }
  };

  const removeEvent = async (id?: string) => {
    if (!id) return;
    const ok = await runManage(`[self:manage_events]{action: "delete", event_id: "${id}"}`);
    if (ok) load(year, month);
  };

  // 날짜 명확 이벤트(none/monthly/yearly)를 일자 → 이벤트[] 로 매핑
  const eventsByDay = useMemo(() => {
    const map: Record<number, CalEvent[]> = {};
    const daysInMonth = new Date(year, month, 0).getDate();
    for (const e of events) {
      const rep = e.repeat || 'none';
      const parsed = e.date ? e.date.split('-').map(Number) : null; // [y,m,d]
      let day: number | null = null;
      if (rep === 'none' && parsed && parsed[0] === year && parsed[1] === month) {
        day = parsed[2];
      } else if (rep === 'monthly' && parsed) {
        day = parsed[2];
      } else if (rep === 'yearly') {
        const ym = e.month ?? (parsed ? parsed[1] : null);
        const yd = e.day ?? (parsed ? parsed[2] : null);
        if (ym === month && yd) day = yd;
      }
      if (day && day >= 1 && day <= daysInMonth) {
        (map[day] ||= []).push(e);
      }
    }
    return map;
  }, [events, year, month]);

  // 주기성 일정(매일/매주/주기) — 그리드에 안 넣고 따로 나열
  const recurring = useMemo(
    () => events.filter((e) => ['daily', 'weekly', 'interval'].includes(e.repeat || '')),
    [events]
  );

  // 그리드 셀 구성 (앞 공백 + 1..말일)
  const cells = useMemo(() => {
    const firstWd = new Date(year, month - 1, 1).getDay(); // 0=일
    const daysInMonth = new Date(year, month, 0).getDate();
    const arr: (number | null)[] = Array(firstWd).fill(null);
    for (let d = 1; d <= daysInMonth; d++) arr.push(d);
    while (arr.length % 7 !== 0) arr.push(null);
    return arr;
  }, [year, month]);

  const isToday = (d: number) =>
    today.getFullYear() === year && today.getMonth() + 1 === month && today.getDate() === d;

  const selEvents = selDay ? (eventsByDay[selDay] || []) : [];

  return (
    <div className="h-full w-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* 헤더: 월 네비게이션 */}
      <div className="shrink-0 flex items-center justify-between px-5 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <button onClick={() => go(-1)} className="w-8 h-8 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-stone-500">‹</button>
          <div className="text-lg font-semibold tabular-nums">{year}년 {month}월</div>
          <button onClick={() => go(1)} className="w-8 h-8 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-stone-500">›</button>
        </div>
        <div className="flex items-center gap-2 text-xs text-stone-400">
          {loading ? '불러오는 중…' : `이번 달 일정 ${events.length}건`}
          <button onClick={goToday} className="px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50">오늘</button>
          <button onClick={openAdd} className="px-2.5 py-1 rounded-lg bg-stone-800 text-white hover:bg-stone-700">+ 추가</button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto px-5 pb-6">
        <div className="max-w-2xl mx-auto">
          {error && <div className="py-6 text-center text-rose-500 text-sm">{error}</div>}

          {/* 요일 헤더 */}
          <div className="grid grid-cols-7 mb-1">
            {WEEKDAYS.map((w, i) => (
              <div key={w} className={`text-center text-xs py-1 ${i === 0 ? 'text-rose-500' : i === 6 ? 'text-blue-500' : 'text-stone-400'}`}>{w}</div>
            ))}
          </div>

          {/* 월간 그리드 */}
          <div className="grid grid-cols-7 gap-1">
            {cells.map((d, i) => {
              if (d === null) return <div key={i} className="min-h-[3.5rem]" />;
              const evs = eventsByDay[d] || [];
              const wd = i % 7;
              const sel = selDay === d;
              return (
                <button key={i} onClick={() => setSelDay(d)}
                  className={`min-h-[3.5rem] rounded-lg border p-1 flex flex-col items-stretch text-left transition
                    ${sel ? 'border-stone-800 bg-white shadow-sm' : 'border-stone-200 bg-white hover:border-stone-400'}`}>
                  <span className={`self-start text-xs leading-none ${isToday(d) ? 'w-5 h-5 flex items-center justify-center rounded-full bg-stone-800 text-white' : wd === 0 ? 'text-rose-500' : wd === 6 ? 'text-blue-500' : 'text-stone-600'}`}>{d}</span>
                  <div className="mt-0.5 space-y-0.5 overflow-hidden">
                    {evs.slice(0, 2).map((e, k) => (
                      <div key={k} title={e.title}
                        className={`truncate rounded px-1 py-0.5 text-[10px] leading-tight text-white ${colorOf(e)}`}>{e.title}</div>
                    ))}
                    {evs.length > 2 && <div className="px-1 text-[10px] text-stone-400">+{evs.length - 2}</div>}
                  </div>
                </button>
              );
            })}
          </div>

          {/* 선택 일자 상세 */}
          {selDay && (
            <div className="mt-4">
              <div className="text-sm font-medium text-stone-700 mb-1.5">{month}월 {selDay}일 {isToday(selDay) && <span className="text-xs text-stone-400">(오늘)</span>}</div>
              {selEvents.length === 0 ? (
                <div className="text-sm text-stone-400 py-2">일정 없음</div>
              ) : (
                <div className="space-y-1.5">
                  {selEvents.map((e, k) => (
                    <div key={k} className="bg-white rounded-xl border border-stone-200 px-4 py-2.5 flex items-start gap-3">
                      <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${colorOf(e)}`} />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium">{e.title}
                          {e.time && <span className="ml-2 text-xs text-stone-400">{e.time}</span>}
                          {e.repeat && e.repeat !== 'none' && <span className="ml-2 text-[11px] text-stone-400">{REPEAT_LABEL[e.repeat] || e.repeat}</span>}
                        </div>
                        {e.description && <div className="text-xs text-stone-500 mt-0.5">{e.description}</div>}
                      </div>
                      {e.id && (
                        <button onClick={() => removeEvent(e.id)} title="삭제"
                          className="shrink-0 text-stone-300 hover:text-rose-500 leading-none">✕</button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 정기(매일/매주/주기) 일정 */}
          {recurring.length > 0 && (
            <div className="mt-5">
              <div className="text-xs text-stone-400 mb-1.5">정기 일정</div>
              <div className="flex flex-wrap gap-1.5">
                {recurring.map((e, k) => (
                  <span key={k} className="px-2.5 py-1 rounded-full bg-white border border-stone-200 text-xs text-stone-600">
                    <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${colorOf(e)}`} />
                    {e.title}
                    <span className="ml-1.5 text-stone-400">{REPEAT_LABEL[e.repeat || ''] || e.repeat}{e.time ? ` ${e.time}` : ''}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {!loading && !error && events.length === 0 && (
            <div className="py-10 text-center text-stone-400 text-sm">이번 달 등록된 일정이 없습니다.</div>
          )}
        </div>
      </div>

      {/* 일정 추가 모달 */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[1000] p-4"
          onClick={() => !saving && setShowAdd(false)}>
          <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl border border-stone-200" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-3 border-b border-stone-100 font-semibold text-stone-800">일정 추가</div>
            <div className="px-5 py-4 space-y-2.5">
              <input value={form.title} autoFocus onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && submitAdd()}
                placeholder="제목 (예: 치과 예약)"
                className="w-full px-3 py-2 rounded-xl border border-stone-200 text-sm outline-none focus:border-stone-400" />
              <div className="flex gap-2">
                <input type="date" value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                  className="flex-1 px-3 py-2 rounded-xl border border-stone-200 text-sm outline-none focus:border-stone-400" />
                <input type="time" value={form.time} onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))}
                  className="w-28 px-3 py-2 rounded-xl border border-stone-200 text-sm outline-none focus:border-stone-400" />
              </div>
              <div className="flex gap-2">
                <select value={form.repeat} onChange={(e) => setForm((f) => ({ ...f, repeat: e.target.value }))}
                  className="flex-1 px-3 py-2 rounded-xl border border-stone-200 text-sm bg-white outline-none focus:border-stone-400">
                  {REPEAT_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <select value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                  className="flex-1 px-3 py-2 rounded-xl border border-stone-200 text-sm bg-white outline-none focus:border-stone-400">
                  {TYPE_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <textarea value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="메모 (선택)" rows={2}
                className="w-full px-3 py-2 rounded-xl border border-stone-200 text-sm outline-none focus:border-stone-400 resize-none" />
            </div>
            <div className="px-5 py-3 border-t border-stone-100 flex justify-end gap-2">
              <button onClick={() => setShowAdd(false)} disabled={saving}
                className="px-3 py-2 rounded-xl border border-stone-200 text-sm text-stone-600 hover:bg-stone-50">취소</button>
              <button onClick={submitAdd} disabled={saving || !form.title.trim() || !form.date}
                className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700 disabled:opacity-40">
                {saving ? '추가 중…' : '추가'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
