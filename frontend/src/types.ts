export type GraphType = 'exploration' | 'program' | 'evidence'
export type WorkspaceSection = 'exploration' | 'program' | 'hypotheses' | 'evidence'

export interface Project {
  id: string
  name: string
  goal: string
  status: string
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface GraphNodeData {
  id: string
  project_id: string
  binary_id: string | null
  graph_type: GraphType
  kind: string
  label: string
  entity_key: string
  properties: Record<string, unknown>
  confidence: number
  status: string
  created_by: string
  created_at: string
}

export interface GraphEdgeData {
  id: string
  project_id: string
  source_node_id: string
  target_node_id: string
  kind: string
  properties: Record<string, unknown>
  created_by: string
  created_at: string
}

export interface GraphSnapshot {
  nodes: GraphNodeData[]
  edges: GraphEdgeData[]
}

export interface Intent {
  id: string
  project_id: string
  description: string
  status: string
  priority: number
  creator: string
  worker_id: string | null
  lease_until: string | null
  result_node_id: string | null
  created_at: string
}

export interface Worker {
  id: string
  project_id: string
  name: string
  driver: string
  model: string | null
  status: string
  last_seen_at: string
}

export interface EventItem {
  id: string
  project_id: string
  kind: string
  payload: Record<string, unknown>
  created_at: string
}
