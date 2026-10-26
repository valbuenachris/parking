import "./styles.css";
import { api, ErrorAuth, guardarToken, hayToken } from "./api";
import type { Factura, Resumen, Tarifa, Ticket, TipoVehiculo } from "./types";

const app = document.querySelector<HTMLDivElement>("#app")!;

const moneda = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

const fecha = (iso: string) => new Date(iso).toLocaleString("es-CO");

const tipos: TipoVehiculo[] = ["auto", "moto", "camioneta"];

function aviso(mensaje: string, error = false): void {
  const nodo = document.querySelector<HTMLParagraphElement>("#aviso");
  if (!nodo) return;
  nodo.textContent = mensaje;
  nodo.className = error ? "aviso error" : "aviso";
  window.setTimeout(() => {
    if (nodo.textContent === mensaje) nodo.textContent = "";
  }, 4000);
}

function manejarError(error: unknown): void {
  if (error instanceof ErrorAuth) {
    mostrarAcceso("El token no es válido o la sesión expiró. Vuelve a entrar.");
    return;
  }
  aviso((error as Error).message, true);
}

function tarifasHtml(tarifas: Tarifa[]): string {
  const filas = tarifas
    .map(
      (t) => `
      <tr>
        <td>${t.tipo_vehiculo}</td>
        <td>${moneda.format(t.valor_hora)}</td>
        <td>${t.fraccion_minutos} min</td>
      </tr>`,
    )
    .join("");
  return `<table><thead><tr><th>Tipo</th><th>Valor/hora</th><th>Fracción</th></tr></thead><tbody>${filas}</tbody></table>`;
}

function activosHtml(tickets: Ticket[]): string {
  if (tickets.length === 0) return `<p class="vacio">No hay vehículos dentro.</p>`;
  const filas = tickets
    .map(
      (t) => `
      <tr>
        <td>${t.id}</td>
        <td>${t.placa}</td>
        <td>${t.tipo_vehiculo}</td>
        <td>${fecha(t.hora_entrada)}</td>
        <td><button class="cobrar" data-id="${t.id}">Cobrar salida</button></td>
      </tr>`,
    )
    .join("");
  return `<table><thead><tr><th>#</th><th>Placa</th><th>Tipo</th><th>Entrada</th><th></th></tr></thead><tbody>${filas}</tbody></table>`;
}

function facturasHtml(facturas: Factura[]): string {
  if (facturas.length === 0) return `<p class="vacio">Aún no hay facturas.</p>`;
  const filas = facturas
    .map(
      (f) => `
      <tr>
        <td>${f.id}</td>
        <td>${f.placa}</td>
        <td>${f.minutos} min</td>
        <td>${fecha(f.hora_salida)}</td>
        <td>${moneda.format(f.total)}</td>
      </tr>`,
    )
    .join("");
  return `<table><thead><tr><th>Factura</th><th>Placa</th><th>Tiempo</th><th>Salida</th><th>Total</th></tr></thead><tbody>${filas}</tbody></table>`;
}

function resumenHtml(r: Resumen | null): string {
  if (!r) return "";
  const detalle = Object.entries(r.por_tipo)
    .map(([tipo, total]) => `<li>${tipo}: ${moneda.format(total)}</li>`)
    .join("");
  return `
    <div class="resumen">
      <p><strong>Tickets cerrados:</strong> ${r.tickets_cerrados}</p>
      <p><strong>Facturado total:</strong> ${moneda.format(r.facturado_total)}</p>
      <ul>${detalle || "<li>Sin movimientos en el rango.</li>"}</ul>
    </div>`;
}

function plantilla(): string {
  return `
    <header>
      <h1>Parqueadero</h1>
      <p class="subtitulo">Entradas, salidas, facturas e informes</p>
      <p id="aviso" class="aviso"></p>
    </header>
    <main>
      <section class="tarjeta">
        <h2>Registrar ingreso</h2>
        <form id="form-ingreso">
          <label>Placa <input name="placa" required maxlength="12" placeholder="ABC123" /></label>
          <label>Tipo
            <select name="tipo_vehiculo">
              ${tipos.map((t) => `<option value="${t}">${t}</option>`).join("")}
            </select>
          </label>
          <button type="submit">Registrar entrada</button>
        </form>
      </section>

      <section class="tarjeta">
        <h2>Vehículos dentro</h2>
        <div id="activos"></div>
      </section>

      <section class="tarjeta">
        <h2>Tarifas</h2>
        <form id="form-tarifa">
          <label>Tipo
            <select name="tipo_vehiculo">
              ${tipos.map((t) => `<option value="${t}">${t}</option>`).join("")}
            </select>
          </label>
          <label>Valor por hora <input name="valor_hora" type="number" min="1" step="100" required /></label>
          <label>Fracción (min) <input name="fraccion_minutos" type="number" min="1" max="1440" value="60" required /></label>
          <button type="submit">Guardar tarifa</button>
        </form>
        <div id="tarifas"></div>
      </section>

      <section class="tarjeta">
        <h2>Informe del negocio</h2>
        <form id="form-informe">
          <label>Desde <input name="desde" type="datetime-local" required /></label>
          <label>Hasta <input name="hasta" type="datetime-local" required /></label>
          <button type="submit">Calcular</button>
        </form>
        <div id="resumen"></div>
      </section>

      <section class="tarjeta">
        <h2>Facturas</h2>
        <div id="facturas"></div>
      </section>
    </main>
    <footer>Demo minimalista · los datos se guardan en SQLite</footer>`;
}

async function cargarTarifas(): Promise<void> {
  const contenedor = document.querySelector<HTMLDivElement>("#tarifas")!;
  contenedor.innerHTML = tarifasHtml(await api.tarifas());
}

async function cargarActivos(): Promise<void> {
  const contenedor = document.querySelector<HTMLDivElement>("#activos")!;
  contenedor.innerHTML = activosHtml(await api.activos());
}

async function cargarFacturas(): Promise<void> {
  const contenedor = document.querySelector<HTMLDivElement>("#facturas")!;
  contenedor.innerHTML = facturasHtml(await api.facturas());
}

function conectarEventos(): void {
  const formIngreso = document.querySelector<HTMLFormElement>("#form-ingreso")!;
  formIngreso.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const datos = new FormData(formIngreso);
    try {
      const ticket = await api.ingresar(
        String(datos.get("placa") ?? ""),
        String(datos.get("tipo_vehiculo") ?? "auto") as TipoVehiculo,
      );
      aviso(`Ingreso registrado para ${ticket.placa}`);
      formIngreso.reset();
      await cargarActivos();
    } catch (error) {
      manejarError(error);
    }
  });

  const formTarifa = document.querySelector<HTMLFormElement>("#form-tarifa")!;
  formTarifa.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const datos = new FormData(formTarifa);
    try {
      await api.guardarTarifa({
        tipo_vehiculo: String(datos.get("tipo_vehiculo") ?? "auto") as TipoVehiculo,
        valor_hora: Number(datos.get("valor_hora")),
        fraccion_minutos: Number(datos.get("fraccion_minutos")),
      });
      aviso("Tarifa guardada");
      await cargarTarifas();
    } catch (error) {
      manejarError(error);
    }
  });

  const formInforme = document.querySelector<HTMLFormElement>("#form-informe")!;
  formInforme.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const datos = new FormData(formInforme);
    try {
      const desde = new Date(String(datos.get("desde"))).toISOString();
      const hasta = new Date(String(datos.get("hasta"))).toISOString();
      const resumen = await api.resumen(desde, hasta);
      document.querySelector<HTMLDivElement>("#resumen")!.innerHTML = resumenHtml(resumen);
    } catch (error) {
      manejarError(error);
    }
  });

  document.querySelector<HTMLDivElement>("#activos")!.addEventListener("click", async (evento) => {
    const objetivo = evento.target as HTMLElement;
    if (!objetivo.classList.contains("cobrar")) return;
    const id = Number(objetivo.dataset.id);
    try {
      const { factura } = await api.salida(id);
      aviso(`Factura #${factura.id} por ${moneda.format(factura.total)}`);
      await Promise.all([cargarActivos(), cargarFacturas()]);
    } catch (error) {
      manejarError(error);
    }
  });
}

function mostrarAcceso(mensaje = ""): void {
  app.innerHTML = `
    <header>
      <h1>Parqueadero</h1>
      <p class="subtitulo">Acceso al panel</p>
    </header>
    <main>
      <section class="tarjeta">
        <h2>Ingresa el token</h2>
        <form id="form-acceso">
          <label>Token <input name="token" type="password" required autocomplete="current-password" /></label>
          <button type="submit">Entrar</button>
        </form>
        <p id="aviso" class="aviso error"></p>
      </section>
    </main>`;
  const nodoAviso = document.querySelector<HTMLParagraphElement>("#aviso")!;
  if (mensaje) nodoAviso.textContent = mensaje;
  const form = document.querySelector<HTMLFormElement>("#form-acceso")!;
  form.addEventListener("submit", (evento) => {
    evento.preventDefault();
    guardarToken(String(new FormData(form).get("token") ?? ""));
    iniciarPanel();
  });
}

function iniciarPanel(): void {
  app.innerHTML = plantilla();
  conectarEventos();
  const ahora = new Date();
  const ayer = new Date(ahora.getTime() - 24 * 60 * 60 * 1000);
  const formInforme = document.querySelector<HTMLFormElement>("#form-informe")!;
  const desde = formInforme.elements.namedItem("desde") as HTMLInputElement;
  const hasta = formInforme.elements.namedItem("hasta") as HTMLInputElement;
  desde.value = ayer.toISOString().slice(0, 16);
  hasta.value = ahora.toISOString().slice(0, 16);
  Promise.all([cargarTarifas(), cargarActivos(), cargarFacturas()]).catch(manejarError);
}

if (hayToken()) {
  iniciarPanel();
} else {
  mostrarAcceso();
}
