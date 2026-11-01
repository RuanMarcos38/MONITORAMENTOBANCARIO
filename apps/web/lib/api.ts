export type Row = Record<string, unknown>;

export async function api(path: string, init?: RequestInit) {
  const response = await fetch('/api/v1/' + path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Confira os campos e tente novamente.');
  }
  return data;
}

export function post(path: string, data?: unknown) {
  return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data ?? {}) });
}

export function label(value: unknown): string {
  return value == null ? 'Não informado' : String(value);
}
