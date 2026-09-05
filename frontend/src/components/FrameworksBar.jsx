import React from 'react';

export default function FrameworksBar({ onSelect }) {
  const frameworks = [
    { name: 'Starlette', repo: 'https://github.com/encode/starlette', q: 'Where does URL path routing and matching occur?' },
    { name: 'FastAPI', repo: 'https://github.com/tiangolo/fastapi', q: 'Where is the OpenAPI schema generation logic implemented?' },
    { name: 'Flask', repo: 'https://github.com/pallets/flask', q: 'Where is the main Flask application object defined?' },
    { name: 'Pydantic', repo: 'https://github.com/pydantic/pydantic', q: 'Where are custom regex pattern schemas validated?' },
    { name: 'HTTPX', repo: 'https://github.com/encode/httpx', q: 'How are async connection pools managed?' },
  ];

  return (
    <section className="frameworks-bar">
      <div className="frameworks-title">POPULAR OPEN SOURCE CODEBASES ANALYZED</div>
      <div className="framework-tags">
        {frameworks.map((fw) => (
          <span
            key={fw.name}
            className="fw-item"
            onClick={() => onSelect(fw.repo, fw.q)}
          >
            {fw.name}
          </span>
        ))}
      </div>
    </section>
  );
}
