import { create } from 'zustand'

import { api } from './api'
import type { EventItem, GraphEdgeData, GraphNodeData, GraphType, Intent, Project, Worker, WorkspaceSection } from './types'

interface CairnState {
  projects: Project[]
  project: Project | null
  nodes: GraphNodeData[]
  edges: GraphEdgeData[]
  intents: Intent[]
  workers: Worker[]
  events: EventItem[]
  view: GraphType
  section: WorkspaceSection
  selectedNodeId: string | null
  loading: boolean
  runningWorkerId: string | null
  error: string | null
  loadProjects: () => Promise<void>
  createDemo: () => Promise<void>
  selectProject: (project: Project) => Promise<void>
  refresh: () => Promise<void>
  runWorker: (workerId: string) => Promise<void>
  toggleProject: () => Promise<void>
  setView: (view: GraphType) => void
  setSection: (section: WorkspaceSection) => void
  selectNode: (id: string | null) => void
}

export const useCairnStore = create<CairnState>((set, get) => ({
  projects: [],
  project: null,
  nodes: [],
  edges: [],
  intents: [],
  workers: [],
  events: [],
  view: 'exploration',
  section: 'exploration',
  selectedNodeId: null,
  loading: false,
  runningWorkerId: null,
  error: null,

  loadProjects: async () => {
    if (get().loading) return
    set({ loading: true, error: null })
    try {
      const projects = await api.listProjects()
      set({ projects, loading: false })
      if (projects.length && !get().project) await get().selectProject(projects[0])
    } catch (error) {
      set({ loading: false, error: error instanceof Error ? error.message : 'Failed to load' })
    }
  },
  createDemo: async () => {
    set({ loading: true, error: null })
    try {
      const project = await api.createDemo()
      set((state) => ({ projects: [project, ...state.projects], loading: false }))
      await get().selectProject(project)
    } catch (error) {
      set({ loading: false, error: error instanceof Error ? error.message : 'Failed to create demo' })
    }
  },
  selectProject: async (project) => {
    set({ project, loading: true, selectedNodeId: null, error: null })
    await get().refresh()
  },
  refresh: async () => {
    const project = get().project
    if (!project) return
    try {
      const [graph, intents, workers, events] = await Promise.all([
        api.getGraph(project.id),
        api.getIntents(project.id),
        api.getWorkers(project.id),
        api.getEvents(project.id),
      ])
      set({ nodes: graph.nodes, edges: graph.edges, intents, workers, events, loading: false })
    } catch (error) {
      set({ loading: false, error: error instanceof Error ? error.message : 'Refresh failed' })
    }
  },
  runWorker: async (workerId) => {
    const project = get().project
    if (!project) return
    set({ runningWorkerId: workerId, error: null })
    try {
      await api.runWorker(project.id, workerId)
      await get().refresh()
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Worker failed' })
    } finally {
      set({ runningWorkerId: null })
    }
  },
  toggleProject: async () => {
    const project = get().project
    if (!project) return
    const action = project.status === 'running' ? 'pause' : 'start'
    try {
      const updated = await api.changeProjectState(project.id, action)
      set((state) => ({
        project: updated,
        projects: state.projects.map((item) => item.id === updated.id ? updated : item),
      }))
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'State change failed' })
    }
  },
  setView: (view) => set({ view, selectedNodeId: null }),
  setSection: (section) => {
    const view: GraphType = section === 'program' ? 'program' : section === 'exploration' ? 'exploration' : 'evidence'
    set({ section, view, selectedNodeId: null })
  },
  selectNode: (selectedNodeId) => set({ selectedNodeId }),
}))
