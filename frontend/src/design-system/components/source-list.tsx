/**
 * The sources of a suggestion (UI-20; console UI design, Sources): the KB document versions that
 * the analysis retrieved, each with its citation number, or "–" and "Not cited", its title, ID,
 * version, validity, and effective period. Activating a title opens the full version.
 */
import { StatusBadge } from "@/design-system/components/status-badge";
import type { StatusPresentation } from "@/design-system/components/status-presentations";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** One source. */
export type SourceListItem = {
  readonly key: string;
  /** The citation number; absent when the draft does not cite the version. */
  readonly number?: number;
  readonly title: string;
  readonly documentId: string;
  readonly version: string;
  readonly validity: StatusPresentation;
  /** The effective period in words, for example "Since 1 Sep 2026". */
  readonly period: string;
};

/** Props of {@link SourceList}. */
export type SourceListProps = {
  readonly sources: readonly SourceListItem[];
  /** Opens a source; receives its key and the title button, which the focus returns to. */
  readonly onOpen: (key: string, opener: HTMLElement) => void;
};

/**
 * Render the sources.
 *
 * @param props - The sources and the handler that opens one.
 * @returns The list.
 */
export function SourceList({ sources, onOpen }: SourceListProps) {
  return (
    <ul className="flex flex-col">
      {sources.map((source) => (
        <li
          key={source.key}
          className="flex gap-3 border-t border-border py-3 text-sm first:border-t-0 first:pt-0"
        >
          <span
            aria-hidden="true"
            className="inline-flex h-4 min-w-4 items-center justify-center rounded-sm border border-border bg-background px-1 text-xs font-medium text-text-muted"
          >
            {source.number ?? "–"}
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <button
              type="button"
              aria-label={
                source.number === undefined
                  ? source.title
                  : `Source ${String(source.number)}: ${source.title}`
              }
              className={cn(
                "self-start text-left font-medium text-text underline-offset-2 hover:underline",
                FOCUS_RING_CLASSES,
              )}
              onClick={(event) => {
                onOpen(source.key, event.currentTarget);
              }}
            >
              {source.title}
            </button>
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-text-muted">
                {source.documentId} · {source.version}
              </span>
              <StatusBadge presentation={source.validity} />
            </span>
            <span className="flex flex-wrap gap-2 text-xs text-text-muted">
              <span>{source.period}</span>
              {source.number === undefined ? <span>Not cited</span> : null}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
