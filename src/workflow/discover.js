import dotenv from "dotenv";
import config from "../config.js";
import { fetchLinkedInJobsViaApifyAPI } from "../discovery/linkedin-api.js";
import { saveJobs, saveSummary } from "../storage/tracker.js";
import { log, error } from "../utils/logger.js";

// Load environment variables
dotenv.config();

if (!config.apifyToken) {
  error("APIFY_TOKEN environment variable is not set. Please set it in .env file.");
  process.exit(1);
}

function deduplicateJobs(jobs) {
  const seen = new Set();
  const deduped = [];

  for (const job of jobs) {
    const key = `${job.source}::${job.url}`;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(job);
    }
  }

  return deduped;
}

async function runDiscovery() {
  try {
    log("=== Starting daily discovery workflow via Apify API ===");
    log(`Search: "${config.jobKeywords}" | Location: "${config.jobLocation}" | Remote: ${config.remoteOnly}`);

    // Fetch LinkedIn jobs using the automation-lab/linkedin-jobs-scraper actor
    const linkedInJobs = await fetchLinkedInJobsViaApifyAPI();

    const dedupedJobs = deduplicateJobs(linkedInJobs);

    const summary = {
      date: new Date().toISOString(),
      total_discovered: linkedInJobs.length,
      total_deduplicated: dedupedJobs.length,
      by_source: {
        linkedin: linkedInJobs.length,
      },
    };

    await saveJobs(config.outputDir, dedupedJobs);
    await saveSummary(config.outputDir, summary);

    log("=== Daily discovery workflow complete ===");
    log(`Total: ${dedupedJobs.length} unique jobs saved`);
  } catch (err) {
    error(`Daily discovery workflow failed: ${err.message}`);
    process.exit(1);
  }
}

runDiscovery();
