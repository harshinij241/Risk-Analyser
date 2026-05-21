import fnmatch
from models import FileCommit

BOT_PATTERNS = [
    'bot', 'dependabot', 'renovate', 'github-actions',
    'ci-runner', 'automated', 'semantic-release',
    'snyk', 'greenkeeper', 'imgbot'
]

EXCLUDE_GLOBS = [
    '*.lock', '*-lock.json', '*.min.js', '*.min.css',
    '*.generated.*', '*.pb.go', '*.pb.py', '*.pb.ts',
    'migrations/*', 'dist/*', 'build/*', '__pycache__/*',
    '*.snap', 'vendor/*', 'node_modules/*', '*.sum'
]

def is_bot_commit(commit: FileCommit) -> bool:
    author_lower = commit.author.lower()
    return any(p in author_lower for p in BOT_PATTERNS)

def is_excluded_file(file_path: str) -> bool:
    return any(fnmatch.fnmatch(file_path, pattern) 
            for pattern in EXCLUDE_GLOBS)

def is_meaningful_commit(commit: FileCommit) -> bool:
    """
    Filter out commits that don't represent real understanding.
    Trivial commits: pure formatting, version bumps, merge commits.
    """
    if is_bot_commit(commit):
        return False
    if commit.lines_changed == 0:
        return False

    trivial_patterns = [
        'bump version', 'update changelog', 'merge branch',
        'merge pull request', 'auto-format', 'lint fix',
        'fix typo', 'update dependencies'
    ]
    msg_lower = commit.message.lower()
    if any(p in msg_lower for p in trivial_patterns):
        return False

    return True

def filter_commits(commits: list[FileCommit]) -> list[FileCommit]:
    return [c for c in commits if is_meaningful_commit(c)]