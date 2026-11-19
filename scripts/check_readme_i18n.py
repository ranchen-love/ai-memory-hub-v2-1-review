"""Validate nine README languages and product-first V2.4 onboarding."""
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
        for token in ("2.4.0", "12", "52", "134", "synced_sha", "detected_sha"):
            if token not in content:
                failures.append(f"{name}: required memory feature missing {token}")
        if name in ("README.md", "docs/i18n/README.en.md"):
            prompts = [body for kind, body in blocks if kind == "text"]
            if len(prompts) != 1 or (
                "https://github.com/ranchen-love/ai-memory-hub-v2-1-review" not in prompts[0]
            ):
                failures.append(f"{name}: missing single copyable Agent setup prompt")
            elif any(len(line) > 82 for line in prompts[0].splitlines()):
                failures.append(f"{name}: Agent setup prompt exceeds 82 columns")
            if any(kind == "sh" for kind, _ in blocks):
                failures.append(f"{name}: CLI implementation commands belong in the setup guide")
            for marker in ("AGENTS.md", "onboarding plan/apply/report", "Private"):
                if marker not in content:
                    failures.append(f"{name}: missing Agent onboarding feature {marker}")
        else:
            for marker in ("candidate advance", "version confirm"):
                if marker not in content:
                    failures.append(f"{name}: existing translated feature missing {marker}")
        for level in ("L0", "L1", "L2", "L3"):
            if f"| **{level}" not in content:
                failures.append(f"{name}: missing detailed {level} layer explanation")
        if content.count("\n## ") < 7:
            failures.append(f"{name}: expected complete project overview")
    chinese = (ROOT / "README.md").read_text(encoding="utf-8")
    chapters = (
        "一、主要功能",
        "二、保存的信息领域",
        "三、典型使用场景",
        "四、数据结构与设计原则",
        "五、开始使用",
        "六、隐私、安全与控制权",
        "七、当前建设状态与适用范围",
        "八、文档导航与长期方向",
    )
    headings = tuple(re.findall(r"^## (.+)$", chinese, flags=re.M))
    if headings != chapters:
        failures.append("README.md: must match eight-part product overview")
    english = (ROOT / "docs/i18n/README.en.md").read_text(encoding="utf-8")
    english_chapters = tuple(re.findall(r"^## (.+)$", english, flags=re.M))
    if english_chapters != (
        "I. Main capabilities",
        "II. Information categories",
        "III. Common use cases",
        "IV. Information architecture and design",
        "V. Getting started",
        "VI. Privacy, security and ownership",
        "VII. Current implementation and scope",
        "VIII. Documentation and direction",
    ):
        failures.append("README.en.md: must match product-first eight sections")
    for new_path in ("docs/agent-onboarding.md", "docs/agent-onboarding.zh-CN.md"):
        if not (ROOT / new_path).is_file():
            failures.append(f"Missing Agent first-run guide: {new_path}")
    if "为什么不直接保存一堆聊天记录？" in chinese:
        failures.append("Removed sales comparison table reappeared in Chinese README")
    if any("？" in title or "?" in title for title in headings):
        failures.append("README.md: conversational/question-style chapter heading")
    for checked_file in ("README.md", "docs/i18n/README.en.md"):
        body = (ROOT / checked_file).read_text(encoding="utf-8")
        lines = body.splitlines()
        inside_fence = False
        for i, line in enumerate(lines):
            if line.startswith("```"):
                inside_fence = not inside_fence
                continue
            if inside_fence or i == 0 or not line.strip():
                continue
            prior = lines[i - 1]
            if not prior.strip():
                continue
            same_table = line.startswith("|") and prior.startswith("|")
            same_list = (line.startswith("- ") and prior.startswith("- "))
            if not (same_table or same_list):
                failures.append(
                    f"{checked_file}: missing Markdown block separation at line {i + 1}"
                )
    if "docs/agent-onboarding.zh-CN.md" not in chinese:
        failures.append("Chinese README must link the Agent first-run protocol")
    agent_entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if "docs/agent-onboarding.md" not in agent_entry:
        failures.append("Agent entry must link to the onboarding protocol")
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print("Validated nine READMEs, language navigation, eight product sections, Agent setup prompt, L0-L3 tables, and links.")
if __name__ == "__main__":
    main()
