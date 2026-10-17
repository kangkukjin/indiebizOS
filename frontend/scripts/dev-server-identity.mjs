import { realpathSync } from 'node:fs';

export const identityPath = '/__indiebiz_dev_server';

// A listening port alone does not identify this checkout's renderer.
export function devServerIdentityPlugin() {
  return {
    name: 'indiebiz-dev-server-identity',
    configureServer(server) {
      const identity = { app: 'indiebiz-os', root: realpathSync(server.config.root) };
      server.middlewares.use(identityPath, (_request, response) => {
        response.setHeader('Content-Type', 'application/json');
        response.setHeader('Cache-Control', 'no-store');
        response.end(JSON.stringify(identity));
      });
    },
  };
}
