export type TipoVehiculo = "auto" | "moto" | "camioneta";

export interface Tarifa {
  tipo_vehiculo: TipoVehiculo;
  valor_hora: string;
  fraccion_minutos: number;
}

export interface TarifaEntrada {
  tipo_vehiculo: TipoVehiculo;
  valor_hora: number;
  fraccion_minutos: number;
}

export interface Ticket {
  id: number;
  placa: string;
  tipo_vehiculo: string;
  hora_entrada: string;
  hora_salida: string | null;
  valor_cobrado: string | null;
}

export interface Factura {
  id: number;
  ticket_id: number;
  placa: string;
  tipo_vehiculo: string;
  hora_entrada: string;
  hora_salida: string;
  minutos: number;
  valor_hora: string;
  total: string;
  creada_en: string;
}

export interface Resumen {
  desde: string;
  hasta: string;
  tickets_cerrados: number;
  facturado_total: string;
  por_tipo: Record<string, string>;
}
