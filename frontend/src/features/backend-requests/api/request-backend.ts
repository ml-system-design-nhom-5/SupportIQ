/**
 * Send a `backend` request through the generated client and turn every failure into a
 * {@link RequestFailureError} (CODE-32, ERR-03). Each feature `api/` hook uses these helpers, so
 * failures are parsed in one place.
 */
import { RequestTimeoutError } from "@/api/client";
import {
  parseFailureResponse,
  type RequestFailure,
  RequestFailureError,
} from "@/features/backend-requests/model/request-failure";

/** The result shape of every openapi-fetch call. */
type BackendResult<Data> = {
  readonly data?: Data;
  readonly error?: unknown;
  readonly response: Response;
};

/**
 * Send a request whose success has a body, and map the body to its view model. A body that does
 * not have the shape of the contract is a failure like any other, so every screen shows its error
 * state instead of waiting forever (ERR-04, UI-23).
 *
 * @param send - Calls the generated client.
 * @param toViewModel - Maps the body of the contract to the view model of the feature.
 * @returns The view model of the success response.
 * @throws RequestFailureError for any failure, including a success with a body that cannot be
 *   mapped.
 */
export async function requestData<Data, ViewModel>(
  send: () => Promise<BackendResult<Data>>,
  toViewModel: (body: Data) => ViewModel,
): Promise<ViewModel> {
  const { data: body } = await sendOrThrow(send);
  if (body === undefined) {
    throw new RequestFailureError({ kind: "invalid_response" });
  }
  try {
    return toViewModel(body);
  } catch (error) {
    throw new RequestFailureError({ kind: "invalid_response" }, { cause: error });
  }
}

/**
 * Send a request whose success has no body, such as `204`.
 *
 * @param send - Calls the generated client.
 * @throws RequestFailureError for any failure.
 */
export async function requestNoContent(send: () => Promise<BackendResult<unknown>>): Promise<void> {
  await sendOrThrow(send);
}

/**
 * Classify an error that the client threw instead of returning a response.
 *
 * @param error - What the client threw.
 * @returns The failure, or undefined for a cancellation by the caller, which is not a failure.
 * @throws The original error when it is neither a failure nor a cancellation, which is a defect.
 */
function classifyThrownError(error: unknown): RequestFailure | undefined {
  if (error instanceof RequestTimeoutError) {
    return { kind: "timeout" };
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return undefined;
  }
  if (error instanceof TypeError) {
    return { kind: "network" };
  }
  if (error instanceof SyntaxError) {
    return { kind: "invalid_response" };
  }
  throw error;
}

/**
 * Send a request and wait for its result.
 *
 * @param send - Calls the generated client.
 * @returns The openapi-fetch result of a response with a `2xx` status.
 * @throws RequestFailureError for any failure; the cancellation error when the caller cancelled.
 */
async function sendOrThrow<Data>(
  send: () => Promise<BackendResult<Data>>,
): Promise<BackendResult<Data>> {
  let result: BackendResult<Data>;
  try {
    result = await send();
  } catch (error) {
    const failure = classifyThrownError(error);
    if (failure === undefined) {
      throw error;
    }
    throw new RequestFailureError(failure, { cause: error });
  }
  if (!result.response.ok) {
    throw new RequestFailureError(parseFailureResponse(result.response.status, result.error));
  }
  return result;
}
