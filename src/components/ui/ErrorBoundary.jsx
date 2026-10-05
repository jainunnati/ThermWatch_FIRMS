import React from 'react';

/**
 * Contains a crash to one region of the UI so the rest of ThermWatch keeps
 * working (e.g. a Google Maps failure must not blank alerts or investigation).
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error(`[ThermWatch] ${this.props.name || 'Component'} failed:`, error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className={this.props.fullscreen ? 'crash crash--full' : 'map-fallback'} role="alert">
        <div className="map-fallback__card">
          <p className="map-fallback__title">{this.props.title || 'This part of ThermWatch stopped working'}</p>
          <p className="map-fallback__body">{String(this.state.error?.message || this.state.error)}</p>
          <button type="button" className="btn btn--sm crash__btn" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      </div>
    );
  }
}
