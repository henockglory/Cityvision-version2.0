import pytest
from fastapi.testclient import TestClient

from citevision_ai.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
