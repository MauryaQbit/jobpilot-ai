"""Discovery pipeline package for JobPilot AI."""

from __future__ import annotations

from jobpilot.pipeline.deduplicator import Deduplicator, DedupResult, deduplicator
from jobpilot.pipeline.enricher import Enricher, enricher
from jobpilot.pipeline.normalizer import Normalizer, normalizer
from jobpilot.pipeline.orchestrator import (
    DiscoveryPipeline,
    PipelineResult,
    discovery_pipeline,
)

__all__ = [
    "DedupResult",
    "Deduplicator",
    "DiscoveryPipeline",
    "Enricher",
    "Normalizer",
    "PipelineResult",
    "deduplicator",
    "discovery_pipeline",
    "enricher",
    "normalizer",
]
