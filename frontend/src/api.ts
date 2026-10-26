import type { Factura, Resumen, Tarifa, TarifaEntrada, Ticket, TipoVehiculo } from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const CLAVE_TOKEN = "parqueadero_token";

export class ErrorAuth extends Error {}

let token = sessionStorage.getItem(CLAVE_TOKEN) ?? "";

export function hayToken(): boolean {
  return token.length > 0;
}

export function guardarToken(valor: string): void {
  token = valor.trim();
  if (token) {
    sessionStorage.setItem(CLAVE_TOKEN, token);
  } else {
    sessionStorage.removeItem(CLAVE_TOKEN);
  }
}

export function olvidarToken(): void {
  guardarToken("");
}

async function peticion<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const cabeceras: Record<string, string> = { "Content-Type": "application/json" };
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  const respuesta = await fetch(`${BASE}${ruta}`, {
    ...opciones,
    headers: { ...cabeceras, ...(opciones.headers as Record<string, string> | undefined) },
  });
  if (respuesta.status === 401) {
    olvidarToken();
    throw new ErrorAuth("Token inválido o ausente");
  }
  if (!respuesta.ok) {
    const detalle = await respuesta.json().catch(() => ({ detail: respuesta.statusText }));
    throw new Error(detalle.detail ?? "Error de red");
  }
  if (respuesta.status === 204) {
    return undefined as T;
  }
  return (await respuesta.json()) as T;
}

export const api = {
  tarifas: () => peticion<Tarifa[]>("/tarifas"),
  guardarTarifa: (t: TarifaEntrada) =>
    peticion<Tarifa>(`/tarifas/${t.tipo_vehiculo}`, { method: "PUT", body: JSON.stringify(t) }),
  activos: () => peticion<Ticket[]>("/tickets/activos"),
  ingresar: (placa: string, tipo_vehiculo: TipoVehiculo) =>
    peticion<Ticket>("/tickets/ingresos", {
      method: "POST",
      body: JSON.stringify({ placa, tipo_vehiculo }),
    }),
  salida: (id: number) =>
    peticion<{ factura: Factura; ticket: Ticket }>(`/tickets/${id}/salida`, { method: "POST" }),
  facturas: (desde?: string, hasta?: string) => {
    const params = new URLSearchParams();
    if (desde) params.set("desde", desde);
    if (hasta) params.set("hasta", hasta);
    const qs = params.toString();
    return peticion<Factura[]>(`/facturas${qs ? `?${qs}` : ""}`);
  },
  resumen: (desde: string, hasta: string) =>
    peticion<Resumen>(`/informes/resumen?desde=${encodeURIComponent(desde)}&hasta=${encodeURIComponent(hasta)}`),
};
