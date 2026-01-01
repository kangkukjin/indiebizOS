/**
 * 앱 전역 상태 관리 (Zustand)
 */

import { create } from 'zustand';
import type { Project, Switch, Agent, AppView } from '../types';
import { api } from '../lib/api';

interface AppState {
  // 뷰 상태
  currentView: AppView;
  setCurrentView: (view: AppView) => void;

  // 프로젝트
  projects: Project[];
  currentProject: Project | null;
  loadProjects: () => Promise<void>;
  setCurrentProject: (project: Project | null) => void;

  // 스위치
  switches: Switch[];
  loadSwitches: () => Promise<void>;

  // 에이전트
  agents: Agent[];
  currentAgent: Agent | null;
  loadAgents: (projectId: string) => Promise<void>;
  setCurrentAgent: (agent: Agent | null) => void;

  // 연결 상태
  isConnected: boolean;
  setIsConnected: (connected: boolean) => void;

  // 로딩 상태
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;

  // 에러
  error: string | null;
  setError: (error: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // 뷰 상태
  currentView: 'launcher',
  setCurrentView: (view) => set({ currentView: view }),

  // 프로젝트
  projects: [],
  currentProject: null,
  loadProjects: async () => {
    try {
      set({ isLoading: true, error: null });
      const projects = await api.getProjects();
      set({ projects, isLoading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load projects',
        isLoading: false
      });
    }
  },
  setCurrentProject: (project) => set({ currentProject: project }),

  // 스위치
  switches: [],
  loadSwitches: async () => {
    try {
      const switches = await api.getSwitches();
      set({ switches });
    } catch (error) {
      console.error('Failed to load switches:', error);
    }
  },

  // 에이전트
  agents: [],
  currentAgent: null,
  loadAgents: async (projectId: string) => {
    try {
      const agents = await api.getProjectAgents(projectId);
      set({ agents });
    } catch (error) {
      console.error('Failed to load agents:', error);
    }
  },
  setCurrentAgent: (agent) => set({ currentAgent: agent }),

  // 연결 상태
  isConnected: false,
  setIsConnected: (connected) => set({ isConnected: connected }),

  // 로딩 상태
  isLoading: false,
  setIsLoading: (loading) => set({ isLoading: loading }),

  // 에러
  error: null,
  setError: (error) => set({ error }),
}));
