#!/usr/bin/env python3
"""Build separate local-marketplace and single-plugin ZIP archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "research-author-index-bundle"
PLUGIN = "research-author-index"
REQUIREMENTS = "openpyxl>=3.1,<4\npypdf>=5,<7\n"

MARKETPLACE_INSTALL = """# Research Author Index — ติดตั้งบน Windows ผ่าน Codex app

ZIP นี้เป็น **local marketplace**: ต้องแตกไฟล์ก่อน ไม่ใช่ไฟล์สำหรับกด Upload plugin ZIP โดยตรง

1. แตก ZIP ไปไว้ในโฟลเดอร์ถาวร เช่น `Documents\\ResearchAuthorIndex` อย่าย้ายหรือลบโฟลเดอร์หลังติดตั้ง
2. ใน Codex app เปิดโฟลเดอร์ `research-author-index-bundle` เป็นโปรเจกต์ (โฟลเดอร์นี้มี `.agents/plugins/marketplace.json`)
3. ปิดและเปิด Codex app ใหม่ แล้วไปที่ Plugins Directory เลือก `Research Author Index Pack` และกด Install ที่ `Research Author Index`
4. ติดตั้ง Python 3 ถ้ายังไม่มี แล้วเปิด PowerShell ในโฟลเดอร์ `research-author-index-bundle` รัน:

```powershell
py -3 -m pip install -r .\\plugins\\research-author-index\\requirements.txt
```

หาก `py` ไม่พบ ให้ลอง `python -m pip install -r .\\plugins\\research-author-index\\requirements.txt`
เปิดแชตใหม่หลังติดตั้งหรืออัปเดต เพื่อให้ Codex โหลด skill รุ่นล่าสุด

## ทางเลือก: ให้ marketplace ใช้ได้ทุกโปรเจกต์

ถ้ามี Codex CLI ให้เปิด PowerShell ในโฟลเดอร์ `research-author-index-bundle` แล้วรัน:

```powershell
codex plugin marketplace add (Get-Location).Path
codex plugin add research-author-index@research-author-index-pack
```

จากนั้นปิดและเปิด Codex app ใหม่ คำสั่ง CLI นี้ไม่จำเป็นสำหรับการติดตั้งจากโปรเจกต์ในข้อ 1–3

## อัปเดต

แตก ZIP รุ่นใหม่ทับโฟลเดอร์เดิม แล้วติดตั้ง plugin รุ่นใหม่จาก Plugins Directory หรือรัน `codex plugin add research-author-index@research-author-index-pack` ถ้าใช้ CLI จากนั้นเปิดแชตใหม่

## การใช้งาน

ขอว่า “ค้นผลงาน Scopus และ TCI ของ [ชื่อผู้วิจัย] แล้วทำ Excel”
เริ่มทุกงานด้วยการเปิด Scopus ให้ผู้ใช้เห็น ใช้ Chrome ที่เชื่อมไว้ หรือ Codex Browser หากยังไม่ล็อกอิน ต้องแจ้งให้ผู้ใช้ Login และรอจนตรวจยืนยันได้ก่อนเริ่มค้นหรือประมวลผลข้อมูล
Scopus ใช้แท็บที่ผู้ใช้ล็อกอินและเครื่องมือ UI/Playwright ที่เบราว์เซอร์รองรับ ตรวจจำนวนในหน้าต่าง Export แล้วเริ่มรอ download ก่อนกดดาวน์โหลด CSV ไม่เรียก private API หรือคัดลอก cookies
ThaiJO ใช้สคริปต์อ่านหน้าสาธารณะแบบชุดและใช้เบราว์เซอร์เก็บหน้าที่ยังขาด ต้องตรวจจำนวนครบก่อนสรุปผล
ThaiJO อ่านเลขเล่ม/ฉบับจากหน้าบทความ; ใช้ `scripts/inspect_thaijo_journal.py` เก็บหน้า About/ประกาศ/เอกสารและตรา TCI แล้วตรวจข้อความ Tier/ช่วงปี ก่อนใช้ `scripts/apply_tci_tier.py` เติม Tier ในปีตีพิมพ์และ Tier ปัจจุบันแยกกัน
อ่าน `plugins/research-author-index/skills/research-author-index/SKILL.md` เพื่อดูขั้นตอนทั้งหมด
"""

PLUGIN_INSTALL = """# Research Author Index — single-plugin ZIP

ZIP นี้มี plugin เพียงรายการเดียวและมี `.codex-plugin/plugin.json` ในโฟลเดอร์ชั้นบนสุด
เตรียมไว้สำหรับช่อง Upload plugin ZIP ที่รองรับรูปแบบ plugin โดยตรง เช่นหน้า Admin > Plugins บน ChatGPT web เมื่อบัญชีมีสิทธิ์อัปโหลด

หากต้องการติดตั้ง **ใน Codex app บน Windows** ให้ใช้ไฟล์ `research-author-index-marketplace.zip` แทน: แตก ZIP เปิดโฟลเดอร์ `research-author-index-bundle` เป็นโปรเจกต์ แล้วติดตั้งจาก Plugins Directory ตาม `INSTALL.md` ใน ZIP นั้น

การสร้าง Excel ต้องมี Python 3 และ `openpyxl`:

```powershell
py -3 -m pip install -r requirements.txt
```

เริ่มทุกงานด้วยการเปิด Scopus ให้ผู้ใช้เห็น ใช้ Chrome ที่เชื่อมไว้ หรือ Codex Browser หากยังไม่ล็อกอิน ต้องแจ้งให้ผู้ใช้ Login และรอจนตรวจยืนยันได้ก่อนเริ่มค้นหรือประมวลผลข้อมูล
Scopus ใช้แท็บที่ผู้ใช้ล็อกอินและเครื่องมือ UI/Playwright ที่เบราว์เซอร์รองรับ ตรวจจำนวนในหน้าต่าง Export แล้วเริ่มรอ download ก่อนกดดาวน์โหลด CSV ไม่เรียก private API หรือคัดลอก cookies
ThaiJO ใช้สคริปต์อ่านหน้าสาธารณะแบบชุดและใช้เบราว์เซอร์เก็บหน้าที่ยังขาด ต้องตรวจจำนวนครบก่อนสรุปผล
"""


def plugin_files() -> list[Path]:
    return [
        ROOT / ".codex-plugin/plugin.json",
        *sorted((ROOT / "scripts").glob("*.py")),
        *sorted((ROOT / "tests").glob("*.py")),
        *sorted((ROOT / "skills").rglob("*.md")),
    ]


def add_plugin(z: ZipFile, prefix: str, files: list[Path], install: str | None = None) -> None:
    for file in files:
        z.write(file, f"{prefix}/{file.relative_to(ROOT).as_posix()}")
    z.writestr(f"{prefix}/requirements.txt", REQUIREMENTS)
    if install:
        z.writestr(f"{prefix}/INSTALL.md", install)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="local-marketplace ZIP")
    parser.add_argument("--plugin-output", required=True, type=Path, help="single-plugin ZIP")
    args = parser.parse_args()
    if args.output.resolve() == args.plugin_output.resolve():
        parser.error("output paths must be different")
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if manifest.get("name") != PLUGIN:
        parser.error("plugin name does not match package name")
    marketplace = {
        "name": "research-author-index-pack",
        "interface": {"displayName": "Research Author Index Pack"},
        "plugins": [{
            "name": PLUGIN,
            "source": {"source": "local", "path": f"./plugins/{PLUGIN}"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }],
    }
    files = plugin_files()
    for output in (args.output, args.plugin_output):
        output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED) as z:
        z.writestr(f"{BUNDLE}/.agents/plugins/marketplace.json", json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n")
        z.writestr(f"{BUNDLE}/INSTALL.md", MARKETPLACE_INSTALL)
        add_plugin(z, f"{BUNDLE}/plugins/{PLUGIN}", files)
    with ZipFile(args.plugin_output, "w", ZIP_DEFLATED) as z:
        add_plugin(z, PLUGIN, files, PLUGIN_INSTALL)
    print(f"Created {args.output} and {args.plugin_output}: version {manifest['version']}, {len(files)} plugin files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
