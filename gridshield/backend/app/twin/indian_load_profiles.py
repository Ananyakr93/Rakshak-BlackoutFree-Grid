"""
Indian residential appliance load profiles for GridShield.

Defines realistic Indian-home appliance profiles (power ratings,
priority defaults, shed limits) and a deterministic building-config
generator seeded for reproducibility.

Sources: approximate values from BIS IS 1391, EESL Super-Efficient
Equipment Programme (SEEP), and typical Indian residential surveys.
REFIT data is NOT used — these are entirely synthetic Indian profiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.schemas.scenario import ApplianceConfig, BuildingConfig


@dataclass(frozen=True)
class LoadProfile:
    """Profile for one Indian residential appliance type."""

    appliance_type: str
    rated_power_kw: float
    typical_on_hours_per_day: float     # average hours on per day
    duty_cycle: float                   # fraction of on-time drawing rated power
    min_on_time_s: float
    min_off_time_s: float
    max_shed_minutes: float | None
    priority_default: Literal["critical", "essential", "deferrable"]
    comfort_constraint_notes: str       # human-readable


# ---------------------------------------------------------------------------
# Indian appliance catalogue
# ---------------------------------------------------------------------------
# Approximate values based on:
#   - BIS IS 1391 (fans), IS 302 (AC), IS 2082 (geysers)
#   - EESL SEEP programme published appliance power ratings
#   - Typical Indian residential load surveys (CEA, 2019-2023)

INDIAN_PROFILES: list[LoadProfile] = [
    LoadProfile(
        appliance_type="split_ac_1ton",
        rated_power_kw=1.0,
        typical_on_hours_per_day=8.0,
        duty_cycle=0.6,
        min_on_time_s=120.0,
        min_off_time_s=120.0,
        max_shed_minutes=30.0,
        priority_default="deferrable",
        comfort_constraint_notes="Compressor cycling; comfort limit 30 min shed",
    ),
    LoadProfile(
        appliance_type="split_ac_1_5ton",
        rated_power_kw=1.5,
        typical_on_hours_per_day=8.0,
        duty_cycle=0.6,
        min_on_time_s=120.0,
        min_off_time_s=120.0,
        max_shed_minutes=30.0,
        priority_default="deferrable",
        comfort_constraint_notes="1.5-ton AC; similar constraints to 1-ton",
    ),
    LoadProfile(
        appliance_type="geyser_15l",
        rated_power_kw=2.0,
        typical_on_hours_per_day=1.0,
        duty_cycle=1.0,
        min_on_time_s=60.0,
        min_off_time_s=30.0,
        max_shed_minutes=60.0,
        priority_default="deferrable",
        comfort_constraint_notes="Water stays hot ~60 min in 15L tank",
    ),
    LoadProfile(
        appliance_type="ev_charger_2wheeler",
        rated_power_kw=0.75,
        typical_on_hours_per_day=4.0,
        duty_cycle=1.0,
        min_on_time_s=30.0,
        min_off_time_s=10.0,
        max_shed_minutes=None,
        priority_default="deferrable",
        comfort_constraint_notes="Can defer overnight; no comfort impact",
    ),
    LoadProfile(
        appliance_type="ev_charger_car",
        rated_power_kw=3.3,
        typical_on_hours_per_day=6.0,
        duty_cycle=1.0,
        min_on_time_s=60.0,
        min_off_time_s=10.0,
        max_shed_minutes=None,
        priority_default="deferrable",
        comfort_constraint_notes="Can defer overnight; no comfort impact",
    ),
    LoadProfile(
        appliance_type="ceiling_fan",
        rated_power_kw=0.075,
        typical_on_hours_per_day=16.0,
        duty_cycle=1.0,
        min_on_time_s=10.0,
        min_off_time_s=10.0,
        max_shed_minutes=15.0,
        priority_default="essential",
        comfort_constraint_notes="Essential in Indian summer; 15 min max shed",
    ),
    LoadProfile(
        appliance_type="water_pump",
        rated_power_kw=0.75,
        typical_on_hours_per_day=2.0,
        duty_cycle=1.0,
        min_on_time_s=60.0,
        min_off_time_s=60.0,
        max_shed_minutes=20.0,
        priority_default="essential",
        comfort_constraint_notes="Sump tank provides 20 min buffer",
    ),
    LoadProfile(
        appliance_type="refrigerator",
        rated_power_kw=0.15,
        typical_on_hours_per_day=24.0,
        duty_cycle=0.4,
        min_on_time_s=30.0,
        min_off_time_s=30.0,
        max_shed_minutes=15.0,
        priority_default="essential",
        comfort_constraint_notes="Food safety limit ~15 min; compressor duty cycle ~40%",
    ),
    LoadProfile(
        appliance_type="medical_device",
        rated_power_kw=0.5,
        typical_on_hours_per_day=24.0,
        duty_cycle=1.0,
        min_on_time_s=0.0,
        min_off_time_s=0.0,
        max_shed_minutes=None,
        priority_default="critical",
        comfort_constraint_notes="NEVER shed — life safety equipment",
    ),
    LoadProfile(
        appliance_type="inverter_backed_load",
        rated_power_kw=0.3,
        typical_on_hours_per_day=24.0,
        duty_cycle=1.0,
        min_on_time_s=0.0,
        min_off_time_s=0.0,
        max_shed_minutes=None,
        priority_default="critical",
        comfort_constraint_notes="Has battery backup; should not be shed from grid",
    ),
    LoadProfile(
        appliance_type="lighting_led",
        rated_power_kw=0.04,
        typical_on_hours_per_day=8.0,
        duty_cycle=1.0,
        min_on_time_s=5.0,
        min_off_time_s=5.0,
        max_shed_minutes=10.0,
        priority_default="essential",
        comfort_constraint_notes="LED panel; 10 min max shed for safety",
    ),
]

# Lookup by type name
PROFILE_BY_TYPE: dict[str, LoadProfile] = {p.appliance_type: p for p in INDIAN_PROFILES}


# ---------------------------------------------------------------------------
# Typical Indian building appliance mixes
# ---------------------------------------------------------------------------

# Weight probabilities for each appliance type in a typical Indian home
_APPLIANCE_WEIGHTS: dict[str, float] = {
    "split_ac_1ton": 0.5,
    "split_ac_1_5ton": 0.3,
    "geyser_15l": 0.6,
    "ev_charger_2wheeler": 0.3,
    "ev_charger_car": 0.15,
    "ceiling_fan": 0.95,    # almost every home
    "water_pump": 0.7,
    "refrigerator": 0.9,
    "medical_device": 0.1,
    "inverter_backed_load": 0.4,
    "lighting_led": 0.95,
}


def generate_building_config(
    building_id: str,
    weight_k: int = 1,
    seed: int = 42,
) -> BuildingConfig:
    """
    Generate a realistic Indian building config with a random mix of appliances.

    Fully reproducible given the same seed. Typical result: 4-8 appliances.

    Parameters
    ----------
    building_id : unique ID for this building
    weight_k    : how many real buildings this twin represents
    seed        : random seed for appliance selection
    """
    rng = np.random.default_rng(seed)

    appliances: list[ApplianceConfig] = []
    idx = 0

    for profile in INDIAN_PROFILES:
        prob = _APPLIANCE_WEIGHTS.get(profile.appliance_type, 0.5)
        # Decide how many of this appliance (0, 1, or 2 for fans/lights)
        if profile.appliance_type in ("ceiling_fan", "lighting_led"):
            count = int(rng.binomial(3, prob))  # 0-3 units
        else:
            count = 1 if rng.random() < prob else 0

        for _ in range(count):
            idx += 1
            appliances.append(
                ApplianceConfig(
                    appliance_id=f"{building_id}_A{idx:02d}",
                    appliance_type=profile.appliance_type,
                    priority=profile.priority_default,
                    rated_power_kw=profile.rated_power_kw,
                    min_on_time_s=profile.min_on_time_s,
                    min_off_time_s=profile.min_off_time_s,
                    max_shed_minutes=profile.max_shed_minutes,
                    enrolled=True,
                )
            )

    # Guarantee at least one appliance (a ceiling fan)
    if not appliances:
        idx += 1
        fan = PROFILE_BY_TYPE["ceiling_fan"]
        appliances.append(
            ApplianceConfig(
                appliance_id=f"{building_id}_A{idx:02d}",
                appliance_type=fan.appliance_type,
                priority=fan.priority_default,
                rated_power_kw=fan.rated_power_kw,
                min_on_time_s=fan.min_on_time_s,
                min_off_time_s=fan.min_off_time_s,
                max_shed_minutes=fan.max_shed_minutes,
                enrolled=True,
            )
        )

    return BuildingConfig(
        building_id=building_id,
        weight_k=weight_k,
        appliances=appliances,
    )
