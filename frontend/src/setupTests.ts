// Extended DOM matchers (toBeInTheDocument, toHaveTextContent, ...).
import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// Shared CI runners can be slow enough to exceed the 1s default of the
// findBy* async queries. Allow more wall-clock time without weakening any
// assertion — every wait still requires the same element to appear.
configure({ asyncUtilTimeout: 5000 });

// jsdom has no canvas implementation. lottie-web grabs a 2D context from an
// HTMLCanvasElement at module-load time (before any test body runs), so without
// this stub every suite that transitively imports `lottie-react` crashes during
// collection with "Cannot set properties of null (setting 'fillStyle')".
// Returning a minimal context keeps lottie itself under test instead of mocking
// the whole `lottie-react` module away.
const canvasContextStub = {
  fillStyle: '',
  strokeStyle: '',
  lineWidth: 1,
  globalAlpha: 1,
  globalCompositeOperation: 'source-over',
  font: '10px sans-serif',
  textAlign: 'start',
  textBaseline: 'alphabetic',
  save() {},
  restore() {},
  beginPath() {},
  closePath() {},
  moveTo() {},
  lineTo() {},
  rect() {},
  arc() {},
  fill() {},
  stroke() {},
  clip() {},
  fillRect() {},
  strokeRect() {},
  clearRect() {},
  fillText() {},
  strokeText() {},
  measureText() {
    return { width: 0 };
  },
  createLinearGradient() {
    return { addColorStop() {} };
  },
  createRadialGradient() {
    return { addColorStop() {} };
  },
  drawImage() {},
  translate() {},
  scale() {},
  rotate() {},
  transform() {},
  setTransform() {},
  resetTransform() {},
  setLineDash() {},
  getLineDash() {
    return [];
  },
  quadraticCurveTo() {},
  bezierCurveTo() {},
  ellipse() {},
  arcTo() {},
  isPointInPath() {
    return false;
  },
} as unknown as CanvasRenderingContext2D;

HTMLCanvasElement.prototype.getContext = function getContext() {
  return canvasContextStub;
} as unknown as typeof HTMLCanvasElement.prototype.getContext;

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Lottie (lottie-web) drives its timeline with requestAnimationFrame, which
// jsdom only provides in visual mode — shim both for the test environment.
if (typeof globalThis.requestAnimationFrame !== 'function') {
  globalThis.requestAnimationFrame = ((callback: FrameRequestCallback) =>
    setTimeout(() => callback(performance.now()), 16)) as unknown as typeof requestAnimationFrame;
}
if (typeof globalThis.cancelAnimationFrame !== 'function') {
  globalThis.cancelAnimationFrame = ((handle: number) =>
    clearTimeout(handle)) as typeof cancelAnimationFrame;
}
