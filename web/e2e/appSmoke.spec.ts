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
  await expect(page.getByRole("region", { name: /Workflow territory map/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /Status executing/i })).toBeVisible();
  await expect(page.getByRole("region", { name: /Status in_review/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Gate into executing/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /JIT prompt self review/i })).toBeVisible();

  await page.getByRole("button", { name: /Gate into executing/i }).click();
  await expect(page.getByRole("dialog")).toContainText("v_uuid_present");
  await guard.assertClean();
});

test("concept graph drift header renders without console or network errors", async ({
  page,
  request,
}, testInfo) => {
  // The standalone /drift page was retired in v0.9.7; the same
  // signal now lives as a header card on the Concept Graph page
  // (see [[principle-concept-graph-as-definition]]'s "drift as a
  // metric, not a view" section). E2E moved with it.
  const guard = installConsoleGuard(page, testInfo);
  const projectId = await fixtureProjectId(request);

  await page.goto(`/p/${projectId}/graph`);

  await expect(page.getByTestId("drift-header")).toBeVisible();
  await expect(page.getByTestId("drift-score")).toBeVisible();
  await guard.assertClean();
});
