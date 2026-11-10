from __future__ import annotations

from sqlalchemy import create_engine, inspect

from app.db.session import _migrate_telemetry_components


def test_telemetry_component_migration_is_backward_compatible_and_idempotent():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE telemetry_records (
                    id INTEGER PRIMARY KEY,
                    run_id VARCHAR NOT NULL,
                    frequency_hz FLOAT NOT NULL
                )
                """
            )
            _migrate_telemetry_components(connection)
            _migrate_telemetry_components(connection)

            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("telemetry_records")
            }

            assert "generation_disturbance_pu" in columns
            assert "demand_disturbance_pu" in columns
            assert columns["generation_disturbance_pu"]["default"] == "0"
            assert columns["demand_disturbance_pu"]["default"] == "0"
    finally:
        engine.dispose()
