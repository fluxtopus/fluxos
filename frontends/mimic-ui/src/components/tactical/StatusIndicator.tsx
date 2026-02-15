import * as React from "react"
import { cn } from "@/lib/utils"

export interface StatusIndicatorProps extends React.HTMLAttributes<HTMLDivElement> {
  status: "online" | "offline" | "warning" | "error"
  pulse?: boolean
  label?: string
}

const StatusIndicator = React.forwardRef<HTMLDivElement, StatusIndicatorProps>(
  ({ className, status, pulse = true, label, ...props }, ref) => {
    const colors = {
      online: "bg-green-500",
      offline: "bg-gray-500",
      warning: "bg-amber-500",
      error: "bg-red-500",
    }

    const glows = {
      online: "shadow-[0_0_10px_oklch(0.65_0.15_150),0_0_20px_oklch(0.65_0.15_150)]",
      offline: "shadow-[0_0_10px_oklch(0.5_0.01_260),0_0_20px_oklch(0.5_0.01_260)]",
      warning: "shadow-[0_0_10px_oklch(0.7_0.15_85),0_0_20px_oklch(0.7_0.15_85)]",
      error: "shadow-[0_0_10px_oklch(0.577_0.245_27),0_0_20px_oklch(0.577_0.245_27)]",
    }

    if (label) {
      return (
        <div ref={ref} className={cn("flex items-center gap-2", className)} {...props}>
          <div
            className={cn(
              "w-2 h-2 rounded-full",
              colors[status],
              pulse && "pulse-glow",
              glows[status]
            )}
          />
          <span className="font-mono text-sm uppercase">{label}</span>
        </div>
      )
    }

    return (
      <div
        ref={ref}
        className={cn(
          "w-3 h-3 rounded-full",
          colors[status],
          pulse && "pulse-glow",
          glows[status],
          className
        )}
        {...props}
      />
    )
  }
)
StatusIndicator.displayName = "StatusIndicator"

export { StatusIndicator }
