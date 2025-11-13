// Tiny validation helpers. Use zod for complex shapes in routes.

export function requireFields(body, fields = []) {
  const missing = fields.filter((f) => body[f] === undefined || body[f] === null || body[f] === "");
  if (missing.length) {
    const err = new Error(`Missing required fields: ${missing.join(", ")}`);
    err.status = 400;
    throw err;
  }
}

export function toInt(v, def = 0) {
  const n = Number.parseInt(String(v), 10);
  return Number.isFinite(n) ? n : def;
}

export function isEmail(str) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(str || "").trim());
}
