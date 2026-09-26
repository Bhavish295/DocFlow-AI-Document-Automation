from fastapi import APIRouter

from app.api.routes import (
    agent,
    analytics,
    anomalies,
    audit_logs,
    auth,
    classification,
    document_relationships,
    documents,
    duplicates,
    health,
    ingestion,
    investigations,
    processing_jobs,
    rag,
    reviews,
    sql,
    users,
    validations,
    vendors,
    workflows,
)


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(audit_logs.router, tags=["audit-logs"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(ingestion.router, tags=["ingestion"])
api_router.include_router(processing_jobs.router, tags=["processing-jobs"])
api_router.include_router(classification.router, tags=["classification"])
api_router.include_router(document_relationships.router, tags=["document-relationships"])
api_router.include_router(validations.router, tags=["validations"])
api_router.include_router(vendors.router, tags=["vendors"])
api_router.include_router(reviews.router, tags=["reviews"])
api_router.include_router(rag.router, tags=["rag"])
api_router.include_router(sql.router, tags=["sql"])
api_router.include_router(investigations.router, tags=["investigations"])
api_router.include_router(agent.router, tags=["agent"])
api_router.include_router(analytics.router, tags=["analytics"])
api_router.include_router(workflows.router, tags=["workflows"])
api_router.include_router(anomalies.router, tags=["anomalies"])
api_router.include_router(duplicates.router, tags=["duplicates"])
