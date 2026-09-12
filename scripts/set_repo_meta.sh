#!/usr/bin/env bash
# 给仓库设置 description 与 topics。
#
# 为什么需要这个脚本：git push 走的是 SSH key，而 GitHub 的仓库设置
# （description / topics）只能通过 REST API 修改，需要 Personal Access Token。
# SSH key 无法用于 API 鉴权。
#
# 建 token 的页面：
#   fine-grained（推荐）: https://github.com/settings/personal-access-tokens/new
#   注意：不要用 https://github.com/settings/tokens/new（那是 classic，权限过宽）
#
# 用法：
#   1. 建一个 token（见下方权限说明）
#   2. export GITHUB_TOKEN=ghp_xxx    # 或 gh auth login 后运行
#   3. ./scripts/set_repo_meta.sh
#
# token 权限要求（fine-grained token）——两个端点都要 Administration: write：
#   PATCH /repos/{owner}/{repo}          → Administration (write)
#   PUT   /repos/{owner}/{repo}/topics   → Administration (write)
# 注意：Metadata (read) 不够，那只够读。Actions 里也读不到代码内容。
# Repository access → Only select repositories → 只勾 xxdeye/red-ocean-scanner
# Permissions → Repository permissions → Administration → Read and write
#   （其余权限全部保持 No access）
#
# 安全做法：把 Expiration 设成 7 天或更短，用完立刻 Revoke。
#
# 若用 classic token（不推荐，权限过宽）：需要 repo scope。
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

api() {  # method path [json_body]
  # 用数组拼参数，避免 ${3:+...} 在空值时产生多余参数
  local args=(-sS -X "$1"
    -H "Authorization: Bearer ${GITHUB_TOKEN}"
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28")
  [ -n "${3:-}" ] && args+=(-d "$3")
  args+=("https://api.github.com/repos/${REPO}$2")
  curl "${args[@]}"
}

# 用 argv 传值，不要用 `python3 -c ... NAME=value`——那种写法是把
# NAME=value 当成了 python 的位置参数，不是环境变量，会抛 KeyError 且静默失败。
DESC_JSON="$(python3 -c 'import json,sys; print(json.dumps({"description": sys.argv[1]}))' "$DESCRIPTION")"
TOPICS_JSON="$(python3 -c 'import json,sys; print(json.dumps({"names": json.loads(sys.argv[1])}))' "$TOPICS")"

echo "==> 写入 description"
resp="$(api PATCH "" "$DESC_JSON")"
echo "$resp" | python3 -c '
import json,sys
d=json.load(sys.stdin)
if "message" in d and "description" not in d:
    print("  失败:", d["message"], file=sys.stderr); sys.exit(1)
print("  description →", d.get("description"))
' || exit 1

echo "==> 写入 topics"
resp="$(api PUT /topics "$TOPICS_JSON")"
echo "$resp" | python3 -c '
import json,sys
d=json.load(sys.stdin)
if "message" in d and "names" not in d:
    print("  失败:", d["message"], file=sys.stderr); sys.exit(1)
print("  topics →", ", ".join(d.get("names") or []))
' || exit 1

echo "==> 复核（匿名读取，确认对公众可见）"
curl -sS -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${REPO}" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("  仓库:       ", d.get("full_name"))
print("  visibility: ", d.get("visibility"))
print("  description:", d.get("description"))
print("  topics:     ", ", ".join(d.get("topics") or []) or "(空)")
'
