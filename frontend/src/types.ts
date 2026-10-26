export type TipoVehiculo = "auto" | "moto" | "camioneta";

export interface Tarifa {
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
  valor_cobrado: number | null;
}

export interface Factura {
  id: number;
  ticket_id: number;
  placa: string;
  tipo_vehiculo: string;
  hora_entrada: string;
  hora_salida: string;
  minutos: number;
  valor_hora: number;
  total: number;
  creada_en: string;
}

export interface Resumen {
  desde: string;
  hasta: string;
  tickets_cerrados: number;
  facturado_total: number;
  por_tipo: Record<string, number>;
}
