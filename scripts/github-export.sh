#!/bin/sh
# Pushes a commit to the public GitHub repository without coding-agent files (CLAUDE.md, AGENTS.md and the like)
# and without Co-Authored-By trailers in commit messages.
# The rewrite is deterministic, so exporting the same history again gives the same commits and a plain push works.
# Usage: scripts/github-export.sh <commit> <target ref> <remote url>
set -eu

commit=$1
target=$2
remote=$3

git branch -f github-export "$commit"
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --prune-empty --msg-filter '
  awk '"'"'tolower($0) ~ /^co-authored-by:/ { next }
    { line[++n] = $0 }
    END { while (n > 0 && line[n] == "") n--; for (i = 1; i <= n; i++) print line[i] }'"'"'
' --index-filter '
  git rm -r -q --cached --ignore-unmatch -- \
    CLAUDE.md "*/CLAUDE.md" CLAUDE.local.md AGENTS.md "*/AGENTS.md" GEMINI.md "*/GEMINI.md" \
    .claude .cursor .cursorrules .windsurfrules .github/copilot-instructions.md
' github-export >/dev/null

git push "$remote" "refs/heads/github-export:$target"
