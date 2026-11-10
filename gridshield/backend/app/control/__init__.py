"""
Control layer for GridShield: edge agents and shedding/restoration policies.

Contains:
  - BasePolicy and concrete policy implementations (P0, P1, P2)
  - StaggeredRestorationPolicy (§6.4)
  - EdgeAgent: per-building controller that evaluates policies each tick
"""
