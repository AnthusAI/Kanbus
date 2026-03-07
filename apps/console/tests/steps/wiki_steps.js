import { Before, Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { mkdir, rm, writeFile, readFile } from "fs/promises";
import path from "path";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const wikiRoot = projectRoot ? path.join(projectRoot, "wiki") : null;

function requireWikiRoot() {
  if (!wikiRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for wiki tests");
  }
  return wikiRoot;
}

function assertSafeWikiPath(input) {
  if (!input.endsWith(".md")) {
    throw new Error(`Wiki path must end with .md: ${input}`);
  }
  if (input.includes("..") || input.startsWith("/") || input.includes("\\")) {
    throw new Error(`Unsafe wiki path: ${input}`);
  }
  return input;
}

async function ensureWikiRoot() {
  const root = requireWikiRoot();
  await mkdir(root, { recursive: true });
  return root;
}

async function resetWiki() {
  const root = requireWikiRoot();
  await rm(root, { recursive: true, force: true });
  await mkdir(root, { recursive: true });
}

async function writeWikiPage(relativePath, content) {
  const root = await ensureWikiRoot();
  const safePath = assertSafeWikiPath(relativePath);
  const target = path.join(root, safePath);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, content, "utf-8");
}

async function readWikiPage(relativePath) {
  const root = requireWikiRoot();
  const target = path.join(root, relativePath);
  return readFile(target, "utf-8");
}

async function reloadIfWikiStale(world) {
  if (!world.wikiStale) {
    return;
  }
  await world.page.reload({ waitUntil: "domcontentloaded" });
  world.wikiStale = false;
}

Before(function () {
  this.wikiStale = false;
});

Given("the wiki storage is empty", async function () {
  await resetWiki();
  this.wikiStale = true;
});

Given("a wiki page {string} exists with content:", async function (relativePath, docString) {
  await writeWikiPage(relativePath, docString);
  this.wikiStale = true;
});

When("I select wiki page {string}", async function (relativePath) {
  await reloadIfWikiStale(this);
  await this.page.getByRole("button", { name: relativePath }).click();
});

When("I create a wiki page named {string}", async function (relativePath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => {
    dialog.accept(relativePath);
  });
  await this.page.getByRole("button", { name: "Actions" }).click();
  await this.page.getByRole("menuitem", { name: "New page" }).click();
  await expect(this.page.getByRole("button", { name: relativePath })).toBeVisible();
});

When("I try to create a wiki page named {string}", async function (relativePath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => {
    dialog.accept(relativePath);
  });
  await this.page.getByRole("button", { name: "Actions" }).click();
  await this.page.getByRole("menuitem", { name: "New page" }).click();
});

When("I rename the wiki page {string} to {string}", async function (fromPath, toPath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => {
    dialog.accept(toPath);
  });
  await this.page.getByRole("button", { name: "Actions" }).click();
  await this.page.getByRole("menuitem", { name: "Rename page" }).click();
  await expect(this.page.getByRole("button", { name: toPath })).toBeVisible();
});

When("I delete the wiki page {string}", async function (relativePath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => dialog.accept());
  await this.page.getByRole("button", { name: "Actions" }).click();
  await this.page.getByRole("menuitem", { name: "Delete page" }).click();
});

When("I type wiki content:", async function (docString) {
  await reloadIfWikiStale(this);
  await this.page.getByRole("textbox", { name: "Write markdown..." }).fill(docString);
});

When("I save the wiki page", async function () {
  await reloadIfWikiStale(this);
  await this.page.getByRole("button", { name: "Save" }).click();
});

When("I render the wiki page", async function () {
  await reloadIfWikiStale(this);
  await this.page.getByRole("button", { name: /Render/ }).click();
});

When("I attempt to select wiki page {string} without confirming", async function (relativePath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => dialog.dismiss());
  await this.page.getByRole("button", { name: relativePath }).click();
});

When("I attempt to leave the wiki view without confirming", async function () {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => dialog.dismiss());
  await this.page.getByTestId("view-toggle-board").click();
});

Then("the wiki view should be active", async function () {
  await expect(this.page.getByTestId("view-toggle-wiki")).toHaveAttribute("data-active", "true");
  await expect(this.page.getByTestId("wiki-view")).toBeVisible();
});

Then("the wiki view should be inactive", async function () {
  await expect(this.page.getByTestId("view-toggle-wiki")).toHaveAttribute("data-active", "false");
  await expect(this.page.getByTestId("wiki-view")).not.toBeVisible();
});

Then("the wiki empty state should be visible", async function () {
  await expect(this.page.getByText("Empty wiki")).toBeVisible();
});

Then("the wiki page list should include {string}", async function (relativePath) {
  await expect(this.page.getByRole("button", { name: relativePath })).toBeVisible();
});

Then("the wiki page list should not include {string}", async function (relativePath) {
  await expect(this.page.getByRole("button", { name: relativePath })).toHaveCount(0);
});

Then("the wiki editor path should be {string}", async function (relativePath) {
  await expect(this.page.locator(".wiki-editor").getByText(relativePath)).toBeVisible();
});

Then("the wiki editor content should equal:", async function (docString) {
  const textarea = this.page.getByRole("textbox", { name: "Write markdown..." });
  await expect(textarea).toHaveValue(docString);
});

Then("the wiki preview should contain {string}", async function (expected) {
  await expect(this.page.locator(".wiki-preview")).toContainText(expected);
});

Then("the wiki status should show {string}", async function (expected) {
  await expect(this.page.locator(".wiki-editor")).toContainText(expected);
});

Then("the wiki error banner should contain {string}", async function (message) {
  await expect(this.page.locator(".wiki-error")).toContainText(message);
});

Then("the wiki preview should still contain {string}", async function (expected) {
  const preview = this.page.locator(".wiki-preview");
  await expect(preview).toContainText(expected);
});
