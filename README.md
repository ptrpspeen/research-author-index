# Research Author Index

ปลั๊กอินสำหรับ Codex ช่วยค้นผลงานนักวิจัยจาก **Scopus** และ **ThaiJO/TCI** แล้วสร้าง Excel สองชีต พร้อมลิงก์บทความ, h-index, หลักฐาน CiteScore Q และ TCI Tier

## ติดตั้งผ่าน GitHub

ต้องมี Codex ที่รองรับ plugins, Python 3.9 ขึ้นไป และ Chrome ที่เชื่อมกับ Codex หรือ Codex Browser

```sh
codex plugin marketplace add ptrpspeen/research-author-index
codex plugin add research-author-index@research-author-index-pack
python3 -m pip install 'openpyxl>=3.1,<4' 'pypdf>=5,<7'
```

Windows ใช้ `py -3 -m pip install "openpyxl>=3.1,<4" "pypdf>=5,<7"` แทนคำสั่ง Python ด้านบน เปิดแชตใหม่หลังติดตั้ง เพื่อโหลด skill

หากไม่มี Codex CLI ดาวน์โหลด **research-author-index-marketplace.zip** จาก [Releases](https://github.com/ptrpspeen/research-author-index/releases/latest) แล้วทำตาม [INSTALL.md](INSTALL.md) ส่วน **research-author-index-plugin.zip** เป็นแพ็กเกจปลั๊กอินเดี่ยวสำหรับช่องอัปโหลดที่รองรับรูปแบบนั้น

## ใช้งาน

สั่ง Codex เช่น:

> ใช้ Research Author Index ค้นผลงาน Scopus และ ThaiJO/TCI ของ [ชื่อเต็ม] สังกัด [หน่วยงาน] แล้วทำ Excel พร้อมหลักฐาน Q และ Tier

ทุกงานเริ่มด้วยการเปิด Scopus ให้ผู้ใช้เห็น และตรวจว่าล็อกอินบัญชีแล้ว หากยังไม่ล็อกอินจะรอให้ผู้ใช้ทำเอง การล็อกอินกับสิทธิ์เข้าถึง Scopus ของสถาบันเป็นคนละส่วน ผู้ใช้ต้องมีสิทธิ์ที่เหมาะสม

- Scopus ใช้ browser UI และ CSV Export จาก session ของผู้ใช้
- ThaiJO ใช้หน้าสาธารณะและเครื่องมือ browser ตรวจรายการที่ยังขาด
- Q ใช้ CiteScore percentile พร้อมปี สาขา และ URL หลักฐาน
- Tier แยก **ในปีตีพิมพ์** และ **ปัจจุบัน ณ วันที่ตรวจ** โดยเก็บ About, Indexing/ประวัติ, ประกาศ, PDF และภาพที่ลิงก์ไว้
- ข้อความต่อเนื่อง “ตั้งแต่ปี…” ของวารสารถูกระบุเป็น `publisher_since` แยกจากช่วงรับรองที่ระบุชัด
- ข้อมูลที่ยังยืนยันไม่ได้เว้นว่างพร้อมข้อจำกัด ต้องตรวจหลักฐานก่อนเติมค่า การผ่าน validation ของไฟล์ไม่ได้ยืนยันว่าการค้นทุกฐานหรือทุกปีครบแล้ว

ดูขั้นตอนเต็มใน [SKILL.md](plugins/research-author-index/skills/research-author-index/SKILL.md) และ [การเก็บหลักฐาน Tier](plugins/research-author-index/skills/research-author-index/references/tier-evidence.md)

## พัฒนาและทดสอบ

```sh
git clone https://github.com/ptrpspeen/research-author-index.git
cd research-author-index
python3 -m pip install -r plugins/research-author-index/requirements.txt
python3 -m unittest discover -s plugins/research-author-index/tests -v
```

ชุดทดสอบทำงานแบบ offline โดยสร้างข้อมูลตัวอย่าง ข้อทดสอบ captured ThaiJO profile จะข้ามเมื่อไม่มี local fixture; ไม่จำเป็นต้องเผยแพร่ข้อมูลผู้วิจัยเพื่อรันชุดทดสอบหลัก

สร้าง ZIP ทั้งสองรูปแบบจาก source:

```sh
python3 plugins/research-author-index/scripts/build_share_zip.py \
  --output dist/research-author-index-marketplace.zip \
  --plugin-output dist/research-author-index-plugin.zip
```

บน Windows ใช้ `py -3` และรวมคำสั่ง build เป็นบรรทัดเดียว ผลลัพธ์อยู่ใน `dist/`

เวอร์ชันและรายละเอียดการเปลี่ยนแปลง: [CHANGELOG.md](CHANGELOG.md)
