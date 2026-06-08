import fnmatch
from .models import FileCommit
from enum import Enum

class FileType(Enum):
    SOURCE_CODE  = "source_code"
    CONFIG       = "config"
    ARTIFACT     = "artifact"
    BINARY       = "binary"
    DOCS         = "docs"
    UNKNOWN      = "unknown"

SOURCE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx',
    '.java', '.go', '.rb', '.rs', '.cpp',
    '.c', '.cs', '.php', '.swift', '.kt',
    '.scala', '.r', '.m', '.h'
}

CONFIG_EXTENSIONS = {
    '.json', '.yml', '.yaml', '.toml',
    '.ini', '.cfg', '.conf', '.env'
}

BINARY_EXTENSIONS = {
    '.phar', '.exe', '.dll', '.so',
    '.bin', '.jar', '.war', '.class',
    '.png', '.jpg', '.gif', '.pdf'
}

DOC_EXTENSIONS = {
    '.md', '.rst', '.txt', '.adoc'
}

BOT_PATTERNS = [
    'bot', 'dependabot', 'renovate', 'github-actions',
    'ci-runner', 'automated', 'semantic-release',
    'snyk', 'greenkeeper', 'imgbot'
]

EXCLUDE_GLOBS = [
    '*.lock', '*-lock.json', '*.sum',
    '*.min.js', '*.min.css', '*.generated.*',
    '*.pb.go', '*.pb.py', '*.pb.ts', '*.snap',
    'dist/*', 'build/*', '__pycache__/*',
    'vendor/*', 'node_modules/*',
    '*.phar', '*.exe', '*.dll', '*.so',
    '*.bin', '*.jar', '*.war', '*.class',
    '.gitignore', '.gitattributes',
    '.editorconfig', '.prettierrc',
    '.eslintrc', '.eslintrc.*',
    '*.md', '*.rst', '*.txt',
    'LICENSE', 'LICENCE', 'CHANGELOG',
    'Dockerfile', 'Makefile',
    '*.yml', '*.yaml',
    '*.toml', '*.ini', '*.cfg',
    '*.env.example','migrations/*',
    'composer.phar',
]

def classify_file(file_path: str) -> FileType:
    """
    Classifies a file before it enters the risk pipeline.
    Only SOURCE_CODE files should get full risk analysis.
    """
    import os
    ext  = os.path.splitext(file_path)[1].lower()
    name = os.path.basename(file_path).lower()

    if ext in BINARY_EXTENSIONS:
        return FileType.BINARY
    if ext in DOC_EXTENSIONS:
        return FileType.DOCS
    if ext in CONFIG_EXTENSIONS:
        return FileType.CONFIG
    if name in {'.gitignore', '.gitattributes',
                'makefile', 'dockerfile'}:
        return FileType.CONFIG
    if ext in SOURCE_EXTENSIONS:
        return FileType.SOURCE_CODE

    return FileType.UNKNOWN


def should_analyze(file_path: str) -> bool:
    """
    Returns True only for files worth full risk analysis.
    Everything else is excluded before scoring even starts.
    """
    if is_excluded_file(file_path):
        return False

    file_type = classify_file(file_path)
    return file_type == FileType.SOURCE_CODE


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