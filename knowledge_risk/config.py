from dataclasses import dataclass, field


@dataclass
class DecayConfig:
    """Controls how fast knowledge is considered stale."""
    lambda_decay: float = 0.005
    # 0.005 → ~50% retained after 6 months
    # 0.003 → slower decay, for stable long-lived codebases
    # 0.008 → faster decay, for fast-moving teams


@dataclass
class WeightConfig:
    """Formula weights. Must sum to 1.0 for the fragility term."""
    ownership: float = 0.45
    recency: float   = 0.25
    complexity: float = 0.20
    churn: float     = 0.10

    def __post_init__(self):
        fragility_sum = self.ownership + self.recency
        amplifier_sum = self.complexity + self.churn
        if not (0.99 <= fragility_sum <= 1.01):  # float tolerance
            raise ValueError(
                f"Ownership + Recency must sum to ~1.0, got {fragility_sum:.3f}"
            )
        if not (0.29 <= amplifier_sum <= 0.31):
            raise ValueError(
                f"Complexity + Churn must sum to ~0.30, got {amplifier_sum:.3f}"
            )


@dataclass
class ChurnConfig:
    """Controls churn measurement window and weighting."""
    window_days: int    = 90
    commit_weight: float = 0.6
    lines_weight: float  = 0.4


@dataclass
class ComplexityConfig:
    """Controls how raw complexity signals are combined."""
    loc_weight: float       = 0.5
    decisions_weight: float = 0.3
    imports_weight: float   = 0.2


@dataclass
class ConfidenceConfig:
    """Thresholds for confidence level computation."""
    min_commits_high: int   = 10
    min_commits_medium: int = 3
    min_file_age_days: int  = 30
    min_authors_for_hhi: int = 2
    stale_threshold: float  = 0.95   # decayed_recency above this = FULLY_STALE
    high_churn_commits: int = 30     # commits in window = HIGH_CHURN


@dataclass
class FilterConfig:
    """Controls what gets excluded before analysis."""
    bot_patterns: list[str] = field(default_factory=lambda: [
        'bot', 'dependabot', 'renovate', 'github-actions',
        'ci-runner', 'automated', 'semantic-release',
        'snyk', 'greenkeeper', 'imgbot'
    ])
    exclude_globs: list[str] = field(default_factory=lambda: [
        '*.lock', '*-lock.json', '*.min.js', '*.min.css',
        '*.generated.*', '*.pb.go', '*.pb.py', '*.pb.ts',
        'migrations/*', 'dist/*', 'build/*', '__pycache__/*',
        '*.snap', 'vendor/*', 'node_modules/*', '*.sum'
    ])
    trivial_commit_patterns: list[str] = field(default_factory=lambda: [
        'bump version', 'update changelog', 'merge branch',
        'merge pull request', 'auto-format', 'lint fix',
        'fix typo', 'update dependencies'
    ])
    min_lines_changed: int = 1   # commits below this are trivial


@dataclass
class PipelineConfig:
    """Top-level pipeline behaviour."""
    top_n: int              = 20     # files to return for LLM summarization
    min_file_age_days: int  = 0      # 0 = include all files
    follow_renames: bool    = True   # use git --follow
    max_commits_per_file: int = 500  # cap to avoid huge repo slowdowns



@dataclass
class RiskConfig:
    """
    Master config. Pass this single object through the pipeline.
    All submodules read from it — nothing is hardcoded elsewhere.
    """
    decay: DecayConfig      = field(default_factory=DecayConfig)
    weights: WeightConfig   = field(default_factory=WeightConfig)
    churn: ChurnConfig      = field(default_factory=ChurnConfig)
    complexity: ComplexityConfig = field(default_factory=ComplexityConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    filters: FilterConfig   = field(default_factory=FilterConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)


# ── Preset configurations ──────────────────────────────────────────────────
# Ready-made configs for common team types.
# Users can start with a preset and override specific values.

def preset_fast_moving_team() -> RiskConfig:
    """
    For startups or teams shipping multiple times per day.
    Faster decay, higher churn sensitivity.
    """
    config = RiskConfig()
    config.decay.lambda_decay = 0.008
    config.churn.window_days = 60
    config.confidence.high_churn_commits = 20
    return config


def preset_stable_enterprise() -> RiskConfig:
    """
    For mature codebases with slow, deliberate change cycles.
    Slower decay, longer churn window.
    """
    config = RiskConfig()
    config.decay.lambda_decay = 0.003
    config.churn.window_days = 180
    config.confidence.min_commits_high = 20
    return config


def preset_open_source() -> RiskConfig:
    """
    For open source repos with many transient contributors.
    Higher bar for meaningful authorship, wider bot filter.
    """
    config = RiskConfig()
    config.filters.min_lines_changed = 5  # ignore tiny patches
    config.confidence.min_authors_for_hhi = 3
    config.filters.bot_patterns.extend([
        'allcontributors', 'stale', 'codecov', 'netlify'
    ])
    return config


# ── YAML/JSON loading ──────────────────────────────────────────────────────

def load_from_dict(data: dict) -> RiskConfig:
    """
    Load config from a parsed YAML or JSON dict.
    Supports partial overrides — unspecified keys use defaults.

    Example .knowledge-risk.yml:
        decay:
            lambda_decay: 0.006
        pipeline:
            top_n: 30
        filters:
            exclude_globs:
                - "*.lock"
                - "generated/*"
    """
    config = RiskConfig()

    if 'decay' in data:
        for k, v in data['decay'].items():
            setattr(config.decay, k, v)

    if 'weights' in data:
        for k, v in data['weights'].items():
            setattr(config.weights, k, v)
        config.weights.__post_init__()  # re-validate after override

    if 'churn' in data:
        for k, v in data['churn'].items():
            setattr(config.churn, k, v)

    if 'complexity' in data:
        for k, v in data['complexity'].items():
            setattr(config.complexity, k, v)

    if 'confidence' in data:
        for k, v in data['confidence'].items():
            setattr(config.confidence, k, v)

    if 'filters' in data:
        for k, v in data['filters'].items():
            setattr(config.filters, k, v)

    if 'pipeline' in data:
        for k, v in data['pipeline'].items():
            setattr(config.pipeline, k, v)

    return config


def load_from_yaml(path: str) -> RiskConfig:
    import yaml
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    return load_from_dict(data or {})


def load_from_json(path: str) -> RiskConfig:
    import json
    with open(path, 'r') as f:
        data = json.load(f)
    return load_from_dict(data)