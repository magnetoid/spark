/** Time helpers that respect the brand's timezone without a date library. */

const partsCache = new Map<string, Intl.DateTimeFormat>();

function fmt(tz: string): Intl.DateTimeFormat {
  let f = partsCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", {
      timeZone: tz, hourCycle: "h23",
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    partsCache.set(tz, f);
  }
  return f;
}

export interface ZonedParts { year: number; month: number; day: number; hour: number; minute: number; second: number; weekday: number }

/** Calendar fields of an instant in `tz`. weekday: 0 = Monday … 6 = Sunday. */
export function zonedParts(date: Date | string, tz: string): ZonedParts {
  const d = typeof date === "string" ? new Date(date) : date;
  const p: Record<string, number> = {};
  for (const part of fmt(tz).formatToParts(d)) if (part.type !== "literal") p[part.type] = Number(part.value);
  const utcDay = new Date(Date.UTC(p.year, p.month - 1, p.day)).getUTCDay();
  return { year: p.year, month: p.month, day: p.day, hour: p.hour, minute: p.minute, second: p.second, weekday: (utcDay + 6) % 7 };
}

/** `YYYY-MM-DD` of an instant in `tz`. */
export function zonedDateKey(date: Date | string, tz: string): string {
  const p = zonedParts(date, tz);
  return `${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")}`;
}

/** `YYYY-MM-DDTHH:MM` for a datetime-local input, in `tz`. */
export function toLocalInput(iso: string | null | undefined, tz: string): string {
  if (!iso) return "";
  const p = zonedParts(iso, tz);
  return `${zonedDateKey(iso, tz)}T${String(p.hour).padStart(2, "0")}:${String(p.minute).padStart(2, "0")}`;
}

/** The instant (UTC ISO) that a datetime-local value means in `tz`. */
export function fromLocalInput(value: string, tz: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!m) return null;
  const [, y, mo, d, h, mi] = m.map(Number);
  // Guess UTC, measure the zone's offset at that guess, correct once (twice for DST edges).
  let guess = Date.UTC(y, mo - 1, d, h, mi);
  for (let i = 0; i < 2; i++) {
    const p = zonedParts(new Date(guess), tz);
    const asIf = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute);
    guess += Date.UTC(y, mo - 1, d, h, mi) - asIf;
  }
  return new Date(guess).toISOString();
}

export function fmtTime(iso: string, tz: string) {
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}

export function fmtDateTime(iso: string, tz: string) {
  return new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}

export function fmtDay(key: string, opts: Intl.DateTimeFormatOptions = { weekday: "long", day: "numeric", month: "short" }) {
  const [y, m, d] = key.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, { ...opts, timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

export function addDays(key: string, n: number): string {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

/** Monday of the week that contains `key`. */
export function startOfWeek(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return addDays(key, -((dt.getUTCDay() + 6) % 7));
}

export function todayKey(tz: string) {
  return zonedDateKey(new Date(), tz);
}
