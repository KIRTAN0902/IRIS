import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/format";

/** Instrument console overlay. Used for protected, interruptive actions only. */
export function Dialog(props: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root {...props} />;
}

export function DialogContent({
  title,
  children,
  className,
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ops-void/80" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2",
          "border border-ops-line-bright bg-ops-panel",
          "max-h-[85vh] overflow-y-auto",
          className,
        )}
      >
        <div className="flex items-center justify-between border-b border-ops-line px-4 py-3">
          <DialogPrimitive.Title className="label-caps text-ink">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close
            aria-label="Close"
            className="text-ink-faint hover:text-ink focus-visible:text-caution"
          >
            <X size={16} strokeWidth={1.5} />
          </DialogPrimitive.Close>
        </div>
        <div className="p-4">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function EmptyState({
  message,
  hint,
}: {
  message: string;
  hint?: string;
}) {
  return (
    <div className="border border-dashed border-ops-line px-4 py-8 text-center">
      <p className="text-[14px] text-ink-dim">{message}</p>
      {hint && <p className="mt-1 text-[12px] text-ink-faint">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div role="alert" className="border border-critical-dim bg-critical-dim/30 px-4 py-3">
      <p className="text-[13px] text-critical">{message}</p>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <span className={cn("block animate-pulse bg-ops-line", className)} />;
}
