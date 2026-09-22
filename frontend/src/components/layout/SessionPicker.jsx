import { useState } from "react";

import {
  MONTHS,
  WEEKDAYS,
  isWeekend,
  monthGrid,
  monthOf,
  replayBounds,
  shiftMonth,
  toIso,
} from "../../lib/calendar";
import { CalendarIcon, ChevronIcon, ClockIcon } from "../icons";
import { usePopover } from "./Popover";

function label(iso) {
  const { year, month } = monthOf(iso);
  return `${iso.slice(8, 10)} ${MONTHS[month].slice(0, 3)} ${year}`;
}

/**
 * The replay date of the desk. A session is chosen from a
 * calendar, never typed: a half-typed year used to be sent to
 * the API as "0002". Only the last year of weekdays can be
 * picked; nothing after the latest session, and a date is
 * applied on the click, once.
 */
export default function SessionPicker({ asOf, latestSession, onTimeTravel }) {
  const [root, isOpen, setOpen] = usePopover();
  const today = toIso(new Date());
  const bounds = replayBounds(latestSession ?? today);
  const [shown, setShown] = useState(() => monthOf(asOf ?? bounds.max));

  const open = () => {
    setShown(monthOf(asOf ?? bounds.max));
    setOpen(!isOpen);
  };

  const pick = (iso) => {
    onTimeTravel(iso === bounds.max ? null : iso);
    setOpen(false);
  };

  const index = ({ year, month }) => year * 12 + month;
  const canGoBack = index(shown) > index(monthOf(bounds.min));
  const canGoForward = index(shown) < index(monthOf(bounds.max));

  return (
    <div className="menu" ref={root}>
      <button
        type="button"
        className={`topbar__asof menu__button ${asOf ? "is-replay" : ""} ${isOpen ? "is-open" : ""}`}
        title={
          asOf
            ? "Replay: nothing after this date exists for the desk"
            : "Live. Pick a past session to replay the desk as of that day"
        }
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={open}
      >
        <ClockIcon size={16} />
        <span className="stat__label">{asOf ? "REPLAY" : "LIVE"}</span>
        <span className="mono asof__date">{asOf ? label(asOf) : "Today"}</span>
        <CalendarIcon size={15} />
      </button>

      {isOpen && (
        <div className="menu__panel calendar" role="dialog" aria-label="Replay date">
          <div className="calendar__head">
            <button
              type="button"
              className="calendar__nav"
              disabled={!canGoBack}
              aria-label="Previous month"
              onClick={() => setShown(shiftMonth(shown, -1))}
            >
              <span className="calendar__arrow calendar__arrow--back"><ChevronIcon size={16} /></span>
            </button>
            <span className="calendar__month">
              {MONTHS[shown.month]} <span className="mono">{shown.year}</span>
            </span>
            <button
              type="button"
              className="calendar__nav"
              disabled={!canGoForward}
              aria-label="Next month"
              onClick={() => setShown(shiftMonth(shown, 1))}
            >
              <span className="calendar__arrow calendar__arrow--forward"><ChevronIcon size={16} /></span>
            </button>
          </div>

          <div className="calendar__grid" role="grid">
            {WEEKDAYS.map((day, index) => (
              <span key={index} className="calendar__weekday eyebrow">
                {day}
              </span>
            ))}

            {monthGrid(shown).map((iso) => {
              const outside = monthOf(iso).month !== shown.month;
              const closed = isWeekend(iso) || iso < bounds.min || iso > bounds.max;
              const selected = iso === (asOf ?? bounds.max);

              return (
                <button
                  key={iso}
                  type="button"
                  role="gridcell"
                  className={[
                    "calendar__day mono",
                    outside ? "is-outside" : "",
                    selected ? "is-selected" : "",
                    iso === bounds.max ? "is-latest" : "",
                  ].join(" ")}
                  disabled={closed}
                  aria-selected={selected}
                  onClick={() => pick(iso)}
                >
                  {Number(iso.slice(8, 10))}
                </button>
              );
            })}
          </div>

          <div className="calendar__foot">
            <span className="calendar__hint">Sessions of the last year</span>
            <button
              type="button"
              className="btn btn--ghost btn--small"
              disabled={!asOf}
              onClick={() => pick(bounds.max)}
            >
              Back to today
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
