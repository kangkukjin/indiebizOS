/** Exercises the real messenger card renderer with fixture IBL responses in browser tests. */
import { createRoot } from 'react-dom/client';
import { GenericInstrument, type AppInstrument } from '../components/GenericInstrument';

const fixture = (window as unknown as { messengerFixture?: AppInstrument }).messengerFixture;
if (fixture) {
  const root = document.createElement('div');
  document.body.append(root);
  createRoot(root).render(<GenericInstrument instrument={fixture} />);
}
