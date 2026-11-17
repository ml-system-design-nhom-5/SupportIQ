/**
 * A marker of a KB citation in a draft (UI-20): the number of its source in the `ai` tone, because
 * the draft is AI output (UI-13). Hovering or focusing it shows the document title, the version,
 * the validity with the effective dates, and the snippet; activating it opens the document version.
 */
import { FileText } from "lucide-react";

import { CitationHint } from "@/design-system/components/citation-hint";
import { StatusBadge } from "@/design-system/components/status-badge";
import type { StatusPresentation } from "@/design-system/components/status-presentations";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** The marker classes; the source list numbers its sources with the same look. */
const MARKER_CLASSES =
  "mx-1 inline-flex h-4 min-w-4 items-center justify-center rounded-sm border border-ai/35 bg-ai-subtle px-1 align-text-top text-xs font-medium text-ai";

/** What the hint knows about the source of the citation. */
export type CitationSource = {
  /** The title of the document version, or its ID when the analysis did not return it. */
  readonly title: string;
  readonly documentId: string;
  readonly version: string;
  /** The validity, absent when the analysis did not return the version. */
  readonly validity?: StatusPresentation;
  /** The effective period in words, absent with the validity. */
  readonly period?: string;
};

/** Props of {@link CitationMarker}. */
export type CitationMarkerProps = {
  /** The number of the source in the Sources panel. */
  readonly number: number;
  readonly source: CitationSource;
  /** The passage of the version that supports the segment, shown as plain text (SEC-22). */
  readonly snippet: string;
  /** Opens the document version; receives the marker, which the focus returns to. */
  readonly onActivate: (marker: HTMLElement) => void;
};

/**
 * Render the marker with its hint.
 *
 * @param props - The number, the source, the snippet, and the activation handler.
 * @returns The marker.
 */
export function CitationMarker({ number, source, snippet, onActivate }: CitationMarkerProps) {
  return (
    <CitationHint
      label={`Source ${String(number)}: ${source.title}`}
      markerClassName={cn(MARKER_CLASSES, FOCUS_RING_CLASSES)}
      marker={number}
      activationHint="Activate the marker to read the full version"
      onActivate={onActivate}
    >
      <div className="flex flex-col gap-2 p-3">
        <p className="flex items-center gap-2 font-semibold">
          <Icon icon={FileText} />
          {source.title}
        </p>
        <p className="font-mono text-xs text-text-muted">
          {source.documentId} · {source.version}
        </p>
        {source.validity === undefined ? null : (
          <p className="flex flex-wrap items-center gap-2">
            <StatusBadge presentation={source.validity} />
            <span className="text-xs text-text-muted">{source.period}</span>
          </p>
        )}
        <p className="wrap-break-word whitespace-pre-wrap">“{snippet}”</p>
      </div>
    </CitationHint>
  );
}
