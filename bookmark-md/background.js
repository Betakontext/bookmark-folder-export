// background.js – Bookmark Folder Export
//
// Right-click a bookmark folder → export as .md / .html / .txt / .zip
// No external dependencies, no network requests, no data collection.
//
// Contact: dev@betakontext.de
// Repo: https://github.com/betakontext/bookmark-folder-export
// License: MIT

// ─── Context Menu ──────────────────────────────────────────────────────────
browser.contextMenus.create({ id: "export-root", title: "Export as …", contexts: ["bookmark"] });
browser.contextMenus.create({ id: "export-md",   title: "Markdown (.md)",   parentId: "export-root", contexts: ["bookmark"] });
browser.contextMenus.create({ id: "export-html", title: "Netscape HTML (.html)", parentId: "export-root", contexts: ["bookmark"] });
browser.contextMenus.create({ id: "export-txt",  title: "Plain Text (.txt)", parentId: "export-root", contexts: ["bookmark"] });
browser.contextMenus.create({ id: "export-zip",  title: "ZIP (all formats)", parentId: "export-root", contexts: ["bookmark"] });

browser.contextMenus.onClicked.addListener(async (info) => {
  const fmt = {
    "export-md": "md",
    "export-html": "html",
    "export-txt": "txt",
    "export-zip": "zip",
  }[info.menuItemId];
  if (!fmt) return;

  const tree = await browser.bookmarks.getSubTree(info.bookmarkId);
  const root = tree[0];

  // Single bookmark (not a folder) → just md/txt, no subfolder logic
  if (root.type !== "folder") {
    const title = root.title || "(untitled)";
    const content = fmt === "html"
      ? renderNetscapeHTML(root, title)
      : fmt === "txt"
        ? `${title}\t${root.url}\n`
        : `# ${title}\n\n- [${title}](${root.url})\n`;

    const ext = fmt === "html" ? "html" : fmt === "txt" ? "txt" : "md";
    await download(content, `${sanitize(root.title)}.${ext}`, "application/octet-stream");
    return;
  }

  // Folder → render in requested format
  if (fmt === "zip") {
    const files = {
      [`${sanitize(root.title)}_bookmarks.md`]:    renderMarkdown(root),
      [`${sanitize(root.title)}_bookmarks.html`]:  renderNetscapeHTML(root, root.title),
      [`${sanitize(root.title)}_bookmarks.txt`]:   renderTxt(root),
    };
    const zipBlob = createZip(files);
    await downloadBlob(zipBlob, `${sanitize(root.title)}_bookmarks.zip`);
  } else {
    const renderers = {
      md:   () => renderMarkdown(root),
      html: () => renderNetscapeHTML(root, root.title),
      txt:  () => renderTxt(root)
    };
    const ext = fmt === "html" ? "html" : fmt;
    const mime = fmt === "html" ? "text/html" : "application/octet-stream";
    await download(renderers[fmt](), `${sanitize(root.title)}_bookmarks.${ext}`, mime);
  }
});

// ─── Renderers ─────────────────────────────────────────────────────────────

function renderMarkdown(node) {
  const lines = [`# ${node.title}`, ""];
  function renderChildren(children, depth = 0) {
    const indent = "  ".repeat(depth);
    for (const child of children || []) {
      if (child.type === "folder") {
        lines.push(`${indent}- **${child.title}**`);
        renderChildren(child.children, depth + 1);
      } else {
        lines.push(`${indent}- [${child.title || "(untitled)"}](${child.url})`);
      }
    }
  }
  renderChildren(node.children);
  return lines.join("\n") + "\n";
}

function renderNetscapeHTML(node, title) {
  const lines = [
    "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
    '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
    `<TITLE>Bookmarks</TITLE>`,
    `<H1>${esc(title)}</H1>`,
    "<DL><p>",
  ];

  function emit(children, indent) {
    for (const child of children || []) {
      if (child.type === "folder") {
        lines.push(`${indent}<DT><H3>${esc(child.title)}</H3>`);
        lines.push(`${indent}<DL><p>`);
        emit(child.children, indent + "    ");
        lines.push(`${indent}</DL><p>`);
      } else {
        lines.push(`${indent}<DT><A HREF="${child.url}">${esc(child.title || "(untitled)")}</A>`);
      }
    }
  }

  emit(node.children, "    ");
  lines.push("</DL><p>");
  return lines.join("\n") + "\n";
}

function renderTxt(node) {
  const lines = [`# ${node.title}`, ""];
  function collect(children, depth = 0) {
    const prefix = "  ".repeat(depth);
    for (const child of children || []) {
      if (child.type === "folder") {
        lines.push(`${prefix}[${child.title}]`);
        collect(child.children, depth + 1);
      } else {
        lines.push(`${prefix}${child.title || "(untitled)"}\t${child.url}`);
      }
    }
  }
  collect(node.children);
  return lines.join("\n") + "\n";
}

// ─── Minimal ZIP (stored, no compression) ──────────────────────────────────

function createZip(files) {
  const encoder = new TextEncoder();
  const chunks = [];
  const central = [];
  let offset = 0;

  for (const [name, content] of Object.entries(files)) {
    const nameBytes = encoder.encode(name);
    const data = encoder.encode(content);
    const crc = crc32(data);

    // Local file header
    const lfh = new DataView(new ArrayBuffer(30));
    lfh.setUint32(0, 0x04034b50, true);  // signature
    lfh.setUint16(4, 20, true);           // version needed
    lfh.setUint16(6, 0, true);            // flags
    lfh.setUint16(8, 0, true);            // method: stored
    lfh.setUint16(10, 0, true);           // mod time
    lfh.setUint16(12, 0, true);           // mod date
    lfh.setUint32(14, crc, true);
    lfh.setUint32(18, data.length, true); // compressed size
    lfh.setUint32(22, data.length, true); // uncompressed size
    lfh.setUint16(26, nameBytes.length, true);
    lfh.setUint16(28, 0, true);           // extra len

    chunks.push(new Uint8Array(lfh.buffer), nameBytes, data);
    offset += 30 + nameBytes.length + data.length;

    // Central directory entry
    const cd = new DataView(new ArrayBuffer(46));
    cd.setUint32(0, 0x02014b50, true);
    cd.setUint16(4, 20, true);
    cd.setUint16(6, 20, true);
    cd.setUint16(8, 0, true);
    cd.setUint16(10, 0, true);
    cd.setUint16(12, 0, true);
    cd.setUint16(14, 0, true);
    cd.setUint32(16, crc, true);
    cd.setUint32(20, data.length, true);
    cd.setUint32(24, data.length, true);
    cd.setUint16(28, nameBytes.length, true);
    cd.setUint16(30, 0, true);
    cd.setUint16(32, 0, true);
    cd.setUint16(34, 0, true);
    cd.setUint16(36, 0, true);
    cd.setUint32(38, 0, true);
    cd.setUint32(42, offset - (30 + nameBytes.length + data.length), true); // local header offset (approx)

    central.push(new Uint8Array(cd.buffer), nameBytes);
  }

  const centralSize = central.reduce((s, c) => s + c.length, 0);
  const centralStart = offset;

  // End of central directory
  const eocd = new DataView(new ArrayBuffer(22));
  eocd.setUint32(0, 0x06054b50, true);
  eocd.setUint16(4, 0, true);
  eocd.setUint16(6, 0, true);
  eocd.setUint16(8, Object.keys(files).length, true);
  eocd.setUint16(10, Object.keys(files).length, true);
  eocd.setUint32(12, centralSize, true);
  eocd.setUint32(16, centralStart, true);
  eocd.setUint16(20, 0, true);

  const totalSize = offset + centralSize + 22;
  const result = new Uint8Array(totalSize);
  let pos = 0;
  for (const c of [...chunks, ...central, new Uint8Array(eocd.buffer)]) {
    result.set(c, pos);
    pos += c.length;
  }
  return new Blob([result], { type: "application/zip" });
}

// CRC-32 (required for ZIP)
function crc32(data) {
  let table = crc32.table;
  if (!table) {
    table = crc32.table = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
      let c = i;
      for (let j = 0; j < 8; j++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      table[i] = c;
    }
  }
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < data.length; i++) {
    crc = (crc >>> 8) ^ table[(crc ^ data[i]) & 0xFF];
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

// ─── Utilities ─────────────────────────────────────────────────────────────

function sanitize(name) {
  return (name || "untitled").replace(/[\\/:*?"<>|]/g, "_").trim() || "untitled";
}

function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function download(content, filename, mime) {
  const blob = new Blob([content], { type: "text/html" });
  await downloadBlob(blob, filename);
}

async function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const downloadId = await browser.downloads.download({ url, filename, saveAs: true });

  const cleanup = (delta) => {
    if (delta.id !== downloadId || !delta.state) return;
    if (delta.state.current === "complete" || delta.state.current === "interrupted") {
      browser.downloads.onChanged.removeListener(cleanup);
      URL.revokeObjectURL(url);
    }
  };
  browser.downloads.onChanged.addListener(cleanup);
}
