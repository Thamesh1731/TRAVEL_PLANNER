// Minimal session gate. Replace with JWT strategy later.
// Expects req.session.userId or a signed cookie named "uid".

export function requireAuth(req, res, next) {
  const uid = req.signedCookies?.uid || req.cookies?.uid || req.session?.userId;
  if (!uid) return res.status(401).json({ error: "Unauthorized" });
  req.userId = uid;
  next();
}

export default requireAuth;
