from pathlib import Path
import re

def inject_esttab_html(
    readme_path: str | Path,
    html_path: str | Path,
):
    """
    Replace the ESTTAB block in README.md corresponding to html_path.

    Marker format in README must be:
    <!-- ESTTAB:START:relative/path/to/file.html -->
    <!-- ESTTAB:END:relative/path/to/file.html -->
    """

    readme_path = Path(readme_path)
    html_path = Path(html_path)

    html_rel = html_path.as_posix()

    start_marker = f"<!-- ESTTAB:START:{html_rel} -->"
    end_marker   = f"<!-- ESTTAB:END:{html_rel} -->"
    
    readme = readme_path.read_text(encoding="utf-8")
    table  = html_path.read_text(encoding="utf-8").strip()

    if start_marker not in readme or end_marker not in readme:
        raise ValueError(
            f"Markers not found for {html_rel} in {readme_path}"
        )

    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        flags=re.DOTALL,
    )

    replacement = (
        start_marker
        + "\n\n"
        + table
        + "\n\n"
        + end_marker
    )

    new_readme = pattern.sub(replacement, readme)

    readme_path.write_text(new_readme, encoding="utf-8")
    
if __name__ == "__main__":
        
    path_ = input("Path to the MD file we are updating:")    
        
    readme_path = Path(path_)
    readme = readme_path.read_text(encoding="utf-8")
    
    import re 
    pattern = re.compile(
        r"<!-- ESTTAB:START:(.*?) -->"
    )
    matches = pattern.findall(readme)
    
    for match in matches:
        print(f"Injecting table from {match}...")
        try:
            html_path = Path(match)
            inject_esttab_html(readme_path, html_path)
        except:
            print(f"  Failed to inject table from {match}.")