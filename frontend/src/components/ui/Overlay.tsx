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
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px]" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2",
          "rounded-xl border border-ops-line bg-ops-ground shadow-2xl",
          "max-h-[85vh] overflow-y-auto",
          className,
        )}
      >
        <div className="flex items-center justify-between px-5 pt-4 pb-1">
          <DialogPrimitive.Title className="text-[17px] font-semibold text-ink">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close
            aria-label="Close"
            className="rounded-md p-1 text-ink-faint hover:bg-ops-raised hover:text-ink"
          >
            <X size={16} strokeWidth={1.5} />
          </DialogPrimitive.Close>
        </div>
        <div className="px-5 pb-5 pt-2">{children}</div>
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
    <div className="px-1 py-6">
      <p className="text-[14px] text-ink-faint">{message}</p>
      {hint && <p className="mt-1 text-[12px] text-ink-faint">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded-md bg-critical-dim px-3 py-2">
      <p className="text-[13px] text-critical">{message}</p>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <span className={cn("block animate-pulse rounded bg-ops-line", className)} />;
}
