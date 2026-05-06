import { ApifyClient } from "apify-client";
import config from "../config.js";
import { log, error } from "../utils/logger.js";

const client = new ApifyClient({ token: config.apifyToken });

function normalizeJob({ source, title, company, location, postedDate, url, salary, description, snippet }) {
  return {
    source,
    job_title: title || "Data Engineering",
    company: company || "Unknown",
    location: location || "United States",
    remote: /remote/i.test(location || ""),
    posted_date: postedDate || new Date().toISOString(),
    url,
    description: description || snippet || "",
    requirements: null,
    salary: salary || null,
    id: `${source.toLowerCase()}-${encodeURIComponent(url)}`,
    raw_payload: { title, company, location, salary }
  };
}

export async function fetchIndeedJobsViaApifyAPI() {
  try {
    log("Fetching Indeed jobs via Apify API actor: apify/indeed-scraper");
    
    const input = {
      searchTerm: config.jobKeywords,
      locationFilter: config.jobLocation,
      positionTypes: ["remote"],
      maxPages: 1
    };

    log(`Starting Indeed Apify actor with input: ${JSON.stringify(input)}`);
    
    const run = await client.actor("apify/indeed-scraper").call(input);
    const jobs = [];

    if (run && run.defaultDatasetId) {
      const dataset = await client.dataset(run.defaultDatasetId).listItems();
      
      if (dataset && dataset.items) {
        for (const item of dataset.items) {
          jobs.push(
            normalizeJob({
              source: "Indeed",
              title: item.positionName || item.jobTitle,
              company: item.companyName,
              location: item.location,
              postedDate: item.postedDate,
              url: item.jobUrl || item.url,
              salary: item.salary || item.salaryRange,
              description: item.description,
              snippet: item.snippet
            })
          );
        }
      }
    }

    log(`Indeed API fetch completed: ${jobs.length} jobs found`);
    return jobs;
  } catch (err) {
    error(`Indeed API fetch failed: ${err.message}`);
    return [];
  }
}

export async function fetchZipRecruiterJobsViaApifyAPI() {
  try {
    log("Fetching ZipRecruiter jobs via Apify API actor: apify/ziprecruiter-scraper");
    
    const input = {
      search: config.jobKeywords,
      location: config.jobLocation,
      remote: true,
      days: config.maxAgeDays,
      maxPages: 1
    };

    log(`Starting ZipRecruiter Apify actor with input: ${JSON.stringify(input)}`);
    
    const run = await client.actor("apify/ziprecruiter-scraper").call(input);
    const jobs = [];

    if (run && run.defaultDatasetId) {
      const dataset = await client.dataset(run.defaultDatasetId).listItems();
      
      if (dataset && dataset.items) {
        for (const item of dataset.items) {
          jobs.push(
            normalizeJob({
              source: "ZipRecruiter",
              title: item.jobTitle || item.title,
              company: item.company,
              location: item.location,
              postedDate: item.datePosted || item.postedDate,
              url: item.jobUrl || item.url,
              salary: item.salary || item.salaryRange,
              description: item.description,
              snippet: item.snippet
            })
          );
        }
      }
    }

    log(`ZipRecruiter API fetch completed: ${jobs.length} jobs found`);
    return jobs;
  } catch (err) {
    error(`ZipRecruiter API fetch failed: ${err.message}`);
    return [];
  }
}
