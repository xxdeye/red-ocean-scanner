#!/usr/bin/env bash
# 给仓库设置 description 与 topics。
#
# 为什么需要这个脚本：git push 走的是 SSH key，而 GitHub 的仓库设置
# （description / topics）只能通过 REST API 修改，需要 Personal Access Token。
# SSH key 无法用于 API 鉴权。
#
# 用法：
#   1. 建一个 token（见 README 或下方说明）
#   2. export GITHUB_TOKEN=ghp_xxx    # 或 gh auth login 后运行
#   3. ./scripts/set_repo_meta.sh
#
# token 权限要求（fine-grained token）：
#   Repository access → 只选 xxdeye/red-ocean-scanner
#   Permissions → Repository permissions → Metadata: Read and write
#   这是最小权限，只能改仓库元信息，不能读代码、不能推送，也不能删仓库。
set -euo pipefail

REPO="${REPO:-xxdeye/red-ocean-scanner}"
DESCRIPTION="Validate a product idea before building it — measures supply and search demand, returns a red/yellow/green verdict. Global + Chinese markets, no API keys."
TOPICS='["red-ocean","blue-ocean","niche-validation","market-research","app-store","github-api","china","claude-skills","agent-skills","indie-hacker","product-validation","geo-arbitrage"]'

if [ -z "${GITHUB_TOKEN:-}" ]; then
  # 若装了 gh CLI 且已登录，直接借用它的凭据
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    GITHUB_TOKEN="$(gh auth token)"
    echo "使用 gh CLI 的凭据"
  else
    echo "缺少 GITHUB_TOKEN。请先：" >&2
    echo "  export GITHUB_TOKEN=ghp_xxx" >&2
    echo "或安装并登录 gh CLI：gh auth login" >&2
    exit 1
  fi
fi

api() {  # method path json_body
  curl -sS -X "$1" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}$2" \
    ${3:+-d "$3"}
}

echo "==> 写入 description"
api PATCH "" "$(python3 -c '
import json,os
print(json.dumps({"description": os.environ["DESCRIPTION"]}))
' DESCRIPTION="$DESCRIPTION")" >/dev/null

echo "==> 写入 topics"
api PUT /topics "$(python3 -c '
import json,os
print(json.dumps({"names": json.loads(os.environ["TOPICS"])}))
' TOPICS="$TOPICS")" >/dev/null

echo "==> 当前状态"
api GET "" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("  仓库:      ", d.get("full_name"))
print("  visibility:", d.get("visibility"))
print("  description:", d.get("description"))
print("  topics:    ", ", ".join(d.get("topics") or []) or "(空)")
'
