import dotenv from "dotenv";

dotenv.config();

const env = (key, fallback = undefined) => {
  const v = process.env[key];
  return v === undefined || v === "" ? fallback : v;
};

export const config = {
  env: env("NODE_ENV", "development"),
  port: Number(env("PORT", 8000)),
  sessionSecret: env("SESSION_SECRET", "dev_secret_change"),
  pyPlannerUrl: env("PY_PLANNER_URL", "http://127.0.0.1:8001"),
  corsOrigin: env("CORS_ORIGIN", ""), // e.g., http://localhost:5173 for SPA
};

export default config;
