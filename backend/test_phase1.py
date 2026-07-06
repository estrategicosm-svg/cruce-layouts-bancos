import sys
from fastapi.testclient import TestClient
from main import app
from infrastructure.database.orm.base import Base
import infrastructure.security.jwt_utils as jwt_utils

print("Testing FastAPI instantiation...")
client = TestClient(app)

print("Testing /api/v1/health/live...")
live_response = client.get("/api/v1/health/live")
assert live_response.status_code == 200
print(f"Live Status: {live_response.json()}")

print("Testing /api/v1/health/ready...")
ready_response = client.get("/api/v1/health/ready")
assert ready_response.status_code == 200
print(f"Ready Status: {ready_response.json()}")

print("SQLAlchemy Base imported successfully.")
print("JWT Utils imported successfully.")
print("All validations completed successfully.")
