"""
API for the recipe search engine
"""
from fastapi import FastAPI
from peft import PeftModel
from pydantic import BaseModel
from redis.commands.search.query import Query
from sentence_transformers import SentenceTransformer
from typing import Optional, List
import boto3
import json
import logging
import numpy as np
import os
import redis
import uvicorn

# Initialize logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

####################################################################################################
# Global variables
####################################################################################################
# Initialize FastAPI app
app = FastAPI(
    title="Recipe API",
    description="A simple REST API for recipe management",
    version="1.0.0"
)
LOGGER.info("FastAPI app initialized")

# Initialize embeddings model
EMBEDDINGS_MODEL = PeftModel.from_pretrained(
    SentenceTransformer("sentence-transformers/all-mpnet-base-v2"),
    "carlosalvarezg/all-mpnet-base-v2"
)
EMBEDDINGS_MODEL.eval()
LOGGER.info("Embeddings model initialized")


def get_secret(secret_name):
    region_name = "us-east-1"
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except Exception as e:
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            return json.loads(get_secret_value_response['SecretString'])
        else:
            raise ValueError("Secret value is not a string")

# Initialize Redis client
try:
    REDIS_CREDS = get_secret("redis_data")
except Exception as exc:
    LOGGER.error(exc)
    REDIS_CREDS = {
        "REDIS_HOST": os.getenv("REDIS_HOST"),
        "REDIS_PORT": os.getenv("REDIS_PORT"),
        "REDIS_USERNAME": os.getenv("REDIS_USERNAME"),
        "REDIS_PASSWORD": os.getenv("REDIS_PASSWORD")
    }
print(REDIS_CREDS)
REDIS_CLIENT = redis.Redis(
    host=REDIS_CREDS['REDIS_HOST'],
    port=int(REDIS_CREDS['REDIS_PORT']),
    decode_responses=True,
    username=REDIS_CREDS['REDIS_USERNAME'],
    password=REDIS_CREDS['REDIS_PASSWORD'],
)
LOGGER.info("Redis client initialized")

# Cache expiration time in seconds
CACHE_EXPIRATION = 3
LOGGER.info("Cache expiration time initialized")

# Query to get the top 100 results from the index
QUERY = (
    Query('(*)=>[KNN 100 @vector $query_vector AS vector_score]')
    .sort_by('vector_score')
    .return_fields('vector_score', 'id', '$.title', '$.link')
    .dialect(2)
)
LOGGER.info("Query initialized")

####################################################################################################
# Models
####################################################################################################


class ClickData(BaseModel):
    """
    Click data model
    params:
        query: str
        link: str
    """
    query: str
    link: str

####################################################################################################
# Helper functions
####################################################################################################


def get_cached_results(query_text: str) -> Optional[List[dict]]:
    """
    Retrieve cached results for a query if they exist.
    params:
        query_text: str
    returns:
        list: cached results
    """
    cache_key = f"search_cache:{query_text}"
    cached_results = REDIS_CLIENT.get(cache_key)
    if cached_results:
        return eval(cached_results)  # Convert string back to list
    return None


def cache_results(query_text: str, results: List[dict]) -> None:
    """
    Cache search results for a query.
    params:
        query_text: str
        results: list
    returns:
        None
    """
    cache_key = f"search_cache:{query_text}"
    try:
        REDIS_CLIENT.setex(cache_key, CACHE_EXPIRATION, str(results))
    except Exception as e:
        LOGGER.error("Error caching results %s for query %s", results, query_text)
        LOGGER.error("Error: %s", e)
        raise e


def get_recipes_by_query(query_text: str, page: int = 1, items_per_page: int = 3) -> List[dict]:
    """
    Creates a query table with pagination and caching.
    params:
        query_text: str
        page: int
        items_per_page: int
    returns:
        list: paginated results
    """
    # Try to get cached results first
    cached_results = get_cached_results(query_text)

    if cached_results:
        # Calculate pagination for cached results
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        return cached_results[start_idx:end_idx]

    # If no cache, perform the search
    results_list = []
    encoded_query = EMBEDDINGS_MODEL.encode([query_text]).tolist()[0]

    try:
        result_docs = (
            REDIS_CLIENT.ft("idx:recipes")
            .search(QUERY, {"query_vector": np.array(encoded_query, dtype=np.float16).tobytes()})
            .docs
        )

        for doc in result_docs:
            # Access fields directly as attributes
            title = getattr(doc, '$.title', 'No title available')
            link = getattr(doc, '$.link', 'No link available')
            results_list.append({
                "title": title,
                "link": link,
            })

    except Exception as e:
        LOGGER.error("Error getting recipes by query %s", query_text)
        LOGGER.error("Error: %s", e)
        raise e

    # Cache the results (with error handling)
    try:
        cache_results(query_text, results_list)
    except redis.exceptions.OutOfMemoryError:
        # If we can't cache, just continue without caching
        LOGGER.warning("Could not cache results due to memory constraints")
        pass

    # Calculate pagination
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    return results_list[start_idx:end_idx]


def store_click_data(query: str, link: str) -> None:
    """
    Store click data in Redis as a hash where we track both timestamp and click count.
    The data is stored in the format:
    - Key: clicks:{query}:{link}
    - Fields: timestamp, count
    params:
        query: str
        link: str
    returns:
        None
    """
    click_key = f"clicks:{query}:{link}"

    # Check if this query-link pair already exists
    if REDIS_CLIENT.exists(click_key):
        # Increment the counter
        REDIS_CLIENT.hincrby(click_key, "count", 1)
    else:
        # Create new record with initial count of 1
        REDIS_CLIENT.hset(click_key, mapping={
            "count": 1
        })

####################################################################################################
# Endpoints
####################################################################################################


@app.post("/click")
async def record_click(click_data: ClickData) -> dict:
    """
    Record click data
    params:
        click_data: ClickData
    returns:
        dict: status and message
    """
    try:
        store_click_data(click_data.query, click_data.link)
        return {"status": "success", "message": "Click data recorded"}
    except Exception as e:
        LOGGER.error("Error recording click data %s", click_data)
        LOGGER.error("Error: %s", e)
        return {"status": "error", "message": str(e)}


@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint
    returns:
        dict: status
    """
    return {"status": "healthy"}


@app.get("/recipes/query={query}&page={page}")
async def get_recipes(query: str, page: int) -> dict:
    """
    Get recipes by query
    params:
        query: str
        page: int
    returns:
        dict: recipes
    """
    if page < 1:
        return {"error": "Page number must be greater than 0"}

    try:
        results = get_recipes_by_query(query, page=page)
    except Exception as e:
        LOGGER.error("Error getting recipes by query %s", query)
        LOGGER.error("Error: %s", e)
        return {"error": str(e)}

    return {
        "query": query,
        "page": page,
        "results": results,
        "has_more": len(results) == 3
    }


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8080, reload=True)
