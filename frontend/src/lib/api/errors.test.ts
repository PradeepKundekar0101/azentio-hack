import { describe, expect, it } from "vitest";

import { ApiError, getErrorMessage, isUnauthorized, toApiError, unwrap } from "./errors";

const response = (status: number) => new Response(null, { status });

describe("toApiError", () => {
  it("reads code, message and details from the error envelope", () => {
    const details = [{ loc: ["body", "username"], message: "Field required", type: "missing" }];
    const error = toApiError(
      { error: { code: "validation_error", message: "Request is invalid", details } },
      response(422),
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.code).toBe("validation_error");
    expect(error.message).toBe("Request is invalid");
    expect(error.details).toEqual(details);
  });

  it("falls back to a message for the status when the body is not an envelope", () => {
    const error = toApiError("<html>Bad Gateway</html>", response(502));
    expect(error.code).toBe("error");
    expect(error.message).toMatch(/not reachable/);
    expect(error.details).toBeNull();
  });

  it("names the status when it has no fallback message", () => {
    expect(toApiError(undefined, response(418)).message).toBe("Request failed (418).");
  });
});

describe("unwrap", () => {
  it("returns data for a successful response", () => {
    expect(unwrap({ data: { username: "demo" }, response: response(200) })).toEqual({ username: "demo" });
  });

  it("throws ApiError for an error response", () => {
    const body = { error: { code: "invalid_credentials", message: "Invalid username or password", details: null } };
    expect(() => unwrap({ error: body, response: response(401) })).toThrow("Invalid username or password");
  });
});

describe("helpers", () => {
  it("detects 401s", () => {
    expect(isUnauthorized(new ApiError(401, "unauthorized", "Not logged in"))).toBe(true);
    expect(isUnauthorized(new ApiError(403, "forbidden", "No"))).toBe(false);
    expect(isUnauthorized(new Error("x"))).toBe(false);
  });

  it("explains network failures", () => {
    expect(getErrorMessage(new TypeError("Failed to fetch"))).toMatch(/Could not reach the server/);
    expect(getErrorMessage("nope")).toBe("Something went wrong.");
  });
});
