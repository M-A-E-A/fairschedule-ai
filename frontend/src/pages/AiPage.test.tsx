import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderApp, signedInAs, stubFetch } from '../testUtils';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AiPage', () => {
  it('asks the assistant and shows its answer', async () => {
    const fetchMock = stubFetch({
      '/auth/me': signedInAs('student'),
      '/ai/chat': (init?: RequestInit) => {
        const prompt = JSON.parse(String(init?.body)).prompt;
        return {
          answer: `You have CS101 on Monday at 09:00. (asked: ${prompt})`,
        };
      },
    });
    renderApp('/ai');

    fireEvent.change(await screen.findByLabelText('Message'), {
      target: { value: 'When is my next class?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(screen.getByText(/You have CS101 on Monday/)).toBeInTheDocument();
    });
    expect(screen.getByText('When is my next class?')).toBeInTheDocument();

    const chatCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes('/ai/chat') && String((init as RequestInit | undefined)?.method) === 'POST',
    );
    expect(JSON.parse(String(chatCall?.[1]?.body))).toEqual({
      prompt: 'When is my next class?',
    });
  });

  it('states that the assistant cannot mutate schedules', async () => {
    stubFetch({ '/auth/me': signedInAs('student') });
    renderApp('/ai');

    expect(
      await screen.findByText(/can never change the timetable/i),
    ).toBeInTheDocument();
  });
});
