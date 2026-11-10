from fastapi.testclient import TestClient

from app.main import app


def test_invalid_path_parameter_uses_consistent_validation_envelope() -> None:
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/scenarios/not-a-uuid"
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed"
    assert error["details"][0]["field"] == "scenario_id"
    assert isinstance(error["details"][0]["message"], str)
