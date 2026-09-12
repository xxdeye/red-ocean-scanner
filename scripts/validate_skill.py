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


def frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    return m.group(1) if m else None


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
        fm = frontmatter(text)
        if fm is None:
            errs.append("缺少 YAML frontmatter")
            fm = ""

        # name
        nm = re.search(r"^name:\s*(.+)$", fm, re.M)
        if not nm:
            errs.append("frontmatter 缺少 name")
            val = ""
        else:
            val = nm.group(1).strip().strip("\"'")
            if val != name:
                errs.append(f"name '{val}' 与目录名 '{name}' 不一致")
            if not re.fullmatch(r"[a-z0-9-]+", val):
                errs.append("name 只能含小写字母/数字/连字符")
            if len(val) > 64:
                errs.append(f"name 长度 {len(val)}，上限 64")

        # description
        dm = re.search(r"description:\s*[>|]?\s*\n?(.*?)(?=\n[a-zA-Z_-]+:\s|\Z)",
                       fm, re.S)
        desc = " ".join(dm.group(1).split()) if dm else ""
        if not desc:
            errs.append("frontmatter 缺少 description")
        else:
            if len(desc) > 1024:
                errs.append(f"description 长度 {len(desc)}，上限 1024")
            if not re.search(r"when|use |触发|mention", desc, re.I):
                warns.append("description 缺少明确触发语")

        # 行数
        lines = text.count("\n") + 1
        if lines > 500:
            warns.append(f"SKILL.md {lines} 行，建议把细节拆到 references/")

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
