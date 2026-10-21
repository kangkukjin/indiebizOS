export type EmbeddedState = {
  id: string; url?: string; pending: boolean; state: string; controlled: boolean;
  busy?: boolean; needsUser?: boolean;
};

// Track only tabs created by the agent, never the user's existing tabs.
export class EmbeddedTabLifecycle {
  private opened = new Set<string>();
  private closeWhenDone = false;
  private attention = new Set<string>();

  retain() { this.closeWhenDone = false; }

  sync(rows: EmbeddedState[], panelOpen: boolean) {
    const present = new Set(rows.map(r => r.id));
    const removed = [...this.opened].filter(id => !present.has(id));
    const added = rows.filter(r => r.pending && r.url && !this.opened.has(r.id));
    const attention = rows.filter(r => r.controlled && r.needsUser);
    const show = added.length > 0 || attention.some(r => !this.attention.has(r.id));
    this.attention = new Set(attention.map(r => r.id));
    if (show && !panelOpen) this.closeWhenDone = true;
    for (const r of added) this.opened.add(r.id);
    for (const id of removed) this.opened.delete(id);
    if (rows.some(r => this.opened.has(r.id) &&
        r.state === '사용자 조작 중')) this.retain();
    // Idle means the current call finished, even if the model forgets to call close.
    // Keep the guest mounted so subsequent calls use the same document and refs.
    const busy = rows.some(r => r.controlled && (r.busy ?? true));
    const close = this.closeWhenDone && !busy && !attention.length;
    if (close) this.closeWhenDone = false;
    return { added, removed, close, show };
  }
}
