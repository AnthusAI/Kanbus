export function newOperationId(): string {
  return crypto.randomUUID();
}
