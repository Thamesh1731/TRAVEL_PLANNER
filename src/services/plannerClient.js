import fetch from "node-fetch";
import { config } from "../config/index.js";

const PY = config.pyPlannerUrl;

export async function planWithPython({ traveler_type, destination, days, stay_lat, stay_lng, use_groq }) {
  const body = {
    traveler_type,
    destination,
    days: Number(days),
    use_groq: Boolean(use_groq),
    ...(stay_lat !== undefined && stay_lng !== undefined ? { stay_lat, stay_lng } : {}),
  };

  const r = await fetch(`${PY}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  let out = null;
  try {
    out = await r.json();
  } catch {
    // ignore JSON parse error to surface HTTP error
  }

  if (!r.ok) {
    const msg = out?.detail || out?.error || `Planner service error (HTTP ${r.status})`;
    const err = new Error(msg);
    err.status = 502;
    err.details = out;
    throw err;
  }

  return out;
}

export default { planWithPython };
