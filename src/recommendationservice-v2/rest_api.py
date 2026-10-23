from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import time

from agent import run_ai_agent_recommendations, check_nosql_health, nosql_store
from metrics import tracker, CONTENT_TYPE_LATEST

app = FastAPI(
    title="RecEngine-AI: Autonomous Cross-Sell & Bundling SaaS API",
    description="B2B AI Agent API (Option B - COEN 424). Provides context-aware product recommendations via Gemini tool-calling and Cloud Firestore NoSQL.",
    version="2.0.0",
)


class RecommendationRequest(BaseModel):
    user_id: str = Field(..., example="user-concordia-99", description="Unique shopper ID for Firestore session lookup")
    product_ids: List[str] = Field(..., example=["OLJCESPC7Z", "66VCHSJNUP"], description="List of SKU IDs currently in the user's cart")
    max_results: int = Field(default=5, ge=1, le=10)


class RecommendationResponse(BaseModel):
    user_id: str
    recommended_product_ids: List[str]
    served_by_version: str = Field(example="v2-ai-agent")
    reasoning_summary: str = Field(example="Selected vintage camera lens and tripod based on vintage camera in cart.")
    tokens_used: int = Field(example=340)
    estimated_cost_usd: float = Field(example=0.000051)
    latency_ms: float = Field(example=412.5)


class FaultConfigRequest(BaseModel):
    error_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Probability (0.0-1.0) of simulated failure for canary rollback demo")
    extra_latency_ms: Optional[float] = Field(default=None, ge=0.0, le=10000.0, description="Artificial latency (ms) injected into each request")
    corrupt_output: Optional[bool] = Field(default=None, description="If true, injects an invalid SKU to trigger a correctness threshold rollback")


@app.post("/api/v1/recommendations", response_model=RecommendationResponse, tags=["AI Merchandising Agent"])
def generate_recommendations(req: RecommendationRequest):
    start = time.time()
    try:
        # Calls the exact same AI Agent & Firestore logic used by the gRPC ListRecommendations() handler
        result = run_ai_agent_recommendations(
            user_id=req.user_id,
            product_ids=req.product_ids,
            max_results=req.max_results,
            protocol="rest",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI Agent execution failed: {exc}")

    latency = round((time.time() - start) * 1000, 2)
    return RecommendationResponse(
        user_id=req.user_id,
        recommended_product_ids=result["product_ids"],
        served_by_version="v2-ai-agent",
        reasoning_summary=result["reasoning"],
        tokens_used=result["tokens"],
        estimated_cost_usd=result["cost_usd"],
        latency_ms=latency,
    )


@app.get("/api/v1/users/{user_id}", tags=["NoSQL Session Data Model"])
def get_user_session_profile(user_id: str) -> Dict[str, Any]:
    """Inspect a shopper's session profile and AI agent context stored in Cloud Firestore NoSQL."""
    return nosql_store.get_user_session(user_id)


@app.get("/api/v1/health", tags=["Monitoring & Canary"])
def health_check():
    nosql_info = check_nosql_health()
    return {
        "status": "SERVING",
        "version": "v2-ai-agent",
        "nosql_connected": nosql_info["connected"],
        "nosql_backend": nosql_info["backend"],
    }


@app.get("/api/v1/metrics", tags=["Monitoring & Canary"])
def get_canary_and_cost_metrics() -> Dict[str, Any]:
    """Returns real-time Availability, p95 Latency, Correctness %, Cost per Request (v1 vs v2), and Canary Promote/Rollback decision."""
    return tracker.get_summary()


@app.post("/api/v1/fault", tags=["Monitoring & Canary"])
def configure_fault_injection(cfg: FaultConfigRequest) -> Dict[str, Any]:
    """Configure fault injection at runtime to demonstrate canary rollback during live demo."""
    updated = tracker.configure_fault(
        error_rate=cfg.error_rate,
        extra_latency_ms=cfg.extra_latency_ms,
        corrupt_output=cfg.corrupt_output,
    )
    return {"status": "updated", "fault_injection": updated}


@app.get("/metrics", tags=["Monitoring & Canary"])
def prometheus_metrics():
    """Prometheus scrape endpoint for Grafana / Cloud Monitoring dashboards."""
    return Response(content=tracker.export_prometheus(), media_type=CONTENT_TYPE_LATEST)
