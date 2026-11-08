import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";
import { RenderPropsSchema } from "../src/schemas/render-props";

describe("RenderProps Zod Schema Contract", () => {
  const fixturesDir = path.resolve(__dirname, "../src/fixtures");
  const samplePath = path.join(fixturesDir, "render_props.sample.json");
  const invalidDir = path.join(fixturesDir, "invalid");

  it("should validate sample render_props successfully", () => {
    const raw = fs.readFileSync(samplePath, "utf-8");
    const json = JSON.parse(raw);
    const parsed = RenderPropsSchema.parse(json);
    expect(parsed.schemaVersion).toBe(1);
    expect(parsed.chapterId).toBe("sample_chapter");
    expect(parsed.scenes.length).toBeGreaterThan(0);
  });

  it("should reject all invalid fixtures", () => {
    const files = fs.readdirSync(invalidDir).filter((f) => f.endsWith(".json"));
    expect(files.length).toBeGreaterThanOrEqual(8);

    for (const file of files) {
      const filePath = path.join(invalidDir, file);
      const raw = fs.readFileSync(filePath, "utf-8");
      const json = JSON.parse(raw);
      expect(() => {
        RenderPropsSchema.parse(json);
      }, `Expected Zod to reject invalid fixture: ${file}`).toThrow();
    }
  });
});
