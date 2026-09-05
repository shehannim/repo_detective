import React from 'react';

export default function Hero({ onExploreClick }) {
  return (
    <header className="hero">
      <h1 className="hero-title">
        <span className="gradient-text">Unlimited</span><br />
        Repo Intelligence
      </h1>
      <p className="hero-subtitle">
        Codebase structure and architectural reasoning you need.
        Instant NetworkX dependency graphs, cited files & real-time answers.
      </p>

      <div className="feature-pills">
        <div className="pill">
          <span className="pill-icon">✓</span>
          <span>Zero Hallucinations</span>
        </div>
        <div className="pill">
          <span className="pill-icon">✓</span>
          <span>NetworkX DiGraph</span>
        </div>
        <div className="pill">
          <span className="pill-icon">✓</span>
          <span>Sub-second graph cache</span>
        </div>
      </div>

      <div className="glow-btn-wrapper">
        <div className="glow-btn-backdrop"></div>
        <button onClick={onExploreClick} className="glow-btn">
          <span>Explore codebase</span>
          <span>→</span>
        </button>
      </div>
    </header>
  );
}
