#!/usr/bin/env bash
# Dental AI GitHub issue -> local coding agent bridge (Termux)
set -Eeuo pipefail
REPO="dentalaidestek/dental-ai-v02"
BRANCH="feature/mobile-web-parity-20261110"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v gh >/dev/null || { echo "GitHub CLI (gh) bulunamadi. pkg install gh"; exit 1; }
command -v codex >/dev/null || { echo "Codex CLI bulunamadi veya Termux'ta calismiyor."; exit 1; }
gh auth status >/dev/null || { echo "Once gh auth login yap."; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Kaydedilmemis degisiklikler var, durduruldu."; exit 1; }
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "Yanlis dal, durduruldu."; exit 1; }
git pull --ff-only origin "$BRANCH"
mkdir -p .agent-local
issue="$(gh issue list -R "$REPO" --state open --label termux-agent --json number,author --jq '[.[]|select(.author.login=="dentalaidestek")]|sort_by(.number)|.[0].number // empty')"
if [[ -z "$issue" ]]; then echo "Yeni termux-agent gorevi yok."; exit 0; fi
body="$(gh issue view "$issue" -R "$REPO" --json body --jq .body)"
[[ -n "$body" ]] || { echo "Bos gorev."; exit 1; }
prompt_file=".agent-local/task-$issue.txt"
printf '%s\n' "Repo: $REPO" "Work only on $BRANCH. Do not deploy, merge, access secrets, or run destructive commands. Preserve clinical patient isolation. Inspect source before changing code. Run relevant tests. Do not weaken tests merely to make them pass. Task:" "$body" > "$prompt_file"
echo "Gorev #$issue basliyor; kodlama ajani yerelde calisacak."
codex exec --sandbox workspace-write - < "$prompt_file"
echo "Ajan bitti. Degisiklikler:"
git status --short
echo "Otomatik commit/push yapilmadi. Kontrol ve onay sonrasi gonderilebilir."
