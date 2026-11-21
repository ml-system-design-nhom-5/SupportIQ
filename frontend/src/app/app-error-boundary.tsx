/**
 * The last error boundary, around the providers and the router (TS-16 allows this class). The
 * route error boundaries catch the errors of each screen first.
 */
import { TriangleAlert } from "lucide-react";
import { Component, type ReactNode } from "react";

import { PageColumn, StateMessage } from "@/design-system";

/** Props of {@link AppErrorBoundary}. */
export type AppErrorBoundaryProps = {
  readonly children: ReactNode;
};

/** Whether a descendant threw. */
type AppErrorBoundaryState = {
  readonly hasError: boolean;
};

/** Shows a plain-language message when the app cannot render at all (UI-25). */
export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  override state: AppErrorBoundaryState = { hasError: false };

  /**
   * Switch to the error state.
   *
   * @returns The new state.
   */
  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true };
  }

  /**
   * Render the app, or the error state.
   *
   * @returns The children, or the message.
   */
  override render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <PageColumn area="shop">
        <StateMessage
          icon={TriangleAlert}
          headingLevel={1}
          title="SupportIQ could not start"
          description="Reload the page. If the problem stays, ask the team that runs this demo."
        />
      </PageColumn>
    );
  }
}
