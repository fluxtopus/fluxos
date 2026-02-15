import * as React from "react"
import { cn } from "@/lib/utils"
import { StatusIndicator } from "./StatusIndicator"

export interface PageHeaderProps {
  title: string
  subtitle?: string
  status?: "online" | "offline" | "warning" | "error"
  className?: string
}

const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  status = "online",
  className,
}) => {
  return (
    <div className={cn("mb-8", className)}>
      <div className="flex items-center gap-4 mb-2">
        <StatusIndicator status={status} pulse />
        <h1 className="text-4xl font-bold font-sans uppercase tracking-wider">{title}</h1>
      </div>
      {subtitle && (
        <div className="text-muted-foreground ml-7 font-mono text-sm">
          {subtitle}
        </div>
      )}
    </div>
  )
}

export { PageHeader }
