import { ApifyClient } from "apify-client";
import config from "../config.js";
import { log, error } from "../utils/logger.js";

const client = new ApifyClient({ token: config.apifyToken });

// Actor ID for the LinkedIn Jobs Scraper by automation-lab
const LINKEDIN_ACTOR_ID = "automation-lab/linkedin-jobs-scraper";

/**
 * Normalize a raw LinkedIn job item from the Apify dataset
 * into the shared Job-Bot schema.
 */
function normalizeLinkedInJob(item) {
  return {
    source: "LinkedIn",
    job_title: item.title || "Data Engineering",
    company: item.companyName || "Unknown",
    company_url: item.companyLinkedinUrl || null,
    company_logo: item.companyLogo || null,
    location: item.location || "United States",
    remote: /remote/i.test(item.title || "") || /remote/i.test(item.location || "") || item.workplaceType === "Remote",
    posted_date: item.postedAt || null,
    scraped_at: item.scrapedAt || new Date().toISOString(),
    url: item.url || null,
    apply_url: item.applyUrl || item.url || null,
    description: item.descriptionText || "",
    description_html: item.descriptionHtml || "",
    requirements: null,
    salary: item.salary || null,
    seniority_level: item.seniorityLevel || null,
    employment_type: item.employmentType || null,
    job_function: item.jobFunction || null,
    industries: item.industries || null,
    applicants_count: item.applicantsCount || null,
    benefits: item.benefits || null,
    id: `linkedin-${item.id || encodeURIComponent(item.url || "")}`,
    raw_payload: item,
  };
}

/**
 * Fetch LinkedIn Data Engineering jobs via the Apify API.
 * Uses the automation-lab/linkedin-jobs-scraper actor.
 *
 * @param {Object} options - Override default search parameters
 * @param {string} options.searchQuery - Search keywords (default: from config)
 * @param {string} options.location - Location filter (default: from config)
 * @param {number} options.maxJobs - Max jobs to scrape (default: 999)
 * @param {string} options.workplaceType - "2" = remote, "1" = on-site, "3" = hybrid
 * @param {string} options.datePosted - "r86400" = last 24h, "r604800" = last week
 * @param {boolean} options.scrapeJobDetails - Whether to scrape full descriptions
 * @returns {Promise<Array>} Normalized job objects
 */
export async function fetchLinkedInJobsViaApifyAPI(options = {}) {
  try {
    const input = {
      searchQuery: options.searchQuery || config.jobKeywords,
      location: options.location || config.jobLocation,
      maxJobs: options.maxJobs || 999,
      workplaceType: options.workplaceType || "2",           // Remote
      datePosted: options.datePosted || "r86400",             // Last 24 hours
      sortBy: options.sortBy || "R",                          // Most recent
      experienceLevel: options.experienceLevel || "all",
      jobType: options.jobType || "all",
      scrapeJobDetails: options.scrapeJobDetails !== undefined ? options.scrapeJobDetails : true,
      maxRequestRetries: config.apify.maxRetries,
    };

    log(`Starting LinkedIn Apify actor (${LINKEDIN_ACTOR_ID}) with input:`);
    log(JSON.stringify(input, null, 2));

    const run = await client.actor(LINKEDIN_ACTOR_ID).call(input, {
      timeoutSecs: config.apify.timeoutSeconds,
      memoryMbytes: 256,
    });

    const jobs = [];

    if (run && run.defaultDatasetId) {
      log(`Actor run completed. Dataset ID: ${run.defaultDatasetId}`);
      const dataset = await client.dataset(run.defaultDatasetId).listItems();

      if (dataset && dataset.items) {
        for (const item of dataset.items) {
          jobs.push(normalizeLinkedInJob(item));
        }
      }
    } else {
      error("Actor run completed but no dataset was returned.");
    }

    log(`LinkedIn API fetch completed: ${jobs.length} jobs found`);
    return jobs;
  } catch (err) {
    error(`LinkedIn API fetch failed: ${err.message}`);
    return [];
  }
}

/**
 * Fetch jobs from a previous LinkedIn actor run's dataset.
 * Useful for re-processing data without re-running the actor.
 *
 * @param {string} datasetId - The Apify dataset ID from a previous run
 * @returns {Promise<Array>} Normalized job objects
 */
export async function fetchLinkedInJobsFromDataset(datasetId) {
  try {
    log(`Fetching jobs from existing dataset: ${datasetId}`);
    const dataset = await client.dataset(datasetId).listItems();
    const jobs = [];

    if (dataset && dataset.items) {
      for (const item of dataset.items) {
        jobs.push(normalizeLinkedInJob(item));
      }
    }

    log(`Fetched ${jobs.length} jobs from dataset ${datasetId}`);
    return jobs;
  } catch (err) {
    error(`Failed to fetch from dataset ${datasetId}: ${err.message}`);
    return [];
  }
}
