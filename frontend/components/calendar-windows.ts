export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const SPANISH_WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

export function calendarWindows(values?: string[] | null) {
  return (values ?? []).flatMap(value => {
    const match = /^([a-z]+)\s+(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})$/i.exec(value.trim());
    if (!match) return [];
    const day = WEEKDAYS.findIndex(name => name.toLowerCase() === match[1].toLowerCase());
    const start = Number(match[2]) * 60 + Number(match[3]);
    const end = Number(match[4]) * 60 + Number(match[5]);
    return day >= 0 && start >= 0 && start < end && end <= 1440 ? [{ day, start, end }] : [];
  });
}
