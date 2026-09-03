import { env } from "@/config/env";
import { ApiError } from "@/api/errors";
import { getAccessToken } from "@/auth/tokenStorage";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type RequestOptions = {
  method?: HttpMethod;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  headers?: HeadersInit;
  signal?: AbortSignal;
  auth?: boolean;
};

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(
    `${env.apiBaseUrl}${normalizedPath}`,
    window.location.origin,
  );

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }

  return env.apiBaseUrl ? url.toString() : `${url.pathname}${url.search}`;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  let detail = response.statusText || `Request failed (${response.status})`;

  try {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      body = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        (typeof (body as { detail: unknown }).detail === "string" ||
          Array.isArray((body as { detail: unknown }).detail))
      ) {
        const rawDetail = (body as { detail: string | unknown[] }).detail;
        detail = Array.isArray(rawDetail)
          ? rawDetail
              .map((item) =>
                typeof item === "object" && item && "msg" in item
                  ? String((item as { msg: unknown }).msg)
                  : String(item),
              )
              .join("; ")
          : rawDetail;
      }
    } else {
      const text = await response.text();
      if (text) {
        detail = text;
        body = text;
      }
    }
  } catch {
    // Keep the status text fallback when the body cannot be parsed.
  }

  return new ApiError(response.status, detail, body);
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    query,
    headers: customHeaders,
    signal,
    auth = true,
  } = options;

  const headers = new Headers(customHeaders);
  if (body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (auth) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    throw new ApiError(
      0,
      error instanceof Error
        ? `Network error: ${error.message}`
        : "Network error while contacting the API",
    );
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
