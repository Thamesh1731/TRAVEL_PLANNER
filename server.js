require('dotenv').config();
const path = require('path');
const express = require('express');
const mongoose = require('mongoose');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const cookieParser = require('cookie-parser');
const { OAuth2Client } = require('google-auth-library');
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

const app = express();

// Middleware
app.use(express.json());
app.use(cookieParser());
// If you serve the frontend from this same app, origin:true is fine.
// If you serve from a different origin in dev, set origin to that URL.
app.use(cors({ origin: true, credentials: true }));

// Static frontend
app.use(express.static(path.join(__dirname, 'public')));
app.get('/', (req, res) => {
res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// MongoDB connection
(async () => {
try {
await mongoose.connect(process.env.MONGODB_URI, { dbName: 'authdemo' });
console.log('Connected to MongoDB Atlas');
} catch (e) {
console.error('Mongo connect error', e);
process.exit(1);
}
})();

// User model
const userSchema = new mongoose.Schema(
{
firstName: String,
lastName: String,
email: { type: String, unique: true, required: true, index: true },
passwordHash: String,
provider: { type: String, enum: ['local', 'google'], default: 'local' },
googleSub: String,
},
{ timestamps: true }
);

const User = mongoose.model('User', userSchema);

// JWT helper
function sign(userId) {
return jwt.sign({ uid: userId }, process.env.JWT_SECRET, { expiresIn: '7d' });
}

// Register
app.post('/api/register', async (req, res) => {
try {
console.log('[register] body:', req.body);
const { firstName, lastName, email, password } = req.body;
if (!email || !password) {
  return res.status(400).json({ message: 'Missing fields' });
}

const exists = await User.findOne({ email });
if (exists) {
  return res.status(409).json({ message: 'Email already registered' });
}

const passwordHash = await bcrypt.hash(password, 12);
const user = await User.create({
  firstName: firstName || '',
  lastName: lastName || '',
  email,
  passwordHash,
  provider: 'local',
});

const token = sign(user._id.toString());
res.cookie('token', token, { httpOnly: true, sameSite: 'lax' });
res.json({ ok: true });
} catch (e) {
if (e && e.code === 11000) {
// Duplicate key (unique index on email)
return res.status(409).json({ message: 'Email already registered' });
}
console.error('[register] error:', e);
res.status(500).json({ message: 'Server error' });
}
});

// Login
app.post('/api/login', async (req, res) => {
try {
console.log('[login] body:', req.body);
const { email, password } = req.body;
const user = await User.findOne({ email, provider: 'local' });
if (!user) {
  return res.status(401).json({ message: 'Invalid email or password' });
}

const ok = await bcrypt.compare(password, user.passwordHash || '');
if (!ok) {
  return res.status(401).json({ message: 'Invalid email or password' });
}

const token = sign(user._id.toString());
res.cookie('token', token, { httpOnly: true, sameSite: 'lax' });
res.json({ ok: true });
} catch (e) {
console.error('[login] error:', e);
res.status(500).json({ message: 'Server error' });
}
});

// Google Sign-In
const googleClient = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);

app.post('/api/google', async (req, res) => {
try {
const { credential } = req.body;
if (!credential) {
return res.status(400).json({ message: 'Missing credential' });
}
// Verify the ID token from GIS
const ticket = await googleClient.verifyIdToken({
  idToken: credential,
  audience: process.env.GOOGLE_CLIENT_ID,
});
const payload = ticket.getPayload(); // { sub, email, given_name, family_name, ... }

if (!payload?.email || !payload?.sub) {
  return res.status(401).json({ message: 'Invalid Google token' });
}

// Upsert user
let user = await User.findOne({ email: payload.email });
if (!user) {
  user = await User.create({
    firstName: payload.given_name || '',
    lastName: payload.family_name || '',
    email: payload.email,
    provider: 'google',
    googleSub: payload.sub,
  });
} else if (user.provider === 'local' && !user.googleSub) {
  // link google to existing local account
  user.googleSub = payload.sub;
  user.provider = 'google';
  await user.save();
}

const token = sign(user._id.toString());
res.cookie('token', token, { httpOnly: true, sameSite: 'lax' });
res.json({ ok: true });
} catch (e) {
console.error('[google] error:', e?.response?.data || e);
res.status(401).json({ message: 'Google verification failed' });
}
});

// Me (optional)
app.get('/api/me', (req, res) => {
try {
const token =
req.cookies.token || (req.headers.authorization || '').replace('Bearer ', '');
if (!token) return res.status(401).json({ message: 'No token' });
const decoded = jwt.verify(token, process.env.JWT_SECRET);
res.json({ ok: true, uid: decoded.uid });
} catch (e) {
res.status(401).json({ message: 'Invalid token' });
}
});

// Itinerary planner route
app.post('/api/itinerary', async (req, res) => {
  try {
    const body = req.body || {};
    const { traveler_type, destination, days, stay_lat, stay_lng, use_groq } = body;
    if (!traveler_type || !destination || !days) {
      return res.status(400).json({ error: 'Missing required fields: traveler_type, destination, days' });
    }
    if (days < 1 || days > 14) {
      return res.status(400).json({ error: 'days must be between 1 and 14' });
    }

    const payload = {
      traveler_type: String(traveler_type).trim(),
      destination: String(destination).trim(),
      days: Number(days),
      use_groq: Boolean(use_groq),
    };

    if (stay_lat !== undefined && stay_lng !== undefined) {
      payload.stay_lat = Number(stay_lat);
      payload.stay_lng = Number(stay_lng);
    }

    // Call Python planner
    const pyUrl = process.env.PY_PLANNER_URL || 'http://127.0.0.1:8001';
    const r = await fetch(`${pyUrl}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    let out = null;
    try {
      out = await r.json();
    } catch {
      // ignore JSON parse error to surface HTTP error
    }

    if (!r.ok) {
      const msg = out?.detail || out?.error || `Planner service error (HTTP ${r.status})`;
      return res.status(r.status).json({ error: msg });
    }

    res.json(out);
  } catch (e) {
    console.error('[itinerary]', e);
    res.status(500).json({ error: e.message || 'Planner error' });
  }
});

// Start
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log('Server listening on', PORT));