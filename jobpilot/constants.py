"""Shared constants for JobPilot AI.

Includes AI-relevance filtering phrases, salary thresholds, and default search
scopes. These constants are shared across scraping, analysis, and UI layers.
"""

from __future__ import annotations

import re

RELEVANT_PHRASES = [
    "ai",
    "artificial intelligence",
    "ml",
    "machine learning",
    "data science",
    "data scientist",
    "data engineer",
    "nlp",
    "natural language processing",
    "computer vision",
    "deep learning",
    "ai engineer",
    "ai agent engineer",
    "ai agent",
    "agentic ai engineer",
    "ai researcher",
    "research engineer",
    "mlops",
    "machine learning engineer",
    "ml engineer",
    "senior ml engineer",
    "staff ml engineer",
    "principal ml engineer",
    "ai software engineer",
    "ml infrastructure engineer",
    "mlops engineer",
    "deep learning engineer",
    "computer vision engineer",
    "nlp engineer",
    "speech recognition engineer",
    "reinforcement learning engineer",
    "ai research scientist",
    "machine learning researcher",
    "research scientist",
    "applied scientist",
    "principal researcher",
    "generative ai engineer",
    "rag engineer",
    "retrieval-augmented generation developer",
    "rag pipeline engineer",
    "ai agent developer",
    "gpu machine learning engineer",
    "cuda engineer",
    "performance engineer",
    "deep learning compiler engineer",
    "gpgpu engineer",
    "ml acceleration engineer",
    "ai hardware engineer",
    "cuda libraries engineer",
    "tensorrt engineer",
    "ai solutions architect",
    "ai architect",
    "ai platform architect",
    "agentic",
]

AI_REGEX = re.compile(
    r"(?i)\b(" + "|".join(re.escape(p) for p in RELEVANT_PHRASES) + r")\b"
)

SEARCH_KEYWORDS = ["ai", "machine learning", "data science"]
SEARCH_LOCATIONS = ["USA", "Remote"]

# Salary filtering constants
SALARY_UNBOUNDED_THRESHOLD = 750_000  # Values at or above this are unbounded
SALARY_DEFAULT_MIN = 0
SALARY_DEFAULT_MAX = SALARY_UNBOUNDED_THRESHOLD

# UI constants for the salary slider
SALARY_SLIDER_STEP = 25_000
SALARY_SLIDER_FORMAT = "$%dk"

# Remote-type markers used by the normalizer
REMOTE_MARKERS = ("remote", "work from home", "wfh", "anywhere")
HYBRID_MARKERS = ("hybrid", "mix of", "in-office")

# A broad skills lexicon used by the deterministic (offline) analysis fallback.
SKILLS_LEXICON = [
    "python",
    "java",
    "javascript",
    "typescript",
    "golang",
    "go",
    "rust",
    "c++",
    "c#",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "sql",
    "bash",
    "powershell",
    "r",
    "matlab",
    "pytorch",
    "tensorflow",
    "keras",
    "jax",
    "scikit-learn",
    "pandas",
    "numpy",
    "huggingface",
    "transformers",
    "langchain",
    "llamaindex",
    "spark",
    "kafka",
    "airflow",
    "dbt",
    "docker",
    "kubernetes",
    "k8s",
    "terraform",
    "ansible",
    "aws",
    "gcp",
    "azure",
    "sagemaker",
    "vertex ai",
    "azure ml",
    "mlflow",
    "wandb",
    "fastapi",
    "flask",
    "django",
    "rails",
    "react",
    "vue",
    "angular",
    "node",
    "express",
    "graphql",
    "redis",
    "postgresql",
    "postgres",
    "mysql",
    "mongodb",
    "elasticsearch",
    "dynamodb",
    "snowflake",
    "bigquery",
    "redshift",
    "databricks",
    "git",
    "ci/cd",
    "jenkins",
    "github actions",
    "gitlab ci",
    "ollama",
    "vllm",
    "triton",
    "cuda",
    "tensorrt",
    "onnx",
    "opencv",
    "linux",
    "rest",
    "grpc",
]

# Education levels, ordered from least to most advanced.
EDUCATION_LEVELS = [
    "high school",
    "associate",
    "bachelor",
    "bachelors",
    "master",
    "masters",
    "msc",
    "mba",
    "phd",
    "doctorate",
]

# Experience-level buckets used for seniority normalization.
EXPERIENCE_LEVELS = [
    "entry",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
]
