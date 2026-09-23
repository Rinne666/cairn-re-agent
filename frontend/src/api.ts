import type { EventItem, GraphSnapshot, Intent, Project, Worker } from './types'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'
export const WS = import.meta.env.VITE_WS_URL ?? API.replace(/^http/, 'ws')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(body.detail ?? 'Request failed')
  }
  return response.json() as Promise<T>
}

export const api = {
  listProjects: () => request<Project[]>('/projects'),
  createDemo: () => request<Project>('/projects/demo', { method: 'POST' }),
  changeProjectState: (projectId: string, action: 'start' | 'pause') =>
    request<Project>(`/projects/${projectId}/${action}`, { method: 'POST' }),
  getGraph: (projectId: string) => request<GraphSnapshot>(`/projects/${projectId}/graph`),
  getIntents: (projectId: string) => request<Intent[]>(`/projects/${projectId}/intents`),
  getWorkers: (projectId: string) => request<Worker[]>(`/projects/${projectId}/workers`),
  getEvents: (projectId: string) => request<EventItem[]>(`/projects/${projectId}/events?limit=40`),
  runWorker: (projectId: string, workerId: string) =>
    request(`/projects/${projectId}/workers/${workerId}/run-once`, { method: 'POST' }),
}
