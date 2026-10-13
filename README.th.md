# Relay — ส่งงานต่อระหว่าง session ของ Claude Code

[English](README.md)

plugin เล็กๆ สำหรับคนที่ใช้ Claude Code หลาย session ไม่ว่าจะวันละ session, หลาย terminal พร้อมกัน หรือให้ model หนึ่งวางแผนแล้วอีก model ลงมือ — เลิก copy-paste ข้าม session มาใช้ไฟล์ + กติกาแทน และมี hook กันนิสัย shell ที่ทำ secret หลุดเข้า transcript

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

## License

MIT — ดู [LICENSE](LICENSE)
