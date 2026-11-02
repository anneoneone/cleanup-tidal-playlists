import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConfirmPanel } from "./ConfirmPanel";

function renderPanel() {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmPanel
      title="Restore?"
      confirmLabel="Restore now"
      onConfirm={onConfirm}
      onCancel={onCancel}
      danger
    >
      <p>Replaces the database.</p>
    </ConfirmPanel>,
  );
  return { onConfirm, onCancel };
}

describe("ConfirmPanel", () => {
  it("focuses Cancel, not the confirm button", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("ignores a confirm right after opening (double tap)", async () => {
    const user = userEvent.setup();
    const now = vi.spyOn(performance, "now");
    now.mockReturnValue(1000);
    const { onConfirm } = renderPanel();

    now.mockReturnValue(1100);
    await user.click(screen.getByRole("button", { name: "Restore now" }));
    expect(onConfirm).not.toHaveBeenCalled();

    now.mockReturnValue(1500);
    await user.click(screen.getByRole("button", { name: "Restore now" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    now.mockRestore();
  });

  it("cancels on Escape", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderPanel();
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
