import { expect, test } from "@playwright/test";

import { installConsoleGuard } from "./consoleGuard";

interface ProjectSummary {
  id: string;
  name: string;
}

async function fixtureProjectId(request: {
  get: (url: string) => Promise<{ json: () => Promise<ProjectSummary[]> }>;
}) {
  const projects = await (await request.get("/api/projects")).json();
  const project = projects.find((item) => item.name === "ui-e2e");
  expect(project, "fixture project should be discoverable").toBeTruthy();
  return project?.id ?? "";
}

test("serves favicon assets", async ({ page }, testInfo) => {
  const guard = installConsoleGuard(page, testInfo);

  const favicon = await page.request.get("/favicon.ico");
  expect(favicon.status()).toBe(200);
  expect(favicon.headers()["content-type"]).toContain("image");

  await page.goto("/");
  await expect(page).toHaveTitle(/Tripwire UI/);
  await guard.assertClean();
});

test("workflow page renders against real API payload without console regressions", async ({
  page,
  request,
}, testInfo) => {
  const guard = installConsoleGuard(page, testInfo);
  const projectId = await fixtureProjectId(request);

  await page.goto(`/p/${projectId}/workflow`);

  await expect(page.getByRole("heading", { name: /^Workflow$/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /Workflow map canvas/i })).toBeVisible();
  await expect(page.getByLabel(/Validator uuid present/i)).toBeVisible();
  await expect(page.getByLabel(/Validator stale concept/i)).toBeVisible();
  await expect(page.getByLabel(/JIT prompt self-review/i)).toBeVisible();
  await guard.assertClean();
});

test("drift page renders without console or network errors", async ({
  page,
  request,
}, testInfo) => {
  const guard = installConsoleGuard(page, testInfo);
  const projectId = await fixtureProjectId(request);

  await page.goto(`/p/${projectId}/drift`);

  await expect(page.getByRole("heading", { name: /Drift report/i })).toBeVisible();
  await expect(page.getByTestId("drift-score")).toBeVisible();
  await guard.assertClean();
});
