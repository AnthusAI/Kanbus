import { When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { readFile, writeFile } from "fs/promises";
import path from "path";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;

When("I scroll the board to the right", async function () {
  await this.page.getByText("Doing issue").first().waitFor({ timeout: 8000 });
  const scrollLeft = await this.page.evaluate(async () => {
    const board = document.querySelector(".kb-grid");
    board.scrollLeft = board.scrollWidth;
    await new Promise((resolve) => setTimeout(resolve, 300));
    return board.scrollLeft;
  });
  expect(scrollLeft).toBeGreaterThan(0);
  this.boardScrollLeft = scrollLeft;
});

When("I record the board horizontal scroll position", async function () {
  await this.page.evaluate(() => {
    const board = document.querySelector(".kb-grid");
    window.__boardScrollSamples = [];
    const sample = () => {
      window.__boardScrollSamples.push(board.scrollLeft);
      window.__boardScrollHandle = requestAnimationFrame(sample);
    };
    sample();
  });
});

When(
  "the issue {string} is moved to {string} by a realtime update",
  async function (issueId, status) {
    const issuePath = path.join(projectRoot, "issues", `${issueId}.json`);
    const issue = JSON.parse(await readFile(issuePath, "utf-8"));
    issue.status = status;
    issue.updated_at = new Date().toISOString();
    await writeFile(issuePath, JSON.stringify(issue, null, 2));
    await this.page.waitForTimeout(2000);
  }
);

Then("the board horizontal scroll position should never have changed", async function () {
  const samples = await this.page.evaluate(() => {
    cancelAnimationFrame(window.__boardScrollHandle);
    return window.__boardScrollSamples;
  });
  expect(samples.length).toBeGreaterThan(10);
  expect(Math.min(...samples)).toBe(this.boardScrollLeft);
  expect(Math.max(...samples)).toBe(this.boardScrollLeft);
});
