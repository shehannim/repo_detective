import React from 'react';
import { LOGO_DATA } from '../logoData';

export default function Navbar() {
  return (
    <nav className="nav">
      <a
        href="/"
        className="nav-brand"
        title="Return to home page"
        aria-label="Repo Detective Home"
        style={{
          textDecoration: 'none',
          color: 'inherit',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '12px',
          cursor: 'pointer',
          transition: 'transform 0.2s ease, opacity 0.2s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'scale(1.02)';
          e.currentTarget.style.opacity = '0.9';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'scale(1)';
          e.currentTarget.style.opacity = '1';
        }}
      >
        <img
          src={LOGO_DATA}
          alt="Repo Detective Mascot"
          style={{
            width: '42px',
            height: '42px',
            objectFit: 'contain',
            display: 'block',
            filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.4))',
          }}
        />
        <span style={{ fontSize: '18px', fontWeight: 800, letterSpacing: '-0.4px' }}>
          Repo Detective
        </span>
      </a>
      <div className="nav-status">
        <span className="status-dot"></span>
        <span>Intelligence Engine Active</span>
      </div>
    </nav>
  );
}
