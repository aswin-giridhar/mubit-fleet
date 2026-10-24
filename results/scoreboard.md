# Scoreboard

40 generated incidents (seed 61), identical for every model. Correct = the advice matches the fleet policy for the injected cause and passes the safety validator.

| | claude-sonnet-4-5 | claude-haiku-4-5 |
|---|---|---|
| Correct advice | 90% | 72% |
| Unsafe advice blocked by code | 0 | 1 |
| Escalated to a human | 40% | 42% |
| Latency p50 / p90 | 9.5s / 12.3s | 5.3s / 6.8s |
| Calls per incident | 2.4 | 2.2 |
| Tokens per incident (in / out) | 3610 / 419 | 3296 / 437 |
| Est. $ per 1,000 incidents | $17.11 | $5.48 |

## Correct advice by incident type

| | claude-sonnet-4-5 | claude-haiku-4-5 |
|---|---|---|
| double_parked_short | 4/4 | 3/4 |
| double_parked_abandoned | 4/4 | 3/4 |
| construction_closure | 2/4 | 2/4 |
| police_hand_signals | 4/4 | 4/4 |
| emergency_vehicle | 4/4 | 3/4 |
| debris_small | 4/4 | 4/4 |
| debris_large | 4/4 | 1/4 |
| sensor_degraded | 4/4 | 4/4 |
| rider_safety | 4/4 | 4/4 |
| conflicting_reports | 2/4 | 1/4 |

Costs are estimates from list prices; latency is measured end to end through Mubit.
