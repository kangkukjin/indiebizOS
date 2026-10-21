export type EmbeddedState = {
  id: string; url?: string; pending: boolean; state: string; controlled: boolean;
  busy?: boolean; needsUser?: boolean; popup?: boolean;
};

// Track only tabs created by the agent, never the user's existing tabs.
export class EmbeddedTabLifecycle {
  private opened = new Set<string>();
  private closeWhenDone = false;
  private attention = new Set<string>();
  private focusedAuth?: string;

  retain() {
    // Typing an OTP is part of the handoff, not a request to keep the panel open.
    if (!this.attention.size) this.closeWhenDone = false;
  }

  sync(rows: EmbeddedState[], panelOpen: boolean) {
    const present = new Set(rows.map(r => r.id));
    const removed = [...this.opened].filter(id => !present.has(id));
    const added = rows.filter(r => r.pending && r.url && !this.opened.has(r.id));
    const attention = rows.filter(r => r.controlled && r.needsUser && !r.popup);
    const focusId = attention.find(r => !this.attention.has(r.id))?.id
      || (this.focusedAuth && !attention.some(r => r.id === this.focusedAuth) ? attention[0]?.id : undefined);
    if (focusId) this.focusedAuth = focusId;
    else if (!attention.length) this.focusedAuth = undefined;
    const show = !!focusId;
    this.attention = new Set(attention.map(r => r.id));
    if (show && !panelOpen) this.closeWhenDone = true;
    for (const r of added) this.opened.add(r.id);
    for (const id of removed) this.opened.delete(id);
    // Only authentication opens the panel. Background work never delays its exit.
    const close = this.closeWhenDone && !attention.length;
    if (close) this.closeWhenDone = false;
    return { added, removed, close, show, focusId };
  }
}
