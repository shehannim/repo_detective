import React from 'react';

export default function PresetCards({ onSelect }) {
  const presets = [
    {
      step: 1,
      title: 'Starlette ASGI',
      desc: 'Inspect routing mechanisms, ASGI dispatchers, and HTTP request lifetimes.',
      repo: 'https://github.com/encode/starlette',
      q: 'Where does URL path routing and matching occur?',
    },
    {
      step: 2,
      title: 'FastAPI Core',
      desc: 'Trace OpenAPI generation, APIRouter extensions, and Pydantic validation chains.',
      repo: 'https://github.com/tiangolo/fastapi',
      q: 'Where is the OpenAPI schema generation logic implemented?',
    },
    {
      step: 3,
      title: 'Flask Framework',
      desc: 'Explore sans-I/O app scaffolds, request context stacks, and Jinja bindings.',
      repo: 'https://github.com/pallets/flask',
      q: 'Where is the main Flask application object defined?',
    },
  ];

  return (
    <div>
      <div className="section-title">
        <div className="section-tag">A Step-by-Step Approach</div>
        <div className="section-heading">Inspect, without the hassle</div>
      </div>

      <div className="demo-cards-row">
        {presets.map((p) => (
          <div
            key={p.step}
            className="preset-card"
            onClick={() => onSelect(p.repo, p.q)}
          >
            <div className="step-number">{p.step}</div>
            <div className="preset-content">
              <div className="preset-title">{p.title}</div>
              <div className="preset-desc">{p.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
