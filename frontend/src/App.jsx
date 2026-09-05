import React, { useState, useRef, useEffect } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import FrameworksBar from './components/FrameworksBar';
import PresetCards from './components/PresetCards';
import QueryForm from './components/QueryForm';
import ReasoningPanel from './components/ReasoningPanel';
import ReportPanel from './components/ReportPanel';

export default function App() {
  const [repoUrl, setRepoUrl] = useState('https://github.com/encode/starlette');
  const [question, setQuestion] = useState('Where does URL path routing and matching occur?');
  const [steps, setSteps] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [stepCount, setStepCount] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  const queryFormRef = useRef(null);
  const timerRef = useRef(null);

  const handleSelectPreset = (repo, q) => {
    setRepoUrl(repo);
    setQuestion(q);
    if (queryFormRef.current) {
      queryFormRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!repoUrl.trim() || !question.trim()) return;

    setLoading(true);
    setError(null);
    setSteps([]);
    setResult(null);
    setStepCount(0);
    setElapsed(0);

    const startTime = Date.now();
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setElapsed((Date.now() - startTime) / 1000);
    }, 100);

    const apiBase = import.meta.env.VITE_API_URL || '';

    try {
      const response = await fetch(`${apiBase}/ask/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: repoUrl.trim(),
          question: question.trim(),
          top_n: 3,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const event = JSON.parse(line);

            if (event.type === 'step') {
              setSteps((prev) => [...prev, event]);
              setStepCount((prev) => prev + 1);
            } else if (event.type === 'result') {
              if (timerRef.current) clearInterval(timerRef.current);
              setResult(event.data);
              setElapsed(event.data.elapsed_seconds || 0);
            } else if (event.type === 'error') {
              if (timerRef.current) clearInterval(timerRef.current);
              setError(event.message);
            }
          } catch (jsonErr) {
            console.error('Failed to parse NDJSON line:', line, jsonErr);
          }
        }
      }
    } catch (err) {
      if (timerRef.current) clearInterval(timerRef.current);
      setError(err.message);
    } finally {
      setLoading(false);
      if (timerRef.current) clearInterval(timerRef.current);
    }
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  return (
    <div>
      <div className="glow-orb-top"></div>
      <div className="glow-orb-mid"></div>

      <Navbar />

      <main className="container">
        <Hero onExploreClick={() => queryFormRef.current?.scrollIntoView({ behavior: 'smooth' })} />
        <FrameworksBar onSelect={handleSelectPreset} />
        <PresetCards onSelect={handleSelectPreset} />
        <QueryForm
          formRef={queryFormRef}
          repoUrl={repoUrl}
          setRepoUrl={setRepoUrl}
          question={question}
          setQuestion={setQuestion}
          onSubmit={handleSubmit}
          loading={loading}
        />

        <div className="panels-row">
          <ReasoningPanel
            steps={steps}
            loading={loading}
            stepCount={stepCount}
            elapsed={elapsed}
          />
          <ReportPanel
            result={result}
            loading={loading}
            error={error}
          />
        </div>
      </main>
    </div>
  );
}
