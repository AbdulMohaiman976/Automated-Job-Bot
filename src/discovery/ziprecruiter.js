import axios from "axios";
import * as cheerio from "cheerio";
import { log, error } from "../utils/logger.js";

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

function buildZipRecruiterUrl({ keywords, location, maxAgeDays }) {
  const params = new URLSearchParams();
  params.set("search", keywords);
  params.set("location", location);
  params.set("radius", "0");
  params.set("days", String(maxAgeDays));
  params.set("remote", "true");
  params.set("page", "1");
  return `https://www.ziprecruiter.com/candidate/search?${params.toString()}`;
}

function parsePostedAge(text) {
  const cleaned = text?.toLowerCase().trim() ?? "";
  if (!cleaned) {
    return null;
  }
  if (cleaned.includes("just posted") || cleaned.includes("today")) {
    return new Date().toISOString();
  }
  const match = cleaned.match(/(\d+)\+?\s*day/);
  if (match) {
    const daysAgo = Number(match[1]);
    const date = new Date();
    date.setDate(date.getDate() - daysAgo);
    return date.toISOString();
  }
  return null;
}

export async function fetchZipRecruiterJobs({ keywords, location, maxAgeDays }) {
  const url = buildZipRecruiterUrl({ keywords, location, maxAgeDays });
  log(`Fetching ZipRecruiter jobs from ${url}`);

  const response = await axios.get(url, {
    headers: {
      "User-Agent": USER_AGENT,
      "Accept-Language": "en-US,en;q=0.9",
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    },
    timeout: 20000
  });

  const $ = cheerio.load(response.data);
  const jobs = [];

  $("article.job_result, .job_result, .job_card").each((index, element) => {
    const node = $(element);
    const link = node.find("a[href*='/r/'], a[href*='/job/']").first();
    const jobPath = link.attr("href") || "";
    if (!jobPath) {
      return;
    }

    const url = jobPath.startsWith("http") ? jobPath : `https://www.ziprecruiter.com${jobPath}`;
    const title = node.find("h2, .job_title, .just_job_title").text().trim();
    const company = node.find("span.company_name, .company, .job_company").text().trim();
    const locationText = node.find("span.location, .location, .job_location").text().trim();
    const snippet = node.find("p.job_snippet, .job-snippet, .job_description").text().trim();
    const postedText = node.find("span.posted, .post_date, .job_age").text().trim();
    const postedDate = parsePostedAge(postedText) || new Date().toISOString();

    jobs.push({
      source: "ZipRecruiter",
      job_title: title || "Data Engineering",
      company: company || "Unknown",
      location: locationText || "United States",
      remote: /remote/i.test(locationText) || true,
      posted_date: postedDate,
      url,
      description: snippet,
      requirements: null,
      salary: null,
      id: `ziprecruiter-${encodeURIComponent(url)}`,
      raw_payload: {
        posted_text: postedText,
        snippet
      }
    });
  });

  log(`ZipRecruiter discovered ${jobs.length} jobs`);
  return jobs.slice(0, 50);
}
