import * as React from "react"
import { cn } from "@/lib/utils"

export interface TacticalTableProps extends React.HTMLAttributes<HTMLTableElement> {}

const TacticalTable = React.forwardRef<HTMLTableElement, TacticalTableProps>(
  ({ className, ...props }, ref) => {
    return (
      <div className="w-full overflow-auto rounded-lg border border-border">
        <table
          ref={ref}
          className={cn("w-full caption-bottom text-sm", className)}
          {...props}
        />
      </div>
    )
  }
)
TacticalTable.displayName = "TacticalTable"

const TacticalTableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead
    ref={ref}
    className={cn("bg-muted/50 border-b border-border", className)}
    {...props}
  />
))
TacticalTableHeader.displayName = "TacticalTableHeader"

const TacticalTableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody
    ref={ref}
    className={cn("[&_tr:last-child]:border-0", className)}
    {...props}
  />
))
TacticalTableBody.displayName = "TacticalTableBody"

const TacticalTableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      "border-b border-border transition-colors hover:bg-muted/30",
      "data-[state=selected]:bg-muted",
      className
    )}
    {...props}
  />
))
TacticalTableRow.displayName = "TacticalTableRow"

const TacticalTableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <th
    ref={ref}
    className={cn(
      "h-12 px-4 text-left align-middle font-mono font-medium text-muted-foreground uppercase tracking-wider text-xs",
      "[&:has([role=checkbox])]:pr-0",
      className
    )}
    {...props}
  />
))
TacticalTableHead.displayName = "TacticalTableHead"

const TacticalTableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn("p-4 align-middle [&:has([role=checkbox])]:pr-0", className)}
    {...props}
  />
))
TacticalTableCell.displayName = "TacticalTableCell"

export {
  TacticalTable,
  TacticalTableHeader,
  TacticalTableBody,
  TacticalTableRow,
  TacticalTableHead,
  TacticalTableCell,
}
