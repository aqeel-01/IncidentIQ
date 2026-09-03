import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="state-panel state-panel--error" role="alert">
          <h2>Something broke in the UI</h2>
          <p>{this.state.error.message}</p>
          <button
            type="button"
            className="button"
            onClick={() => this.setState({ error: null })}
          >
            Dismiss
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
