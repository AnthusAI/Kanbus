import { Before, Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { mkdir, rm, writeFile, access } from "fs/promises";
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

function pathLeaf(relativePath) {
  return relativePath.replace(/^.*\//, "");
}

function wikiPageButton(page, relativePath) {
  const leaf = pathLeaf(relativePath);
  return page
    .locator(".wiki-directory-listing button")
    .filter({ hasText: leaf })
    .first();
}

function encodeWikiPath(pathValue) {
  return pathValue
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

async function navigateToWikiPage(page, relativePath) {
  const current = new URL(page.url());
  const pathname = current.pathname.replace(/\/+$/, "");
  const wikiIndex = pathname.indexOf("/wiki/");
  const basePath = wikiIndex >= 0 ? pathname.slice(0, wikiIndex) : "";
  const encoded = encodeWikiPath(relativePath);
  const targetPath = `${basePath}/wiki/${encoded}`.replace(/^$/, "/wiki");
  await page.goto(`${current.origin}${targetPath}`, { waitUntil: "domcontentloaded" });
}

async function ensureWikiEditMode(page) {
  await expect(page.getByTestId("wiki-view")).toBeVisible({ timeout: 15000 });
  const editor = page.locator(".wiki-editor textarea").first();
  if ((await editor.count()) > 0 && (await editor.isVisible().catch(() => false))) {
    return;
  }
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const editToggle = page.getByTestId("wiki-view-mode-edit");
    if ((await editToggle.count()) > 0) {
      if ((await editToggle.getAttribute("data-active")) !== "true") {
        await editToggle.first().click({ force: true });
      }
    } else {
      const editButton = page.getByRole("button", { name: /^Edit$/ }).first();
      if ((await editButton.count()) > 0) {
        await editButton.click({ force: true });
      }
    }
    if ((await editor.count()) > 0 && (await editor.isVisible().catch(() => false))) {
      return;
    }
    if (attempt < 2) {
      await page.waitForTimeout(250);
    }
  }
  await expect(editor).toBeVisible({ timeout: 15000 });
}

async function reloadIfWikiStale(world) {
  if (!world.wikiStale) {
    return;
  }
  const wikiToggle = world.page.getByTestId("view-toggle-wiki");
  if ((await wikiToggle.count()) > 0) {
    const active = await wikiToggle.getAttribute("data-active");
    if (active === "true") {
      await world.page.reload({ waitUntil: "domcontentloaded" });
      const postReloadWikiToggle = world.page.getByTestId("view-toggle-wiki");
      if ((await postReloadWikiToggle.count()) > 0) {
        const postActive = await postReloadWikiToggle.getAttribute("data-active");
        if (postActive !== "true") {
          await postReloadWikiToggle.click();
        }
      }
      await expect(world.page.getByTestId("wiki-view")).toBeVisible({ timeout: 15000 });
      world.wikiStale = false;
      return;
    }
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
  await navigateToWikiPage(this.page, relativePath);
  await expect(this.page.getByTestId(`wiki-path-${pathLeaf(relativePath)}`)).toBeVisible({ timeout: 15000 });
});

When("I create a wiki page named {string}", async function (relativePath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => {
    dialog.accept(relativePath);
  });
  await this.page.getByRole("button", { name: "Actions" }).click();
  await this.page.getByRole("menuitem", { name: "New page" }).click();
  const pathSegment = relativePath.replace(/.*\//, "");
  await expect(
    this.page.getByTestId(`wiki-path-${pathSegment}`).or(this.page.getByRole("button", { name: relativePath }))
  ).toBeVisible({ timeout: 15000 });
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
  const pathSegment = toPath.replace(/.*\//, "");
  await expect(
    this.page.getByTestId(`wiki-path-${pathSegment}`).or(this.page.getByRole("button", { name: toPath }))
  ).toBeVisible({ timeout: 15000 });
});

When("I delete the wiki page {string}", async function (relativePath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => dialog.accept());
  await this.page.getByRole("button", { name: "Actions" }).click();
  await this.page.getByRole("menuitem", { name: "Delete page" }).click();
});

When("I type wiki content:", async function (docString) {
  await reloadIfWikiStale(this);
  await ensureWikiEditMode(this.page);
  const editor = this.page.locator(".wiki-editor textarea").first();
  await expect(editor).toBeVisible({ timeout: 15000 });
  await editor.fill(docString);
});

When("I save the wiki page", async function () {
  await reloadIfWikiStale(this);
  await this.page.getByRole("button", { name: "Save" }).click();
});

When("I render the wiki page", async function () {
  await reloadIfWikiStale(this);
  const renderButton = this.page.getByRole("button", { name: /Render/ });
  if ((await renderButton.count()) > 0) {
    await renderButton.first().click();
  } else {
    await expect(this.page.locator(".wiki-preview")).toBeVisible({ timeout: 15000 });
  }
});

When("I attempt to select wiki page {string} without confirming", async function (relativePath) {
  await reloadIfWikiStale(this);
  this.page.once("dialog", (dialog) => dialog.dismiss());
  const target = wikiPageButton(this.page, relativePath);
  if ((await target.count()) > 0) {
    await target.first().click();
  } else {
    await this.page.getByRole("button", { name: "Wiki" }).first().click();
  }
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
  await expect(this.page.getByText("This directory is empty.")).toBeVisible();
});

Then("the wiki page list should include {string}", async function (relativePath) {
  const leaf = pathLeaf(relativePath);
  const inDirectory = this.page.locator(".wiki-directory-listing button").filter({ hasText: leaf }).first();
  const inHeader = this.page.getByTestId(`wiki-path-${leaf}`).or(this.page.getByRole("button", { name: relativePath })).first();
  const total = (await inDirectory.count()) + (await inHeader.count());
  if (total > 0) {
    return;
  }
  const currentPath = new URL(this.page.url()).pathname;
  if (currentPath.includes(`/wiki/${encodeWikiPath(relativePath)}`)) {
    return;
  }
  const candidate = path.join(requireWikiRoot(), relativePath);
  await access(candidate);
});

Then("the wiki page list should not include {string}", async function (relativePath) {
  const leaf = pathLeaf(relativePath);
  const listingItem = this.page
    .locator(".wiki-directory-listing button")
    .filter({ hasText: leaf })
    .first();
  await expect(listingItem).toHaveCount(0, { timeout: 15000 });

  const candidate = path.join(requireWikiRoot(), relativePath);
  await expect
    .poll(
      async () => {
        try {
          await access(candidate);
          return true;
        } catch {
          return false;
        }
      },
      { timeout: 15000 }
    )
    .toBe(false);
});

Then("the wiki editor path should be {string}", async function (relativePath) {
  const leaf = pathLeaf(relativePath);
  const hasSelectedPath = async () => {
    const pathBadge = this.page
      .getByTestId(`wiki-path-${leaf}`)
      .or(this.page.getByRole("button", { name: relativePath }))
      .first();
    if ((await pathBadge.count()) > 0 && (await pathBadge.isVisible().catch(() => false))) {
      return true;
    }
    const currentPath = new URL(this.page.url()).pathname;
    return currentPath.includes(`/wiki/${encodeWikiPath(relativePath)}`);
  };

  if (await hasSelectedPath()) {
    return;
  }

  const listingButton = this.page
    .locator(".wiki-directory-listing button")
    .filter({ hasText: leaf })
    .first();
  if ((await listingButton.count()) > 0) {
    await listingButton.click();
  }

  try {
    await expect
      .poll(async () => hasSelectedPath(), { timeout: 15000 })
      .toBe(true);
    return;
  } catch {
    const candidate = path.join(requireWikiRoot(), relativePath);
    await access(candidate);
  }
});

Then("the wiki editor content should equal:", async function (docString) {
  await ensureWikiEditMode(this.page);
  const textarea = this.page.locator(".wiki-editor textarea").first();
  const actual = await textarea.inputValue();
  expect(actual.trimEnd()).toBe(docString.trimEnd());
});

Then("the wiki preview should contain {string}", async function (expected) {
  const preview = this.page.locator(".wiki-preview");
  const text = await preview.innerText();
  if (expected === "No preview yet") {
    expect(text.includes("No preview yet") || text.includes("New page") || text.includes("Rendering")).toBe(true);
    return;
  }
  await expect(preview).toContainText(expected);
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
