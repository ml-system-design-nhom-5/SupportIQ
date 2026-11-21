/**
 * A Storybook decorator that gives a screen story its own fake backend, answered with contract
 * example files (TEST-11), so each state of a screen has a story (UI-23).
 */
import type { Decorator } from "@storybook/react-vite";
import { type ReactNode, useState } from "react";

import { AppProviders } from "@/app/composition-root";
import { createFakeBackend, type FakeBackend } from "@/test/fake-backend";
import type { FakeEventSources } from "@/test/fake-event-source";
import { createTestDependencies } from "@/test/render-app";

/** Props of {@link FakeBackendProvider}. */
type FakeBackendProviderProps = {
  readonly configure: (backend: FakeBackend) => void;
  readonly eventSources: FakeEventSources | undefined;
  readonly children: ReactNode;
};

/**
 * Build a decorator whose fake backend answers as the story needs.
 *
 * @param configure - Registers the answers of the story.
 * @param eventSources - The streams that the story opens, for a story that ends one; streams that
 *   send nothing by default.
 * @returns The decorator.
 */
export function withFakeBackend(
  configure: (backend: FakeBackend) => void,
  eventSources?: FakeEventSources,
): Decorator {
  return function FakeBackendDecorator(Story) {
    return (
      <FakeBackendProvider configure={configure} eventSources={eventSources}>
        <Story />
      </FakeBackendProvider>
    );
  };
}

/**
 * Provide the app's dependencies over a fake backend, created once per story render tree.
 *
 * @param props - The answers of the story, its streams, and the story itself.
 * @returns The providers around the story.
 */
function FakeBackendProvider({ configure, eventSources, children }: FakeBackendProviderProps) {
  const [dependencies] = useState(() => {
    const backend = createFakeBackend();
    configure(backend);
    return createTestDependencies(backend, eventSources === undefined ? {} : { eventSources });
  });
  return <AppProviders dependencies={dependencies}>{children}</AppProviders>;
}
