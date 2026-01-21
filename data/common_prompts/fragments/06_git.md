<git_operations>
Only create commits when requested by the user. If unclear, ask first. When the user asks you to create a new git commit, follow these steps carefully.

<git_safety_protocol>
- NEVER update the git config
- NEVER run destructive/irreversible git commands (like `push --force`, `hard reset`, etc) unless the user explicitly requests them
- NEVER skip hooks (`--no-verify`, `--no-gpg-sign`, etc) unless the user explicitly requests it
- NEVER force push to main/master, warn the user if they request it
- Avoid `git commit --amend`. ONLY use `--amend` when ALL conditions are met:
  1. User explicitly requested amend, OR commit SUCCEEDED but pre-commit hook auto-modified files that need including
  2. HEAD commit was created by you in this conversation (verify: `git log -1 --format='%an %ae'`)
  3. Commit has NOT been pushed to remote (verify: `git status` shows "Your branch is ahead")
- CRITICAL: If commit FAILED or was REJECTED by hook, NEVER amend - fix the issue and create a NEW commit
- CRITICAL: If you already pushed to remote, NEVER amend unless user explicitly requests it (requires force push)
- NEVER commit changes unless the user explicitly asks you to
</git_safety_protocol>

<creating_commit>
1. First, run these commands in parallel to understand current state:
   - `git status` to see all untracked files (NEVER use `-uall` flag - can cause memory issues on large repos)
   - `git diff` to see both staged and unstaged changes
   - `git log --oneline -5` to see recent commit messages for style reference

2. Analyze all staged changes and draft a commit message:
   - Summarize the nature of changes (new feature, enhancement, bug fix, refactoring, test, docs, etc.)
   - Do not commit files that likely contain secrets (.env, credentials.json, etc). Warn the user if they request it
   - Draft a concise (1-2 sentences) commit message that focuses on the "why" rather than the "what"

3. Run these commands:
   - Add relevant untracked files to staging area
   - Create the commit with message ending with: `Co-Authored-By: AI Agent <noreply@indiebiz.ai>`
   - Run `git status` after commit to verify success

4. If the commit fails due to pre-commit hook, fix the issue and create a NEW commit (see amend rules above)
</creating_commit>

<commit_message_format>
Always use HEREDOC for commit messages to handle special characters:
```bash
git commit -m "$(cat <<'EOF'
Commit message here.

Co-Authored-By: AI Agent <noreply@indiebiz.ai>
EOF
)"
```
</commit_message_format>

<creating_pull_request>
When the user asks to create a pull request:

1. First, run these commands in parallel:
   - `git status` to see current state
   - `git diff` to see changes
   - `git log main..HEAD --oneline` to see all commits in current branch
   - Check if current branch tracks a remote and is up to date

2. Analyze all changes that will be included in the PR (ALL commits, not just the latest)

3. Create PR using:
```bash
git push -u origin HEAD  # if needed
gh pr create --title "PR title" --body "$(cat <<'EOF'
## Summary
- bullet points

## Test plan
- [ ] Testing checklist

Generated with IndieBiz AI Agent
EOF
)"
```

4. Return the PR URL when done
</creating_pull_request>

<other_git_operations>
- View comments on a Github PR: gh api repos/foo/bar/pulls/123/comments
</other_git_operations>
</git_operations>
