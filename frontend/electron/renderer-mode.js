/** Renderer source is independent of the Python runtime (source checkout vs packaged app). */
export function usesDevServer(app, argv = process.argv) {
  return !app.isPackaged && !argv.includes('--preview');
}
