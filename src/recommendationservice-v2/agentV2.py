"""
RecommendationService v2 — Clean AI Agent (agentV2.py)
Model: NVIDIA Nemotron 3.5 Lightning (free) (`nvidia/nemotron-3.5-lightning:free`)
via OpenRouter API with tool calling and Cloud Firestore (`cloudchasersdb`).
"""

import copy
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

try:
    import demo_pb2
    import demo_pb2_grpc
    import grpc

    GRPC_AVAILABLE = True
except ImportError:
    grpc = None
    demo_pb2 = None
    demo_pb2_grpc = None
    GRPC_AVAILABLE = False

from logger import getJSONLogger

logger = getJSONLogger("recommendationservice-v2-agent")

try:
    from google.cloud import firestore

    FIRESTORE_LIB_AVAILABLE = True
except ImportError:
    firestore = None
    FIRESTORE_LIB_AVAILABLE = False

OPENROUTER_API_URL = os.environ.get(
    "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
)
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3.5-lightning:free"

# Default product catalog matching src/productcatalogservice/products.json
DEFAULT_CATALOG_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "OLJCESPC7Z",
        "name": "Sunglasses",
        "description": "Add a modern touch to your outfits with these sleek aviator sunglasses.",
        "categories": ["accessories"],
        "price_usd": 19.99,
    },
    {
        "id": "66VCHSJNUP",
        "name": "Tank Top",
        "description": "Perfectly cropped cotton tank, with a scooped neckline.",
        "categories": ["clothing", "tops"],
        "price_usd": 18.99,
    },
    {
        "id": "1YMWWN1N4O",
        "name": "Watch",
        "description": "This gold-tone stainless steel watch will work with most of your outfits.",
        "categories": ["accessories"],
        "price_usd": 109.99,
    },
    {
        "id": "L9ECAV7KIM",
        "name": "Loafers",
        "description": "A neat addition to your summer wardrobe.",
        "categories": ["footwear"],
        "price_usd": 89.99,
    },
    {
        "id": "2ZYFJ3GM2N",
        "name": "Hairdryer",
        "description": "This lightweight hairdryer has 3 heat and speed settings. It's perfect for travel.",
        "categories": ["hair", "beauty"],
        "price_usd": 24.99,
    },
    {
        "id": "0PUK6V6EV0",
        "name": "Candle Holder",
        "description": "This small but intricate candle holder is an excellent gift.",
        "categories": ["decor", "home"],
        "price_usd": 18.99,
    },
    {
        "id": "LS4PSXUNUM",
        "name": "Salt & Pepper Shakers",
        "description": "Add some flavor to your kitchen.",
        "categories": ["kitchen"],
        "price_usd": 18.49,
    },
    {
        "id": "9SIQT8TOJO",
        "name": "Bamboo Glass Jar",
        "description": "This bamboo glass jar can hold 57 oz (1.7 l) and is perfect for any kitchen.",
        "categories": ["kitchen"],
        "price_usd": 5.49,
    },
    {
        "id": "6E92ZMYYFZ",
        "name": "Mug",
        "description": "A simple mug with a mustard interior.",
        "categories": ["kitchen"],
        "price_usd": 8.99,
    },
]

IN_MEMORY_NOSQL_STORE: Dict[str, Dict[str, Any]] = {
    "user-concordia-99": {
        "user_id": "user-concordia-99",
        "category_affinity": "vintage photography & retro electronics",
        "past_purchased_skus": ["OLJCESPC7Z"],
        "price_sensitivity": "medium",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "user-kitchen-pro": {
        "user_id": "user-kitchen-pro",
        "category_affinity": "home barista, coffee & kitchenware",
        "past_purchased_skus": ["6E92ZMYYFZ", "2ZYFJ3GM2N"],
        "price_sensitivity": "low",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
}


class FirestoreNoSQLStore:
    """Manages shopper profiles and AI agent context in Cloud Firestore."""

    def __init__(self):
        self.project_id = os.environ.get(
            "GCP_PROJECT_ID", "cloud-chasers-microservices"
        )
        self.database_id = os.environ.get("FIRESTORE_DATABASE_ID", "cloudchasersdb")
        self.collection_name = os.environ.get("FIRESTORE_COLLECTION", "user_sessions")
        self._client = None
        self._firestore_active = False
        self._init_client()

    def _init_client(self) -> None:
        if not FIRESTORE_LIB_AVAILABLE or os.environ.get("DISABLE_FIRESTORE", "0") == "1":
            return
        try:
            self._client = firestore.Client(
                project=self.project_id, database=self.database_id
            )
            self._firestore_active = True
            logger.info(
                f"Connected to Cloud Firestore (project={self.project_id}, database={self.database_id})"
            )
        except Exception as exc:
            logger.warning(f"Firestore unavailable ({exc}); using in-memory store.")
            self._client = None
            self._firestore_active = False

    def is_connected(self) -> bool:
        return True

    def backend_mode(self) -> str:
        return "cloud-firestore" if self._firestore_active else "in-memory-nosql-fallback"

    def get_user_session(self, user_id: str) -> Dict[str, Any]:
        if self._firestore_active and self._client is not None:
            try:
                doc = (
                    self._client.collection(self.collection_name)
                    .document(user_id)
                    .get(timeout=3.0)
                )
                if doc.exists:
                    data = doc.to_dict() or {}
                    data["nosql_source"] = "cloud-firestore"
                    return data
            except Exception as exc:
                logger.warning(f"Firestore read failed for user_id={user_id}: {exc}")

        if user_id in IN_MEMORY_NOSQL_STORE:
            profile = copy.deepcopy(IN_MEMORY_NOSQL_STORE[user_id])
            profile["nosql_source"] = self.backend_mode()
            return profile

        default_profile = {
            "user_id": user_id,
            "category_affinity": "general lifestyle, accessories & home essentials",
            "past_purchased_skus": [],
            "price_sensitivity": "medium",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "nosql_source": self.backend_mode(),
        }
        IN_MEMORY_NOSQL_STORE[user_id] = copy.deepcopy(default_profile)
        return default_profile

    def update_user_session(
        self,
        user_id: str,
        cart_skus: List[str],
        recommended_skus: List[str],
        reasoning: str,
        tokens_used: int = 0,
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = self.get_user_session(user_id)
        updated_doc = {
            "user_id": user_id,
            "category_affinity": existing.get("category_affinity", "general lifestyle"),
            "past_purchased_skus": existing.get("past_purchased_skus", []),
            "price_sensitivity": existing.get("price_sensitivity", "medium"),
            "last_cart_skus": list(cart_skus),
            "last_recommended_skus": list(recommended_skus),
            "last_reasoning": reasoning,
            "last_tokens_used": tokens_used,
            "updated_at": now_iso,
        }
        IN_MEMORY_NOSQL_STORE[user_id] = copy.deepcopy(updated_doc)

        if self._firestore_active and self._client is not None:
            try:
                self._client.collection(self.collection_name).document(user_id).set(
                    updated_doc, merge=True, timeout=3.0
                )
            except Exception as exc:
                logger.warning(f"Firestore write failed for user_id={user_id}: {exc}")

        return updated_doc


class CatalogBackendClient:
    """Queries Online Boutique ProductCatalogService over gRPC."""

    def __init__(self, product_catalog_stub=None):
        self._stub = product_catalog_stub
        self._channel = None

    def _get_stub(self):
        if self._stub is not None:
            return self._stub
        if not GRPC_AVAILABLE:
            return None
        catalog_addr = os.environ.get("PRODUCT_CATALOG_SERVICE_ADDR", "")
        if catalog_addr:
            if self._channel is None:
                self._channel = grpc.insecure_channel(catalog_addr)
            self._stub = demo_pb2_grpc.ProductCatalogServiceStub(self._channel)
        return self._stub

    @staticmethod
    def _proto_product_to_dict(prod) -> Dict[str, Any]:
        units = getattr(prod.price_usd, "units", 0)
        nanos = getattr(prod.price_usd, "nanos", 0)
        price = round(float(units) + (float(nanos) / 1e9), 2)
        return {
            "id": prod.id,
            "name": prod.name,
            "description": prod.description,
            "categories": list(prod.categories),
            "price_usd": price,
        }

    def list_products(self) -> List[Dict[str, Any]]:
        stub = self._get_stub()
        if stub is not None:
            try:
                resp = stub.ListProducts(demo_pb2.Empty(), timeout=2.5)
                if resp and resp.products:
                    return [self._proto_product_to_dict(p) for p in resp.products]
            except Exception as exc:
                logger.warning(f"gRPC ListProducts failed ({exc}); using local catalog.")
        return copy.deepcopy(DEFAULT_CATALOG_PRODUCTS)

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        stub = self._get_stub()
        if stub is not None:
            try:
                resp = stub.GetProduct(
                    demo_pb2.GetProductRequest(id=product_id), timeout=2.0
                )
                if resp and resp.id:
                    return self._proto_product_to_dict(resp)
            except Exception:
                pass
        for p in self.list_products():
            if p["id"] == product_id:
                return p
        return None

    def search_products(self, query: str) -> List[Dict[str, Any]]:
        stub = self._get_stub()
        if stub is not None:
            try:
                resp = stub.SearchProducts(
                    demo_pb2.SearchProductsRequest(query=query), timeout=2.5
                )
                if resp and resp.results:
                    return [self._proto_product_to_dict(p) for p in resp.results]
            except Exception:
                pass
        q = (query or "").strip().lower()
        all_prods = self.list_products()
        if not q:
            return all_prods
        matched = [
            p
            for p in all_prods
            if any(
                token
                in " ".join(
                    [p["name"], p["description"]] + p.get("categories", [])
                ).lower()
                for token in q.replace(",", " ").split()
            )
        ]
        return matched if matched else all_prods


nosql_store = FirestoreNoSQLStore()


def check_nosql_health() -> Dict[str, Any]:
    return {
        "connected": nosql_store.is_connected(),
        "backend": nosql_store.backend_mode(),
        "collection": nosql_store.collection_name,
    }


def _filter_valid_skus(
    candidate_ids: List[str],
    cart_product_ids: List[str],
    catalog_products: List[Dict[str, Any]],
    max_results: int = 5,
) -> List[str]:
    """Keeps only valid catalog SKUs that are not already in the user's cart."""
    valid_ids = {p["id"] for p in catalog_products}
    cart_set = set(cart_product_ids or [])
    cleaned: List[str] = []
    seen = set()

    for pid in candidate_ids or []:
        if not isinstance(pid, str):
            continue
        pid = pid.strip()
        if pid in valid_ids and pid not in cart_set and pid not in seen:
            seen.add(pid)
            cleaned.append(pid)

    return cleaned[:max_results]


def _call_openrouter_chat(
    api_key: str,
    model_name: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Sends an OpenAI-compatible Chat Completions request to OpenRouter."""
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        OPENROUTER_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/GoogleCloudPlatform/microservices-demo",
            "X-Title": "COEN424-RecEngine-AI-v2",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=25.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenRouter HTTP {http_err.code} for model '{model_name}': {err_body}"
        ) from http_err
    except Exception as exc:
        raise RuntimeError(
            f"OpenRouter request failed for model '{model_name}': {exc}"
        ) from exc


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Extracts the JSON recommendation object from the model response."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise RuntimeError(f"AI model did not return valid JSON. Raw output: {text!r}")


def _run_openrouter_nemotron_agent(
    user_id: str,
    cart_product_ids: List[str],
    max_results: int,
    catalog_client: CatalogBackendClient,
) -> Dict[str, Any]:
    """Executes NVIDIA Nemotron 3.5 Lightning via OpenRouter with tool calling."""
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable is not set."
        )

    model_name = os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)

    tools_schema = [
        {
            "type": "function",
            "function": {
                "name": "get_user_session_profile",
                "description": "Fetch shopper profile, category affinity, past purchases, and price sensitivity from Cloud Firestore NoSQL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "shopper_user_id": {
                            "type": "string",
                            "description": "The unique user_id of the shopper.",
                        }
                    },
                    "required": ["shopper_user_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_cart_products_details",
                "description": "Fetch full product details (name, categories, price_usd, description) from ProductCatalogService for SKUs currently in the cart.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sku_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of SKU IDs in the shopper's cart.",
                        }
                    },
                    "required": ["sku_ids"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_catalog_products",
                "description": "Search ProductCatalogService for candidate complementary products matching a category or keyword query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Category or keyword search string.",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_all_catalog_products",
                "description": "List all available products from ProductCatalogService, optionally filtered by a maximum USD price.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_price_usd": {
                            "type": "number",
                            "description": "Optional maximum USD price filter (0 for no limit).",
                        }
                    },
                },
            },
        },
    ]

    allowed_tools = {
        "get_user_session_profile",
        "get_cart_products_details",
        "search_catalog_products",
        "list_all_catalog_products",
    }

    def execute_tool(func_name: str, args: Dict[str, Any]) -> Any:
        if func_name == "get_user_session_profile":
            uid = str(args.get("shopper_user_id") or user_id)
            return nosql_store.get_user_session(uid)
        if func_name == "get_cart_products_details":
            skus = args.get("sku_ids") or cart_product_ids
            return [
                p for sku in skus if (p := catalog_client.get_product(sku)) is not None
            ]
        if func_name == "search_catalog_products":
            q = str(args.get("query") or "")
            return catalog_client.search_products(q)
        if func_name == "list_all_catalog_products":
            max_p = float(args.get("max_price_usd") or 0.0)
            prods = catalog_client.list_products()
            if max_p > 0:
                prods = [p for p in prods if float(p.get("price_usd", 0.0)) <= max_p]
            return prods
        return {"error": f"Unknown tool: {func_name}"}

    system_instruction = (
        "You are RecEngine-AI, an autonomous e-commerce merchandising AI agent for Online Boutique. "
        "Use the provided tools (`get_user_session_profile`, `get_cart_products_details`, "
        "`list_all_catalog_products`, `search_catalog_products`) to inspect the shopper's Cloud Firestore "
        "profile and the ProductCatalogService items. "
        "Select up to `max_results` complementary product IDs from the catalog that are NOT already in `cart_product_ids`, "
        "tailored to the shopper's cart items, category_affinity, and price_sensitivity.\n"
        "Respond ONLY with a valid JSON object matching this exact schema:\n"
        '{"recommended_product_ids": ["SKU1", "SKU2"], "reasoning_summary": "Concise explanation of why these SKUs were chosen."}'
    )

    user_prompt = (
        f"Generate product recommendations for user_id='{user_id}', "
        f"current cart_product_ids={json.dumps(list(cart_product_ids))}, "
        f"max_results={max_results}."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    tool_calls_made = 0

    def make_agent_result(parsed: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(parsed, dict):
            raise RuntimeError("The model's final JSON must be an object.")
        recommended_ids = parsed.get("recommended_product_ids")
        reasoning = parsed.get("reasoning_summary")
        if not isinstance(recommended_ids, list):
            raise RuntimeError("Final JSON is missing recommended_product_ids list.")
        if not isinstance(reasoning, str):
            raise RuntimeError("Final JSON is missing reasoning_summary string.")
        return {
            "product_ids": recommended_ids,
            "reasoning": reasoning,
            "tokens": total_input_tokens + total_output_tokens,
            "cost_usd": 0.0,
            "engine": f"openrouter ({model_name})",
        }

    for turn in range(4):
        resp_data = _call_openrouter_chat(
            api_key=api_key,
            model_name=model_name,
            messages=messages,
            tools=tools_schema,
        )

        usage = resp_data.get("usage") or {}
        total_input_tokens += int(usage.get("prompt_tokens", 0) or 0)
        total_output_tokens += int(usage.get("completion_tokens", 0) or 0)

        choices = resp_data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {resp_data}")

        msg = choices[0].get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        content_text = msg.get("content") or ""

        # 1. Native OpenAI-compatible structured tool calls
        if tool_calls:
            messages.append(msg)
            for tc in tool_calls:
                func_info = tc.get("function") or {}
                func_name = func_info.get("name", "")
                if func_name not in allowed_tools:
                    raise RuntimeError(f"Unknown tool requested: {func_name}")
                raw_args = func_info.get("arguments") or "{}"
                parsed_args = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )
                tool_output = execute_tool(func_name, parsed_args)
                tool_calls_made += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{tool_calls_made}"),
                        "name": func_name,
                        "content": json.dumps(tool_output),
                    }
                )
            continue

        # 2. Textual <tool_call> output from Nemotron
        if "<tool_call>" in content_text:
            function_match = re.search(r"<function=([a-zA-Z0-9_]+)>", content_text)
            if not function_match:
                raise RuntimeError(f"Malformed textual tool call: {content_text!r}")
            func_name = function_match.group(1)
            if func_name not in allowed_tools:
                raise RuntimeError(f"Unknown textual tool call: {func_name}")

            parsed_args: Dict[str, Any] = {}
            for match in re.finditer(
                r"<parameter=([a-zA-Z0-9_]+)>\s*(.*?)\s*</parameter>",
                content_text,
                flags=re.DOTALL,
            ):
                parsed_args[match.group(1)] = match.group(2).strip()

            if func_name == "get_cart_products_details":
                raw_skus = parsed_args.get("sku_ids", "[]")
                try:
                    parsed_args["sku_ids"] = json.loads(raw_skus)
                except json.JSONDecodeError:
                    parsed_args["sku_ids"] = [
                        sku.strip() for sku in raw_skus.split(",") if sku.strip()
                    ]
            elif func_name == "list_all_catalog_products":
                parsed_args["max_price_usd"] = float(
                    parsed_args.get("max_price_usd", "0") or 0
                )

            tool_output = execute_tool(func_name, parsed_args)
            tool_calls_made += 1
            messages.append({"role": "assistant", "content": content_text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool result for {func_name}:\n"
                        f"{json.dumps(tool_output)}\n\n"
                        "Use this result to continue the recommendation task."
                    ),
                }
            )
            continue

        # 3. Direct JSON response
        try:
            parsed = _extract_json_object(content_text)
            return make_agent_result(parsed)
        except Exception:
            messages.append({"role": "assistant", "content": content_text})
            break

    # 4. Final JSON-only request without tools
    messages.append(
        {
            "role": "user",
            "content": (
                "FINAL RESPONSE REQUIRED. Do not call or describe any tools. "
                f"Select up to {max_results} valid product IDs that are not in the cart "
                f"{json.dumps(list(cart_product_ids))}. "
                "Return ONLY a valid JSON object in this exact format: "
                '{"recommended_product_ids":["SKU1"],"reasoning_summary":"Brief explanation."}'
            ),
        }
    )

    resp_data = _call_openrouter_chat(
        api_key=api_key,
        model_name=model_name,
        messages=messages,
        tools=None,
    )
    usage = resp_data.get("usage") or {}
    total_input_tokens += int(usage.get("prompt_tokens", 0) or 0)
    total_output_tokens += int(usage.get("completion_tokens", 0) or 0)

    choices = resp_data.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {resp_data}")

    final_text = (choices[0].get("message") or {}).get("content") or ""
    parsed = _extract_json_object(final_text)
    return make_agent_result(parsed)


def run_ai_agent_recommendations(
    user_id: str,
    product_ids: List[str],
    max_results: int = 5,
    product_catalog_stub=None,
) -> Dict[str, Any]:
    """Main entry point shared by gRPC `ListRecommendations()` and FastAPI `/api/v1/recommendations`."""
    start_time = time.time()
    user_id = (user_id or "anonymous-shopper").strip()
    cart_product_ids = list(product_ids or [])
    max_results = max(1, min(int(max_results or 5), 10))

    catalog_client = CatalogBackendClient(product_catalog_stub=product_catalog_stub)

    agent_result = _run_openrouter_nemotron_agent(
        user_id=user_id,
        cart_product_ids=cart_product_ids,
        max_results=max_results,
        catalog_client=catalog_client,
    )

    all_products = catalog_client.list_products()
    final_ids = _filter_valid_skus(
        candidate_ids=agent_result["product_ids"],
        cart_product_ids=cart_product_ids,
        catalog_products=all_products,
        max_results=max_results,
    )

    nosql_store.update_user_session(
        user_id=user_id,
        cart_skus=cart_product_ids,
        recommended_skus=final_ids,
        reasoning=agent_result["reasoning"],
        tokens_used=agent_result["tokens"],
    )

    latency_ms = round((time.time() - start_time) * 1000.0, 2)
    logger.info(
        f"[v2-ai-agent] user_id={user_id} cart={cart_product_ids} recommended={final_ids} latency_ms={latency_ms}"
    )

    return {
        "product_ids": final_ids,
        "reasoning": agent_result["reasoning"],
        "tokens": agent_result["tokens"],
        "cost_usd": agent_result["cost_usd"],
        "latency_ms": latency_ms,
    }
