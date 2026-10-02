// Dates as people read them. A date-only value ("2026-12-01") is a calendar day, not a moment: it is built
// from its parts, so no time zone can move it to the previous day.

const DAY = 24 * 60 * 60 * 1000;

function calendarDay(value: string) {
  const [year = 0, month = 1, day = 1] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function formatDate(value: string) {
  return calendarDay(value).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(value: string) {
  return new Date(value).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Whole days from today to a calendar day: negative when it has passed. */
export function daysUntil(value: string, now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((calendarDay(value).getTime() - today.getTime()) / DAY);
}

/** Whole days since a moment. */
export function daysSince(value: string, now = new Date()) {
  return Math.floor((now.getTime() - new Date(value).getTime()) / DAY);
}

export function deadlineHint(value: string, now = new Date()) {
  const days = daysUntil(value, now);
  if (days < 0) return `${-days} day${days === -1 ? "" : "s"} overdue`;
  if (days === 0) return "due today";
  return `in ${days} day${days === 1 ? "" : "s"}`;
}

export function todayIso(now = new Date()) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes} min ${seconds % 60} s` : `${seconds} s`;
}

export function plural(count: number, one: string, many = `${one}s`) {
  return `${count.toLocaleString("en-GB")} ${count === 1 ? one : many}`;
}
