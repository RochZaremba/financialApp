export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      credentials: "same-origin",
      headers: {
        ...(options.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      "Brak połączenia. Sprawdź internet i spróbuj ponownie.",
      0,
    );
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({
      detail: "Serwer jest chwilowo niedostępny. Spróbuj ponownie.",
    }));
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      path !== "/auth/me"
    )
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : "Sprawdź dane formularza.",
      response.status,
    );
  }
  return response.json() as Promise<T>;
}
export function json(method: string, body: unknown, key?: string): RequestInit {
  return {
    method,
    body: JSON.stringify(body),
    headers: key ? { "Idempotency-Key": key } : undefined,
  };
}
