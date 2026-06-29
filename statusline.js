#!/usr/bin/env node
/**
 * Claude Code statusline script (Windows-friendly, Node.js).
 *
 * Việc của script này có 2 phần:
 *   1. In ra một dòng status ngắn gọn để Claude Code hiển thị ở statusline.
 *   2. Ghi đè toàn bộ JSON (bao gồm rate_limits) ra một file local
 *      để các công cụ khác (dashboard, widget desktop, v.v.) đọc mỗi phút.
 *
 * Cài đặt (Windows):
 *   1. Lưu file này vào: %USERPROFILE%\.claude\statusline.js
 *   2. Trong %USERPROFILE%\.claude\settings.json thêm:
 *        "statusLine": {
 *          "type": "command",
 *          "command": "node %USERPROFILE%\\.claude\\statusline.js"
 *        }
 *   3. Khởi động lại Claude Code.
 *
 * Lưu ý: statusline chỉ chạy KHI Claude Code đang mở một phiên active
 * và đang render UI — nó không phải cron job nền. Nếu bạn cần dữ liệu
 * cập nhật "mỗi phút" ngay cả khi không gõ gì, xem ghi chú cuối file.
 */

const fs = require("fs");
const os = require("os");
const path = require("path");

const HBLOCKS = ['░', '▏', '▎', '▍', '▌', '▋', '▊', '▉', '█'];

function fillChars(f) {
  const c1 = f < 0.5 ? HBLOCKS[Math.round(f * 2 * 8)] : '█';
  const c2 = f < 0.5 ? '░' : HBLOCKS[Math.round((f - 0.5) * 2 * 8)];
  return [c1, c2];
}

// units: số block (5 hoặc 7), unitMs: độ dài 1 unit tính ms
// resetsAt: unix ms khi window reset, usedPct: % đã dùng
function buildBar(units, unitMs, resetsAt, usedPct) {
  const now      = Date.now();
  const startsAt = resetsAt - units * unitMs;
  const elapsed  = now - startsAt;
  const idx      = Math.min(units - 1, Math.floor(elapsed / unitMs));
  const frac     = (elapsed % unitMs) / unitMs;
  const size     = units * 2;

  const flat = [];
  for (let i = 0; i < units; i++) {
    if (i < idx)        flat.push('█', '█');
    else if (i === idx) flat.push(...fillChars(frac));
    else                flat.push('░', '░');
  }
  flat[Math.min(size - 1, Math.floor(usedPct / 100 * size))] = '▒';
  return Array.from({ length: units }, (_, i) => flat[i * 2] + flat[i * 2 + 1]).join('·');
}

let raw = "";
process.stdin.on("data", (chunk) => (raw += chunk));
process.stdin.on("end", () => {
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    process.stdout.write("statusline: invalid JSON input");
    return;
  }

  // Dump raw data để debug — xóa khi không cần nữa
  try {
    const dumpFile = path.join(os.homedir(), ".claude", "statusline-data.json");
    fs.writeFileSync(dumpFile, JSON.stringify(data, null, 2), "utf8");
  } catch (_) {}

  const rl = data.rate_limits || {};
  const fiveHour = rl.five_hour || {};
  const sevenDay = rl.seven_day || {};

  // ---- 1. Ghi file snapshot để công cụ khác đọc ----
  const outDir = path.join(os.homedir(), ".claude");
  const outFile = path.join(outDir, "usage_state.json");

  const snapshot = {
    updated_at: new Date().toISOString(),
    session_id: data.session_id,
    model: data.model && data.model.display_name,
    cost_usd: data.cost && data.cost.total_cost_usd,
    context_used_pct: data.context_window && data.context_window.used_percentage,
    five_hour: {
      used_percentage: fiveHour.used_percentage ?? null,
      // resets_at từ Claude Code là unix timestamp (giây)
      resets_at_unix: fiveHour.resets_at ?? null,
      resets_at_iso: fiveHour.resets_at
        ? new Date(fiveHour.resets_at * 1000).toISOString()
        : null,
    },
    seven_day: {
      used_percentage: sevenDay.used_percentage ?? null,
      resets_at_unix: sevenDay.resets_at ?? null,
      resets_at_iso: sevenDay.resets_at
        ? new Date(sevenDay.resets_at * 1000).toISOString()
        : null,
    },
  };

  try {
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outFile, JSON.stringify(snapshot, null, 2), "utf8");
  } catch (e) {
    // Không chặn statusline nếu ghi file lỗi
  }

  // ---- 2. In ra statusline ngắn gọn ----
  const model = (data.model && data.model.display_name) || "Claude";
  const cost = data.cost && data.cost.total_cost_usd != null
    ? `$${data.cost.total_cost_usd.toFixed(2)}`
    : "";
  const ctxPct = data.context_window && data.context_window.used_percentage != null
    ? data.context_window.used_percentage.toFixed(0)
    : "?";

  const pct5h = fiveHour.used_percentage != null ? fiveHour.used_percentage.toFixed(0) : "?";
  const bar5h = fiveHour.used_percentage != null && fiveHour.resets_at != null
    ? " " + buildBar(5, 3600000, fiveHour.resets_at * 1000, fiveHour.used_percentage)
    : "";

  const pct7d = sevenDay.used_percentage != null ? sevenDay.used_percentage.toFixed(0) : "?";
  const bar7d = sevenDay.used_percentage != null && sevenDay.resets_at != null
    ? " " + buildBar(7, 86400000, sevenDay.resets_at * 1000, sevenDay.used_percentage)
    : "";

  process.stdout.write(`Context ${ctxPct}% - ${model} - ${cost} | 5h${bar5h} ${pct5h}% | 7d${bar7d} ${pct7d}%`);
});
