import { useEffect, useRef, useState } from "react";

/**
 * A button that opens a panel under itself. The panel closes
 * on a click elsewhere or on Escape. Returns the ref for the
 * root element, whether it is open, and the setter.
 */
export function usePopover() {
  const root = useRef(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return undefined;

    const away = (event) => {
      if (root.current && !root.current.contains(event.target)) setOpen(false);
    };
    const escape = (event) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);

    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return [root, open, setOpen];
}
