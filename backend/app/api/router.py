from fastapi import APIRouter

from app.api.routes import artifacts, graph, intents, projects, realtime, workers

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(artifacts.router, tags=["artifacts"])
api_router.include_router(graph.router, tags=["graph"])
api_router.include_router(intents.router, tags=["intents"])
api_router.include_router(workers.router, tags=["workers"])
api_router.include_router(realtime.router, tags=["events"])
