/**
 * Fake `EventSource`s for tests and stories. Prism does not mock a stream (ADR-0022, statement
 * 9), so a test opens the suggestion progress stream here: it sends the events, and ends the stream
 * the way the browser reports it.
 */
import type { SuggestionEventSource } from "@/features/console-tickets";

/** The `readyState` values of `EventSource` (HTML). */
const readyStates = { connecting: 0, open: 1, closed: 2 } as const;

/** One stream that the app opened. */
export type FakeEventSource = SuggestionEventSource & {
  /** The absolute URL of the stream. */
  readonly url: string;
  /** Whether the app, or the end of the stream, closed it. */
  readonly isClosed: boolean;
  /** Sends one `suggestion` event with this data, as `backend` does. */
  readonly emit: (data: string) => void;
  /** Ends the stream as one that the browser connects again, such as at its maximum length. */
  readonly endAndReconnect: () => void;
  /** Ends the stream as one that the browser does not connect again: a `204` or a refusal. */
  readonly endForGood: () => void;
};

/** The streams of a test. */
export type FakeEventSources = {
  readonly open: (url: string) => SuggestionEventSource;
  /** Every stream that the app opened, in order. */
  readonly opened: readonly FakeEventSource[];
};

/**
 * Create the streams of a test, which send nothing until the test makes them.
 *
 * @returns The opener and the streams that it opened.
 */
export function createFakeEventSources(): FakeEventSources {
  const opened: FakeEventSource[] = [];
  return {
    open: (url) => {
      const source = createFakeEventSource(url);
      opened.push(source);
      return source;
    },
    opened,
  };
}

/**
 * Create one stream.
 *
 * @param url - The absolute URL of the stream.
 * @returns The stream, open.
 */
function createFakeEventSource(url: string): FakeEventSource {
  const listeners = createListeners();
  let readyState: number = readyStates.open;
  const end = (nextState: number) => {
    // A real `EventSource` sends nothing after `close()`.
    if (readyState !== readyStates.closed) {
      readyState = nextState;
      listeners.dispatch("error", new MessageEvent("error"));
    }
  };
  return {
    url,
    get readyState() {
      return readyState;
    },
    get isClosed() {
      return readyState === readyStates.closed;
    },
    addEventListener: listeners.add,
    close: () => {
      readyState = readyStates.closed;
    },
    emit: (data) => {
      if (readyState !== readyStates.closed) {
        listeners.dispatch("suggestion", new MessageEvent("suggestion", { data }));
      }
    },
    endAndReconnect: () => {
      end(readyStates.connecting);
    },
    endForGood: () => {
      end(readyStates.closed);
    },
  };
}

/**
 * Keep the listeners of one stream.
 *
 * @returns Adds a listener of one event type, and calls the listeners of one event type.
 */
function createListeners() {
  const listeners = new Map<string, ((event: MessageEvent) => void)[]>();
  return {
    add: (type: string, listener: (event: MessageEvent) => void) => {
      listeners.set(type, [...(listeners.get(type) ?? []), listener]);
    },
    dispatch: (type: string, event: MessageEvent) => {
      for (const listener of listeners.get(type) ?? []) {
        listener(event);
      }
    },
  };
}
