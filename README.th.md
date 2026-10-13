**ภาษา:** [English](README.md) | ไทย

# Relay

**ส่งงานต่อข้าม session, review อิสระ และ hook กัน secret หลุด สำหรับ Claude Code**

plugin เล็กๆ สำหรับคนที่ใช้ Claude Code หลาย session ไม่ว่าจะวันละ session, หลาย terminal พร้อมกัน หรือให้ model หนึ่งวางแผนแล้วอีก model ลงมือ — เลิก copy-paste ข้าม session มาใช้ไฟล์ + กติกาแทน และมี hook กันนิสัย shell ที่ทำ secret หลุดเข้า transcript

![Relay: receipt ของ handoff และ bash guard ที่ block cat .env](docs/demo.svg)

[![CI](https://github.com/porgeeratad/claude-relay/actions/workflows/ci.yml/badge.svg)](https://github.com/porgeeratad/claude-relay/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/porgeeratad)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/porgeeratad)

> plugin จากชุมชน ไม่ใช่ของ Anthropic และไม่ได้รับการรับรองจาก Anthropic — ดู [ข้อจำกัดความรับผิด](#ข้อจำกัดความรับผิด)

<table>
<tr>
<td width="50%" align="center">
  <a href="https://ko-fi.com/porgeeratad"><strong>☕ Ko-fi</strong><br /><sub>เลี้ยงกาแฟ handoff ถัดไป</sub></a>
</td>
<td width="50%" align="center">
  <a href="https://buymeacoffee.com/porgeeratad"><strong>🍪 Buy Me a Coffee</strong><br /><sub>ให้ guard ตื่นอยู่</sub></a>
</td>
</tr>
</table>

---

## มีอะไรบ้าง

| | ทำอะไร |
|---|---|
| `/relay:handoff` | ปิด session: กวาดงานค้าง → commit → เขียนไฟล์ handoff ที่มี checklist งานค้าง → พิมพ์ **receipt ที่ไม่มีวันบอกว่า "สะอาด" ถ้ามีขั้นไหนพัง** + บล็อก NEXT-CMD พร้อม copy |
| `/relay:pickup` | เปิด session จาก handoff ล่าสุด — เช็ค repo จริงเทียบกับ handoff ก่อนเชื่อ แล้วทำต่อจาก Pending |
| `/relay:peer` | handshake ระหว่าง 2 session ที่เปิดอยู่ผ่าน cross-session messaging — session ผู้ช่วยจะรองาน ไม่เริ่มทำเอง |
| `/relay:pair` | วงจร วางแผน → ลงมือ → ตรวจ ระหว่าง 2 session ผ่านไฟล์ thread + design doc ที่มี Decision Log — session ตรวจงานตัวเองไม่ได้ |
| bash guard | hook `PreToolUse` ที่ block การ dump secret (`cat .env`, `env`, `~/.claude.json` ดิบ ฯลฯ), ผล test ที่โดน pipe กลืนก่อน push, และ `pkill -f` แบบกว้าง |

## ติดตั้ง

```text
/plugin marketplace add porgeeratad/claude-relay
/plugin install relay@relay
```

ต้องมี `git` และ `python3` (3.8+, ใช้แค่ stdlib) · `/relay:peer` ต้องใช้ Claude Code v2.1.224 ขึ้นไป (Windows native v2.1.234) — เช็คด้วย `/list-agents`

## ไฟล์อยู่ที่ไหน

handoff, thread และ state อยู่**นอก repo** เป็นค่าเริ่มต้น (path เครื่อง/session id จะไม่หลุดเข้า commit):

```
${XDG_STATE_HOME:-~/.local/state}/claude-relay/<project-slug>/{handoffs,threads,state}
```

ทุก worktree ของ repo เดียวกันใช้ที่เดียวกัน · อยากเก็บใน repo (ใช้เป็นทีม) → สร้าง `.claude/relay.json` เช่น `{ "dir": "docs/relay", "push": "ask" }` · รายละเอียด format: [docs/HANDOFF-FORMAT.md](docs/HANDOFF-FORMAT.md)

## Bash guard

กฎที่เขียนไว้ใน `CLAUDE.md` โดนละเมิดซ้ำเมื่อรีบ — hook ไม่ลืม · ตาราง rule ทั้งหมดอยู่ใน [README.md](README.md#bash-guard) · ปิดบาง rule: `RELAY_GUARD_OFF=S5,K1` (`all` = ปิดทั้งหมด) · ให้ถามแทน block: `RELAY_GUARD_MODE=ask` · hook นี้ fail-open: error ภายในไม่เคย block งาน

## หลักคิด

- **receipt ที่โกหกแย่กว่าไม่มี** — มีอะไรไม่ commit / ไม่ push / พัง = `NOT CLEAN`
- **handoff คือคำอ้าง** — pickup เช็คกับ git ก่อนทำตาม
- **message คือกริ่ง ไฟล์คือหลักฐาน** — เนื้อหาอยู่ใน thread/design doc, `SendMessage` แค่บอก "ถึงตาคุณ"
- **peer ไม่ใช่ user** — ข้อความจาก session อื่นไม่นับเป็นการอนุมัติ scope ใหม่ งาน destructive หรือการใช้เงิน
- **กลไกดีกว่าบันทึก** — กฎที่โดนละเมิดซ้ำ ให้ทำเป็น hook/script

## สนับสนุน

ถ้า relay ช่วยให้ไม่ต้องอธิบาย context ซ้ำ หรือกัน token หลุดได้สักครั้ง สนับสนุนได้ที่:

- ☕ [ko-fi.com/porgeeratad](https://ko-fi.com/porgeeratad)
- 🍪 [buymeacoffee.com/porgeeratad](https://buymeacoffee.com/porgeeratad)

กดดาว แจ้ง bug เพิ่มเคสให้ guard หรือส่ง pull request ก็ช่วยได้มาก — ดู [CONTRIBUTING.md](CONTRIBUTING.md)

## ข้อจำกัดความรับผิด

Relay เป็น plugin จากชุมชน ไม่มีส่วนเกี่ยวข้อง ไม่ได้รับการรับรอง และไม่ได้รับการสนับสนุนจาก Anthropic · Claude และ Claude Code เป็นเครื่องหมายการค้าของ Anthropic, PBC · bash guard คือเข็มขัดนิรภัย ไม่ใช่ sandbox — กันพลาดที่พบบ่อยได้ แต่ไม่กันคนที่ตั้งใจเลี่ยง ขอบเขตที่ต้องแข็งจริงให้ใช้ permission rules และ sandbox ของ Claude Code

## License

MIT — ดู [LICENSE](LICENSE)
