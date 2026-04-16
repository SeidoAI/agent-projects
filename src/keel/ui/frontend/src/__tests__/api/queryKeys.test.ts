import { isPrefix, queryKeys, staleTime } from "@/lib/api/queryKeys";
import { describe, expect, it } from "vitest";

describe("queryKeys", () => {
  it("returns stable tuples for the same inputs", () => {
    const a = queryKeys.issue("p1", "KUI-1");
    const b = queryKeys.issue("p1", "KUI-1");
    expect(a).toEqual(b);
  });

  it("returns different tuples for different inputs", () => {
    const a = queryKeys.issue("p1", "KUI-1");
    const b = queryKeys.issue("p1", "KUI-2");
    expect(a).not.toEqual(b);
  });

  it("projects returns expected shape", () => {
    expect(queryKeys.projects()).toEqual(["projects"]);
  });

  it("project returns expected shape", () => {
    expect(queryKeys.project("p1")).toEqual(["projects", "p1"]);
  });

  it("issues returns expected shape", () => {
    expect(queryKeys.issues("p1")).toEqual(["issues", "p1"]);
  });

  it("issuesFiltered includes filters", () => {
    const filters = { status: "todo" };
    expect(queryKeys.issuesFiltered("p1", filters)).toEqual(["issues", "p1", filters]);
  });

  it("issue returns expected shape", () => {
    expect(queryKeys.issue("p1", "KUI-5")).toEqual(["issues", "p1", "KUI-5"]);
  });

  it("nodes returns expected shape", () => {
    expect(queryKeys.nodes("p1")).toEqual(["nodes", "p1"]);
  });

  it("node returns expected shape", () => {
    expect(queryKeys.node("p1", "api-client")).toEqual(["nodes", "p1", "api-client"]);
  });

  it("reverseRefs returns expected shape", () => {
    expect(queryKeys.reverseRefs("p1", "n1")).toEqual(["nodes", "p1", "n1", "reverseRefs"]);
  });

  it("graph returns expected shape", () => {
    expect(queryKeys.graph("p1", "deps")).toEqual(["graph", "p1", "deps"]);
    expect(queryKeys.graph("p1", "concept")).toEqual(["graph", "p1", "concept"]);
  });

  it("sessions returns expected shape", () => {
    expect(queryKeys.sessions("p1")).toEqual(["sessions", "p1"]);
  });

  it("session returns expected shape", () => {
    expect(queryKeys.session("p1", "s1")).toEqual(["sessions", "p1", "s1"]);
  });

  it("sessionArtifacts returns expected shape", () => {
    expect(queryKeys.sessionArtifacts("p1", "s1")).toEqual(["sessions", "p1", "s1", "artifacts"]);
  });

  it("artifact returns expected shape", () => {
    expect(queryKeys.artifact("p1", "s1", "plan.md")).toEqual([
      "sessions",
      "p1",
      "s1",
      "artifacts",
      "plan.md",
    ]);
  });

  it("artifactManifest returns expected shape", () => {
    expect(queryKeys.artifactManifest("p1")).toEqual(["projects", "p1", "artifact-manifest"]);
  });

  it("enum returns expected shape", () => {
    expect(queryKeys.enum("p1", "statuses")).toEqual(["projects", "p1", "enums", "statuses"]);
  });

  it("orchestration returns expected shape", () => {
    expect(queryKeys.orchestration("p1")).toEqual(["projects", "p1", "orchestration"]);
  });

  it("v2 keys: containers", () => {
    expect(queryKeys.containers()).toEqual(["containers"]);
  });

  it("v2 keys: messages", () => {
    expect(queryKeys.messages("s1")).toEqual(["messages", "s1"]);
  });

  it("v2 keys: unreadMessages", () => {
    expect(queryKeys.unreadMessages()).toEqual(["messages", "unread"]);
  });

  it("v2 keys: githubPrs", () => {
    expect(queryKeys.githubPrs("SeidoAI/keel")).toEqual(["github", "prs", "SeidoAI/keel"]);
  });
});

describe("staleTime", () => {
  it("has expected default values", () => {
    expect(staleTime.default).toBe(30_000);
    expect(staleTime.enum).toBe(300_000);
    expect(staleTime.orchestration).toBe(300_000);
    expect(staleTime.container).toBe(5_000);
    expect(staleTime.github).toBe(60_000);
    expect(staleTime.message).toBe(0);
  });
});

describe("isPrefix", () => {
  it("returns true when prefix matches", () => {
    expect(isPrefix(["issues", "p1", "KUI-1"], ["issues", "p1"])).toBe(true);
  });

  it("returns true for exact match", () => {
    expect(isPrefix(["issues", "p1"], ["issues", "p1"])).toBe(true);
  });

  it("returns false when prefix does not match", () => {
    expect(isPrefix(["issues", "p1"], ["nodes", "p1"])).toBe(false);
  });

  it("returns false when prefix is longer than key", () => {
    expect(isPrefix(["issues"], ["issues", "p1"])).toBe(false);
  });

  it("returns true for empty prefix", () => {
    expect(isPrefix(["issues", "p1"], [])).toBe(true);
  });
});
