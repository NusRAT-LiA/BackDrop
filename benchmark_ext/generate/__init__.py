"""benchmark_ext.generate: the authoring pipeline (mirrors appworld/generate/).

Task templates are code (`tasks/task_generators/`, one `Scenario` per stock scenario); task instances are pure
data under `benchmark_ext/data/tasks/<family>_<variant>/`, in the exact AppWorld anatomy. `emit.py` writes
them and re-checks the stock no-op floor on each.
"""
