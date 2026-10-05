"""ThermWatch intelligence core.

Self-contained package: FIRMS observations -> validated observations -> stateful
sources/events -> historical profile -> robust baseline -> §14 assessment object.

It does not import the legacy pipeline modules (baseline.py, normalize.py, ...) and
does not touch the frontend. See docs/THERMWATCH_CORE.md.
"""
from .schema import PIPELINE_VERSION, SCHEMA_VERSION, DataMode, Observation  # noqa: F401
