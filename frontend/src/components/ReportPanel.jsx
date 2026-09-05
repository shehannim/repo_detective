import React, { useState, useRef } from 'react';
import { marked } from 'marked';
import hljs from 'highlight.js';

marked.setOptions({
  highlight: function (code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
    return hljs.highlight(code, { language }).value;
  },
});

export default function ReportPanel({ result, loading, error }) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const cardRef = useRef(null);

  const toggleFullscreen = () => {
    if (!cardRef.current) return;
    if (!document.fullscreenElement) {
      cardRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const renderContent = () => {
    if (error) {
      return <div style={{ color: '#f87171', fontWeight: 600 }}>Error: {error}</div>;
    }

    if (loading && !result) {
      return (
        <div style={{ color: 'var(--text-muted)' }}>
          Analyzing repository graph and invoking reasoning model...
        </div>
      );
    }

    if (!result) {
      return (
        <div style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>
          Submit a query above to inspect files and grounded reasoning.
        </div>
      );
    }

    // Prepare confidence badge
    let confLevel = 'Low';
    let confClass = 'conf-low';
    if (result.results && result.results.length > 0) {
      const maxScore = result.results[0].score;
      if (maxScore > 10.0) {
        confLevel = 'High Confidence';
        confClass = 'conf-high';
      } else if (maxScore > 2.0) {
        confLevel = 'Medium Confidence';
        confClass = 'conf-med';
      }
    }

    let parsedHtml = '';
    if (result.used_llm && result.llm_explanation) {
      let exp = result.llm_explanation;
      const cleanRepo = (result.repo_url || '').replace(/\.git$/, '');
      // Linkify backticked file paths into GitHub links
      exp = exp.replace(/\`([a-zA-Z0-9_\-\.\/]+)\`/g, (match, path) => {
        if (path.includes('/') || (path.includes('.') && !path.includes(' '))) {
          return `<a href="${cleanRepo}/blob/master/${path}" target="_blank" rel="noreferrer"><code>${path}</code></a>`;
        }
        return match;
      });
      parsedHtml = marked.parse(exp);
    }

    return (
      <div>
        <div className="result-meta-row">
          <span>Target: <strong>{result.repo_url}</strong></span>
          <span>Graph: <strong>{result.cached ? 'Cached hit' : 'Cloned'}</strong></span>
          <span>Latency: <strong>{result.elapsed_seconds}s</strong></span>
          <span className={`conf-pill ${confClass}`} style={{ marginLeft: 'auto' }}>
            {confLevel}
          </span>
        </div>

        {result.used_llm && result.llm_explanation ? (
          <div
            className="llm-markdown"
            dangerouslySetInnerHTML={{ __html: parsedHtml }}
          />
        ) : (
          <div>
            <h4 style={{ color: '#c084fc', marginBottom: 12 }}>Top Ranked Files:</h4>
            <ul>
              {(result.results || []).map((f, i) => (
                <li key={i} style={{ marginBottom: 8 }}>
                  <code>{f.file}</code> (Score: <strong>{f.score}</strong>)
                  <br />
                  <small style={{ color: 'var(--text-muted)' }}>{f.explanation}</small>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="output-card" ref={cardRef}>
      <div className="card-header">
        <div className="card-title">
          <span>Architectural Report</span>
        </div>
        <button
          onClick={toggleFullscreen}
          className="fullscreen-btn"
          title={isFullscreen ? 'Exit full screen' : 'View full screen'}
        >
          {isFullscreen ? '×' : '⛶'}
        </button>
      </div>
      <div className="card-body">{renderContent()}</div>
    </div>
  );
}
