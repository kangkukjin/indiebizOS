export type EmbeddedState = {
  id: string; url?: string; pending: boolean; state: string; controlled: boolean;
};

// Track only tabs created by the agent, never the user's existing tabs.
export class EmbeddedTabLifecycle {
  private opened = new Set<string>();
  private closeWhenDone = false;

  retain() { this.closeWhenDone = false; }

  sync(rows: EmbeddedState[], panelOpen: boolean) {
    const present = new Set(rows.map(r => r.id));
    const removed = [...this.opened].filter(id => !present.has(id));
    const added = rows.filter(r => r.pending && r.url && !this.opened.has(r.id));
    if (!this.opened.size && added.length) this.closeWhenDone = !panelOpen;
    for (const r of added) this.opened.add(r.id);
    for (const id of removed) this.opened.delete(id);
    if (rows.some(r => this.opened.has(r.id) &&
        (!r.controlled || r.state === '사용자 조작 중'))) this.retain();
    const close = this.closeWhenDone && !this.opened.size && removed.length > 0;
    if (close) this.closeWhenDone = false;
    return { added, removed, close };
  }
}
