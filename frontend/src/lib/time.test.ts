import { describe, expect, it } from "vitest";
import { fromLocalInput, startOfWeek, toLocalInput, zonedParts } from "./time";

describe("time", () => {
  it("round-trips a local time through a zone with DST", () => {
    const iso = fromLocalInput("2026-07-14T09:30", "Europe/Belgrade")!;
    expect(iso).toBe("2026-07-14T07:30:00.000Z");
    expect(toLocalInput(iso, "Europe/Belgrade")).toBe("2026-07-14T09:30");
    const winter = fromLocalInput("2026-01-14T09:30", "Europe/Belgrade")!;
    expect(winter).toBe("2026-01-14T08:30:00.000Z");
  });

  it("knows weekdays with Monday first", () => {
    expect(zonedParts("2026-11-07T12:00:00Z", "UTC").weekday).toBe(5); // Saturday
    expect(startOfWeek("2026-11-07")).toBe("2026-11-02");
  });
});
