import * as React from "react"
import { cn } from "@/lib/utils"

export interface TacticalPanelProps extends React.HTMLAttributes<HTMLDivElement> {
  grid?: boolean
}

const TacticalPanel = React.forwardRef<HTMLDivElement, TacticalPanelProps>(
  ({ className, grid = true, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "relative rounded-lg border border-border bg-card/30 p-6",
          "backdrop-blur shadow-sm",
          className
        )}
        {...props}
      >
        {grid && (
          <div className="absolute inset-0 bg-[linear-gradient(to_right,oklch(0.26_0.01_260)_1px,transparent_1px),linear-gradient(to_bottom,oklch(0.26_0.01_260)_1px,transparent_1px)] bg-[size:2rem_2rem] opacity-20 rounded-lg pointer-events-none" />
        )}
        <div className="relative z-10">{children}</div>
      </div>
    )
  }
)
TacticalPanel.displayName = "TacticalPanel"

export { TacticalPanel }
