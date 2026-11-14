import { describe, expect, it } from "vitest";
import { ApiError, unwrap } from "./api";

describe("unwrap", () => {
  it("returns the data of a successful answer", () => {
    expect(unwrap({ data: { id: 1 }, response: new Response("{}", { status: 200 }) })).toEqual({ id: 1 });
  });

  it("treats an empty 204 answer as success, so a delete does not show an error", () => {
    expect(unwrap({ data: undefined, response: new Response(null, { status: 204 }) })).toBeUndefined();
  });

  it("throws the server's code and detail for a refused request", () => {
    const refused = { error: { code: "not_found", detail: "No such webhook" }, response: new Response("{}", { status: 404 }) };
    expect(() => unwrap(refused)).toThrow(ApiError);
    expect(() => unwrap(refused)).toThrow("No such webhook");
  });

  it("throws for a failed answer that has no body", () => {
    expect(() => unwrap({ error: undefined, response: new Response(null, { status: 502, statusText: "Bad Gateway" }) })).toThrow("Bad Gateway");
  });
});
