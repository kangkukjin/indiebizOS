import { createHash } from 'node:crypto';
import { fault } from './embedded-browser-tabs.js';

export function secureOrigin(url) {
  try { const u = new URL(url); return u.protocol === 'https:' && !u.username && !u.password ? u.origin : null; }
  catch { return null; }
}

export class EmbeddedAuth {
  constructor(tabs, vault, instance) {
    this.tabs = tabs; this.vault = vault; this.instance = instance; this.secrets = new Set();
  }
  accounts(origin) {
    if (!secureOrigin(origin)) return [];
    return this.vault.listAll().filter(e => secureOrigin(e.origin) === origin).map(e => ({
      account_ref: createHash('sha256').update(`${this.instance}\0${origin}\0${e.username}`).digest('hex').slice(0, 24),
      label: `${e.username.slice(0, 2)}***`, username: e.username,
    }));
  }
  redact(value) {
    if (typeof value === 'string') { for (const s of this.secrets) if (s) value = value.split(s).join('[protected]'); return value; }
    if (Array.isArray(value)) return value.map(v => this.redact(v));
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, this.redact(v)]));
    return value;
  }
  async run(r, args, deadline, manualUsername) {
    const mode = args.mode || 'status';
    if (!['status', 'login', 'resume', 'cancel'].includes(mode)) throw fault('UNSUPPORTED_OPERATION');
    if (mode === 'cancel') {
      r.authWaiting = false; if (this.tabs.authOwner === r.owner) this.tabs.authOwner = null;
      return { state: 'cancelled' };
    }
    const probe = await this.tabs.page(r, 'auth_probe');
    const accounts = this.accounts(probe.origin);
    const publicAccounts = accounts.map(({ account_ref, label }) => ({ account_ref, label }));
    if (mode !== 'login') {
      let state = probe.state;
      if (mode === 'resume' && state === 'unknown') {
        r.authWaiting = false; if (this.tabs.authOwner === r.owner) this.tabs.authOwner = null;
        if (args.ref) {
          const result = await this.tabs.page(r, 'wait', { ref: args.ref });
          if (result.matched) state = 'authenticated';
        }
      }
      return { ...probe, state, accounts: publicAccounts,
        verification: state === 'authenticated' ? 'caller_selected_destination_element' : 'inspect_destination' };
    }
    if (probe.user_action_required) return { state: 'user_action_required', reason: 'additional_authentication' };
    const chosen = manualUsername != null ? accounts.find(a => a.username === manualUsername) :
      args.account_ref ? accounts.find(a => a.account_ref === args.account_ref) : accounts.length === 1 ? accounts[0] : null;
    if (!chosen) return { state: accounts.length ? 'account_selection_required' : 'user_action_required', accounts: publicAccounts };
    if (!probe.password_ref && !probe.username_ref) throw fault('LOGIN_FIELDS_REQUIRED');
    if (!secureOrigin(probe.origin)) throw fault('AUTH_REQUIRES_HTTPS');
    if (this.tabs.authOwner && this.tabs.authOwner !== r.owner) throw fault('AUTH_SESSION_BUSY');
    this.tabs.check(r, deadline);
    const credential = this.vault.getCredential(probe.origin, chosen.username);
    if (!credential) throw fault('CREDENTIAL_UNAVAILABLE');
    this.secrets.add(credential.password);
    const attempt = `${probe.document_id}:${chosen.account_ref}:${!!probe.password_ref}`;
    if (args.submit_ref && r.authAttempt === attempt) return { state: 'user_action_required', reason: 'verify_previous_login' };
    if (args.submit_ref) r.authAttempt = attempt;
    this.tabs.authOwner = r.owner; r.authWaiting = !!args.submit_ref;
    // Suppress the legacy warehouse credential capture before any page input event.
    r.sensitive = true;
    try {
      return await this.tabs.page(r, 'auth_fill', { origin: probe.origin, document_id: probe.document_id,
        username_ref: args.username_ref || probe.username_ref, password_ref: args.password_ref || probe.password_ref,
        submit_ref: args.submit_ref, username: credential.username, password: credential.password });
    } finally {
      if (!args.submit_ref && this.tabs.authOwner === r.owner) this.tabs.authOwner = null;
    }
  }
}
