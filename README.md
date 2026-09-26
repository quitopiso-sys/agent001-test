# AGENT #001 — Paso 4: nube + panel visible

Esta versión está preparada para **GitHub Actions + GitHub Pages**.

## Qué verás en el panel
Aunque no opere, verás cada ciclo:

- hora del análisis
- precio BTC / ETH
- señal `BUY`, `SELL` o `HOLD`
- acción real del simulador (`HOLD`, `WAIT`, `BUY CHF ...`, `SELL CHF ...`, `BLOCKED`)
- patrimonio
- estado de vida
- tabla separada de operaciones simuladas

## Coste
La configuración está pensada para un **repositorio público**.
GitHub Actions con runners estándar es gratuito para repositorios públicos y
GitHub Pages está disponible en repositorios públicos de GitHub Free.

## Cómo ponerlo online

1. Crea un repositorio **público** nuevo en GitHub, por ejemplo `agent001-test.`.
2. Sube TODO el contenido de este ZIP, manteniendo la carpeta:
   `.github/workflows/agent001.yml`
3. En GitHub abre **Actions** y permite workflows si te lo solicita.
4. Abre **Settings → Pages**.
5. En `Build and deployment`, selecciona:
   - Source: **Deploy from a branch**
   - Branch: **main**
   - Folder: **/(root)**
6. Guarda.
7. En la pestaña **Actions**, abre `AGENT-001 paper trading` y pulsa
   **Run workflow** una vez para probarlo.

Después, GitHub lo ejecutará aproximadamente cada 15 minutos.

## Dirección del panel

GitHub Pages te mostrará la URL cuando quede publicado. Normalmente será:

`https://TU-USUARIO.github.io/agent001-test./`

## Nota importante

Los workflows programados de GitHub no son un reloj de tiempo real; pueden
retrasarse algunos minutos en momentos de carga. Para nuestro paper test de
15 minutos esto es aceptable.

## Seguridad

- NO contiene API keys.
- NO usa una cuenta Coinbase.
- NO envía órdenes reales.
- NO necesita tarjeta.
- TODO el saldo es virtual.
