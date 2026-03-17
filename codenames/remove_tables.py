from pathlib import Path
import re


def remove_esttab_html(readme_path: "str | Path") -> None:
    """Strip injected HTML content from all ESTTAB blocks, leaving markers intact."""
    readme_path = Path(readme_path)
    readme = readme_path.read_text(encoding="utf-8")
    for match in re.compile(r"<!-- ESTTAB:START:(.*?) -->").findall(readme):
        start = f"<!-- ESTTAB:START:{match} -->"
        end   = f"<!-- ESTTAB:END:{match} -->"
        readme = re.compile(
            re.escape(start) + r".*?" + re.escape(end), re.DOTALL
        ).sub(start + "\n" + end, readme)
    readme_path.write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    path_ = input("Path to the MD file we are updating: ")
    remove_esttab_html(path_)