import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/format";

const buttonVariants = cva(
  cn(
    "inline-flex items-center justify-center gap-1.5 whitespace-nowrap select-none",
    "font-medium text-[13px] rounded-md border transition-colors duration-150 cursor-pointer",
    "disabled:pointer-events-none disabled:opacity-40 disabled:cursor-not-allowed",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ai/40",
  ),
  {
    variants: {
      variant: {
        ai: [
          "bg-transparent border-transparent text-ai hover:bg-ai-dim",
          "data-[active=true]:bg-ai-dim",
        ],
        go: [
          "bg-transparent border-transparent text-go hover:bg-go-dim",
          "data-[active=true]:bg-go-dim",
        ],
        solid: "bg-ink text-ops-ground border-ink hover:opacity-85",
        outline: "border-ops-line-bright bg-transparent text-ink hover:bg-ops-raised",
        ghost: "border-transparent bg-transparent text-ink-dim hover:text-ink hover:bg-ops-raised",
        danger: "border-transparent bg-transparent text-critical hover:bg-critical-dim",
      },
      size: {
        sm: "h-7 px-2 text-[12px]",
        md: "h-8 px-3 text-[13px]",
        lg: "h-10 px-4 text-[14px]",
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

