import { Boxes, Cpu, FileCode2, Pause, Play, RefreshCw } from 'lucide-react'

import { useCairnStore } from '../store'

export function Topbar() {
  const project = useCairnStore((state) => state.project)
  const workers = useCairnStore((state) => state.workers)
  const refresh = useCairnStore((state) => state.refresh)
  const toggleProject = useCairnStore((state) => state.toggleProject)
  const activeWorkers = workers.filter((worker) => worker.status === 'busy').length
  const isRunning = project?.status === 'running'
  const binaryName = project?.name.includes('CrackMe') ? 'license-checker.exe' : 'No binary attached'

  return (
    <header className="topbar">
      <div className="brand" aria-label="Cairn home">
        <span className="brand-mark"><Boxes size={15} /></span>
        <strong>Cairn</strong>
      </div>

      <div className="project-context">
        <div className="project-breadcrumb">
          <strong>{project?.name ?? 'No project'}</strong>
          <span>/</span>
          <FileCode2 size={13} />
          <code>{binaryName}</code>
        </div>
        <p>{project?.goal}</p>
      </div>

      <div className="runtime-status">
        <span className={`project-state state-${project?.status}`}>
          <i /> {project?.status ?? 'offline'}
        </span>
        <span className="worker-count" title="Active workers">
          <Cpu size={13} /> {activeWorkers}/{workers.length}
        </span>
        <button className="toolbar-button" onClick={() => void refresh()} title="Refresh snapshot">
          <RefreshCw size={14} />
        </button>
        <button className="toolbar-button primary-control" onClick={() => void toggleProject()}>
          {isRunning ? <Pause size={13} /> : <Play size={13} />}
          {isRunning ? 'Pause' : 'Resume'}
        </button>
      </div>
    </header>
  )
}
