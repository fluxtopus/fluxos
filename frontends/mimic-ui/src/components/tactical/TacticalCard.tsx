import * as React from "react"
import { cn } from "@/lib/utils"

export interface TacticalCardProps extends React.HTMLAttributes<HTMLDivElement> {
  glow?: boolean
}

const TacticalCard = React.forwardRef<HTMLDivElement, TacticalCardProps>(
  ({ className, glow = false, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "relative rounded-lg border bg-card/50 backdrop-blur text-card-foreground shadow-sm",
          "border-border hover:border-primary/50 transition-all duration-300",
          glow && "hover:shadow-[0_0_20px_oklch(0.75_0.15_45/0.3)]",
          className
        )}
        {...props}
      />
    )
  }
)
TacticalCard.displayName = "TacticalCard"

const TacticalCardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 p-6", className)}
    {...props}
  />
))
TacticalCardHeader.displayName = "TacticalCardHeader"

const TacticalCardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      "text-xl font-semibold leading-none tracking-tight font-sans",
      className
    )}
    {...props}
  />
))
TacticalCardTitle.displayName = "TacticalCardTitle"

const TacticalCardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
))
TacticalCardContent.displayName = "TacticalCardContent"

export { TacticalCard, TacticalCardHeader, TacticalCardTitle, TacticalCardContent }
