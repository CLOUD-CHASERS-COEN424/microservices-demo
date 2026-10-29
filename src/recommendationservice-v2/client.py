#!/usr/bin/python
#
# Client script for testing RecommendationService v2 over gRPC.

import sys

import demo_pb2
import demo_pb2_grpc
import grpc
from logger import getJSONLogger

logger = getJSONLogger("recommendationservice-v2-client")

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8080"
    user_id = sys.argv[2] if len(sys.argv) > 2 else "user-summer-runner"
    product_ids = sys.argv[3:] if len(sys.argv) > 3 else ["66VCHSJNUP"]

    channel = grpc.insecure_channel("localhost:" + port)
    stub = demo_pb2_grpc.RecommendationServiceStub(channel)
    request = demo_pb2.ListRecommendationsRequest(
        user_id=user_id, product_ids=product_ids
    )
    response = stub.ListRecommendations(request)
    logger.info(
        f"[ListRecommendationsResponse] user_id={user_id} recommended_product_ids={list(response.product_ids)}"
    )
