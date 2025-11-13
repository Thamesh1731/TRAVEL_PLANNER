import { Router } from "express";
import { requireFields, toInt } from "../utils/validate.js";
import { planWithPython } from "../services/plannerClient.js";
import requireAuth from "./middleware/requireAuth.js";

const router = Router();

// You can protect this route by adding requireAuth as middleware:
router.post("/", /* requireAuth, */ async (req, res) => {
  try {
    const body = req.body || {};
    requireFields(body, ["traveler_type", "destination", "days"]);
    const payload = {
      traveler_type: String(body.traveler_type).trim(),
      destination: String(body.destination).trim(),
      days: toInt(body.days, 1),
      use_groq: Boolean(body.use_groq),
    };

    if (body.stay_lat !== undefined && body.stay_lng !== undefined) {
      payload.stay_lat = Number(body.stay_lat);
      payload.stay_lng = Number(body.stay_lng);
    }

    if (payload.days < 1 || payload.days > 14) {
      return res.status(400).json({ error: "days must be between 1 and 14" });
    }

    // Call Python planner (swap to internal JS logic if you prefer)
    const data = await planWithPython(payload);
    res.json(data);
  } catch (e) {
    console.error("[itinerary]", e);
    res.status(e.status || 500).json({ error: e.message || "Planner error" });
  }
});

export default router;
