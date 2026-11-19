export type ProgramInlineView = 'today' | 'week' | 'month';

export type ProgramInlineCreate = {
  date: string;
  type: 'CLASS' | 'APPOINTMENT';
  label: '＋ Ders ekle' | '＋ Program ekle';
};

function dayNumber(value: string): number | null {
  if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(value)) return null;
  const timestamp = Date.parse(`${value}T00:00:00.000Z`);
  if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== value) return null;
  return timestamp / 86_400_000;
}

function validWallDateTime(value: string): boolean {
  if (!/^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}$/.test(value)) return false;
  if (dayNumber(value.slice(0, 10)) === null) return false;
  const hour = Number(value.slice(11, 13));
  const minute = Number(value.slice(14, 16));
  return hour < 24 && minute < 60;
}

export function programInlineCreateFor(view: ProgramInlineView, date: string): ProgramInlineCreate | null {
  if (view === 'month' || dayNumber(date) === null) return null;
  return view === 'week'
    ? { date, type: 'CLASS', label: '＋ Ders ekle' }
    : { date, type: 'APPOINTMENT', label: '＋ Program ekle' };
}

/** Apply the web inline-add date while preserving suggested wall-clock times and overnight duration. */
export function programDateTimeOnDay(startAt: string, endAt: string, targetDay: string): { start_at: string; end_at: string } {
  const startDay = validWallDateTime(startAt) ? dayNumber(startAt.slice(0, 10)) : null;
  const endDay = endAt === '' ? null : validWallDateTime(endAt) ? dayNumber(endAt.slice(0, 10)) : null;
  const targetDayNumber = dayNumber(targetDay);
  if (startDay === null || targetDayNumber === null || endAt !== '' && endDay === null) {
    throw new Error('Program başlangıç tarihi doğrulanamadı.');
  }
  const endOffset = endDay === null ? 0 : endDay - startDay;
  if (endOffset < 0) throw new Error('Program bitiş tarihi başlangıçtan önce olamaz.');
  const shiftedEndDay = endDay === null
    ? ''
    : new Date((targetDayNumber + endOffset) * 86_400_000).toISOString().slice(0, 10);
  return {
    start_at: `${targetDay}${startAt.slice(10)}`,
    end_at: endAt === '' ? '' : `${shiftedEndDay}${endAt.slice(10)}`
  };
}
