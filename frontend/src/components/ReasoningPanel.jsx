import React, { useRef, useEffect } from 'react';

export default function ReasoningPanel({ steps, loading, stepCount, elapsed }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps]);

  return (
    <div className="output-card">
      <div className="card-header">
        <div className="card-title">
          <span>Reasoning Steps</span>
          {loading && <span className="purple-spinner"></span>}
        </div>
        {(stepCount > 0 || loading) && (
          <span className="badge-counter">
            {stepCount} steps • {elapsed.toFixed(1)}s
          </span>
        )}
      </div>
      <div className="card-body" ref={scrollRef}>
        {steps.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>
            Live reasoning steps will stream here in real-time...
          </div>
        ) : (
          steps.map((step, idx) => (
            <div key={idx} className="step-entry">
              <span className="step-clock">+{Number(step.ts).toFixed(3)}s</span>
              <span className="step-text">{step.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
