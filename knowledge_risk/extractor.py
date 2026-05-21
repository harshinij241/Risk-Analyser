import math
import ast
from collections import defaultdict
from datetime import datetime
from typing import Optional
from models import FileCommit, RawFeatures
from filters import filter_commits

DECISION_KEYWORDS = {
    'python': ['if ', 'elif ', 'else:', 'for ', 'while ',
            'except', 'and ', 'or ', 'not '],
    'javascript': ['if ', 'else ', 'for ', 'while ', 'switch',
                'catch', '&&', '||', '? '],
    'java': ['if ', 'else ', 'for ', 'while ', 'switch',
            'catch', '&&', '||', '? '],
    'default': ['if ', 'else', 'for ', 'while ', 'switch',
                'catch', 'except', '&&', '||']
}

def detect_language(file_path: str) -> str:
    ext_map = {
        '.py': 'python', '.js': 'javascript', '.ts': 'javascript',
        '.java': 'java', '.go': 'default', '.rb': 'default'
    }
    for ext, lang in ext_map.items():
        if file_path.endswith(ext):
            return lang
    return 'default'


def compute_hhi_raw(commits: list[FileCommit]) -> tuple[float, list[tuple]]:
    """
    Returns HHI and ranked author shares.
    Uses meaningful commits only, weighted by lines changed.
    """
    meaningful = filter_commits(commits)
    if not meaningful:
        return 1.0, []

    author_lines = defaultdict(int)
    for c in meaningful:
        author_lines[c.author] += c.lines_changed

    total = sum(author_lines.values())
    if total == 0:
        return 1.0, []

    shares = {a: lines / total for a, lines in author_lines.items()}
    hhi = sum(s ** 2 for s in shares.values())

    ranked = sorted(shares.items(), key=lambda x: x[1], reverse=True)
    return round(hhi, 4), ranked[:3]


def compute_recency_raw(commits: list[FileCommit],
                        lambda_decay: float = 0.005
                        ) -> tuple[float, float, Optional[datetime]]:
    """
    Returns:
    - decayed_recency (staleness): 0 = fresh, 1 = fully stale
    - living_knowledge: 0 = nobody remembers, 1 = fully retained
    - last_meaningful_commit datetime
    """
    meaningful = filter_commits(commits)
    if not meaningful:
        return 1.0, 0.0, None

    # Per author: contribution share + age of most recent commit
    author_lines = defaultdict(int)
    author_min_age = {}   # min age = most recent

    for c in meaningful:
        author_lines[c.author] += c.lines_changed
        age = c.age_days
        if c.author not in author_min_age:
            author_min_age[c.author] = age
        else:
            author_min_age[c.author] = min(author_min_age[c.author], age)

    total_lines = sum(author_lines.values())
    if total_lines == 0:
        return 1.0, 0.0, None

    living_knowledge = 0.0
    for author, lines in author_lines.items():
        share = lines / total_lines
        decay = math.exp(-lambda_decay * author_min_age[author])
        living_knowledge += share * decay

    living_knowledge = round(min(living_knowledge, 1.0), 4)
    decayed_recency = round(1.0 - living_knowledge, 4)

    # Most recent meaningful commit across all authors
    last_commit = min(meaningful, key=lambda c: c.age_days).timestamp

    return decayed_recency, living_knowledge, last_commit


def compute_complexity_raw(file_path: str) -> dict:
    """
    Returns raw complexity signals — not normalized.
    Uses AST for Python files, keyword proxy for others.
    """
    try:
        with open(file_path, 'r', errors='ignore') as f:
            source = f.read()
            lines = source.splitlines()
    except FileNotFoundError:
        return {'loc': 0, 'decisions': 0, 'imports': 0, 
                'method': 'unavailable'}

    loc = len([l for l in lines if l.strip()])

    # Try AST-based for Python (much more accurate)
    if file_path.endswith('.py'):
        try:
            tree = ast.parse(source)
            decisions = sum(
                1 for node in ast.walk(tree)
                if isinstance(node, (
                    ast.If, ast.For, ast.While, ast.ExceptHandler,
                    ast.With, ast.Assert, ast.BoolOp
                ))
            )
            imports = sum(
                1 for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            )
            return {'loc': loc, 'decisions': decisions,
                    'imports': imports, 'method': 'ast'}
        except SyntaxError:
            pass  # fall through to keyword proxy

    # Keyword proxy for everything else
    lang = detect_language(file_path)
    keywords = DECISION_KEYWORDS.get(lang, DECISION_KEYWORDS['default'])
    decisions = sum(
        1 for line in lines
        for kw in keywords
        if kw in line
    )
    imports = sum(
        1 for line in lines
        if line.strip().startswith(
            ('import ', 'from ', 'require(', '#include', 'use ')
        )
    )
    return {'loc': loc, 'decisions': decisions,
            'imports': imports, 'method': 'keyword_proxy'}


def compute_churn_raw(commits: list[FileCommit],
                    window_days: int = 90) -> dict:
    """
    Returns raw churn signals over a rolling window.
    """
    meaningful = filter_commits(commits)
    recent = [c for c in meaningful if c.age_days <= window_days]

    return {
        'commit_count': len(recent),
        'lines_changed': sum(c.lines_changed for c in recent),
        'unique_authors': len(set(c.author for c in recent)),
        'window_days': window_days
    }


def extract_raw_features(file_path: str,
                        commits: list[FileCommit]) -> RawFeatures:
    """
    Single entry point. Extracts all raw features for one file.
    No normalization happens here.
    """
    meaningful = filter_commits(commits)

    hhi, top_authors = compute_hhi_raw(commits)
    decayed_recency, living_knowledge, last_commit = compute_recency_raw(commits)
    complexity = compute_complexity_raw(file_path)
    churn = compute_churn_raw(commits)

    file_age = (datetime.now() - min(
        c.timestamp for c in commits
    )).days if commits else 0

    return RawFeatures(
        file_path=file_path,
        hhi=hhi,
        decayed_recency=decayed_recency,
        complexity=complexity,
        churn=churn,
        total_commits=len(commits),
        unique_authors=len(set(c.author for c in meaningful)),
        file_age_days=file_age,
        has_sparse_history=len(meaningful) < 3
    )