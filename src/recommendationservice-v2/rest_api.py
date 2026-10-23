from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
import time

app = FastAPI(
    title="RecEngine-AI: Autonomous Cross-Sell & Bundling SaaS API",
    description="B2B AI Agent API (Option B - COEN 424). Provides context-aware product recommendations via Gemini tool-calling and Cloud Firestore NoSQL.",
    version="2.0.0"
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

@app.post("/api/v1/recommendations", response_model=RecommendationResponse, tags=["AI Merchandising Agent"])
def generate_recommendations(req: RecommendationRequest):
    start = time.time()
    # Calls the exact same AI Agent & Firestore logic used by your gRPC ListRecommendations() handler!
    result = run_ai_agent_recommendations(req.user_id, req.product_ids, req.max_results)
    latency = round((time.time() - start) * 1000, 2)
    return RecommendationResponse(
        user_id=req.user_id,
        recommended_product_ids=result["product_ids"],
        served_by_version="v2-ai-agent",
        reasoning_summary=result["reasoning"],
        tokens_used=result["tokens"],
        estimated_cost_usd=result["cost_usd"],
        latency_ms=latency
    )

@app.get("/api/v1/health", tags=["Monitoring & Canary"])
def health_check():
    return {"status": "SERVING", "version": "v2-ai-agent", "nosql_connected": True}