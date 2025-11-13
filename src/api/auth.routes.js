import { Router } from "express";
import crypto from "crypto";
import { requireFields, isEmail } from "../utils/validate.js";

const router = Router();

// In-memory users for demo (email -> { id, hash, salt, firstName, lastName })
// Replace with MongoDB/Prisma later.
const users = new Map();

function hashPassword(password, salt = crypto.randomBytes(16).toString("hex")) {
  const hash = crypto.pbkdf2Sync(password, salt, 10000, 64, "sha512").toString("hex");
  return { salt, hash };
}

function verifyPassword(password, user) {
  const { hash } = hashPassword(password, user.salt);
  return crypto.timingSafeEqual(Buffer.from(hash, "hex"), Buffer.from(user.hash, "hex"));
}

// POST /api/register
router.post("/register", async (req, res) => {
  try {
    const { firstName, lastName, email, password } = req.body || {};
    requireFields(req.body || {}, ["firstName", "lastName", "email", "password"]);
    if (!isEmail(email)) return res.status(400).json({ message: "Invalid email" });
    if ((password || "").length < 6) return res.status(400).json({ message: "Password too short" });

    const key = String(email).toLowerCase();
    if (users.has(key)) return res.status(409).json({ message: "Email already registered" });

    const id = crypto.randomUUID();
    const { salt, hash } = hashPassword(password);
    users.set(key, { id, email: key, firstName, lastName, salt, hash });

    return res.status(201).json({ ok: true });
  } catch (e) {
    console.error("[register]", e);
    return res.status(e.status || 500).json({ message: e.message || "Registration failed" });
  }
});

// POST /api/login
router.post("/login", async (req, res) => {
  try {
    const { email, password } = req.body || {};
    requireFields(req.body || {}, ["email", "password"]);
    const key = String(email).toLowerCase();
    const user = users.get(key);
    if (!user || !verifyPassword(password, user)) {
      return res.status(401).json({ message: "Invalid credentials" });
    }
    // Issue a signed cookie uid
    res.cookie("uid", user.id, {
      httpOnly: true,
      sameSite: "lax",
      signed: true,
      // secure: true, // enable in production HTTPS
      maxAge: 7 * 24 * 60 * 60 * 1000,
    });
    return res.json({ ok: true, user: { id: user.id, email: user.email, firstName: user.firstName } });
  } catch (e) {
    console.error("[login]", e);
    return res.status(e.status || 500).json({ message: e.message || "Login failed" });
  }
});

// POST /api/logout
router.post("/logout", (req, res) => {
  res.clearCookie("uid");
  res.json({ ok: true });
});

// POST /api/google (placeholder)
// Expect { credential } from Google Identity Services; verify on server in production.
router.post("/google", async (req, res) => {
  const { credential } = req.body || {};
  if (!credential) return res.status(400).json({ message: "Missing credential" });
  // TODO: verify JWT with Google certs and extract email/sub. For now, accept and set cookie.
  const id = `google-${crypto.randomUUID()}`;
  res.cookie("uid", id, { httpOnly: true, sameSite: "lax", signed: true, maxAge: 7 * 24 * 60 * 60 * 1000 });
  res.json({ ok: true, user: { id } });
});

export default router;
