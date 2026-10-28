#!/usr/bin/python
"""
RecommendationService v2 (AI Agent Version) - gRPC + REST Server.
Uses agentV2.py (NVIDIA Nemotron 3.5 Lightning via OpenRouter + Cloud Firestore).
"""

import os
import threading
import time
from concurrent import futures

import grpc
import demo_pb2
import demo_pb2_grpc
try:
    from grpc_health.v1 import health_pb2
    from grpc_health.v1 import health_pb2_grpc
    GRPC_HEALTH_AVAILABLE = True
except ImportError:
    health_pb2 = None
    health_pb2_grpc = None
    GRPC_HEALTH_AVAILABLE = False

from agentV2 import run_ai_agent_recommendations
from logger import getJSONLogger

logger = getJSONLogger("recommendationservice-v2-server")

product_catalog_stub = None


class RecommendationServiceV2(demo_pb2_grpc.RecommendationServiceServicer):
    """gRPC Servicer for RecommendationService v2 backed by agentV2."""

    def __init__(self, catalog_stub=None):
        self.catalog_stub = catalog_stub

    def ListRecommendations(self, request, context):
        max_responses = int(os.environ.get("MAX_RECOMMENDATIONS", "5"))
        stub = self.catalog_stub or product_catalog_stub
        try:
            result = run_ai_agent_recommendations(
                user_id=request.user_id,
                product_ids=list(request.product_ids),
                max_results=max_responses,
                product_catalog_stub=stub,
            )
            prod_list = result["product_ids"]
            logger.info(
                f"[Recv ListRecommendations v2] user_id={request.user_id} product_ids={prod_list} reasoning={result['reasoning']}"
            )
            response = demo_pb2.ListRecommendationsResponse()
            response.product_ids.extend(prod_list)
            return response
        except Exception as exc:
            logger.error(f"[ListRecommendations v2 ERROR] user_id={request.user_id} err={exc}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"RecommendationService v2 AI Agent error: {exc}")
            return demo_pb2.ListRecommendationsResponse()

    def Check(self, request, context):
        if GRPC_HEALTH_AVAILABLE:
            return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)
        return demo_pb2.Empty()

    def Watch(self, request, context):
        if GRPC_HEALTH_AVAILABLE:
            return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.UNIMPLEMENTED)
        return demo_pb2.Empty()


def _start_rest_http_server(http_port: int) -> None:
    try:
        import uvicorn
        from rest_api import app

        logger.info(f"Starting FastAPI REST server on port {http_port}")
        uvicorn.run(app, host="0.0.0.0", port=http_port, log_level="warning")
    except Exception as exc:
        logger.warning(f"Could not start background FastAPI server on port {http_port}: {exc}")


if __name__ == "__main__":
    logger.info("initializing recommendationservice-v2 (AI Agent)")

    port = os.environ.get("PORT", "8080")
    http_port = int(os.environ.get("HTTP_PORT", "8081"))
    catalog_addr = os.environ.get("PRODUCT_CATALOG_SERVICE_ADDR", "")
    if catalog_addr:
        logger.info("product catalog address: " + catalog_addr)
        channel = grpc.insecure_channel(catalog_addr)
        product_catalog_stub = demo_pb2_grpc.ProductCatalogServiceStub(channel)

    if os.environ.get("DISABLE_HTTP_SERVER", "0") != "1":
        http_thread = threading.Thread(
            target=_start_rest_http_server,
            args=(http_port,),
            daemon=True,
        )
        http_thread.start()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service = RecommendationServiceV2(catalog_stub=product_catalog_stub)
    demo_pb2_grpc.add_RecommendationServiceServicer_to_server(service, server)
    if GRPC_HEALTH_AVAILABLE:
        health_pb2_grpc.add_HealthServicer_to_server(service, server)

    logger.info("recommendationservice-v2 gRPC listening on port: " + port)
    server.add_insecure_port("[::]:" + port)
    server.start()

    try:
        while True:
            time.sleep(10000)
    except KeyboardInterrupt:
        server.stop(0)
