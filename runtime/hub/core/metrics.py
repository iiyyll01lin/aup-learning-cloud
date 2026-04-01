from prometheus_client import Counter, Gauge, Histogram

# GPU spawn attempts
spawn_gpu_total = Counter(
    "hub_spawn_gpu_total",
    "GPU spawn attempts",
    ["accelerator"],
)

# Spawn failures
spawn_failed_total = Counter(
    "hub_spawn_failed_total",
    "Failed spawn attempts",
    ["reason"],
)

# Active sessions (derived from running usage sessions)
hub_active_sessions = Gauge(
    "hub_active_sessions",
    "Active running user sessions",
)

# Session runtime histogram
session_runtime_minutes = Histogram(
    "hub_session_runtime_minutes",
    "Container runtime in minutes",
    buckets=[5, 15, 30, 60, 120, 360],
)

# Spawn duration (seconds)
spawn_duration_seconds = Histogram(
    "hub_spawn_duration_seconds",
    "Time spent spawning user containers",
    buckets=[1, 2, 5, 10, 20, 30, 60, 120, 300],
)

# Quota denied
quota_denied_total = Counter(
    "hub_quota_denied_total",
    "Quota denied events",
    ["reason"],
)

# Quota consumption
quota_deducted_total = Counter(
    "hub_quota_deducted_total",
    "Quota consumed",
)

# Pod failures
pod_failure_total = Counter(
    "hub_pod_failure_total",
    "Pod failures",
    ["reason"],
)

# Git clone failures
repo_clone_failed_total = Counter(
    "hub_repo_clone_failed_total",
    "Repository clone failures",
)
