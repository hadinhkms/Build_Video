import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";
import { RenderPropsSchema } from "../src/schemas/render-props";

describe("Real Props File Validation", () => {
  const envPath = process.env.RENDER_PROPS;

  it("should validate file pointed by RENDER_PROPS if provided", () => {
    if (!envPath) {
      // Bỏ qua khi biến RENDER_PROPS không được đặt
      expect(true).toBe(true);
      return;
    }

    const resolved = path.resolve(process.cwd(), envPath);
    expect(fs.existsSync(resolved), `Props file not found: ${resolved}`).toBe(true);

    const raw = fs.readFileSync(resolved, "utf-8");
    const json = JSON.parse(raw);
    const parsed = RenderPropsSchema.parse(json);
    expect(parsed.schemaVersion).toBe(1);
    expect(parsed.scenes.length).toBeGreaterThan(0);
  });
});
