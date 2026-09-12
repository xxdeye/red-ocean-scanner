#!/usr/bin/env python3
"""校验本 skill 是否符合 Agent Skills 规范。

规则来自 agentskills.io 规范与头部 skill 仓库实践：
  · name: 1-64 字符，仅小写字母/数字/连字符，且必须与目录名一致
  · description: 1-1024 字符，且含触发语
  · SKILL.md 少于 500 行（超出应拆到 references/）
  · SKILL.md 必须有 YAML frontmatter，含 name 与 description
  · 附带的 .py 脚本必须能通过语法编译

用法: python3 scripts/validate_skill.py
"""
import pathlib
import py_compile
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

RED, GRN, YEL, RST = "\033[0;31m", "\033[0;32m", "\033[1;33m", "\033[0m"
issues = warnings = passed = 0


def count_tokens(text):
    """返回 (token 数, 是否精确)。装了 tiktoken 就精确，否则粗估。"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), True
    except Exception:                                        # noqa: BLE001
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        ascii_ish = len(text) - cjk
        return int(cjk * 1.4 + ascii_ish / 3.5), False


def frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    return m.group(1) if m else None


def parse_fm(fm):
    """无依赖的最小 YAML frontmatter 解析（只支持本 skill 用到的子集）。

    必须真的解析而不只做正则，因为一个真实 bug 只有解析才能抓到：
    `description: >` 是块标量，**空行会终止它**，导致其后的
    `license:` 变成 description 的一部分，frontmatter 静默损坏。
    """
    out, key, buf, block = {}, None, [], False
    for line in fm.split("\n"):
        if key and block:
            if line.strip() == "":            # 空行终止块标量
                out[key] = " ".join(buf).strip()
                key, buf, block = None, [], False
                continue
            if line.startswith((" ", "\t")):
                buf.append(line.strip())
                continue
            out[key] = " ".join(buf).strip()
            key, buf, block = None, [], False
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v in (">", "|", ">-", "|-"):
            key, buf, block = k, [], True
        elif v == "":                          # 嵌套映射（如 metadata:）
            out[k] = {}
            key = None
        else:
            out[k] = v.strip("\"'")
    if key and block:
        out[key] = " ".join(buf).strip()
    return out


def main():
    global issues, warnings, passed
    print("Auditing skills against Agent Skills specification")
    print("=" * 52)

    for d in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        name, errs, warns = d.name, [], []
        f = d / "SKILL.md"
        if not f.exists():
            print(f"{RED}FAIL{RST} {name} — 缺少 SKILL.md")
            issues += 1
            continue

        text = f.read_text(encoding="utf-8")
        fm_raw = frontmatter(text)
        if fm_raw is None:
            errs.append("缺少 YAML frontmatter")
            fm_raw = ""
        fmd = parse_fm(fm_raw)

        # name（规范：1-64 字符，仅 a-z0-9-，不得以连字符开头/结尾，不得连续连字符）
        val = str(fmd.get("name", ""))
        if not val:
            errs.append("frontmatter 缺少 name")
        else:
            if val != name:
                errs.append(f"name '{val}' 与目录名 '{name}' 不一致")
            if not re.fullmatch(r"[a-z0-9-]+", val):
                errs.append("name 只能含小写字母/数字/连字符")
            if len(val) > 64:
                errs.append(f"name 长度 {len(val)}，上限 64")
            if val.startswith("-") or val.endswith("-"):
                errs.append("name 不得以连字符开头或结尾")
            if "--" in val:
                errs.append("name 不得含连续连字符")

        # description（规范：1-1024 字符）
        desc = str(fmd.get("description", "")).strip()
        if not desc:
            # 块标量被空行截断时会走到这里——明确提示这个坑
            errs.append("frontmatter 缺少 description"
                        "（若已写 description: >，检查块内是否有空行截断了它）")
        else:
            if len(desc) > 1024:
                errs.append(f"description 长度 {len(desc)}，上限 1024")
            if not re.search(r"when|use |触发|mention", desc, re.I):
                warns.append("description 缺少明确触发语")

        # 已知字段（规范定义的可选字段）
        KNOWN = {"name", "description", "license", "compatibility",
                 "metadata", "allowed-tools"}
        for k in fmd:
            if k not in KNOWN:
                warns.append(f"frontmatter 未知字段 '{k}'（规范未定义）")

        # 行数（规范：<500 行硬建议）
        lines = text.count("\n") + 1
        if lines > 500:
            warns.append(f"SKILL.md {lines} 行，建议把细节拆到 references/")

        # token 量（官方渐进披露建议：SKILL.md 正文 <5000 token）
        # 优先用 tiktoken 精确计数；没装则退化为粗估并注明是估算值。
        # 单一系数无法同时拟合多个样本（实测偏差可达 25%），所以不假装精确。
        n_tok, exact = count_tokens(text)
        if n_tok > 5000:
            tag = "" if exact else "（粗估）"
            warns.append(f"SKILL.md 正文{tag} {n_tok} token，超过官方建议的 5000；"
                         f"考虑把细节移入 references/")

        # 脚本可编译
        for py in sorted(d.glob("*.py")):
            try:
                with tempfile.TemporaryDirectory() as td:
                    py_compile.compile(str(py), cfile=str(pathlib.Path(td) / "o.pyc"),
                                       doraise=True)
            except py_compile.PyCompileError:
                errs.append(f"{py.name} 语法错误")

        # references 存在性提示
        if lines > 300 and not (d / "references").exists():
            warns.append("SKILL.md 较长但无 references/ 目录")

        if errs:
            print(f"{RED}FAIL{RST} {name}")
            for e in errs:
                print(f"   ✗ {e}")
            issues += 1
        else:
            print(f"{GRN}PASS{RST} {name} — {lines} 行, description {len(desc)} 字符")
            passed += 1
        for w in warns:
            print(f"{YEL}   ! {w}{RST}")
            warnings += 1

    # 跑离线回归测试（不打网络，只验裁决逻辑）
    tests = sorted((ROOT / "tests").glob("test_*.py")) if (ROOT / "tests").exists() else []
    for t in tests:
        import subprocess
        r = subprocess.run([sys.executable, str(t)], capture_output=True, text=True)
        last = [x for x in r.stdout.strip().splitlines() if x.strip()]
        summary = last[-1].strip() if last else "(无输出)"
        if r.returncode == 0:
            print(f"{GRN}PASS{RST} {t.name} — {summary}")
            passed += 1
        else:
            print(f"{RED}FAIL{RST} {t.name} — {summary}")
            print(r.stdout[-800:])
            issues += 1

    print("-" * 52)
    print(f"通过 {passed} · 错误 {issues} · 警告 {warnings}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
