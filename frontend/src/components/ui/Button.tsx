import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/format";

const buttonVariants = cva(
  cn(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap select-none",
    "font-[family-name:var(--font-display)] font-semibold uppercase tracking-[0.1em] text-[12px]",
    "rounded-lg border transition-all duration-150 cursor-pointer active:scale-[0.98]",
    "disabled:pointer-events-none disabled:opacity-40 disabled:cursor-not-allowed",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-dim focus-visible:ring-offset-1 focus-visible:ring-offset-ops-ground",
  ),
  {
    variants: {
      variant: {
        ai: [
          "bg-ops-raised border-ops-line-bright text-ink hover:bg-ops-line-bright hover:border-ink-dim",
          "data-[active=true]:bg-ink data-[active=true]:text-ops-void",
        ],
        go: [
          "bg-go/10 border-go/40 text-go hover:bg-go/20 hover:border-go/70 hover:text-ink shadow-xs",
          "data-[active=true]:bg-go data-[active=true]:text-ops-void",
        ],
        solid: "bg-ink text-ops-void border-ink hover:bg-white hover:shadow-xs",
        outline: "border-ops-line-bright text-ink-dim hover:border-ink-dim hover:text-ink hover:bg-ops-raised bg-ops-panel",
        ghost: "border-transparent text-ink-dim hover:text-ink hover:bg-ops-raised",
        danger: "bg-critical/10 border-critical/30 text-critical hover:bg-critical/20 hover:border-critical/60 hover:text-ink",
      },
      size: {
        sm: "h-7 px-2.5 text-[11px]",
        md: "h-9 px-3.5 text-[12px]",
        lg: "h-11 px-5 text-[13px]",
      },
    },
    defaultVariants: { variant: "outline", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";

