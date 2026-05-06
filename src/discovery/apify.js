import { CheerioCrawler } from "@crawlee/cheerio";
import { RequestQueue } from "@crawlee/core";
import config from "../config.js";
import { log, error } from "../utils/logger.js";

function buildIndeedSearchUrl({ keywords, location, maxAgeDays }) {
  const params = new URLSearchParams();
  params.set("q", keywords);
  params.set("l", location);
  params.set("fromage", String(maxAgeDays));
  params.set("sort", "date");
  params.set("radius", "0");
  params.set("remotejob", "1");
  params.set("limit", "50");
  return `https://www.indeed.com/jobs?${params.toString()}`;
}

function buildZipRecruiterSearchUrl({ keywords, location, maxAgeDays }) {
  const params = new URLSearchParams();
  params.set("search", keywords);
  params.set("location", location);
  params.set("radius", "0");
  params.set("days", String(maxAgeDays));
  params.set("remote", "true");
  params.set("page", "1");
  return `https://www.ziprecruiter.com/candidate/search?${params.toString()}`;
}

function normalizeJob({ source, title, company, location, postedDate, url, description, snippet, rawPayload }) {
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
    salary: null,
    id: `${source.toLowerCase()}-${encodeURIComponent(url)}`,
    raw_payload: rawPayload || {}
  };
}

function parseIndeedCard($, card) {
  const link = $(card).find("a[data-jk], a[title], a[href*='/rc/clk'], a[href*='/company/']").first();
  const jobPath = link.attr("href") || "";
  const url = jobPath.startsWith("http") ? jobPath : `https://www.indeed.com${jobPath}`;
  const title = $(card).find("h2.jobTitle span, h2.title span, .jobTitle").first().text().trim();
  const company = $(card).find("span.companyName, .company, .companyName").first().text().trim();
  const location = $(card).find("div.companyLocation, .location").first().text().trim();
  const snippet = $(card).find("div.job-snippet, .summary").text().trim();
  const postedText = $(card).find("span.date, .date").first().text().trim();

  return normalizeJob({
    source: "Indeed",
    title,
    company,
    location,
    postedDate: postedText,
    url,
    snippet,
    rawPayload: { posted_text: postedText, snippet }
  });
}

function parseZipRecruiterCard($, card) {
  const link = $(card).find("a[href*='/r/'], a[href*='/job/']").first();
  const jobPath = link.attr("href") || "";
  const url = jobPath.startsWith("http") ? jobPath : `https://www.ziprecruiter.com${jobPath}`;
  const title = $(card).find("h2, .job_title, .just_job_title").first().text().trim();
  const company = $(card).find("span.company_name, .company, .job_company").first().text().trim();
  const location = $(card).find("span.location, .location, .job_location").first().text().trim();
  const snippet = $(card).find("p.job_snippet, .job-snippet, .job_description").first().text().trim();
  const postedText = $(card).find("span.posted, .post_date, .job_age").first().text().trim();

  return normalizeJob({
    source: "ZipRecruiter",
    title,
    company,
    location,
    postedDate: postedText,
    url,
    snippet,
    rawPayload: { posted_text: postedText, snippet }
  });
}

async function fetchJobsFromPage(startUrl, source) {
  const requestQueue = await RequestQueue.open();
  await requestQueue.addRequest({ 
    url: startUrl, 
    userData: { label: "LIST", source },
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
  });

  let proxyConfiguration;
  if (config.useApifyProxy) {
    try {
      proxyConfiguration = await createProxyConfiguration();
    } catch (err) {
      error(`Unable to initialize Apify proxy configuration: ${err.message}`);
      proxyConfiguration = undefined;
    }
  }

  const jobs = [];

  const crawler = new CheerioCrawler({
    requestQueue,
    maxRequestRetries: config.apify.maxRetries,
    navigationTimeoutSecs: config.apify.timeoutSeconds,
    handleFailedRequestFunction: async ({ request }) => {
      error(`Failed request ${request.url}`);
    },
    handlePageFunction: async ({ request, $ }) => {
      const source = request.userData.source;
      const pageJobs = [];

      if (source === "Indeed") {
        $(".job_seen_beacon, .result, .tapItem").each((index, element) => {
          pageJobs.push(parseIndeedCard($, element));
        });
      } else if (source === "ZipRecruiter") {
        $("article.job_result, .job_result, .job_card").each((index, element) => {
          pageJobs.push(parseZipRecruiterCard($, element));
        });
      }

      log(`Parsed ${pageJobs.length} jobs from ${source} listing page`);
      jobs.push(...pageJobs);
    }
  });

  await crawler.run();
  return jobs;
}

export async function fetchIndeedJobsApify() {
  const url = buildIndeedSearchUrl({ keywords: config.jobKeywords, location: config.jobLocation, maxAgeDays: config.maxAgeDays });
  log(`Apify running Indeed discovery using ${url}`);
  return fetchJobsFromPage(url, "Indeed");
}

export async function fetchZipRecruiterJobsApify() {
  const url = buildZipRecruiterSearchUrl({ keywords: config.jobKeywords, location: config.jobLocation, maxAgeDays: config.maxAgeDays });
  log(`Apify running ZipRecruiter discovery using ${url}`);
  return fetchJobsFromPage(url, "ZipRecruiter");
}
