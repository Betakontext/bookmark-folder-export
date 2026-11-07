# 🔖 Bookmark folder export → Markdown / HTML / TXT / ZIP

Export a single Firefox bookmark folder (recursively) as `.md`, `.html`, `.txt` or `.zip`.

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![Firefox](https://img.shields.io/badge/Firefox-140%2B-ff5722)](https://www.mozilla.org/firefox/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![No Telemetry](https://img.shields.io/badge/telemetry-none-green)]()
[![Platforms](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-2ea44f)]()

| Tool | Use case |
|------|----------|
| `firefox_folder_export.py` | CLI – scripting, automation |
| `bookmark-md/` | Browser add-on – right-click & go |

---

## Python Script

**Requires:** Python 3.8+, Firefox

### Usage

```bash
# Export a folder as Markdown (default)
python3 firefox_folder_export.py "Jobsearch"

# Choose format: md, html, txt, zip
python3 firefox_folder_export.py "Jobsearch" -f html
python3 firefox_folder_export.py "Jobsearch" -f txt -o ~/Notes/jobsearch.txt
python3 firefox_folder_export.py "Jobsearch" -f zip -o ~/Notes/jobsearch.zip

# Custom output path (dir auto-created)
python3 firefox_folder_export.py "Jobsearch" -o ~/Notes/jobsearch.md

# Filter by profile name (substring match)
python3 firefox_folder_export.py "Jobsearch" --profile release

# Export by folder ID (robust for duplicate names)
python3 firefox_folder_export.py --id 42 -f md

# List all available folders (with IDs)
python3 firefox_folder_export.py --list

# Help
python3 firefox_folder_export.py -h
```

### Options

| Flag | Description |
|------|-------------|
| `-f`, `--format` | Output format: `md` (default), `html`, `txt`, `zip` |
| `-o`, `--output` | Output file path (default: `<folder>_bookmarks.<ext>`) |
| `--profile` | Filter by Firefox profile name (substring) |
| `--id` | Export by numeric folder ID instead of name |
| `--list` | List all folders with IDs and exit |

### Output Formats

| Format | Description |
|--------|-------------|
| `md` | Hierarchical Markdown list – ideal for AI chat / notes |
| `html` | Netscape Bookmark File – importable by any browser |
| `txt` | Tab-separated flat list – good for grep / scripts |
| `zip` | All three formats in one archive |

### Example Output (Markdown)

```markdown
# Jobsearch

- [Company A](https://example.com)
- **Applications**
  - [Cover letter](https://docs.example.com)
  - [CV 2026](https://docs.example.com/cv)
```

### How it works

1. Finds `places.sqlite` (Linux: native/XDG/Snap/Flatpak, Windows, macOS)
2. Copies DB + WAL to `/tmp` (safe while Firefox runs)
3. Recursively queries the folder tree (ordered by `position`)
4. Renders in chosen format, writes output, deletes temp files

---

## Firefox Add-on

### Install (dev)

`about:debugging` → **Load Temporary Add-on** → select `bookmark-md/manifest.json`

### Usage

1. Open Bookmarks Manager (`Ctrl+Shift+O`)
2. Right-click a folder → **Export as …**
3. Choose format:
   - **Markdown (.md)**
   - **Netscape HTML (.html)**
   - **Plain Text (.txt)**
   - **ZIP (all formats)**
4. Choose save location & filename

> Right-clicking a single bookmark (not a folder) exports just that entry.

### Permissions

`bookmarks` (read tree) · `downloads` (save file) · No telemetry

### Troubleshooting

| Problem | Fix |
|---------|-----|
| Profile not found | `about:profiles` → check actual path |
| Folder not found | Case-sensitive – use `--list` |
| Add-on menu missing | Right-click in Bookmarks Manager, not sidebar |

------------------------

Forks, stars, ideas via Pull request are welcome!

Contact: dev@betakontext.de
