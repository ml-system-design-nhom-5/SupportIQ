/**
 * A Storybook decorator that gives a screen story its own fake backend, answered with contract
 * example files (TEST-11), so each state of a screen has a story (UI-23).
 */
import type { Decorator } from "@storybook/react-vite";
import { type ReactNode, useState } from "react";

import { AppProviders } from "@/app/composition-root";
import { createFakeBackend, type FakeBackend } from "@/test/fake-backend";
import { createTestDependencies } from "@/test/render-app";

/** Props of {@link FakeBackendProvider}. */
type FakeBackendProviderProps = {
  readonly configure: (backend: FakeBackend) => void;
  readonly children: ReactNode;
};

/**
 * Build a decorator whose fake backend answers as the story needs.
 *
 * @param configure - Registers the answers of the story.
 * @returns The decorator.
 */
export function withFakeBackend(configure: (backend: FakeBackend) => void): Decorator {
  return function FakeBackendDecorator(Story) {
    return (
      <FakeBackendProvider configure={configure}>
        <Story />
      </FakeBackendProvider>
    );
  };
}

/**
 * Provide the app's dependencies over a fake backend, created once per story render tree.
 *
 * @param props - The answers of the story and the story itself.
 * @returns The providers around the story.
 */
function FakeBackendProvider({ configure, children }: FakeBackendProviderProps) {
  const [dependencies] = useState(() => {
    const backend = createFakeBackend();
    configure(backend);
    return createTestDependencies(backend);
  });
  return <AppProviders dependencies={dependencies}>{children}</AppProviders>;
}
