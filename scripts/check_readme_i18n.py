"""Check README language navigation, local links and runnable example consistency."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "README.md",
    "README.zh-CN.md",
    "README.ja.md",
    "README.ko.md",
    "README.es.md",
    "README.fr.md",
    "README.de.md",
    "README.pt-BR.md",
    "README.ru.md",
)
REQUIRED_COMMANDS = (
    "python -m ai_memory_hub --root ../hub-demo init --preset ordinary",
    "python -m ai_memory_hub --root ../hub-demo source grant demo normalized --path examples --consent",
    "python -m ai_memory_hub --root ../hub-demo local run --source demo",
    "python -m ai_memory_hub --root ../hub-demo local status",
    "python -m ai_memory_hub --root ../hub-demo session show calibration-session --layer L2",
    "python -m ai_memory_hub --root ../hub-demo asset check calibration-notes",
    "python -m ai_memory_hub --root ../hub-demo asset copy calibration-notes --consent",
)
def main():
    failures = []
    nav = None
    for name in FILES:
        path = ROOT / name
        if not path.is_file():
            failures.append(f"{name}: missing translation")
            continue
        text = path.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.startswith("**Languages:**")]
        if len(lines) != 1:
            failures.append(f"{name}: expected exactly one language navigation")
        elif nav is None:
            nav = lines[0]
        elif nav != lines[0]:
            failures.append(f"{name}: inconsistent navigation")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            target = target.split("#", 1)[0]
            if target and "://" not in target and not target.startswith("mailto:"):
                if not (ROOT / target).is_file():
                    failures.append(f"{name}: broken local link {target}")
        for translation in FILES:
            if f"]({translation})" not in text:
                failures.append(f"{name}: missing navigation destination {translation}")
        blocks = re.findall(r"```([\w-]+)\n([\s\S]*?)\n```", text)
        if sum(language == "mermaid" for language, _ in blocks) != 1:
            failures.append(f"{name}: missing or duplicate architecture diagram")
        if any(re.search(r"\n[ \t]*\n", body) for _, body in blocks):
            failures.append(f"{name}: blank line inside code fence")
        demos = [body.splitlines() for language, body in blocks if language == "sh" and REQUIRED_COMMANDS[0] in body]
        if len(demos) != 1 or tuple(demos[0]) != REQUIRED_COMMANDS:
            failures.append(f"{name}: synthetic quick-start commands have drifted")
        for command in ("transfer pack", "transfer receive", "transfer inspect", "transfer file"):
            if not any(command in body for _, body in blocks):
                failures.append(f"{name}: missing working transfer example ({command})")
        if "2.2.0" not in text:
            failures.append(f"{name}: package version missing")
        if text.count("\n## ") < 7:
            failures.append(f"{name}: expected full product and usage sections")
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print(f"Validated {len(FILES)} complete README translations, navigation, links, diagrams and examples.")
if __name__ == "__main__":
    main()
