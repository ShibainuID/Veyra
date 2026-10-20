import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "../lib/cn";
import { Skeleton } from "./feedback";

export type SortDirection = "ascending" | "descending";
export interface SortState {
  columnId: string;
  direction: SortDirection;
}

export interface Column<T> {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Makes the header a sort button. Nulls sort last. */
  sortValue?: (row: T) => string | number | null | undefined;
  align?: "start" | "end";
  /** CSS width for the column (for example "88px" for the tag column). */
  width?: string;
  /** The cell that carries the row link; the link stretches over the whole row. */
  primary?: boolean;
  /** Stacked layout: sit in the left lead column (the tag), with no label. */
  lead?: boolean;
  /** Shown beside the header text, such as one provenance chip for the whole column. */
  headerAddon?: ReactNode;
  /** Read with the header by assistive technology, such as what the addon means for every cell. */
  headerDescription?: string;
}

export interface DataTableProps<T> {
  /** Describes the table for assistive technology; shown only when `captionVisible`. */
  caption: string;
  captionVisible?: boolean;
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  rowHref?: (row: T) => string;
  selectedKey?: string | null;
  /** Controlled sort; omit for the table to sort itself starting from `defaultSort`. */
  sort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
  defaultSort?: SortState | null;
  loading?: boolean;
  loadingRows?: number;
  /** Rendered in place of rows when there are none. */
  empty?: ReactNode;
  /** Rendered in place of rows when loading failed. */
  error?: ReactNode;
  /** "narrow" keeps the table's columns down to a 34rem container (for a table that drops columns to fit). */
  stack?: "default" | "narrow";
  className?: string;
}

function compare(a: string | number | null | undefined, b: string | number | null | undefined): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "en", { numeric: true });
}

/**
 * A semantic table with 64px rows. Each row links through its primary cell; below 720px of
 * container width the rows stack, with the tag on the left and labelled values beside it.
 */
export function DataTable<T>({
  caption,
  captionVisible = false,
  columns,
  rows,
  rowKey,
  rowHref,
  selectedKey,
  sort: controlledSort,
  onSortChange,
  defaultSort = null,
  loading = false,
  loadingRows = 4,
  empty,
  error,
  stack = "default",
  className,
}: DataTableProps<T>) {
  const [internalSort, setInternalSort] = useState<SortState | null>(defaultSort);
  const sort = controlledSort !== undefined ? controlledSort : internalSort;

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.id === sort.columnId);
    if (!column?.sortValue) return rows;
    const value = column.sortValue;
    const factor = sort.direction === "ascending" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      if (va == null || vb == null) return compare(va, vb);
      return compare(va, vb) * factor;
    });
  }, [rows, columns, sort]);

  const toggleSort = (columnId: string) => {
    const next: SortState =
      sort?.columnId === columnId && sort.direction === "ascending"
        ? { columnId, direction: "descending" }
        : { columnId, direction: "ascending" };
    if (controlledSort === undefined) setInternalSort(next);
    onSortChange?.(next);
  };

  const fullRow = (content: ReactNode) => (
    <tr>
      <td colSpan={columns.length} className="h-auto! border-0! px-0! py-4!">
        {content}
      </td>
    </tr>
  );

  let body: ReactNode;
  if (loading) {
    body = Array.from({ length: loadingRows }, (_, i) => (
      <tr key={`loading-${i}`} aria-hidden="true">
        {columns.map((column) => (
          <td key={column.id} data-lead={column.lead ? "" : undefined}>
            <Skeleton height={column.lead ? "40px" : "16px"} width={column.lead ? "56px" : "70%"} />
          </td>
        ))}
      </tr>
    ));
  } else if (error) {
    body = fullRow(error);
  } else if (sorted.length === 0) {
    body = empty ? fullRow(empty) : null;
  } else {
    body = sorted.map((row) => {
      const key = rowKey(row);
      const href = rowHref?.(row);
      const selected = selectedKey != null && key === selectedKey;
      return (
        <tr key={key} data-linked={href ? "" : undefined} data-selected={selected ? "" : undefined}>
          {columns.map((column) => {
            const content = column.cell(row);
            return (
              <td
                key={column.id}
                data-label={column.header}
                data-align={column.align}
                data-primary={column.primary ? "" : undefined}
                data-lead={column.lead ? "" : undefined}
              >
                {column.primary && href ? (
                  <Link to={href} className="dt-row-link" aria-current={selected ? "true" : undefined}>
                    {content}
                  </Link>
                ) : (
                  content
                )}
              </td>
            );
          })}
        </tr>
      );
    });
  }

  return (
    <div className={cn("dt-wrap", className)} data-stack={stack === "narrow" ? "narrow" : undefined}>
      <table className="dt" aria-busy={loading || undefined}>
        <caption className={captionVisible ? "pb-3 text-start text-muted" : "sr-only"}>
          {caption}
          {loading && <span className="sr-only"> (loading)</span>}
        </caption>
        <colgroup>
          {columns.map((column) => (
            <col key={column.id} style={column.width ? { width: column.width } : undefined} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((column) => {
              const active = sort?.columnId === column.id;
              const SortIcon = !active ? ArrowUpDown : sort.direction === "ascending" ? ArrowUp : ArrowDown;
              return (
                <th
                  key={column.id}
                  scope="col"
                  data-align={column.align}
                  aria-sort={column.sortValue ? (active ? sort.direction : "none") : undefined}
                >
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1 py-1">
                    {column.sortValue ? (
                      <button type="button" className="dt-sort" onClick={() => toggleSort(column.id)}>
                        {column.header}
                        <SortIcon aria-hidden="true" className={cn("size-4", !active && "opacity-60")} strokeWidth={2.5} />
                      </button>
                    ) : (
                      column.header
                    )}
                    {column.headerAddon}
                    {column.headerDescription && <span className="sr-only">{column.headerDescription}</span>}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </div>
  );
}
