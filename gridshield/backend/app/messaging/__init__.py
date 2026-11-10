"""
Messaging layer for GridShield.

Provides an in-process publish/subscribe bus with optional fault injection
(message loss, delay, duplication, out-of-order delivery). Topic structure
mirrors MQTT for future compatibility. MQTT/Mosquitto is a stretch goal
and is NOT used in Phase 1.
"""
