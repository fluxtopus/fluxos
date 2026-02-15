import * as React from "react"
import { cn } from "@/lib/utils"

export interface TacticalSelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {}

const TacticalSelect = React.forwardRef<HTMLSelectElement, TacticalSelectProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <select
        className={cn(
          "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2",
          "font-mono text-sm ring-offset-background",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "transition-all duration-200",
          className
        )}
        ref={ref}
        {...props}
      >
        {children}
      </select>
    )
  }
)
TacticalSelect.displayName = "TacticalSelect"

export { TacticalSelect }
