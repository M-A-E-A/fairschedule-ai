import { render, screen } from '@testing-library/react';
import LottieLoader from './LottieLoader';

describe('LottieLoader', () => {
  it('renders the Lottie animation with an accessible label', () => {
    render(<LottieLoader label="Loading timetable…" />);
    const status = screen.getByRole('status', { name: 'Loading timetable…' });
    expect(status).toBeInTheDocument();
    expect(status).toHaveTextContent('Loading timetable…');
    // lottie-react renders its SVG player inside the status element.
    expect(status.querySelector('svg')).not.toBeNull();
  });

  it('falls back to a default label', () => {
    render(<LottieLoader />);
    expect(screen.getByRole('status', { name: 'Loading…' })).toBeInTheDocument();
  });
});
