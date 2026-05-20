#!/usr/bin/env python3
"""生成政策全量库 policy_data.json"""
import os, sys, re, json, io, argparse
from pathlib import Path
from datetime import datetime
from smb.SMBConnection import SMBConnection

NAS_IP = "192.168.1.89"
NAS_USER = "15305298591"
NAS_PASS = "IcEwu9001781"
SMB_SHARE = "deepdata"
REMOTE_BASE = "obsidian/core2/知识库/3.电力交易政策/markdown"
OUTPUT = "policy_data.json"

def load_policy_files(smb_conn, base_path, max_files=0, content_limit=2000):
    """递归读取所有 .md 文件"""
    files = []
    file_count = [0]  # using list to allow mutation in nested function

    def _walk(path, category=""):
        try:
            entries = smb_conn.listPath(SMB_SHARE, path)
        except Exception:
            return
        for entry in entries:
            name = entry.filename
            if name in (".", "..", ".trash", ".obsidian"):
                continue
            full = f"{path}/{name}"
            if entry.isDirectory:
                sub = f"{category}/{name}" if category else name
                _walk(full, sub)
            elif name.endswith(".md"):
                buf = io.BytesIO()
                try:
                    smb_conn.retrieveFile(SMB_SHARE, full, buf)
                    content = buf.getvalue().decode("utf-8", errors="replace")
                except Exception:
                    continue
                if len(content.strip()) < 30:
                    continue
                # title
                title = ""
                m = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
                if m: title = m.group(1).strip().strip('"').strip("'")
                if not title:
                    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                    if m: title = m.group(1).strip()
                if not title: title = name.replace(".md", "")
                # tags
                tags = []
                m = re.search(r"tags:\s*\[([^\]]+)\]", content)
                if m: tags = [t.strip().strip('"').strip("'") for t in m.group(1).split(",") if t.strip()]
                # links
                links = list(set(l.split("|")[0].strip() for l in re.findall(r"\[\[([^\]]+)\]\]", content)))
                # province
                province = ""
                parts = full.replace("\\", "/").split("/")
                if "省级" in parts:
                    idx = parts.index("省级")
                    if idx+1 < len(parts): province = parts[idx+1]
                elif "区域级" in parts:
                    idx = parts.index("区域级")
                    if idx+1 < len(parts): province = parts[idx+1]
                elif "国家级" in parts or "concepts" in parts:
                    province = "全国"
                # body
                body = content if len(content) <= content_limit else content[:content_limit] + "\n\n...（内容截断）"
                files.append({
                    "id": name.replace(".md", ""),
                    "title": title, "tags": tags, "links": links[:30],
                    "province": province, "category": category,
                    "content": body, "size": len(content),
                })
                file_count[0] += 1
                if max_files > 0 and file_count[0] >= max_files:
                    return
            if max_files > 0 and file_count[0] >= max_files:
                break
        if max_files > 0 and file_count[0] >= max_files:
            return

    _walk(base_path, "")
    return files

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--content-limit", type=int, default=1500)
    parser.add_argument("--output", default=OUTPUT)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    print(f"🔌 连接 NAS {NAS_IP}...")
    conn = SMBConnection(NAS_USER, NAS_PASS, "policy-gen", "nas", use_ntlm_v2=True, is_direct_tcp=True)
    assert conn.connect(NAS_IP, 445), "连接失败"
    print("✅ 已连接")

    print(f"📂 扫描 {REMOTE_BASE}...")
    files = load_policy_files(conn, REMOTE_BASE, args.max_files, args.content_limit)
    conn.close()
    print(f"📊 共 {len(files)} 个文件")

    cats = {}
    for f in files:
        c = f["category"].split("/")[0] if f["category"] else "其他"
        cats[c] = cats.get(c, 0) + 1
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"   {c}: {n}")

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_files": len(files),
        "total_links": sum(len(f["links"]) for f in files),
        "categories": {k: v for k, v in sorted(cats.items(), key=lambda x: -x[1])},
        "files": files,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1 if args.pretty else None)
    print(f"✅ 已生成: {args.output} ({Path(args.output).stat().st_size/1024:.0f} KB)")

if __name__ == "__main__":
    main()
