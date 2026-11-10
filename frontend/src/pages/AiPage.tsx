import { FormEvent, useRef, useState } from 'react';
import { apiFetch } from '../api';
import LottieLoader from '../components/LottieLoader';

interface ChatTurn {
  question: string;
  answer: string;
}

export default function AiPage() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const question = prompt.trim();
    if (!question) {
      return;
    }
    setBusy(true);
    setError('');
    setPrompt('');
    try {
      const response = await apiFetch<{ answer: string }>('/ai/chat', {
        method: 'POST',
        body: JSON.stringify({ prompt: question }),
      });
      setTurns((previous) => [...previous, { question, answer: response.answer }]);
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : 'The assistant is unavailable');
      setPrompt(question);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="dashboard-header">
        <div>
          <h1>AI assistant</h1>
          <p className="hint">
            Read-only: answers are grounded in your institution’s data and can never change the timetable.
          </p>
        </div>
      </header>

      <section className="panel chat-panel">
        {turns.length === 0 && (
          <p className="empty-state">Ask about your schedule, rooms or constraints to get started.</p>
        )}
        {turns.map((turn, index) => (
          <div className="chat-turn" key={index}>
            <p className="chat-question">{turn.question}</p>
            <p className="chat-answer">{turn.answer}</p>
          </div>
        ))}
        {busy && <LottieLoader label="Thinking…" />}
        {error && <p className="error-notice" role="alert">{error}</p>}
        <div ref={bottomRef} />
      </section>

      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Ask the assistant…"
          aria-label="Message"
        />
        <button type="submit" disabled={busy}>
          Send
        </button>
      </form>
    </>
  );
}
