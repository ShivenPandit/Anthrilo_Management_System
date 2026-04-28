export const IST_TIME_ZONE = 'Asia/Kolkata';

const toParts = (date: Date) =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: IST_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);

export const toIstYmd = (date: Date): string => {
  const parts = toParts(date);
  const year = parts.find((p) => p.type === 'year')?.value ?? '1970';
  const month = parts.find((p) => p.type === 'month')?.value ?? '01';
  const day = parts.find((p) => p.type === 'day')?.value ?? '01';
  return `${year}-${month}-${day}`;
};

export const getClosedWindowLast7DaysIst = (): { fromDate: string; toDate: string } => {
  const now = new Date();
  const ymd = toIstYmd(now);
  const [year, month, day] = ymd.split('-').map(Number);
  const istMidnight = new Date(Date.UTC(year, month - 1, day, 0, 0, 0));

  const yesterday = new Date(istMidnight);
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);

  const from = new Date(yesterday);
  from.setUTCDate(from.getUTCDate() - 6);

  return {
    fromDate: toIstYmd(from),
    toDate: toIstYmd(yesterday),
  };
};

export const getYesterdayIst = (): string => {
  return getClosedWindowLast7DaysIst().toDate;
};

export const getDayBeforeYesterdayIst = (): string => {
  const yesterday = getYesterdayIst();
  const [year, month, day] = yesterday.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day, 0, 0, 0));
  date.setUTCDate(date.getUTCDate() - 1);
  return toIstYmd(date);
};

export const getIstRelativeDate = (daysFromToday: number): string => {
  const today = toIstYmd(new Date());
  const [year, month, day] = today.split('-').map(Number);
  const base = new Date(Date.UTC(year, month - 1, day, 0, 0, 0));
  base.setUTCDate(base.getUTCDate() + daysFromToday);
  return toIstYmd(base);
};

