export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body: unknown;

  constructor(status: number, detail: string, body: unknown = null) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isUnauthorized(error: unknown): boolean {
  return isApiError(error) && error.isUnauthorized;
}

export function getErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (isApiError(error)) {
    return error.detail || fallback;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
