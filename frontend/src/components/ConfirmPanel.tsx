import { type ReactNode, type RefObject, useEffect, useRef } from "react";
import { Button } from "./Button";
import { cx } from "./cx";

/** Clicks on the confirm button this soon after opening are ignored (double tap). */
const ARM_DELAY_MS = 400;

/**
 * An in-page confirmation (no window.confirm). Focuses Cancel, never the
 * confirm button, so one extra key press or tap cannot confirm. When it
 * closes, focus goes back to `returnFocusRef` or to what had focus before.
 */
export function ConfirmPanel({
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  busy = false,
  danger = false,
  returnFocusRef,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
  danger?: boolean;
  returnFocusRef?: RefObject<HTMLElement | null>;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const openedAt = useRef(0);
  useEffect(() => {
    openedAt.current = performance.now();
    const previous = document.activeElement;
    cancelRef.current?.focus();
    return () => {
      requestAnimationFrame(() => {
        if (document.activeElement && document.activeElement !== document.body) return;
        // Read the ref when closing: the button it points to may be a new one.
        // eslint-disable-next-line react-hooks/exhaustive-deps
        const target = returnFocusRef?.current ?? previous;
        if (target instanceof HTMLElement && target.isConnected) target.focus();
      });
    };
  }, [returnFocusRef]);

  return (
    <div
      role="alertdialog"
      aria-label={title}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !busy) onCancel();
      }}
      className={cx(
        "rounded-lg border-2 bg-surface p-4 shadow-sm",
        danger ? "border-red-500/70" : "border-accent/60",
      )}
    >
      <p className="font-semibold">{title}</p>
      <div className="mt-2 space-y-2 text-sm text-muted">{children}</div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant={danger ? "danger" : "primary"}
          onClick={() => {
            if (performance.now() - openedAt.current >= ARM_DELAY_MS) onConfirm();
          }}
          busy={busy}
        >
          {confirmLabel}
        </Button>
        <Button ref={cancelRef} onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
