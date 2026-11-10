import Lottie from 'lottie-react';

/**
 * Small pulsing-dot animation (inline Lottie JSON, no network fetch) used as
 * the loading state for data views and long-running actions.
 */
const loaderAnimation = {
  v: '5.7.4',
  fr: 30,
  ip: 0,
  op: 60,
  w: 120,
  h: 120,
  nm: 'loader',
  ddd: 0,
  assets: [],
  layers: [
    {
      ddd: 0,
      ind: 1,
      ty: 4,
      nm: 'dot',
      sr: 1,
      ks: {
        o: {
          a: 1,
          k: [
            { i: { x: [0.42], y: [1] }, o: { x: [0.58], y: [0] }, t: 0, s: [30] },
            { i: { x: [0.42], y: [1] }, o: { x: [0.58], y: [0] }, t: 30, s: [100] },
            { t: 60, s: [30] },
          ],
        },
        r: { a: 0, k: 0 },
        p: { a: 0, k: [60, 60, 0] },
        a: { a: 0, k: [0, 0, 0] },
        s: {
          a: 1,
          k: [
            { i: { x: [0.42, 0.42, 0.42], y: [1, 1, 1] }, o: { x: [0.58, 0.58, 0.58], y: [0, 0, 0] }, t: 0, s: [60, 60, 100] },
            { i: { x: [0.42, 0.42, 0.42], y: [1, 1, 1] }, o: { x: [0.58, 0.58, 0.58], y: [0, 0, 0] }, t: 30, s: [110, 110, 100] },
            { t: 60, s: [60, 60, 100] },
          ],
        },
      },
      shapes: [
        {
          ty: 'gr',
          it: [
            { ty: 'el', p: { a: 0, k: [0, 0] }, s: { a: 0, k: [72, 72] } },
            { ty: 'fl', c: { a: 0, k: [0.31, 0.56, 0.97, 1] }, o: { a: 0, k: 100 }, r: 1 },
            {
              ty: 'tr',
              p: { a: 0, k: [0, 0] },
              a: { a: 0, k: [0, 0] },
              s: { a: 0, k: [100, 100] },
              r: { a: 0, k: 0 },
              o: { a: 0, k: 100 },
            },
          ],
        },
      ],
      ip: 0,
      op: 60,
      st: 0,
      bm: 0,
    },
  ],
};

export default function LottieLoader({ label = 'Loading…' }: { label?: string }) {
  return (
    <span className="lottie-loader" role="status" aria-label={label}>
      <Lottie animationData={loaderAnimation} loop aria-label={label} style={{ width: 64, height: 64 }} />
      <span className="lottie-loader-label">{label}</span>
    </span>
  );
}
