import { useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent } from "react";
import { accountPalette } from "./accountPresentation";

type BirthdateFieldProps = {
  value: string;
  onChange: (value: string) => void;
  inputStyle: CSSProperties;
};

const monthNames = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December"
];

function parseDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  const date = new Date(year, month, day);
  if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) return null;
  return date;
}

function isoDate(year: number, month: number, day: number) {
  return `${year.toString().padStart(4, "0")}-${(month + 1).toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

function clampYear(value: number) {
  if (!Number.isFinite(value)) return new Date().getFullYear();
  return Math.max(1900, Math.min(2100, Math.trunc(value)));
}

export default function BirthdateField({ value, onChange, inputStyle }: BirthdateFieldProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const closingRef = useRef(false);
  const selectedDate = parseDate(value);
  const initialDate = selectedDate ?? new Date(1992, 1, 15);
  const [open, setOpen] = useState(false);
  const [viewYear, setViewYear] = useState(initialDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(initialDate.getMonth());

  const days = useMemo(() => {
    const firstWeekday = new Date(viewYear, viewMonth, 1).getDay();
    const count = new Date(viewYear, viewMonth + 1, 0).getDate();
    return [
      ...Array.from({ length: firstWeekday }, () => null),
      ...Array.from({ length: count }, (_, index) => index + 1)
    ];
  }, [viewMonth, viewYear]);

  function openPicker() {
    if (closingRef.current) return;
    const current = parseDate(value);
    if (current) {
      setViewYear(current.getFullYear());
      setViewMonth(current.getMonth());
    }
    setOpen(true);
  }

  function commit(day: number) {
    onChange(isoDate(viewYear, viewMonth, day));
    closePicker();
  }

  function closePicker() {
    closingRef.current = true;
    setOpen(false);
    inputRef.current?.blur();
    window.setTimeout(() => {
      closingRef.current = false;
    }, 160);
  }

  function acceptDate() {
    const current = parseDate(value);
    const accepted = current ?? selectedDate ?? new Date(viewYear, viewMonth, 1);
    const nextValue = isoDate(accepted.getFullYear(), accepted.getMonth(), accepted.getDate());
    onChange(nextValue);
    setViewYear(accepted.getFullYear());
    setViewMonth(accepted.getMonth());
    closePicker();
  }

  function moveMonth(delta: -1 | 1) {
    setViewMonth((month) => {
      const next = month + delta;
      if (next < 0) {
        setViewYear((year) => clampYear(year - 1));
        return 11;
      }
      if (next > 11) {
        setViewYear((year) => clampYear(year + 1));
        return 0;
      }
      return next;
    });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      closePicker();
      return;
    }
    if (event.key === "Enter") {
      acceptDate();
    }
  }

  return (
    <div style={pickerWrapperStyle}>
      <input
        ref={inputRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={openPicker}
        onClick={openPicker}
        onKeyDown={handleKeyDown}
        placeholder="YYYY-MM-DD"
        inputMode="numeric"
        style={inputStyle}
      />
      {open && (
        <div style={popoverStyle}>
          <div style={pickerHeaderStyle}>
            <button type="button" onClick={() => moveMonth(-1)} style={pickerButtonStyle} aria-label="Previous month">
              Prev
            </button>
            <select value={viewMonth} onChange={(event) => setViewMonth(Number(event.target.value))} style={pickerSelectStyle} aria-label="Birth month">
              {monthNames.map((month, index) => <option key={month} value={index}>{month}</option>)}
            </select>
            <input
              value={viewYear}
              onChange={(event) => setViewYear(clampYear(Number(event.target.value)))}
              type="number"
              min={1900}
              max={2100}
              style={yearInputStyle}
              aria-label="Birth year"
            />
            <button type="button" onClick={() => moveMonth(1)} style={pickerButtonStyle} aria-label="Next month">
              Next
            </button>
          </div>
          <div style={weekdayGridStyle}>{["S", "M", "T", "W", "T", "F", "S"].map((day) => <span key={day}>{day}</span>)}</div>
          <div style={dayGridStyle}>
            {days.map((day, index) => day ? (
              <button
                key={day}
                type="button"
                onClick={() => commit(day)}
                onDoubleClick={() => commit(day)}
                style={{
                  ...dayButtonStyle,
                  ...(selectedDate?.getFullYear() === viewYear && selectedDate.getMonth() === viewMonth && selectedDate.getDate() === day ? selectedDayStyle : {})
                }}
              >
                {day}
              </button>
            ) : <span key={`blank-${index}`} />)}
          </div>
          <div style={pickerFooterStyle}>
            <button
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                acceptDate();
              }}
              style={doneButtonStyle}
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const pickerWrapperStyle: CSSProperties = {
  position: "relative",
  minWidth: 0
};

const popoverStyle: CSSProperties = {
  position: "absolute",
  zIndex: 20,
  top: "calc(100% + 0.35rem)",
  left: 0,
  width: "min(100%, 21rem)",
  minWidth: "18rem",
  padding: "0.75rem",
  borderRadius: "14px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "linear-gradient(180deg, rgba(18, 25, 37, 0.98), rgba(11, 14, 18, 0.98))",
  boxShadow: "0 18px 44px rgba(0,0,0,0.36)",
  display: "grid",
  gap: "0.65rem"
};

const pickerHeaderStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "auto minmax(0, 1fr) 5.2rem auto",
  gap: "0.45rem",
  alignItems: "center"
};

const pickerButtonStyle: CSSProperties = {
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "10px",
  padding: "0.48rem 0.55rem",
  background: accountPalette.panelSoft,
  color: accountPalette.silver,
  cursor: "pointer",
  fontWeight: 700
};

const pickerSelectStyle: CSSProperties = {
  minWidth: 0,
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "10px",
  background: "rgba(11, 14, 18, 0.52)",
  color: accountPalette.silver,
  padding: "0.48rem",
  font: "inherit"
};

const yearInputStyle: CSSProperties = {
  ...pickerSelectStyle,
  width: "100%"
};

const weekdayGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(7, 1fr)",
  gap: "0.25rem",
  color: accountPalette.silverMuted,
  fontSize: "0.72rem",
  textAlign: "center",
  fontWeight: 800
};

const dayGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(7, 1fr)",
  gap: "0.25rem"
};

const pickerFooterStyle: CSSProperties = {
  display: "flex",
  justifyContent: "flex-end"
};

const dayButtonStyle: CSSProperties = {
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "10px",
  minHeight: "2rem",
  background: "rgba(11, 14, 18, 0.38)",
  color: accountPalette.silver,
  cursor: "pointer",
  fontWeight: 700
};

const selectedDayStyle: CSSProperties = {
  border: "1px solid rgba(126, 215, 209, 0.48)",
  background: "rgba(126, 215, 209, 0.14)",
  boxShadow: "0 0 16px rgba(126, 215, 209, 0.16)"
};

const doneButtonStyle: CSSProperties = {
  ...pickerButtonStyle,
  border: "1px solid rgba(126, 215, 209, 0.42)",
  background: "linear-gradient(180deg, rgba(16, 71, 75, 0.74) 0%, rgba(18, 25, 37, 0.88) 100%)",
  fontWeight: 800
};
