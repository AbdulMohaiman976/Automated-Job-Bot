import { Actor } from "apify";
import { CheerioCrawler } from "@crawlee/cheerio";

await Actor.init();

const input = await Actor.getInput();
if (!input) {
  throw new Error("No input provided");
}

const { searchTerm = "Data Engineering", locationFilter = "United States", source = "indeed", maxPages = 1 } = input;

const jobs = [];

async function scrapeIndeed() {
  const url = buildIndeedUrl({ searchTerm, locationFilter });
  console.log(`Scraping Indeed: ${url}`);

  const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 10,
    handlePageFunction: async ({ $ }) => {
      $(".job_seen_beacon, .result, .tapItem").each((index, element) => {
        const title = $(element).find("h2.jobTitle span, .jobTitle").first().text().trim();
        const company = $(element).find("span.companyName, .company").first().text().trim();
        const location = $(element).find("div.companyLocation, .location").first().text().trim();
        const snippet = $(element).find("div.job-snippet, .summary").text().trim();
        const link = $(element).find("a[data-jk], a[title]").first();
        const jobPath = link.attr("href") || "";
        const jobUrl = jobPath.startsWith("http") ? jobPath : `https://www.indeed.com${jobPath}`;

        if (title && jobUrl) {
          jobs.push({
            source: "Indeed",
            job_title: title,
            company: company || "Unknown",
            location: location || locationFilter,
            remote: /remote/i.test(location || ""),
            url: jobUrl,
            description: snippet,
            posted_date: new Date().toISOString()
          });
        }
      });
    }
  });

  await crawler.addRequests([{ url }]);
  await crawler.run();
}

async function scrapeZipRecruiter() {
  const url = buildZipRecruiterUrl({ searchTerm, locationFilter });
  console.log(`Scraping ZipRecruiter: ${url}`);

  const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 10,
    handlePageFunction: async ({ $ }) => {
      $("article.job_result, .job_result, .job_card").each((index, element) => {
        const title = $(element).find("h2, .job_title, .just_job_title").first().text().trim();
        const company = $(element).find("span.company_name, .company").first().text().trim();
        const location = $(element).find("span.location, .location").first().text().trim();
        const snippet = $(element).find("p.job_snippet, .job-snippet").first().text().trim();
        const link = $(element).find("a[href*='/r/'], a[href*='/job/']").first();
        const jobPath = link.attr("href") || "";
        const jobUrl = jobPath.startsWith("http") ? jobPath : `https://www.ziprecruiter.com${jobPath}`;

        if (title && jobUrl) {
          jobs.push({
            source: "ZipRecruiter",
            job_title: title,
            company: company || "Unknown",
            location: location || locationFilter,
            remote: /remote/i.test(location || ""),
            url: jobUrl,
            description: snippet,
            posted_date: new Date().toISOString()
          });
        }
      });
    }
  });

  await crawler.addRequests([{ url }]);
  await crawler.run();
}

function buildIndeedUrl({ searchTerm, locationFilter }) {
  const params = new URLSearchParams();
  params.set("q", searchTerm);
  params.set("l", locationFilter);
  params.set("fromage", "1");
  params.set("sort", "date");
  params.set("radius", "0");
  params.set("remotejob", "1");
  params.set("limit", "50");
  return `https://www.indeed.com/jobs?${params.toString()}`;
}

function buildZipRecruiterUrl({ searchTerm, locationFilter }) {
  const params = new URLSearchParams();
  params.set("search", searchTerm);
  params.set("location", locationFilter);
  params.set("radius", "0");
  params.set("days", "1");
  params.set("remote", "true");
  return `https://www.ziprecruiter.com/candidate/search?${params.toString()}`;
}

if (source === "indeed" || source === "all") {
  await scrapeIndeed();
}

if (source === "ziprecruiter" || source === "all") {
  await scrapeZipRecruiter();
}

await Actor.pushData(jobs);
await Actor.exit();
