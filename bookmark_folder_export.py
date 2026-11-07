#!/usr/bin/env python3
"""
Export all bookmarks from a single Firefox folder (including subfolders)
as Markdown, HTML, TXT or ZIP – ideal for pasting into an AI chat.

Cross-platform: Linux (native, XDG, Snap, Flatpak), Windows, macOS.

Usage:
    python3 firefox_folder_export.py "Jobsearch" -o output/Jobsearch.md
    python3 firefox_folder_export.py "Tech" --format html
    python3 firefox_folder_export.py "Tech" --format zip -o tech_export.zip
    python3 firefox_folder_export.py --list
"""

import sqlite3
import shutil
import os
import sys
import re
import tempfile
import argparse
import zipfile
from collections import defaultdict

# ─── Profile discovery ─────────────────────────────────────────────────────
def get_profile_dirs():
    """Return a list of possible Firefox profile root directories."""
    home = os.path.expanduser("~")
    dirs = []

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            dirs.append(os.path.join(appdata, "Mozilla", "Firefox", "Profiles"))
    elif sys.platform == "darwin":
        dirs.append(os.path.join(home, "Library", "Application Support", "Firefox", "Profiles"))
    else:
        dirs.extend([
            os.path.join(home, ".mozilla", "firefox"),
            os.path.join(home, ".config", "mozilla", "firefox"),
            os.path.join(home, "snap", "firefox", "common", ".mozilla", "firefox"),
            os.path.join(home, ".var", "app", "org.mozilla.firefox", ".mozilla", "firefox"),
        ])

    return [d for d in dirs if os.path.isdir(d)]


def find_db_path(profile_name=None):
    """Find a valid places.sqlite. Optionally filter by profile name."""
    for profile_root in get_profile_dirs():
        for entry in sorted(os.listdir(profile_root)):
            if profile_name and profile_name not in entry:
                continue
            candidate = os.path.join(profile_root, entry, "places.sqlite")
            if os.path.isfile(candidate):
                return candidate
    return None


def copy_database(db_path):
    """
    Copy the database (and WAL/SHM sidecar files) to a temp location.
    SQLite will replay the WAL on open, giving us a consistent snapshot
    without needing to lock the original (which Firefox holds open).
    """
    tmp = os.path.join(tempfile.gettempdir(), "places_copy.sqlite")
    shutil.copy2(db_path, tmp)

    for suffix in ("-wal", "-shm"):
        sidecar = db_path + suffix
        if os.path.isfile(sidecar):
            shutil.copy2(sidecar, tmp + suffix)

    return tmp


# ─── Data collection ───────────────────────────────────────────────────────
def collect_data(cur, folder_id, folder_title):
    """Collect folders and bookmarks for the given folder tree."""
    cur.execute("""
        WITH RECURSIVE folder_tree(id, title, parent_id, depth, position) AS (
            SELECT id, title, parent, 0, position
            FROM moz_bookmarks WHERE id = ?
            UNION ALL
            SELECT b.id, b.title, b.parent, ft.depth + 1, b.position
            FROM moz_bookmarks b
            JOIN folder_tree ft ON b.parent = ft.id
            WHERE b.type = 2
        )
        SELECT id, title, parent_id, depth, position
        FROM folder_tree
        ORDER BY depth, position
    """, (folder_id,))
    folders = {r[0]: {"title": r[1], "parent": r[2], "depth": r[3], "position": r[4]}
               for r in cur.fetchall()}

    cur.execute("""
        WITH RECURSIVE folder_tree(id) AS (
            SELECT id FROM moz_bookmarks WHERE id = ?
            UNION ALL
            SELECT b.id FROM moz_bookmarks b
            JOIN folder_tree ft ON b.parent = ft.id
            WHERE b.type = 2
        )
        SELECT b.id, b.title, b.parent, p.url, b.position
        FROM moz_bookmarks b
        JOIN moz_places p ON b.fk = p.id
        WHERE b.type = 1
          AND b.parent IN (SELECT id FROM folder_tree)
        ORDER BY b.parent, b.position
    """, (folder_id,))
    bookmarks = cur.fetchall()

    by_parent = defaultdict(list)
    for bm_id, title, parent, url, pos in bookmarks:
        by_parent[parent].append((bm_id, title, url))

    return folders, by_parent


# ─── Renderers ─────────────────────────────────────────────────────────────
def render_markdown(folder_title, folders, by_parent, folder_id):
    """Hierarchical Markdown list."""
    lines = [f"# {folder_title}", ""]

    def render_folder(fid, depth):
        indent = "  " * depth
        if fid != folder_id:
            lines.append(f"{indent}- **{folders[fid]['title']}**")
            depth += 1
            indent = "  " * depth

        for bm_id, title, url in by_parent.get(fid, []):
            title = title or "(untitled)"
            lines.append(f"{indent}- [{title}]({url})")

        for child_id, info in sorted(folders.items(), key=lambda x: x[1]["position"]):
            if info["parent"] == fid:
                render_folder(child_id, depth)

    render_folder(folder_id, 0)
    return "\n".join(lines) + "\n"


def render_netscape_html(folder_title, folders, by_parent, folder_id):
    """Netscape Bookmark File Format – universal browser standard."""
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        f"<TITLE>Bookmarks</TITLE>",
        f"<H1>{folder_title}</H1>",
        "<DL><p>",
    ]

    def emit_folder(fid, indent="    "):
        for bm_id, title, url in by_parent.get(fid, []):
            title = (title or "(untitled)").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f'{indent}<DT><A HREF="{url}">{title}</A>')

        for child_id, info in sorted(folders.items(), key=lambda x: x[1]["position"]):
            if info["parent"] == fid:
                child_title = info["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f'{indent}<DT><H3>{child_title}</H3>')
                lines.append(f"{indent}<DL><p>")
                emit_folder(child_id, indent + "    ")
                lines.append(f"{indent}</DL><p>")

    emit_folder(folder_id)
    lines.append("</DL><p>")
    return "\n".join(lines) + "\n"


def render_txt(folder_title, folders, by_parent, folder_id):
    """Flat tab-separated list – good for grep / AI chat."""
    lines = [f"# {folder_title}", ""]

    def collect(fid, depth=0):
        for bm_id, title, url in by_parent.get(fid, []):
            prefix = "  " * depth
            title = title or "(untitled)"
            lines.append(f"{prefix}{title}\t{url}")
        for child_id, info in sorted(folders.items(), key=lambda x: x[1]["position"]):
            if info["parent"] == fid:
                lines.append(f"{'  ' * depth}[{info['title']}]")
                collect(child_id, depth + 1)

    collect(folder_id)
    return "\n".join(lines) + "\n"


# ─── Main logic ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Export a Firefox bookmark folder as Markdown, HTML, TXT or ZIP."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="Name of the bookmark folder to export (case-sensitive)."
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file path (default: <folder_name>_bookmarks.<ext> in CWD)."
    )
    parser.add_argument(
        "-f", "--format",
        choices=["md", "html", "txt", "zip"],
        default="md",
        help="Output format (default: md)."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available bookmark folders and exit."
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Filter by profile name (substring match)."
    )
    parser.add_argument(
        "--id",
        type=int,
        default=None,
        help="Export by folder ID instead of name (use --list to find IDs)."
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.1.0"
    )
    args = parser.parse_args()

    # Locate the database
    db_path = find_db_path(profile_name=args.profile)
    if db_path is None:
        print("ERROR: Could not find a Firefox profile with places.sqlite.")
        if args.profile:
            print(f"Profile filter: '{args.profile}'")
        print("Searched in:")
        for d in get_profile_dirs():
            print(f"  {d}")
        print("\nTip: Open Firefox → type 'about:profiles' in the address bar")
        print("to see the actual profile path.")
        sys.exit(1)

    print(f"Using database: {db_path}")

    # Copy to a temp file (avoids lock conflicts with running Firefox)
    tmp = copy_database(db_path)
    conn = sqlite3.connect(tmp)
    cur = conn.cursor()

    try:
        # ── List mode ───────────────────────────────────────────────────────
        if args.list:
            cur.execute("""
                SELECT b.id, b.title, p.title AS parent_title
                FROM moz_bookmarks b
                LEFT JOIN moz_bookmarks p ON b.parent = p.id
                WHERE b.type = 2
                ORDER BY p.title, b.position
            """)
            print("Available bookmark folders:")
            for r in cur.fetchall():
                parent = f"  (in: {r[2]})" if r[2] else ""
                print(f"  [{r[0]}] {r[1]}{parent}")
            sys.exit(0)

        # ── Resolve target folder ───────────────────────────────────────────
        if args.id is not None:
            cur.execute("SELECT id, title FROM moz_bookmarks WHERE id = ? AND type = 2", (args.id,))
            row = cur.fetchone()
            if row is None:
                print(f"Folder with id {args.id} not found. Use --list to see available folders.")
                sys.exit(1)
        elif args.folder:
            cur.execute(
                "SELECT id, title FROM moz_bookmarks WHERE title = ? AND type = 2 LIMIT 1",
                (args.folder,)
            )
            row = cur.fetchone()
            if row is None:
                print(f"Folder '{args.folder}' not found. Available folders:")
                cur.execute("SELECT id, title FROM moz_bookmarks WHERE type = 2 ORDER BY title")
                for r in cur.fetchall():
                    print(f"  [{r[0]}] {r[1]}")
                sys.exit(1)
        else:
            parser.print_help()
            sys.exit(1)

        folder_id, folder_title = row
        print(f"Found folder: {folder_title} (id={folder_id})")

        # ── Collect data ───────────────────────────────────────────────────
        folders, by_parent = collect_data(cur, folder_id, folder_title)

        # ── Determine output path ──────────────────────────────────────────
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', folder_title).strip() or "untitled"


        output_file = args.output
        if output_file is None:
            ext = "zip" if args.format == "zip" else args.format
            output_file = f"{safe_title}_bookmarks.{ext}"

        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # ── Render & write ─────────────────────────────────────────────────
        total = sum(len(v) for v in by_parent.values())

        if args.format == "zip":
            with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{safe_title}_bookmarks.md",
                            render_markdown(folder_title, folders, by_parent, folder_id))
                zf.writestr(f"{safe_title}_bookmarks.html",
                            render_netscape_html(folder_title, folders, by_parent, folder_id))
                zf.writestr(f"{safe_title}_bookmarks.txt",
                            render_txt(folder_title, folders, by_parent, folder_id))
        else:
            renderers = {
                "md": render_markdown,
                "html": render_netscape_html,
                "txt": render_txt,
            }
            content = renderers[args.format](folder_title, folders, by_parent, folder_id)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)

        print(f"✅ Exported {total} bookmarks → {output_file}")

    finally:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            path = tmp + suffix
            if os.path.isfile(path):
                os.remove(path)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
