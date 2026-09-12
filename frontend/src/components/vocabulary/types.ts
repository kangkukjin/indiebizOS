export const ROOT = 'desktop';
export const STORE = 'store';
export const CORE = 'required';
export const TRASH = 'trash';
export const SPECIAL = new Set([STORE, CORE, TRASH]);
export interface Placement { parent: string; x: number; y: number }
export interface VocabularyDesktop {
  folders: Record<string, Placement & { name: string }>;
  placements: Record<string, Placement>;
}
export interface DesktopEdit {
  op: 'move' | 'restore' | 'create_folder' | 'rename' | 'remove_folder' | 'arrange';
  item?: string; parent?: string; name?: string; x?: number; y?: number; columns?: number;
}
export interface Word { name: string; description: string; example?: string }
