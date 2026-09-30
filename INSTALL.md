# Research Author Index — ติดตั้งบน Windows ผ่าน Codex app

ZIP นี้เป็น **local marketplace**: ต้องแตกไฟล์ก่อน ไม่ใช่ไฟล์สำหรับกด Upload plugin ZIP โดยตรง

1. แตก ZIP ไปไว้ในโฟลเดอร์ถาวร เช่น `Documents\ResearchAuthorIndex` อย่าย้ายหรือลบโฟลเดอร์หลังติดตั้ง
2. ใน Codex app เปิดโฟลเดอร์ `research-author-index-bundle` เป็นโปรเจกต์ (โฟลเดอร์นี้มี `.agents/plugins/marketplace.json`)
3. ปิดและเปิด Codex app ใหม่ แล้วไปที่ Plugins Directory เลือก `Research Author Index Pack` และกด Install ที่ `Research Author Index`
4. ติดตั้ง Python 3 ถ้ายังไม่มี แล้วเปิด PowerShell ในโฟลเดอร์ `research-author-index-bundle` รัน:

```powershell
py -3 -m pip install -r .\plugins\research-author-index\requirements.txt
```

หาก `py` ไม่พบ ให้ลอง `python -m pip install -r .\plugins\research-author-index\requirements.txt`
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
