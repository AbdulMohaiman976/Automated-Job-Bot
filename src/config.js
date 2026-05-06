import { config as dotenvConfig } from "dotenv";

// Load environment variables from .env file
dotenvConfig();

export default {
  candidateEmail: process.env.CANDIDATE_EMAIL || "candidate@example.com",
  apifyToken: process.env.APIFY_TOKEN,
  jobKeywords: process.env.JOB_KEYWORDS || "Data Engineer",
  jobLocation: process.env.JOB_LOCATION || "United States",
  remoteOnly: true,
  maxAgeDays: 1,
  outputDir: "./data",
  apify: {
    maxRetries: Number(process.env.APIFY_MAX_RETRIES || 3),
    timeoutSeconds: Number(process.env.APIFY_TIMEOUT_SECONDS || 300),
    maxConcurrency: Number(process.env.APIFY_MAX_CONCURRENCY || 5),
  },
};
