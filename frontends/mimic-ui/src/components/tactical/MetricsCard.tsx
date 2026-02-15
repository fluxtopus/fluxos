import * as React from "react"
import { cn } from "@/lib/utils"
import { StatusIndicator } from "./StatusIndicator"
import { TacticalCard } from "./TacticalCard"

export interface MetricsCardProps {
  label: string
  value: string | number
  status?: "online" | "offline" | "warning" | "error"
  icon?: React.ReactNode
  className?: string
}

const MetricsCard: React.FC<MetricsCardProps> = ({
  label,
  value,
  status = "online",
  icon,
  className,
}) => {
  return (
    <TacticalCard className={cn("p-6", className)} glow>
      <div className="flex items-start justify-between mb-4">
        <StatusIndicator status={status} pulse />
        {icon && (
          <div className="text-muted-foreground opacity-50">
            {icon}
          </div>
        )}
      </div>
      <div>
        <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2 font-mono">
          {label}
        </div>
        <div className="text-3xl font-bold font-mono text-primary">
          {value}
        </div>
      </div>
    </TacticalCard>
  )
}

export { MetricsCard }
