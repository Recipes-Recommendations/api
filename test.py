"""
Test file for the API
"""
import os
from unittest.mock import Mock, patch
import numpy as np
import pytest

# Mock environment variables before importing api
os.environ['REDIS_HOST'] = 'test-host'
os.environ['REDIS_PORT'] = '1234'
os.environ['REDIS_USERNAME'] = 'test-user'
os.environ['REDIS_PASSWORD'] = 'test-pass'

# Now import the API
from api import (  # noqa: E402
        get_cached_results,
        cache_results,
        get_recipes_by_query,
        store_click_data,
        record_click,
        health_check,
        get_recipes,
        ClickData
)

# Mock data
MOCK_CACHED_RESULTS = [
        {"title": "Test Recipe 1", "link": "http://test1.com"},
        {"title": "Test Recipe 2", "link": "http://test2.com"},
        {"title": "Test Recipe 3", "link": "http://test3.com"}
]


class MockRedisDoc:
    def __init__(self, title, link):
        self.title = title
        self.link = link

    def __getattr__(self, name):
        if name == '$.title':
            return self.title
        if name == '$.link':
            return self.link
        return None


MOCK_REDIS_DOCS = [
    MockRedisDoc('Test Recipe 1', 'http://test1.com'),
    MockRedisDoc('Test Recipe 2', 'http://test2.com'),
    MockRedisDoc('Test Recipe 3', 'http://test3.com')
]


@pytest.fixture
def mock_redis() -> Mock:
    """
    Mock Redis client
    """
    with patch('api.REDIS_CLIENT') as mock:
        yield mock


@pytest.fixture
def mock_embeddings_model() -> Mock:
    """
    Mock embeddings model
    """
    with patch('api.EMBEDDINGS_MODEL') as mock:
        mock.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        yield mock


def test_get_cached_results(mock_redis: Mock) -> None:
    """
    Test get_cached_results
    """
    # Test when cache exists
    mock_redis.get.return_value = str(MOCK_CACHED_RESULTS)
    result = get_cached_results("test query")
    assert result == MOCK_CACHED_RESULTS
    mock_redis.get.assert_called_once_with("search_cache:test query")

    # Test when cache doesn't exist
    mock_redis.get.return_value = None
    result = get_cached_results("test query")
    assert result is None


def test_cache_results(mock_redis: Mock) -> None:
    """
    Test cache_results
    """
    cache_results("test query", MOCK_CACHED_RESULTS)
    mock_redis.setex.assert_called_once_with(
        "search_cache:test query",
        3,    # CACHE_EXPIRATION
        str(MOCK_CACHED_RESULTS)
    )


def test_get_recipes_by_query_with_cache(mock_redis: Mock, mock_embeddings_model: Mock) -> None:
    """
    Test get_recipes_by_query with cache
    """
    # Test with cached results
    mock_redis.get.return_value = str(MOCK_CACHED_RESULTS)
    results = get_recipes_by_query("test query", page=1, items_per_page=2)
    assert len(results) == 2
    assert results == MOCK_CACHED_RESULTS[:2]


def test_get_recipes_by_query_without_cache(mock_redis: Mock, mock_embeddings_model: Mock) -> None:
    """
    Test get_recipes_by_query without cache
    """
    # Test without cached results
    mock_redis.get.return_value = None
    mock_redis.ft().search().docs = MOCK_REDIS_DOCS

    results = get_recipes_by_query("test query", page=1, items_per_page=2)
    assert len(results) == 2
    assert results == [
        {"title": "Test Recipe 1", "link": "http://test1.com"},
        {"title": "Test Recipe 2", "link": "http://test2.com"}
    ]


def test_store_click_data_new(mock_redis: Mock) -> None:
    """
    Test store_click_data with new data
    """
    # Test storing new click data
    mock_redis.exists.return_value = False
    store_click_data("test query", "http://test.com")
    mock_redis.hset.assert_called_once_with(
        "clicks:test query:http://test.com",
        mapping={"count": 1}
    )


def test_store_click_data_existing(mock_redis: Mock) -> None:
    """
    Test store_click_data with existing data
    """
    # Test incrementing existing click data
    mock_redis.exists.return_value = True
    store_click_data("test query", "http://test.com")
    mock_redis.hincrby.assert_called_once_with(
        "clicks:test query:http://test.com",
        "count",
        1
    )


@pytest.mark.asyncio
async def test_record_click_success() -> None:
    """
    Test record_click success
    """
    with patch('api.store_click_data') as mock_store:
        click_data = ClickData(query="test query", link="http://test.com")
        result = await record_click(click_data)
        assert result == {"status": "success", "message": "Click data recorded"}
        mock_store.assert_called_once_with("test query", "http://test.com")


@pytest.mark.asyncio
async def test_record_click_error() -> None:
    """
    Test record_click error
    """
    with patch('api.store_click_data', side_effect=Exception("Test error")):
        click_data = ClickData(query="test query", link="http://test.com")
        result = await record_click(click_data)
        assert result == {"status": "error", "message": "Test error"}


@pytest.mark.asyncio
async def test_health_check() -> None:
    """
    Test health_check
    """
    result = await health_check()
    assert result == {"status": "healthy"}


@pytest.mark.asyncio
async def test_get_recipes_invalid_page() -> None:
    """
    Test get_recipes with invalid page
    """
    result = await get_recipes("test query", page=0)
    assert result == {"error": "Page number must be greater than 0"}


@pytest.mark.asyncio
async def test_get_recipes_success() -> None:
    """
    Test get_recipes success
    """
    with patch('api.get_recipes_by_query', return_value=MOCK_CACHED_RESULTS):
        result = await get_recipes("test query", page=1)
        assert result == {
            "query": "test query",
            "page": 1,
            "results": MOCK_CACHED_RESULTS,
            "has_more": True
        }


@pytest.mark.asyncio
async def test_get_recipes_error() -> None:
    """
    Test get_recipes error
    """
    with patch('api.get_recipes_by_query', side_effect=Exception("Test error")):
        result = await get_recipes("test query", page=1)
        assert result == {"error": "Test error"}
