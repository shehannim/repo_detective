import React from 'react';

export default function Navbar() {
  return (
    <nav className="nav">
      <div className="nav-brand">
        <div className="brand-icon">✦</div>
        <span>RepoDetective</span>
      </div>
      <div className="nav-status">
        <span className="status-dot"></span>
        <span>Intelligence Engine Active</span>
      </div>
    </nav>
  );
}
