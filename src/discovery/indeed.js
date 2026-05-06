import axios from "axios";
import * as cheerio from "cheerio";
import { log, error } from "../utils/logger.js";

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

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

function buildIndeedUrl({ keywords, location, maxAgeDays, remoteOnly }) {
  const params = new URLSearchParams();
  params.set("q", keywords);
  params.set("l", location);
  params.set("fromage", String(maxAgeDays));
  params.set("sort", "date");
  params.set("radius", "0");
  if (remoteOnly) {
    params.set("remotejob", "1");
  }
  params.set("limit", "50");
  return `https://www.indeed.com/jobs?${params.toString()}`;
}

async function fetchJobDetail(url) {
  try {
    const response = await axios.get(url, {
      headers: {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
      },
      timeout: 20000
    });
    const $ = cheerio.load(response.data);
    const jobDescription = $("#jobDescriptionText").text().trim() || $(".jobsearch-jobDescriptionText").text().trim();
    return jobDescription || null;
  } catch (err) {
    error(`Indeed detail fetch failed for ${url}: ${err.message}`);
    return null;
  }
}

export async function fetchIndeedJobs({ keywords, location, remoteOnly, maxAgeDays }) {
  const url = buildIndeedUrl({ keywords, location, remoteOnly, maxAgeDays });
  log(`Fetching Indeed jobs from ${url}`);

  const response = await axios.get(url, {
    headers: {
      "User-Agent": USER_AGENT,
      "Accept-Language": "en-US,en;q=0.9",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Referer": "https://www.indeed.com/"
    },
    timeout: 20000
  });

  const $ = cheerio.load(response.data);
  const jobs = [];

  $(".job_seen_beacon, .result, .tapItem").each((index, element) => {
    const node = $(element);
    const link = node.find("a[data-jk], a[title], a[href*='/rc/clk'], a[href*='/company/']").first();
    const jobPath = link.attr("href") || "";
    if (!jobPath) {
      return;
    }

    const url = jobPath.startsWith("http") ? jobPath : `https://www.indeed.com${jobPath}`;
    const title = node.find("h2.jobTitle span, h2.title span, .jobTitle").first().text().trim();
    const company = node.find("span.companyName, .company, .companyName").first().text().trim();
    const locationText = node.find("div.companyLocation, .location").first().text().trim();
    const snippet = node.find("div.job-snippet, .summary").text().trim();
    const postedText = node.find("span.date, .date").first().text().trim();
    const postedDate = parsePostedAge(postedText) || new Date().toISOString();

    jobs.push({
      source: "Indeed",
      job_title: title || "Data Engineering",
      company: company || "Unknown",
      location: locationText || "United States",
      remote: remoteOnly || /remote/i.test(locationText),
      posted_date: postedDate,
      url,
      description: snippet,
      requirements: null,
      salary: null,
      id: `indeed-${encodeURIComponent(url)}`,
      raw_payload: {
        posted_text: postedText,
        snippet
      }
    });
  });

  log(`Indeed discovered ${jobs.length} jobs`);
  return jobs.slice(0, 50);
}
