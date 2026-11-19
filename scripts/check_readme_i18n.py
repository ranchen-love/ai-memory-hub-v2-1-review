"""Validate nine README languages, default Chinese, layout and V2.3 onboarding."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "README.md",
    "docs/i18n/README.en.md",
    "docs/i18n/README.ja.md",
    "docs/i18n/README.ko.md",
    "docs/i18n/README.es.md",
    "docs/i18n/README.fr.md",
    "docs/i18n/README.de.md",
    "docs/i18n/README.pt-BR.md",
    "docs/i18n/README.ru.md",
)
CORE_DEMO = (
    "workspace init --path",
    "workspace check --path",
    "source grant sample normalized",
    "local run --source sample",
)
TRANSFER = ("transfer pack", "transfer receive", "transfer inspect", "transfer file")
LANGUAGE_HEADER = re.compile(r"^\*\*(?:Languages:|语言 / Languages：)\*\*")
LINK = re.compile(r"\]\(([^)]+)\)")
FENCE = re.compile(r"```([\w-]+)\n([\s\S]*?)\n```")
def main():
    failures = []
    nav_labels = None
    expected = {(ROOT / name).resolve() for name in FILES}
    for name in FILES:
        path = ROOT / name
        if not path.is_file():
            failures.append(f"{name}: missing translation")
            continue
        content = path.read_text(encoding="utf-8")
        nav_lines = [line for line in content.splitlines() if LANGUAGE_HEADER.match(line)]
        if len(nav_lines) != 1:
            failures.append(f"{name}: expected one language selector")
        else:
            source_lines = content.splitlines()
            nav_index = source_lines.index(nav_lines[0])
            if nav_index < 1 or nav_index + 1 >= len(source_lines):
                failures.append(f"{name}: malformed language selector placement")
            elif source_lines[nav_index - 1].strip() or source_lines[nav_index + 1].strip():
                failures.append(f"{name}: language selector must be its own paragraph")
            if nav_index + 2 >= len(source_lines) or source_lines[nav_index + 2].strip() != "---":
                failures.append(f"{name}: language selector should have a visual separator")
            pairs = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", nav_lines[0])
            labels = tuple(label for label, _ in pairs)
            if len(pairs) != len(FILES) or len(set(labels)) != len(FILES):
                failures.append(f"{name}: incomplete or duplicate language choices")
            if nav_labels is None:
                nav_labels = labels
            elif labels != nav_labels:
                failures.append(f"{name}: inconsistent language ordering")
            targets = {(path.parent / href).resolve() for _, href in pairs}
            if targets != expected:
                failures.append(f"{name}: language links do not match the nine pages")
        for href in LINK.findall(content):
            href = href.split("#", 1)[0]
            if not href or "://" in href or href.startswith("mailto:"):
                continue
            target = (path.parent / href).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                failures.append(f"{name}: broken local link {href}")
        blocks = FENCE.findall(content)
        if sum(kind == "mermaid" for kind, _ in blocks) != 1:
            failures.append(f"{name}: expected one architecture diagram")
        if any(re.search(r"\n[ \t]*\n", body) for _, body in blocks):
            failures.append(f"{name}: blank line inside code fence")
        demos = [body for kind, body in blocks if kind == "sh" and all(term in body for term in CORE_DEMO)]
        if len(demos) != 1:
            failures.append(f"{name}: V2.3 synthetic onboarding missing or duplicated")
        for command in TRANSFER:
            if not any(kind == "sh" and command in body for kind, body in blocks):
                failures.append(f"{name}: transfer example missing {command}")
        for token in ("2.3.0", "12", "52", "134", "synced_sha", "detected_sha",
                      "candidate advance", "version confirm"):
            if token not in content:
                failures.append(f"{name}: required V2.3 capability missing {token}")
        for level in ("L0", "L1", "L2", "L3"):
            if f"| **{level}" not in content:
                failures.append(f"{name}: missing detailed {level} layer explanation")
        if content.count("\n## ") < 7:
            failures.append(f"{name}: expected complete project overview")
    chinese = (ROOT / "README.md").read_text(encoding="utf-8")
    chapters = (
        "一、这是什么？适合谁？",
        "二、首次使用：让你的 AI 帮你搭建",
        "三、关键能力：为什么这样设计？",
        "四、资料分别放在哪里？",
        "五、安装与快速体验",
        "六、同步、权限与运行维护",
        "七、当前已实现什么？还缺什么？",
        "八、长期目标",
    )
    headings = tuple(re.findall(r"^## (.+)$", chinese, flags=re.M))
    if headings != chapters:
        failures.append("README.md: must match eight-part private-hub structure")
    english = (ROOT / "docs/i18n/README.en.md").read_text(encoding="utf-8")
    if len(re.findall(r"^## ", english, flags=re.M)) != 8:
        failures.append("README.en.md: English guide must have eight main sections")
    for new_path in ("docs/agent-onboarding.md", "docs/agent-onboarding.zh-CN.md"):
        if not (ROOT / new_path).is_file():
            failures.append(f"Missing Agent first-run guide: {new_path}")
    if "为什么不直接保存一堆聊天记录？" in chinese:
        failures.append("Removed sales comparison table reappeared in Chinese README")
    if "docs/agent-onboarding.zh-CN.md" not in chinese:
        failures.append("Chinese README must link the Agent first-run protocol")
    agent_entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if "docs/agent-onboarding.md" not in agent_entry:
        failures.append("Agent entry must link to the onboarding protocol")
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print("Validated nine READMEs, standalone language navigation, eight-part Chinese guide, L0-L3 tables, links and V2.3 examples.")
if __name__ == "__main__":
    main()
