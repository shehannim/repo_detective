import React from 'react';

export default function QueryForm({ repoUrl, setRepoUrl, question, setQuestion, onSubmit, loading, formRef }) {
  return (
    <form ref={formRef} onSubmit={onSubmit} className="query-card" id="querySection">
      <div className="form-group">
        <label className="form-label" htmlFor="repoUrl">
          GitHub Repository URL
        </label>
        <input
          type="text"
          id="repoUrl"
          className="sleek-input"
          placeholder="https://github.com/encode/starlette"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          required
        />
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="question">
          What would you like to know about this codebase?
        </label>
        <input
          type="text"
          id="question"
          className="sleek-input"
          placeholder="e.g. Where does URL routing happen and what classes handle it?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          required
        />
      </div>

      <button type="submit" className="submit-btn" disabled={loading}>
        <span>{loading ? 'Analyzing Repository...' : 'Analyze Repository Structure'}</span>
        <span>✦</span>
      </button>
    </form>
  );
}
