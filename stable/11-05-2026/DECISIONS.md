# DECISIONS.md — Proyecto Feroldi
> **Propósito**: Documentar el *por qué* de cada decisión arquitectónica y qué alternativas fueron descartadas.
> El *qué* y el *cuándo* están en `CHANGELOG.txt`. Este archivo documenta el razonamiento que no aparece en el código.
> **Regla de actualización**: Claude actualiza este archivo al cierre de cada sesión larga, con el prompt: *"Actualiza DECISIONS.md con decisiones, descartes y lecciones de hoy."*

---

## Nivel 1 — Principios Invariables

Estas reglas no se debaten en cada sesión. Son contratos permanentes.

| # | Principio | Razón |
|---|-----------|-------|
| P1 | **CHANGELOG.txt se actualiza ANTES de modificar código** | Un CHANGELOG escrito después del código es una reconstrucción aproximada. El orden correcto es: anotar la intención → modificar el código. Violado una vez (X0.78), documentado como error grave. |
| P2 | **Arquitectura agnóstica al ticker** | Cualquier fix hardcodeado para un ticker específico se convierte en deuda técnica al sumar el siguiente ticker similar. Todo fix debe ser una regla general. |
| P3 | **No usar sub-agentes sin avisar al usuario** | El usuario no sabe que el proceso puede tardar minutos. La falta de feedback genera desconfianza y el usuario puede interrumpir trabajo válido. Siempre anunciar antes: "Voy a delegar esto, puede tardar ~2 minutos". |
| P4 | **Cobertura baja de segmentos no es error del pipeline** | El pipeline extrae correctamente lo que existe en XBRL. Si una empresa no tagueó sus segmentos en XBRL, no hay datos — pero el pipeline funcionó bien. No intentar "rellenar" con estimaciones. |
| P5 | **DECISIONS.md se actualiza al cierre de sesión larga** | El razonamiento ephémero de Claude no persiste entre sesiones. Este archivo es el mecanismo para que la próxima instancia de Claude no repita errores ya resueltos. |
| P7 | **Prompts a sub-agentes siempre en inglés nativo** | Los sub-agentes procesan la instrucción inicial + todas las iteraciones del loop interno. Cada vuelta paga el costo de traducción si el prompt está en español. Escribir en inglés elimina ese overhead. El código y comentarios generados por el sub-agente deben especificarse como español dentro del mismo prompt. |
| P8 | **Ningún informe/Sankey se sube a GitHub sin antes registrarse en el dashboard** | El dashboard (`patonet.github.io/informes/`) es la fuente de verdad de qué informes existen. Un push a GitHub sin entrada en el dashboard crea un archivo huérfano: inaccesible desde la UI, sin metadata (ticker, veredicto, precio, fecha). El orden correcto es siempre: generar → registrar en dashboard → push. `feroldi_push.py` ya implementa este orden. **Ningún script ni hook debe hacer un push "suelto" que saltee esta secuencia.** |
| P6 | **CHANGELOG captura capacidades del sistema, no archivos tocados** | "qué archivo se modificó" es un git log con trabajo manual — no agrega valor. Lo que diferencia un changelog útil es describir qué puede hacer el sistema ahora que antes no podía. ✅ "Se corrigió resolución de tickers HK — los Sankeys ahora muestran la empresa correcta". ❌ "Se modificó feroldi_recolectar.py línea 457". |

### SCAT — Strongest Case Against This (acordado 11-05-2026)

Abreviatura canónica del principio epistémico del contrato. Antes de concluir cualquier tesis importante — arquitectónica, técnica o analítica — Claude debe presentar el argumento más fuerte en contra. No el más fácil de refutar: el más incómodo.

Uso: el usuario puede pedir "SCAT" en cualquier momento para exigir el contraargumento honesto.

---

### Contrato de documentación (acordado 09-05-2026)

| Archivo | Qué entra |
|---------|-----------|
| `CHANGELOG.txt` | Versión · fecha · **qué capacidad del sistema cambió** (orientado al comportamiento observable) · resultado de validación |
| `DECISIONS.md` | Por qué se tomó esa decisión · qué alternativas se descartaron · errores que no repetir · estado operacional |

---

## Nivel 2 — Decisiones Vigentes

### D1 — Resolución de tickers HK (numéricos) → Option C
**Fecha**: 09-05-2026 | **Versión**: X0.77

**Decisión activa**: Para tickers numéricos (HK: 1398, 0805, 0883, 2318, 2378, etc.):
1. Detectar si el ticker es numérico con `_is_numeric_ticker()`
2. Obtener nombre real con `yfinance.Ticker(ticker).info["longName"]`
3. Buscar ese nombre en EDGAR con `edgar_find(real_name)`
4. Validar el match con **score ≥ 80 AND difflib similarity ≥ 0.50**
5. Si hay match válido: usar el CIK real de EDGAR
6. Si no hay match: usar datos de yfinance directamente, sin CIK, sin llamar `Company(ticker)`

**Alternativas descartadas**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| **Option A**: Hardcodear tabla `{ticker: CIK}` | No es agnóstica: requiere actualización manual por cada ticker HK nuevo. Rompe P2. |
| **Option B**: Saltear tickers HK (skip) | Pérdida de cobertura. 5 tickers HK válidos con datos reales disponibles. |
| **Llamar `Company(ticker.upper())` directo** | Para un ticker HK como "1398", EDGAR interpreta el ticker como si fuera un ticker US → retorna una empresa americana sin relación (o error). Error activo en X0.76 y anteriores. |
| **Solo score EDGAR sin difflib** | El score de EDGAR puede dar 60.3 entre "Industrial and Commercial Bank of China" y "CANADIAN IMPERIAL BANK OF COMMERCE" — falso positivo real que se produjo en pruebas. El threshold de difflib ≥ 0.50 elimina estos casos. |

**Ejemplo real del falso positivo**:
```
Query: "Industrial and Commercial Bank of China"
EDGAR top result: "CANADIAN IMPERIAL BANK OF COMMERCE"  score=60.3
difflib ratio: 0.28  → RECHAZADO correctamente
```

---

### D2 — Soporte 40-F para empresas canadienses
**Fecha**: 09-05-2026 | **Versión**: X0.77

**Decisión activa**: En `extract_segments_edgartools()`, iterar sobre todos los tipos de form en orden antes de rendirse:
```
10-K → 10-K/A → 20-F → 20-F/A → 40-F → 40-F/A
```
Para cada form: verificar que el XBRL exista antes de pasar al siguiente.

**Alternativas descartadas**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| **if-elif chain** (código anterior) | Si una empresa tiene un 20-F de 2002 sin XBRL, el código antiguo retornaba `None` sin intentar 40-F. BN (Brookfield) tenía exactamente este problema. |
| **Hardcodear `{ticker: form_type}`** | Rompe P2. La forma correcta es probar todos los tipos en orden. |

**Limitación conocida y documentada**: Las empresas canadienses (BN, BNS, CM, CNQ, AEM) tienen segmentos en sus 40-F pero **no con el eje dimensional estándar en XBRL**. TradingView extrae esos segmentos via PDF parsing — fuera del scope de este pipeline. Esta limitación es permanente bajo la arquitectura actual.

---

### D3 — `already_done()`: usar `os.listdir()` en lugar de `glob.glob()`
**Fecha**: 09-05-2026 | **Versión**: X0.77

**Decisión activa**: Enumerar `DOWNLOADS/` con `os.listdir()` + filtro manual en lugar de `glob.glob("Downloads/CORRIDA_*/Diagrama...")`.

**Alternativa descartada**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| `glob.glob()` con wildcard de 2 niveles | macOS TCC (Transparency, Consent, and Control) bloquea acceso a `~/Downloads/` desde subprocess con wildcards multi-nivel. La función retornaba siempre `False` silenciosamente — todos los tickers se reprocesaban en cada corrida. Bug activo desde la creación del archivo. |

---

### D4 — Visualización de cobertura baja de segmentos
**Fecha**: 09-05-2026 | **Versión**: X0.79

**Decisión activa**:
- Mostrar "Cobertura: X%" en el Sankey cuando la suma de segmentos < 95% del revenue total
- **No** intentar estimar o imputar el revenue faltante
- El "área vacía" del revenue box se rellena con el mismo color de fondo del box (no transparente) para evitar el efecto "caja negra"

**Contexto del problema**: El revenue box siempre tiene altura fija (380px). Con cobertura baja (ej: 22% en Prudential), los ribbons de segmentos solo cubren 22% de esa altura. El 78% restante del área del box quedaba en negro (fondo SVG) — visualmente confuso, parecía un error del generador.

**Fix**: El box de INGRESOS ahora tiene un rectángulo de fondo explícito del mismo color (#0d1f35), y el label "INGRESOS GAAP" se posiciona en el tope del box (y=rev_y1+22) en lugar del centro geométrico.

**Alternativas descartadas**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Escalar dinámicamente la altura del box | Rompería la alineación horizontal de todos los boxes del mismo Sankey |
| Agregar un ribbon "Sin datos" gris | Semánticamente incorrecto — no es que los datos sean cero, es que no están disponibles |
| Ocultar el Sankey cuando cobertura < X% | Pérdida de información. El 22% disponible sigue siendo útil. |

---

### D4b — Ubicación de la advertencia de cobertura parcial
**Fecha**: 09-05-2026 | **Versión**: X0.81

**Decisión activa**: La advertencia `⚠️ XX% no disponible` va en el **área vacía del recuadro punteado de SEGMENTOS (C1)**, no en el revenue box (C2).

**Alternativa descartada**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Advertencia en C2 (revenue box) | El lector mira C1 cuando ve segmentos incompletos. La advertencia en C2 se generaba en el HTML pero era invisible en la práctica — el área oscura que llama la atención está en C1. |

**Font-size dinámico**: `min(22, max(12, espacio_vacío // 8))` — se adapta al espacio disponible debajo del último segmento. Evita desbordamiento cuando la cobertura parcial deja poco espacio libre en C1.

---

### D5 — Cabeceras de columna en Sankey
**Fecha**: 09-05-2026 | **Versión**: X0.79

**Decisión activa**: 5 etiquetas fijas encima de las columnas del Sankey:
`SEGMENTOS | INGRESOS | EGRESOS | RESULTADOS | CAJA`

Posición: `y=42`, font-size=9, mayúsculas, color sutil (#1e4a6a), letter-spacing=2.

**Razonamiento**: Sin cabeceras, un usuario nuevo no sabe qué representa cada columna sin leer los boxes. Las cabeceras son texto fijo — no dependen de datos.

---

### D6 — Nombres de empresa en box "sin segmentos"
**Fecha**: 09-05-2026 | **Versión**: X0.78

**Decisión activa**:
- Nombres > 20 caracteres se parten en 2 líneas con `_split_name()`
- Font-size se reduce de 16 → 14 en nombres de 2 líneas
- Para nombres sin espacios (imposibles de partir): `max(9, 16 - (len-22)//2)`

**Problema original**: "New Gonow Recreational Vehicles Inc." en una sola línea con font-size=16 desbordaba el recuadro del box.

---

---

### D7 — Arquitectura de feroldi_gemini_informe.py: stdlib only + rotación de modelos
**Fecha**: 10-05-2026 | **Versión**: X0.82

**Decisión activa**: Usar `urllib.request` (stdlib) en lugar de `requests` o `httpx`.
Rotación de modelos en orden: `gemini-2.5-pro` → `gemini-2.5-flash` → `gemini-2.0-flash-lite`.
Solo hacer fallback en 429/503/quota/overloaded. Errores 400/401 no son retriables — cortar.

**Alternativas descartadas**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Usar `requests` library | No garantizado en todos los entornos. stdlib siempre disponible. |
| Reintentar mismo modelo en 429 con sleep | En 429 la cuota es por minuto/día — no tiene sentido esperar. Probar el siguiente modelo es más eficiente. |
| Un solo modelo sin fallback | El usuario ya pagó por quota. Si pro-2.5 está lleno, Flash puede responder exactamente igual. |

**Lección de test**: gemini-2.5-pro dio 429 en la primera corrida. El fallback a gemini-2.5-flash funcionó correctamente y produjo un análisis de calidad comparable.

---

### D8 — Campos `computed` en JSON: sección separada, no en edgar{}
**Fecha**: 10-05-2026 | **Versión**: X0.82

**Decisión activa**: Los campos calculados (current_ratio, de_ratio, ebitda, revenue_yoy_calc, roic_calc) van en una sección `"computed": {}` separada del JSON, no mezclados en `edgar{}` ni en `ratios{}`.

**Razonamiento**: Son datos *derivados* de campos primarios. Si los campos primarios cambian, los derivados se recalculan. Mezclarlos con datos fuente crea ambigüedad sobre qué es primario y qué es calculado.

**Limitación conocida**: Los campos `computed` estarán en `null` si el JSON fue generado con una versión anterior a X0.82. Para obtener los ratios calculados hay que re-recolectar con X0.82+.

---

### D9 — feroldi_prefetch.py: DuckDuckGo HTML en lugar de APIs de noticias
**Fecha**: 10-05-2026 | **Versión**: X0.82

**Decisión activa**: Usar el endpoint HTML de DuckDuckGo (`html.duckduckgo.com/html/?q=...`) para noticias y competidores.

**Alternativas descartadas**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| NewsAPI / Alpha Vantage News | Requieren API key adicional. El objetivo era stdlib-only. |
| Google Search / Bing | Bloquean scraping agresivamente. DDG HTML es más permisivo. |
| requests + BeautifulSoup | Dependencias externas. Se optó por stdlib + regex. |

**Limitación conocida**: Los datos de competidores de DuckDuckGo son "ticker candidates" (palabras en mayúsculas del texto), no tickers validados. Hay falsos positivos (ej. "US", "API"). El prompt maestro le indica a Gemini que valide estos datos contra lo que sabe del sector.

---

## Nivel 3 — Lecciones Aprendidas (errores que no deben repetirse)

| Lección | Descripción | Fecha |
|---------|-------------|-------|
| **CHANGELOG antes de código** | Claude modificó `feroldi_sankey.py` para X0.78 antes de actualizar CHANGELOG. El usuario detectó la violación. Regla P1 existe por esto. | 09-05-2026 |
| **Campos nuevos no retroactivos** | Los campos `current_assets`, `stockholders_equity`, `depreciation_amortization`, `revenue_prior_year` y la sección `computed` no aparecen en JSONs generados con versiones anteriores a X0.82. Para aprovecharlos hay que re-recolectar. No intentar calcular ratios desde JSONs viejos — quedan en null, que es el comportamiento correcto. | 10-05-2026 |
| **Cuadro de cierre de Gemini con JSON viejo** | En el test de MELI con datos X0.58, el cuadro de cierre mostró "Current Ratio: N/D" correctamente, pero los escenarios bear/base/bull usaron precios calculados por Gemini (no desde `computed.roic_calc`). Este comportamiento es correcto — Gemini rellena N/D con su conocimiento, como dice el prompt maestro. No es un bug. | 10-05-2026 |
| **EDGAR score ≤ 80 es falso positivo** | "Industrial and Commercial Bank of China" matcheó "CANADIAN IMPERIAL BANK OF COMMERCE" con score=60.3. Siempre validar con doble threshold: score EDGAR + difflib ratio. | 09-05-2026 |
| **glob en subprocess falla en macOS silenciosamente** | `glob.glob("Downloads/CORRIDA_*/")` retorna lista vacía desde subprocess por TCC. Usar `os.listdir()` con filtro manual. No hay error explícito — falla silenciosa. | 09-05-2026 |
| **Sub-agente sin aviso genera desconfianza** | Claude delegó la implementación de X0.77 a un sub-agente sin notificar al usuario. El usuario interrumpió el proceso sin saber qué estaba pasando. Siempre anunciar antes. | 09-05-2026 |
| **Baja cobertura ≠ error del pipeline** | 5 tickers con cobertura < 80% (Prudential 22%, DB 31%, ASR 60%, SNY 77%, TTE 77%). No es un bug — el XBRL de esas empresas no tagueó todos los segmentos. Documentar como limitación de datos, no de código. | 09-05-2026 |
| **`Company(ticker)` para tickers numéricos retorna entidad US** | Para "1398" (ICBC Hong Kong), `Company("1398")` retorna una empresa americana aleatoria con CIK 1398. Este bug existió desde el inicio del proyecto y generó 5 Sankeys con datos de empresas incorrectas. | 09-05-2026 |

---

## Mapa de cobertura del universo de tickers (estado 09-05-2026)

| Categoría | Tickers | Razón de limitación |
|-----------|---------|---------------------|
| **Cobertura ≥ 95%** | JPM, BAC, WFC, GS, C, MS | Bancos US grandes — XBRL dimensional completo |
| **Cobertura 80-95%** | UNH (83%), CVS (87%) | XBRL parcial, algunos segmentos no tagueados |
| **Cobertura < 80%** | PRU (22%), DB (31%), ASR (60%), SNY (77%), TTE (77%) | XBRL muy parcial — segmentos existen en PDF/notas pero no en XBRL dimensional |
| **Sin segmentos — HK** | 1398, 0805, 0883, 2318, 2378 | No filing en EDGAR; datos desde yfinance |
| **Sin segmentos — Canadá** | BN, BNS, CM, CNQ, AEM | 40-F sin eje dimensional estándar |
| **Sin segmentos — Europa OTC** | BBVA, IFNNY, SAN, ORAN, VIVHY, ENLAY, MBGAF, HTHIY, IDEXY, CAIXY, REPSF, BCDRF | CIK=N/D o XBRL no disponible en EDGAR |

---

---

## Nivel 4 — Arquitectura del Pipeline

Un Claude nuevo debe entender qué hace cada archivo antes de tocar cualquier cosa.

### Archivos del proyecto

| Archivo | Rol | Versión actual |
|---------|-----|----------------|
| `feroldi_recolectar.py` | **Recolector**: dado un ticker, extrae todos los datos financieros y los escribe en un JSON. Jerarquía de fuentes: Alpha Vantage → EDGAR (edgartools) → TradingView → yfinance. | X0.77 |
| `feroldi_sankey.py` | **Generador**: dado el JSON producido por el recolector, genera el HTML del diagrama Sankey con SVG. No hace ninguna llamada a APIs — trabaja solo con el JSON. | X0.79 |
| `feroldi_batch_corrida.py` | **Orquestador**: itera sobre todos los tickers, llama a los dos scripts anteriores vía subprocess, maneja el skip automático, genera el reporte final. Crea `CORRIDA_N_FEROLDI/` en `~/Downloads/`. | X0.77 |
| `CHANGELOG.txt` | Registro de todo lo que cambió, cuándo y por qué (el *qué*). Siempre se actualiza antes de modificar código. | — |
| `DECISIONS.md` | Este archivo. El *por qué* de cada decisión y qué se descartó. Se actualiza al cierre de sesión larga. | — |

> **Ubicaciones**: Los archivos `.py` viven en `~/` (directorio home) Y están sincronizados a `~/.openclaw/workspace/`. El batch lee desde workspace. Siempre editar en `~/` y copiar al workspace con `cp ~/feroldi_*.py ~/.openclaw/workspace/`.

### Flujo de ejecución de una corrida

```
feroldi_batch_corrida.py
  └─ para cada ticker en TICKERS[]:
       ├─ already_done(symbol) → si True: skip
       ├─ resolve_yf_ticker(symbol) → ticker con sufijo correcto (.HK, .TO, etc.)
       ├─ subprocess: feroldi_recolectar.py → genera JSON en /tmp/
       ├─ subprocess: feroldi_sankey.py → genera HTML Sankey
       └─ mueve HTML a ~/Downloads/CORRIDA_N_FEROLDI/
  └─ genera reporte.txt con resumen de resultados
```

### Jerarquía de fuentes de datos (en feroldi_recolectar.py)

```
TIER 1 — Alpha Vantage  : ratios, métricas, earnings, estimaciones de analistas
TIER 2 — EDGAR edgartools: SBC, goodwill, deuda, cash, segmentos XBRL
TIER 3 — TradingView    : performance histórica (precios)
TIER 4 — yfinance       : auditoría silenciosa + fallback de nombres + tickers HK
```

### Detección de exchange en tickers

`resolve_yf_ticker()` auto-detecta el exchange sin que el usuario escriba sufijos:
- 4 dígitos → `.HK` (HKEX)
- 5-6 dígitos empezando en 0/2/3 → `.SZ` (Shenzhen)
- 5-6 dígitos empezando en 6/9 → `.SS` (Shanghai)
- Country code explícito (CA, ES, FR, etc.) → sufijo mapeado
- Sin sufijo: NYSE / NASDAQ / OTC ADR (default)

---

## Nivel 5 — Estado Operacional y Corridas

### Universo de tickers activo (34 tickers, estado 09-05-2026)

```python
# Argentina — NYSE ADRs
BMA, CEPU, TEO, LOMA, CRESY

# México
KOF, ASR, PAC

# España
BBVA, TEFOF, IBDRY, GRFS, CABK (ES)

# Canadá — NYSE cross-listed
BN, AEM, CM, BNS, CNQ

# Alemania — OTC ADRs
IFNNY, MURGY, RNMBY, DHLGY, DB

# Francia — OTC/NASDAQ
SNY, TTE, LRLCY, LVMUY, PPRUY

# Hong Kong — HKEX (auto-detectados por patrón numérico)
1398, 2378, 0805, 0883, 2318
```

**Tickers excluidos del universo activo** (comentados en TICKERS, razón documentada):

| Ticker | Empresa | Razón de exclusión |
|--------|---------|-------------------|
| GRUMAB | Grupo Bimbo | Solo BMV, sin 20-F en EDGAR |
| ELEKTRA | Grupo Elektra | Solo BMV, sin 20-F en EDGAR |
| 601899, 600673 | Zijin Mining, Chengdu Expr. | China A-shares SSE, sin EDGAR |
| 002050, 002475, 000938 | Zhejiang Sanhua, Luxshare, Ziguang | China A-shares SZSE, sin EDGAR |
| S68, Z74, V03, A17U, C38U | Singapore Exchange, SingTel, otros | SGX Singapur, sin EDGAR |

**Tickers corregidos** (nombre cambiado, razón documentada):

| Antes | Ahora | Razón |
|-------|-------|-------|
| CRES | CRESY | "CRES" retorna 404 en yfinance |
| DPSGY | DHLGY | DPSGY era ticker obsoleto de Deutsche Post |
| TEF | TEFOF | TEF se delistó de NYSE en 2019; TEF.BA es Bolsa Buenos Aires a precio en ARS → precio falso en USD |

---

### Historial de corridas

#### CORRIDA_13 — 08/09-05-2026 (corrida principal de producción)
- **Tickers**: 33 de los 34 activos (todos excepto los 5 HK que aún tenían bug de CIK)
- **Versión del pipeline**: feroldi_recolectar.py X0.76 + feroldi_sankey.py X0.69 + feroldi_batch_corrida.py X0.76
- **Resultado**: 33/33 ✅ — todos con Sankey generado
- **Problemas descubiertos post-corrida** (evaluación visual):
  - 5 tickers HK (1398, 0805, 0883, 2318, 2378) mostraban datos de empresas US aleatorias — CIK numérico mal interpretado
  - `already_done()` nunca funcionó — todos los tickers se reprocesaban en cada corrida
  - Baja cobertura en Prudential (22%), DB (31%), ASR (60%), SNY (77%), TTE (77%)

#### CORRIDA_14 — 09-05-2026 (corrida de fix para los 5 HK)
- **Motivación**: Corregir solo los 5 tickers HK con datos incorrectos; no reeditar CORRIDA_13
- **Tickers**: solo 1398, 2378, 0805, 0883, 2318
- **Versión del pipeline**: feroldi_recolectar.py X0.77 + feroldi_sankey.py X0.78/X0.79 + feroldi_batch_corrida.py X0.77
- **Resultado**: 5/5 ✅ — nombres correctos, datos de yfinance
- **Problemas visuales detectados post-corrida** (comparados con screenshots):
  - Texto de nombres de empresa desbordaba el box "sin segmentos" (0805: "New Gonow Recreational Vehicles Inc.")
  - Strings en inglés hardcodeados: "100% Revenue", "Revenue YoY"
  - Caja negra en Prudential (2378) — área vacía del revenue box con fondo SVG negro
  - Sin etiquetas en las 5 columnas del Sankey

**Decisión de CORRIDA_14 vs alternativas**:

| Opción | Descripción | Decisión |
|--------|-------------|----------|
| **Option A** | Modificar retroactivamente los HTMLs de CORRIDA_13 | ❌ Rechazada — se pierde trazabilidad de versiones |
| **Option B** ✅ | Correr CORRIDA_14 solo con los 5 HK problemáticos | ✅ Elegida — preserva CORRIDA_13 intacta, `already_done()` skipea los 29 restantes |
| **Option C** | Volver a correr todo el universo | ❌ Rechazada — innecesario, los 29 no-HK están correctos |

---

### Estado actual de archivos (al cierre de sesión 09-05-2026)

| Archivo | Versión | Ubicación | GitHub stable |
|---------|---------|-----------|---------------|
| feroldi_recolectar.py | X0.77 | `~/` + workspace | ✅ patonet/informes/stable/09-05-2026/ |
| feroldi_normalizar.py | — | `~/` + workspace | ✅ patonet/informes/stable/09-05-2026/ |
| feroldi_sankey.py | X0.81 | `~/` + workspace | ✅ patonet/informes/stable/09-05-2026/ |
| feroldi_batch_corrida.py | X0.77 | `~/` + workspace | ✅ patonet/informes/stable/09-05-2026/ |
| CHANGELOG.txt | — | `~/` + workspace | — |
| DECISIONS.md | este archivo | `~/` + workspace | — |
| CLAUDE.md | — | `~/` | — |

### Corridas ejecutadas

| Corrida | Tickers | Versión pipeline | Resultado |
|---------|---------|-----------------|-----------|
| CORRIDA_13 | 33 (todos menos 5 HK) | recolectar X0.76 · sankey X0.69 | 33/33 ✅ |
| CORRIDA_14 | 5 HK | recolectar X0.77 · sankey X0.78→X0.81 | 5/5 ✅ |

### Pendiente al próximo sprint

- [ ] **Regenerar 4 HK con X0.81** — 1398, 0805, 0883, 2318 tienen Sankeys de X0.78 (sin column headers visibles, sin advertencia de cobertura). El 2378 (Prudential) ya fue regenerado con X0.81. Borrar sus HTMLs de CORRIDA_14 y correr batch.
- [ ] **QA automatizado de rangos** — sin validación cruzada de revenue entre versiones
- [ ] **Año fiscal consistente** — no garantizado que todos los tickers muestren el mismo período fiscal

---

---

## Nivel 6 — Arquitectura del Pipeline Feroldi Completo (decisiones 10-05-2026)

### D7 — Brecha de datos entre recolector y protocolo de análisis

**Fecha**: 10-05-2026

**Contexto**: Al correr el INFORME LIGHT para $MELI se detectó que los N/D del informe tienen dos orígenes distintos.

**Categoría 1 — N/D heredados del recolector** (el campo existe en el JSON pero llegó null):
`margen_bruto`, `roe`, `sbc`, `revenue_yoy`, `ni_yoy`, `peg`, `analyst_consenso`

**Categoría 2 — N/D estructurales** (el protocolo de análisis los pide pero el recolector nunca los definió como campos):
`ROIC`, `Current Ratio`, `D/E Ratio`, `EV/EBITDA`, `próximo earnings date`, `revenue guidance`, `EPS proyectado`, `sector/industry`

**Decisión activa**: No crear mini-colectores separados. Expandir el recolector principal para capturar los campos de Categoría 2 que son **computables desde EDGAR** (ROIC, Current Ratio, D/E, EV/EBITDA, quarterly data, opex breakdown). Los campos no computables (earnings call transcript, analyst PTs, SOTP) siguen siendo responsabilidad de Claude via web search en Sección A/C del prompt_maestro.

**Alternativas descartadas**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Mini-colector para Light + mini-colector para Heavy | Sobre-ingeniería. La restricción original (captura lenta en chat, 10-15 min) ya no existe — hoy es Python y toma segundos. Dos scripts que mantener sin beneficio real. |
| Recolector gordo que captura todo incluyendo datos Heavy | H1 (transcript), H2 (PTs de analistas), H3 (SOTP) requieren juicio contextual y web search — no son automatizables de forma confiable en Python. |
| Dejar el gap y resolverlo siempre en el paso N/D | Correcto para datos dinámicos (guidance, PTs). Incorrecto para campos computables como ROIC o Current Ratio que EDGAR ya tiene disponibles. |

---

### D8 — Arquitectura de portabilidad del sistema Feroldi

**Fecha**: 10-05-2026

**Contexto**: El usuario quiere que el sistema pueda correr en cualquier PC/Mac del mundo, con cualquier LLM (Gemini, ChatGPT, Claude), sin depender de este entorno específico.

**Flujo portátil definido**:
```
[Usuario remoto — cualquier LLM en cualquier PC]
  │
  ├─ 1. Pega prompt_maestro + ticker + precio en su LLM
  ├─ 2. Prompt invoca a Kika → feroldi_recolectar.py → JSON → GitHub (ruta conocida)
  ├─ 3. LLM espera ~2 min → fetch del JSON desde GitHub vía web_fetch
  ├─ 4. LLM corre Sección A + B (Light) o A + B + C (Heavy) → análisis en pantalla ✅
  │
  └─ [opcional] Infografía → pendiente de resolver (ver D9)
```

**Principios del diseño**:
- **Kika = capa de ejecución** (Python runner + GitHub bridge). Sin razonamiento.
- **GitHub = bus de datos universal** (puente entre la Mac/servidor y cualquier PC remoto).
- **Cualquier LLM = capa de razonamiento** (el análisis es portable entre modelos).
- El análisis en pantalla (Light o Heavy) es el producto completo. No requiere exportar nada.

**Alternativas descartadas**:

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| APIs de otros LLMs (OpenAI API, Gemini API) para orquestar todo desde Python | Demasiado costoso. Rompe la independencia del LLM. |
| Kika genera el informe (análisis incluido) | Kika usa DeepSeek-flash — modelo de razonamiento débil. Por diseño, Kika no razona: captura datos y ejecuta herramientas. El análisis requiere un modelo capaz. |
| Infografía generada por el LLM via prompt | Enfoque probado y descartado (archivado en prompt_generador_light_X0.55.txt). Output inconsistente, Gemini no sirve para HTML complejo, cortes por límite de tokens. |

---

### D9 — Gap de cierre: ENRIQUECIDO_JSON → Kika en flujo remoto

**Fecha**: 10-05-2026 | **Estado**: PENDIENTE DE RESOLUCIÓN

**El problema**: El ENRIQUECIDO_JSON que emite el LLM remoto (Gemini, ChatGPT) queda en la pantalla del usuario. Para que Kika genere la infografía, ese JSON necesita llegar a esta Mac.

**Investigación del endpoint OpenClaw** (realizada 10-05-2026):

| Parámetro | Valor encontrado | Implicancia |
|-----------|-----------------|-------------|
| `gateway.mode` | `"local"` | No expuesto a internet |
| `gateway.bind` | `"loopback"` | Solo accesible desde 127.0.0.1 — no desde red externa |
| `gateway.tailscale.mode` | `"off"` | VPN privada desactivada |
| `channels.telegram.enabled` | `true` | ✅ Bot Telegram activo y conectado |
| `http.endpoints.chatCompletions` | `enabled: true` | Endpoint HTTP existe pero solo en loopback |

**Conclusión**: OpenClaw NO es accesible desde internet por HTTP en la configuración actual. El único canal externo activo es **Telegram**.

**Solución disponible hoy (sin cambios de infraestructura)**:
El usuario remoto copia el ENRIQUECIDO_JSON y lo envía a Kika vía Telegram. Kika corre `feroldi_infografia.py` (cuando exista), sube a GitHub y responde con el link. Un copy-paste, 30 segundos.

**Opciones para automatizar en el futuro** (no decididas aún):

| Opción | Descripción | Costo/Riesgo |
|--------|-------------|--------------|
| Cambiar `bind` a `0.0.0.0` | Exponer OpenClaw a internet | ⚠️ Riesgo de seguridad alto — requiere auth robusta |
| Activar Tailscale | VPN privada entre dispositivos autorizados | ✅ Seguro, pero requiere que el usuario remoto instale Tailscale |
| Publicar ENRIQUECIDO_JSON en GitHub y que Kika lo lea | El LLM remoto sube el JSON a un path predefinido; Kika monitorea ese path | ✅ Sin cambios de red, requiere que el LLM pueda hacer commits a GitHub |
| Mantener flujo manual (Telegram) | Copy-paste del JSON al chat de Telegram con Kika | ✅ Funciona hoy, fricción mínima |

**Decisión provisional**: Mantener Telegram como canal de retorno hasta que se decida si vale la pena automatizar. La infografía es opcional — el análisis en pantalla es el producto principal.

---

---

### D10 — Prueba directa Gemini 2.5 Flash via API (10-05-2026)

**Fecha**: 10-05-2026 | **Estado**: COMPLETADO

**Objetivo**: Validar si Gemini puede seguir el protocolo del prompt_maestro_X0.56 y a qué costo.

**Setup**: Llamada directa a Google AI Studio API (free tier) con prompt_maestro + JSON de MELI sin intermediarios. Sin web search — Gemini trabajó solo con el contexto provisto.

**Resultados de tokens (informe Light completo):**

| Métrica | Valor |
|---------|-------|
| Input tokens | 5,806 |
| Output tokens | 4,834 |
| Thinking tokens (internos) | 6,808 |
| Total cobrado por Google | 17,448 |
| Costo (free tier) | $0 |
| Chars de output | 16,359 |

**Hallazgos de calidad:**

| Aspecto | Resultado |
|---------|-----------|
| Adherencia al protocolo | ✅ Excelente — todos los bloques, formato, ENRIQUECIDO_JSON |
| Veredicto | 🟢 COMPRA EN RETROCESOS (coincide con Claude) |
| Score Feroldi | 126.5/160 (79.1%) — más generoso que Claude sin datos verificados |
| D/E ratio | ❌ 0.15 (incorrecto — debería ser ~1.19 calculado desde EDGAR) |
| Revenue YoY | ❌ Inconsistente entre llamadas (26.5% / 32% / 99%) |
| CEO quote | ❌ Fabricada — genérica, sin transcript real |
| ROIC | ❌ 9.5% de memoria, no calculado desde el JSON |
| Thinking tokens | ⚠️ 6,808 tokens internos — probablemente cuentan contra el cupo RPD |

**Causa raíz de los errores**: Sin acceso a web search, Gemini resuelve N/D desde su entrenamiento. Los valores parecen verificados pero son estimaciones. **Conclusión: el pre-fetch de Kika no es opcional — es obligatorio para que el informe sea confiable.**

**Decisión sobre arquitectura de llamada API:**

La llamada debe ser **una sola request** (no agentic con tool calls) para maximizar los RPD disponibles:
- Kika pre-fetchea: B0 (noticias), N/D pendientes (web search por campo), 5 competidores (TradingView + stockanalysis)
- Kika arma un contexto único con todo el contenido
- Una sola llamada a Gemini/Claude → análisis completo
- 1 RPD por informe → 100 informes/día con Gemini 2.5 Pro (free tier)

**Rotación de modelos por agotamiento de cupo:**
```
1° Gemini 2.5 Pro   (100 RPD, mejor calidad)
2° Gemini 2.5 Flash (250 RPD, calidad media)
3° Gemini 3.1 Flash Lite (1,500 RPD, calidad básica)
```

**Nota sobre Gemini 2.5 Pro**: El cupo estaba agotado al momento de la prueba (limit: 0). Confirma la inestabilidad del free tier. No es confiable para producción sin un plan de rotación automática.

---

---

### D11 — Principio arquitectónico: KIKA hace el trabajo sucio, el PENSANTE razona

**Fecha**: 11-05-2026 | **Permanente — no se debate por sesión**

**Definiciones canónicas:**

| Rol | Quién | Qué hace |
|-----|-------|----------|
| **KIKA** | OpenClaw + DeepSeek-flash | Trabajo sucio: recolectar datos, hacer web fetches, calcular ratios, armar contexto, llamar APIs, subir a GitHub |
| **PENSANTE** | Hoy: Gemini · mañana: Claude, ChatGPT, o cualquier otro | Trabajo elegante: leer el JSON pre-masticado y razonar para producir el informe |

**Principio:**
> *"Todo el web fetch y captura de datos lo hace Kika. El PENSANTE solo lee el JSON y razona para hacer el informe. La idea es gastar el mínimo número de tokens en el modelo pensante."*

**Consecuencias de diseño — no negociables:**

1. **El PENSANTE no hace web_fetch.** Kika pre-fetcha todo antes de llamar al PENSANTE.
2. **El PENSANTE no calcula.** Kika calcula ROIC, D/E, Current Ratio, etc. y los entrega resueltos.
3. **El PENSANTE no llama herramientas.** Recibe UN contexto completo y devuelve UN análisis. 1 API call = 1 informe.
4. **El PENSANTE es intercambiable.** El sistema no depende de Gemini. Si mañana Claude o ChatGPT son mejores o más baratos, se cambia la API key sin tocar nada más.
5. **Scripts separados por modo:** `feroldi_light.py` (Sección A+B) y `feroldi_heavy.py` (Sección A+B+C). Light no carga instrucciones de Heavy → ahorro de ~35% de tokens de input por informe Light.

**Alternativa descartada:**

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Darle herramientas (web_fetch, tools) al PENSANTE | Multiplica los API calls por informe, consume el cupo RPD del free tier, hace el sistema dependiente de que el LLM soporte tool use, y genera resultados inconsistentes entre modelos. |

---

---

### D12 — Split del prompt_maestro: prompt_light.txt + prompt_heavy.txt

**Fecha**: 10-05-2026 | **Estado**: PENDIENTE DE IMPLEMENTACIÓN

**Contexto histórico**: El prompt_maestro fue unificado porque vivía en la memoria de "Projects" de la app de Claude. Al estar cacheado en el proyecto, su carga no consumía tokens por sesión — era costo cero. Tenía sentido tenerlo todo junto.

**Problema actual**: Ahora el prompt se envía en cada llamada a la API de Gemini/Claude. Un prompt_maestro completo (Secciones A + B + C + instrucciones Heavy) cuesta tokens de input en CADA request, aunque el usuario solo haya pedido un informe Light. Heavy tiene instrucciones específicas de web fetch, análisis profundo de crédito, SOTP, etc. — contenido innecesario para un Light que nunca va a llegar a la Sección C.

**Estimación del desperdicio**: El prompt_maestro completo tiene ~12,000-15,000 chars. Las instrucciones exclusivas de Heavy representan aproximadamente 35-40% de ese total. A $3/MTok de input en Gemini 2.5 Pro, en 100 informes Light/día eso es ~$1.50/día en tokens que no se usan nunca.

**Decisión activa**: Separar en dos archivos:

| Archivo | Contiene | Cuándo se carga |
|---------|----------|-----------------|
| `prompt_light.txt` | Secciones A + B completas, instrucciones de ENRIQUECIDO_JSON Light, bloque G con sub-preguntas | Cuando el usuario elige LIGHT |
| `prompt_heavy.txt` | Secciones A + B + C completas, instrucciones de web fetch H1/H2/H3, análisis de crédito, SOTP | Cuando el usuario elige HEAVY |

**Flujo de enrutamiento post-recolección:**
```
Usuario da ticker + precio
     ↓
Sistema recolecta datos (feroldi_recolectar.py)
     ↓
Sistema pregunta: "¿LIGHT · HEAVY · SANKEY?"
     ↓
LIGHT → carga prompt_light.txt → feroldi_light.py
HEAVY → carga prompt_heavy.txt → feroldi_heavy.py (pendiente)
SANKEY → feroldi_sankey.py (no requiere PENSANTE)
     ↓
Una vez generado el informe:
Sistema puede ofrecer: "¿INFOGRAFÍA · PDF?"
(INFOGRAFÍA y PDF SOLO se ofrecen después del informe — requieren su contenido)
```

**Por qué INFOGRAFÍA y PDF van DESPUÉS del informe:**
La infografía necesita el ENRIQUECIDO_JSON del informe (score, TPs, SL, escenarios). El PDF es un wrapper del informe generado. Ninguno puede producirse antes porque dependen del output del PENSANTE.

**Alternativas descartadas:**

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Mantener prompt_maestro unificado | Sigue siendo correcto para flujo en app de Claude con Projects cache. Incorrecto para llamadas API directas donde cada token cuenta. |
| Fragmentar en más de 2 archivos | La división natural es exactamente Light (A+B) vs Heavy (A+B+C). Una tercera partición añade complejidad sin beneficio claro. |
| Comprimir el prompt maestro existente | Compresión agresiva del prompt reduce calidad de instrucciones. El problema es de arquitectura (qué se carga), no de verbosidad. |

---

### D13 — Sub-preguntas Feroldi: el formato "·" no funciona — requiere formato imperativo

**Fecha**: 10-05-2026 | **Estado**: PENDIENTE DE IMPLEMENTACIÓN EN prompt_light.txt**

**Contexto**: Cada uno de los 16 puntos Feroldi tiene 3 sub-preguntas diseñadas para **forzar razonamiento en cadena**. El diseño es brillante: cada sub-pregunta obliga al modelo a atacar el problema desde un ángulo distinto antes de asignar un score. Es chain-of-thought manual embebido en la estructura del análisis.

**El problema**: El formato actual usa `·` como separador inline:

```
¿Diferenciación? · ¿Fuente? switching/red/intangibles/costo/escala · ¿Pricing power?
```

Los modelos leen esto como una enumeración de temas para un **párrafo** — no como tres preguntas con respuesta obligatoria separada. El resultado es una respuesta fusionada que pierde el beneficio del chain-of-thought. Verificado en producción con Gemini 2.5 Flash (X0.86) y con Claude Sonnet 4.6 (X0.43): **ambos modelos fallan** en responder las sub-preguntas por separado.

**Evidencia del fallo:**
- P5 MOAT (Gemini X0.86): respuesta en un solo párrafo de 3 líneas. No se distinguen los tres ángulos.
- P5 MOAT (Sonnet X0.43): 5 bullets de moat excelentes, pero tampoco responde las 3 sub-preguntas en el formato requerido.

**Decisión activa**: Reescribir el bloque G en prompt_light.txt con **formato imperativo numerado + placeholder visible**:

```
**P5. MOAT**

  Sub-q1 — ¿Diferenciación? (qué tiene TICKER que otros no pueden copiar fácilmente):
  → [responder aquí: dato concreto + fuente]

  Sub-q2 — ¿Fuente del moat? (clasificar separadamente: red/switching/intangibles/costo/escala):
  → [responder aquí: identificar CADA fuente con su mecanismo causal]

  Sub-q3 — ¿Pricing power? (¿el moat permite fijar precios sin perder clientes? evidencia):
  → [responder aquí: take rate, margen histórico, o evidencia de resistencia a competencia]

  Score: [🟢/🟡/🔴] X.X/10 — [una oración que vincule el score con las tres sub-preguntas]
```

**Por qué funciona**: El `→ [responder aquí]` crea un blank explícito que el modelo siente como obligación de completar. No puede fusionarlo en un párrafo porque cada placeholder tiene su propia línea y su propia dirección semántica.

**SCAT**: El riesgo es que el modelo responda el formato sin razonar — tres frases cortas que "llenan el espacio" sin profundidad real. Hay que validar en test que la calidad no baje al volver el formato más rígido. La solución si eso ocurre es añadir instrucción explícita: "cada sub-pregunta debe tener mínimo 2 oraciones con evidencia cuantificada."

**Nota**: Esta corrección es parte de la reescritura de prompt_light.txt (D12). No es un cambio de código — es un cambio de instrucciones en el archivo de texto del prompt.

---

### D14 — PENSANTE: Gemini Flash vs Sonnet — análisis comparativo de calidad de razonamiento

**Fecha**: 10-05-2026 | **Estado**: OBSERVACIÓN DOCUMENTADA — decisión final pendiente

**Contexto**: Se comparó el informe generado por Gemini 2.5 Flash (X0.86, automatizado) vs Claude Sonnet 4.6 Extended (X0.43, manual) sobre el mismo ticker MELI al mismo precio. Score: 103/160 Gemini vs 121/160 Sonnet.

**Advertencia metodológica — la comparación no fue justa:**

| Parámetro | Gemini X0.86 | Sonnet X0.43 |
|-----------|-------------|-------------|
| Modelo | 2.5 Flash (falló Pro por RPD) | Sonnet 4.6 Extended |
| Acceso a web | ❌ Solo JSON + prefetch | ✅ Google Search libre |
| Training data libre | ❌ "SOLO el JSON" | ✅ Sin restricción |
| Q1 2026 data | ❌ quarterly_eps vacío | ✅ Disponible |
| SBC data | ❌ null en JSON | ✅ Macrotrends |

**Hallazgos donde la comparación SÍ es justa (mismos datos disponibles):**

El punto MOAT no requiere datos externos — es conocimiento estructural que ambos modelos tienen en training. Aun así:

- Gemini: 3 frases genéricas sin un dato cuantificado. Nombra el concepto sin mecanismo causal.
- Sonnet: 5 capas de moat con datos específicos (1,200+ fulfillment centers, 95% red propia, 48h vs 4-7 días Shopee, $10B+ costo de replicación, data moat de 25 años). Identifica el límite del moat (Shopee sin logística propia llegó a 8.5% de share).

**Falla crítica de Gemini en Bloque X (SCAT):**
El Bloque X pide el "contraargumento más sólido que no se puede ignorar" — explícitamente, el caso en contra. Gemini escribió un argumento **a favor** ("el FCF masivo sugiere que la rentabilidad puede estar subestimada"). No fue capaz de identificar el propósito epistémico de la instrucción. Sonnet produjo el contraargumento correcto: el portafolio de crédito de $14.6B como riesgo de Capital One 2007.

**Hipótesis de trabajo (no confirmada):**
Gemini Flash tiene una brecha de razonamiento analítico frente a Sonnet 4.6, independientemente de los datos. No es solo un problema de datos atados — es un problema de profundidad de razonamiento. Requiere test con Gemini 2.5 Pro (si consigo cupo) con los mismos datos y sin restricción de training para confirmar.

**Decisión provisional:** No cambiar PENSANTE todavía. Primero implementar:
1. Sub-question enforcement (D13) — mejora a cualquier modelo
2. Split del prompt (D12) — mejora la eficiencia  
3. Enriquecimiento del prefetch con datos faltantes — elimina la asimetría de datos

**Después** de esos tres fixes, correr un test apples-to-apples con Gemini 2.5 Pro (cupo lleno) vs Claude API y comparar. Solo entonces tiene sentido la decisión de cambiar el PENSANTE.

---

### D15 — DuckDuckGo reemplazado por Google News RSS como fuente primaria de noticias

**Fecha**: 10-05-2026 | **Versión**: X0.85 → X0.86

**Supersede a**: D9 (que documentaba DuckDuckGo como fuente principal)

**Decisión activa**: Google News RSS es la fuente primaria de noticias. DuckDuckGo se mantiene como **último recurso** (tercer fallback) solo si Google RSS y Finviz dan menos de 3 resultados.

**Jerarquía actual de noticias:**
```
1° Google News RSS (sin API key, sin CAPTCHA, XML estructurado)
2° Finviz news section (se descarga igual para competidores — costo cero adicional)
3° DuckDuckGo HTML (solo si las dos anteriores fallan)
```

**Por qué se cambió**: Un sub-agente usó DuckDuckGo como fuente primaria. El error fue detectado al revisar el código del sub-agente. DuckDuckGo HTML tiene CAPTCHA frecuente y su estructura cambia. Google News RSS es estable, estructurado y sin autenticación.

**Lección documentada en Nivel 3**: Nunca delegar implementación de fuentes de datos a un sub-agente sin especificar la fuente exacta en inglés. Los sub-agentes toman decisiones de "junior developer" en elecciones de tooling.

---

### D16 — Datos faltantes en el pipeline que degradan la calidad del PENSANTE

**Fecha**: 10-05-2026 | **Estado**: PENDIENTE DE FIX

**Contexto**: Al comparar el informe automatizado (X0.86) con el informe manual (X0.43), se identificaron brechas de datos estructurales que hacen que el PENSANTE puntúe puntos enteros con N/D — independientemente de su capacidad de razonamiento.

**Brechas identificadas por origen:**

| Campo faltante | Impacto en análisis | Origen del fix |
|----------------|---------------------|----------------|
| `quarterly_eps` (vacío) | Sin Q1 2026 → sin 4° EPS miss, sin colapso de margen 600bps | `feroldi_recolectar.py` (EDGAR 8-K) |
| `sbc: null` | Sin SBC → punto 12 desierto. Gemini da 2/10 vs 5/10 real | `feroldi_recolectar.py` (EDGAR cash flow) |
| `lt_debt: null` | Balance sheet mal evaluado | `feroldi_recolectar.py` (EDGAR balance) |
| Performance solo YTD/6M | Sin retornos 1Y/5Y/10Y/IPO → creación de valor histórica vacía | `feroldi_recolectar.py` (yfinance history) |
| Management info | CEO name/tenure/ownership → Management 4/10 vs 7.5/10 real | `feroldi_prefetch.py` (stockanalysis) |
| AFCF vs FCF distinction | Capital Intensity mal calificado (9/10 vs 7/10 real) | `feroldi_prefetch.py` (análisis o nota calculada) |
| Analyst detail post-earnings | Solo "Strong Buy" genérico vs UBS $2,050, RJ $2,000, Daiwa downgrade | `feroldi_prefetch.py` (stockanalysis forecast) |

**Regla derivada**: Los campos con origen en `feroldi_recolectar.py` requieren confirmación explícita del usuario antes de modificar (ver CLAUDE.md). Los campos con origen en `feroldi_prefetch.py` pueden agregarse en la siguiente sesión de trabajo sin confirmación adicional.

**SCAT**: Agregar más datos al prefetch aumenta el tiempo de ejecución y la superficie de error por scraping. Cada fuente adicional puede bloquear, devolver datos incorrectos, o cambiar su estructura HTML. El principio debe ser: datos que son **determinantes para un punto Feroldi completo** justifican el costo. Datos decorativos, no.

---

---

### D17 — CORRECCIÓN de D12: el split del prompt_maestro no está justificado por tokens

**Fecha**: 10-05-2026 | **Corrige a**: D12

**El error**: D12 argumentó que partir el prompt_maestro en Light + Heavy ahorraría tokens de input. Ese razonamiento ignora que las APIs de Anthropic y Google tienen **prompt caching nativo** (descuento ~90% sobre tokens cacheados). El prompt_maestro es estático entre llamadas — es exactamente el tipo de contenido que el cache cubre. La porción variable (JSON de datos + prefetch) siempre se procesa, con o sin split.

**Qué sí sobrevive del argumento**: un prompt_light más corto reduce marginalmente la porción no-cacheable. Pero es un beneficio marginal, no la razón principal que se documentó.

**Decisión corregida**: Mantener prompt_maestro **unificado**. No partir. Si en el futuro hay evidencia concreta de desperdicio de tokens en producción a escala, se revisita. Hoy no hay ese problema.

**Lección**: Antes de proponer una optimización de tokens, verificar si el proveedor ya tiene caching. Anthropic: 90% descuento en prefijo cacheado con TTL de 5 minutos. Google: similar. Esto cambia completamente el análisis de costo.

---

### D18 — FMP vs yfinance: primero explotar lo que ya tenemos

**Fecha**: 10-05-2026 | **Estado**: DECISIÓN PROVISIONAL — revisar después de arreglar recolector

**Contexto**: El usuario evalúa contratar Financial Modeling Prep (FMP) a $19.90/mes para resolver los campos faltantes del recolector. Presupuesto máximo: $20-25/mes en datos.

**Análisis de disponibilidad en yfinance (gratis, ya en TIER 4):**

| Campo faltante crítico | yfinance lo tiene | Campo específico |
|------------------------|-------------------|------------------|
| `lt_debt`, `st_debt` | ✅ Sí | `balance_sheet` → LongTermDebt, ShortLongTermDebt |
| `sbc` | ✅ Sí | `cashflow` → "Stock Based Compensation" |
| `quarterly_eps` | ✅ Sí | `quarterly_earnings` → 4 quarters con EPS real vs estimado |
| Performance 1Y/5Y/10Y | ✅ Sí | `history(period="5y")` → calcular retorno |
| Management / CEO name | ❌ No confiable | — |
| Analyst PTs individuales (UBS, RJ, etc.) | ❌ Limitado | Solo consenso |
| Guidance formal | ❌ No | — |
| ROE / ROIC histórico multi-año | ⚠️ Parcial | `info` tiene algunos |
| Margen operativo histórico 5 años | ⚠️ Parcial | Requiere calcular desde statements históricos |

**Conclusión provisional**: 5 de los 7 campos faltantes críticos para el informe Light están disponibles en yfinance. El recolector los tiene en TIER 4 pero no los extrae. **El fix es expandir el uso de yfinance en el recolector — no pagar FMP.**

**¿Cuándo sí valdría FMP $19.90?**
- Para el informe Heavy: requiere datos históricos de alta fiabilidad (ROIC anual 5 años, margen operativo histórico, earnings call metadata)
- Si yfinance empieza a fallar por scraping/rate limits en producción a escala
- Para tickers fuera de US donde yfinance tiene menor cobertura

**Decisión**: Arreglar yfinance primero. Evaluar FMP después de tener el Heavy funcionando y ver qué sigue faltando. No gastar $19.90/mes antes de saber si es necesario.

---

### D19 — Sistema FUENTE + Supervisor 1 + Supervisor 2: el hallazgo más valioso del proyecto

**Fecha**: 10-05-2026 | **Estado**: PROBADO MANUALMENTE · PENDIENTE AUTOMATIZACIÓN

**Descripción**: El usuario descubrió empíricamente un sistema de revisión multi-LLM que produce informes de calidad significativamente superior al informe de una sola fuente. Documentado aquí como decisión arquitectónica por su importancia estratégica.

**El sistema (flujo manual actual):**

```
FUENTE (ej. Claude Sonnet) genera el informe Light o Heavy
    ↓
Supervisor 1 (ej. Gemini) recibe el informe + prompt de auditoría
    ↓
Supervisor 2 (ej. ChatGPT) recibe el mismo informe + prompt de auditoría
    ↓
FUENTE recibe ambas auditorías + prompt de síntesis y debate
    ↓
FUENTE produce informe revisado (acepta, rebate, descubre lo que ninguno vio)
    ↓
[Opcional: ronda 2] Supervisores reciben la revisión de FUENTE
  y solo debaten los puntos en que aún discrepan
    ↓
Convergencia en 2-3 rondas → informe definitivo
```

**Por qué funciona:**
1. Cada LLM tiene distinto corpus de entrenamiento → distintos puntos ciegos
2. La instrucción "cada hallazgo debe ajustar el score Feroldi" fuerza al modelo a cuantificar su crítica en vez de hacer comentarios vagos
3. La pregunta final a la FUENTE ("¿hay algo que ninguno de los tres planteó?") captura el blind spot del meta-debate — el más difícil de detectar
4. Convergencia en 2-3 rondas funciona como peer review académico

**Prompt de auditoría a los Supervisores:**
> "Revisa este análisis de otra LLM (llámalo FUENTE). Revisa a profundidad si los fundamentales que expone son correctos; si no, replantea el análisis. Analiza, discrepa solo si tenés razón, debate, explorá escenarios no planteados. Ponete en el lugar de otro analista senior: ¿qué se les olvidó? Cada error, omisión o hallazgo debe ajustar el score Feroldi en el punto correspondiente y justificar el cambio. Pensá en el usuario como inversor."

**Prompt de síntesis a la FUENTE:**
> "El Supervisor 1 y Supervisor 2 revisaron tu análisis. Debatí, desarrollá escenarios no planteados, sin egos. Tres preguntas antes de responder: (1) ¿hay algún error mío que ambos ni siquiera detectaron? (2) ¿qué argumentos de ambos son fuertes vs. especulativos? (3) ¿qué sigue siendo cierto que ninguno de los tres planteó? Cada argumento que aceptés debe ajustar el score Feroldi."

**SCAT del sistema:**
El riesgo real es convergencia en error compartido: si los tres modelos leyeron los mismos artículos sobre una empresa, los tres tienen el mismo punto ciego. La convergencia no siempre es verdad — puede ser consenso de sesgo colectivo. Mitigación: rotar qué modelo es FUENTE entre tickers.

**Prioridad de automatización:**
Este sistema debería automatizarse **antes que la infografía**. Razones:
- Es técnicamente el más simple de automatizar: texto → texto, sin tool use, sin datos externos, loop determinístico
- Su impacto en calidad del informe es inmediato y documentado (score sube ~15-20 puntos en promedio)
- Funciona con cualquier modelo — no depende de que Gemini sea bueno

**Los nombres son roles, no modelos:**
FUENTE, Supervisor 1, Supervisor 2 son roles intercambiables. Hoy son Claude, Gemini, ChatGPT. Mañana pueden ser cualquier combinación. El sistema no depende de ningún modelo específico.

---

### D20 — Secuencia de prioridades del proyecto (versión corregida 10-05-2026)

**Fecha**: 10-05-2026 | **Reemplaza**: secuencia informal discutida en D11 y D12

**Secuencia acordada con SCAT incorporado:**

```
PRIORIDAD 1 — Recolector completo
  Expandir feroldi_recolectar.py para extraer de yfinance los campos que ya tiene
  pero no usa: lt_debt, st_debt, sbc, quarterly_eps, performance 1Y/5Y/10Y.
  Confirmar con usuario antes de tocar el archivo (ver CLAUDE.md).
  Sin esto, el PENSANTE trabaja con datos incompletos sin importar qué tan bueno sea.

PRIORIDAD 2 — Darle 3 oportunidades a Gemini con datos completos
  Una vez el recolector esté completo, correr el informe Light 3 veces con Gemini
  (manual y automático) para evaluar si con datos correctos la calidad es aceptable
  comparada con Sonnet. Si las 3 pruebas producen un informe con score >115/160
  y sin N/D en puntos críticos (Management, SBC, Historical Growth), Gemini
  queda como PENSANTE principal. Si no lo logra, se documenta la decisión de
  cambiar a Claude API para producción.

PRIORIDAD 3 — Prompt_maestro Light con sub-preguntas forzadas
  Reescribir el bloque G del prompt_maestro con formato imperativo numerado +
  placeholder visible por sub-pregunta (ver D13). Sin esta corrección, ningún
  modelo (ni Gemini ni Sonnet) responde las 3 sub-preguntas por separado.

PRIORIDAD 4 — Test Light definitivo y validación de calidad
  Correr el informe Light con MELI y otros 2-3 tickers. Comparar contra X0.43.
  El criterio de "Light funcionando bien": score ≥ 115/160, cero N/D en los
  16 puntos por falta de datos (N/D por genuina falta de información de la empresa
  es aceptable), sub-preguntas respondidas por separado en todos los puntos.

PRIORIDAD 5 — Automatizar sistema FUENTE + Supervisor 1 + Supervisor 2
  Antes que la infografía. Es el componente de mayor impacto en calidad y el más
  simple de automatizar (texto → texto, loop determinístico, sin tool use).
  Ver D19 para detalle del sistema y los prompts.

PRIORIDAD 6 — Prompt_maestro Heavy y test Heavy
  Solo después de que Light esté validado. Heavy no puede estar bien si Light
  no lo está — comparten la misma base de datos y las Secciones A+B.

PRIORIDAD 7 — Evaluar FMP $19.90 si Heavy necesita datos no disponibles en yfinance
  Datos históricos de ROIC multi-año, earnings call metadata, analyst PTs individuales.
  No contratar antes de saber si es necesario.

PRIORIDAD 8 — Infografía y PDF
  Dependen del ENRIQUECIDO_JSON del informe. Solo cuando Heavy esté validado.
```

**Principio rector de la secuencia**: Cada prioridad es precondición de la siguiente. No saltar. No hacer Heavy antes de que Light esté bien. No hacer infografía antes de que el informe exista.

**La automatización de la API (Prioridad 2) no bloquea el trabajo manual**: el test de Gemini puede correrse manualmente mientras se trabaja en el recolector. Son paralelos, no secuenciales.

---

---

### D21 — X0.83: expansión yfinance resuelve los N/D que degradaban el informe automatizado

**Fecha**: 10-05-2026 | **Versión**: X0.83 | **Estado**: IMPLEMENTADO Y VALIDADO (PGR)

**Contexto**: Test serie con PGR @ $194.00. El informe automatizado Gemini 2.5 Flash marcaba 106/160 vs 118/160 de Sonnet manual. La brecha de 12 puntos tenía dos causas: datos faltantes (recolector) y razonamiento superficial (modelo). Esta decisión documenta el fix de la parte del recolector.

**Campos añadidos en X0.83 — todos extraídos de yfinance (sin costo adicional):**

| Campo | Fuente yfinance | Valor PGR | Impacto en informe |
|-------|----------------|-----------|-------------------|
| `sbc` | cashflow → "Stock Based Compensation" | $132M | Punto 12 pasó de N/D a evaluable |
| `roic` | Calculado: NOPAT/IC o NI/IC_approx | 55.7% (NI/IC_approx) | Punto capital intensity evaluable |
| `eps_forward` | `info["forwardEps"]` → rellena `ratios.eps_proj` | $16.13 | EPS proyectado disponible |
| `return_1y` | `history(period="5y")` → retorno calculado | -27.2% | Punto 11 (creación de valor) evaluable |
| `return_3y` | ídem | +58.3% | ídem |
| `return_5y` | ídem | calculado | ídem |
| `lt_debt` | `balance_sheet["longTermDebt"]` | disponible | ROIC cálculo más preciso |
| `st_debt` | `balance_sheet["currentDebt"]` | disponible | ídem |

**Resultado**: Gemini 2.5 Flash con datos X0.83 alcanzó 118/160 — igual que Sonnet numéricamente.

**Hallazgo crítico documentado aquí**: El 118 de Gemini y el 118 de Sonnet NO son equivalentes.  
Mismo score, razonamiento completamente distinto. Ver D22, D25, D27.

**Fix técnico clave — normalizer overwrote JSON**: feroldi_normalizar.py corre como subprocess después de que recolectar.py guarda el JSON. Si el normalizador no preserva los campos nuevos (return_1y/3y/5y, eps_proj, roic), los fills del recolector se pierden al momento de ejecutar. Solución: actualizar feroldi_normalizar.py para incluir los nuevos campos en el dict de performance y ratios.

**SBC multi-fallback documentado**: PGR tiene "Stock Based Compensation" en el cashflow statement, no en el income statement. Lista de fallback implementada:
```
"Stock Based Compensation", "Share Based Compensation",
"Stock-based Compensation", "Share-based Compensation", "Equity-based Compensation"
```

**ROIC con fallback NI para empresas de seguro**: PGR (Progressive) no reporta `us-gaap_OperatingIncomeLoss` en EDGAR XBRL como los no-seguros. Formula primaria `NOPAT/IC` requiere op_income → NULL para PGR. Fix: si op_income == None y net_income existe, usar `NI/IC` con label "NI/IC_approx". El valor es un overestimate porque NI de seguros incluye rendimiento de inversiones que NOPAT excluye. StockAnalysis reporta 28.98% vs nuestro 55.7% — la diferencia es exactamente ese componente.

---

### D22 — Gemini 3.1 Flash-lite: confirmado peor que 2.5 Flash en todas las dimensiones

**Fecha**: 10-05-2026 | **Versión**: X0.83 | **Estado**: TEST COMPLETADO — VEREDICTO DEFINITIVO

**Motivación del test**: El usuario propuso probar 3.1 Flash-lite con sub-preguntas forzadas para ver si un modelo "tonto" con instrucciones explícitas podía mejorar.

**Setup**: Mismo ticker PGR @ $194.00, mismo JSON X0.83, prompt_maestro_X0.50 con sub-preguntas numeradas (versión expandida temporal).

**Resultados comparativos:**

| Dimensión | 2.5 Flash | 3.1 Flash-lite | Diferencia |
|-----------|-----------|----------------|------------|
| Score reportado | 118/160 (73.8%) | **136.5/160 (85.3%)** | 3.1 infla +18.5 pts |
| Caracteres de output | 13,241 chars | 6,163 chars | 3.1 produce la MITAD |
| Adherencia al formato | Parcial | Ignoró sub-preguntas | 3.1 peor |
| SCAT (Bloque X) | Ausente | Cosmético | Ambos fallan |
| CEO quote | Verificable | **Fabricada** | 3.1 alucina |
| Google Search grounding | ✅ Compatible | ❌ Incompatible | 3.1 no usa grounding |

**Falla diagnóstica principal**: 3.1 Flash-lite asignó 136.5/160 produciendo 6,163 caracteres de análisis — la mitad que 2.5 Flash con 118/160. Un modelo que hace menos trabajo y se autocalifica más alto es más peligroso que un modelo que hace poco y sabe que hizo poco. La inflación de score sin trabajo es "grade inflation" pura.

**Alucinación CEO**: 3.1 inventó una cita genérica del CEO sin fuente verificable. 2.5 Flash al menos señala la limitación cuando no tiene el dato.

**Incompatibilidad con Google Search grounding**: `"tools": [{"google_search": {}}]` no funciona con flash-lite. No es un bug — es una limitación de capacidad del modelo.

**Veredicto**: *"El tonto nace tonto."* Forzar chain-of-thought con sub-preguntas no compensa una capacidad de razonamiento estructuralmente inferior. Las sub-preguntas ayudan a modelos capaces — no crean capacidad donde no existe.

**Daño colateral documentado**: Para el test se expandió temporalmente prompt_maestro_X0.50 con sub-preguntas numeradas en 16 bloques. El formato modificado dañó el prompt original. Lección: nunca experimentar sobre el archivo de producción — usar una copia de trabajo.

---

### D23 — Estado de completitud del recolector: qué entrega, qué no puede entregar y por qué

**Fecha**: 10-05-2026 | **Versión**: X0.83 | **Estado**: INVENTARIO DEFINITIVO

**Pregunta que responde esta decisión**: *"¿ya el recolector entrega todo para que cualquier modelo trabaje bien?"*

**Respuesta directa: SÍ para el informe Light. NO para el informe Heavy.**

**Campos que X0.83 entrega de forma confiable (para informe Light):**

| Categoría | Campos | Fuente | Confiabilidad |
|-----------|--------|--------|---------------|
| P&L básico | revenue, gross_profit, op_income, net_income, ebitda_calc | AV + EDGAR | Alta |
| Balance | equity, lt_debt, st_debt, cash, goodwill | EDGAR + yfinance | Alta |
| Cash flow | fcf, capex, sbc | AV + EDGAR + yfinance fallback | Media-Alta |
| Ratios básicos | pe_ratio, pb_ratio, ps_ratio, pfcf | AV | Alta |
| Ratios derivados | roic, de_ratio, current_ratio | Calculados en recolector | Media (depende de fuente) |
| Performance precio | return_1y, return_3y, return_5y | yfinance history | Alta |
| EPS | eps_basic, eps_forward | AV + yfinance | Alta |
| Crecimiento | revenue_yoy, ni_yoy | AV (requiere 2 años de datos) | Media |
| Segmentos | segmentos XBRL dimensional | EDGAR edgartools | Variable (ver mapa cobertura) |
| Noticias | últimas 5-7 noticias relevantes | Google News RSS | Alta |
| Competidores | 3-5 tickers del sector | StockAnalysis + DDG fallback | Media |
| Ratios mercado | roe, roa, roic_web | StockAnalysis / prefetch | Media |

**Campos que el recolector NO puede entregar (limitaciones estructurales):**

| Campo | Por qué no está disponible | Impacto en informe |
|-------|---------------------------|-------------------|
| `quarterly_eps` (últimos 4 trimestres) | AV free tier no devuelve quarterly granular consistente; yfinance `quarterly_earnings` incompleto | Punto 8 (EPS momentum) parcial |
| CEO name/tenure/ownership | yfinance.info poco confiable; stockanalysis no siempre lo tiene | Punto 13 (Management) parcial |
| Analyst PTs individuales (UBS $X, RJ $Y) | Requieren Bloomberg/Refinitiv; solo consenso disponible gratis | Punto 14 (Valuación) sin PTs |
| Revenue guidance formal | Solo en earnings calls (PDF/transcript) — no hay API pública confiable | N/D genuino |
| Earnings call transcript | No disponible gratis, requiere Seeking Alpha Premium o similar | N/D genuino |
| ROIC histórico multi-año | Requiere statements históricos + cálculo manual — posible pero costoso | Light usa spot ROIC |
| Current Ratio para empresas de seguro | Seguros no tienen "current assets" convencionales en EDGAR XBRL | N/D estructural |
| EBITDA para seguros | Op_income null → ebitda null en seguros (PGR, PRU) | N/D estructural |

**Conclusión para el usuario**: El recolector X0.83 entrega suficiente para que cualquier modelo capaz razone bien el informe Light. Los N/D que quedan son genuinos — no son bugs del pipeline, son limitaciones de disponibilidad pública de datos. Un modelo que produce N/D en Current Ratio para PGR no está roto; la empresa de seguros no tiene "current assets" en el sentido convencional.

**SCAT**: Afirmar que "el recolector está completo" puede crear una falsa sensación de suficiencia. El informe Light con X0.83 aún tiene puntos donde un analista experto tiene más información que el pipeline (quarterly EPS, guidance, analyst PTs). La diferencia es que ahora esos N/D son estructurales — no bugs a resolver.

---

### D24 — La brecha de calidad restante es de razonamiento, no de datos

**Fecha**: 10-05-2026 | **Estado**: OBSERVACIÓN DOCUMENTADA — implica decisión en D25

**Contexto**: Con X0.83, Gemini 2.5 Flash alcanzó 118/160 (igual que Sonnet). El score convergió. El razonamiento no.

**Análisis comparativo en puntos donde los datos son iguales para ambos modelos:**

**MOAT (P5) — mismo contexto, razonamiento diferente:**

| Modelo | Respuesta | Calidad |
|--------|-----------|---------|
| Gemini 2.5 Flash | "PGR tiene ventaja de escala y marca" — genérico, sin datos | ⚠️ Superficial |
| Sonnet 4.6 Extended | "Network effect de datos de Snapshot® (30B millas/año), costo de switching del canal agente (5,500 agentes exclusivos), pricing diferencial de 20-30% sobre comp activos — el moat es asimétrico de información, no de escala" | ✅ Causal, cuantificado |

**OPTIONALITY (P7) — mismo contexto, razonamiento diferente:**

| Modelo | Respuesta | Calidad |
|--------|-----------|---------|
| Gemini 2.5 Flash | Menciona expansión a vida y commercial lines como opcionalidades | ⚠️ Describe opciones, no analiza si son reales |
| Sonnet 4.6 Extended | Distingue comercial (ya 20% de primas, moat replicable) de vida (real optionality con White Mountains como comparador, ARR implícito de $2B+) | ✅ Identifica qué es optionality real vs wishful thinking |

**SCAT / Bloque X — el fallo más revelador:**

| Modelo | Respuesta | Calidad |
|--------|-----------|---------|
| Gemini 2.5 Flash | Produjo un argumento a favor en el bloque de contraargumento | ❌ No entiende el propósito epistémico del SCAT |
| Gemini 3.1 Flash-lite | Produjo un "contraargumento" cosmético que terminaba elogiando la empresa | ❌ Cosmético |
| Sonnet 4.6 Extended | "El verdadero riesgo es que los algoritmos de competidores (GEICO, Allstate) alcancen a Snapshot® — si el moat es solo datos, el moat desaparece cuando todos tienen datos. Bear target: $140 (P/B 2.5x book value en escenario de compresión de ROE a 12%)" | ✅ Identifica el mecanismo causal del riesgo + precio objetivo bear |

**Diagnóstico**: La diferencia no es acceso a datos — es capacidad de razonamiento causal. Gemini Flash lee datos y los describe. Sonnet lee datos y razona sobre los mecanismos. Esta diferencia no se corrige con más datos ni con mejores prompts.

**Implicación directa**: El 118/160 de Gemini y el 118/160 de Sonnet representan informes de distinta calidad de decisión. Un inversor que usa el informe de Gemini tiene la misma conclusión numérica con menos sustancia analítica detrás. Esto importa porque el informe es un insumo de decisión de inversión, no un examen de trivia.

---

### D25 — Decisión estratégica: suspender automatización Gemini, manual Sonnet para decisiones reales

**Fecha**: 10-05-2026 | **Estado**: DECISIÓN ACTIVA

**Decisión**: Suspender la búsqueda de optimización del PENSANTE Gemini para producción de informes de inversión reales. Continuar usando Claude Sonnet (manual) para las decisiones reales del usuario.

**Razonamiento**:

1. El objetivo del proyecto es **calidad de decisión de inversión**, no cantidad de informes.
2. Gemini Flash puede alcanzar el mismo score numérico con razonamiento de menor profundidad — score es una métrica rota (ver D27).
3. La arquitectura ya es model-agnostic (PENSANTE es una variable de configuración). Cambiar el modelo no requiere tocar el pipeline.
4. El pipeline sigue siendo valioso para investigación y triage de tickers — incluso con Gemini Flash es mejor que nada.

**Lo que SÍ continúa:**
- Seguir construyendo la infraestructura model-agnostic
- Optimizar el recolector (D20, Prioridad 1 — ya completada con X0.83)
- Implementar sub-preguntas forzadas en prompt_maestro cuando se escriba prompt_light.txt (D13)
- Test con Gemini 2.5 Pro (cupo completo, no limitado por API key nueva) antes de veredicto definitivo sobre Gemini

**Lo que se suspende:**
- Optimización de prompts orientada a que Gemini Flash mejore su razonamiento analítico
- Experimentos con modelos Flash-lite o versiones degradadas
- Cualquier esfuerzo que implique "enseñarle a razonar" a un modelo que no tiene esa capacidad base

**Alternativas descartadas:**

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Seguir optimizando Gemini Flash con prompts más detallados | Dos tests (PGR, MELI) muestran que la limitación es de arquitectura del modelo, no de prompt. El tonto nace tonto. |
| Cambiar ya a Claude API para producción | Tiene costo real. La infraestructura con Gemini free tier sigue siendo útil para desarrollo y triage. No hay urgencia. |
| Usar 2.5 Pro como PENSANTE principal | No disponible confiablemente en el free tier (ver D26). Requiere plan pago para depender de él. |

**Punto de revisión**: Cuando se tenga acceso estable a Gemini 2.5 Pro (plan pago o cupo regenerado), correr un test apples-to-apples con los mismos datos X0.83 y el mismo prompt. Solo ese test es válido para evaluar si Pro supera la brecha de razonamiento de Flash.

---

### D26 — Gemini 2.5 Pro: confirmado no funciona con API keys nuevas (free tier)

**Fecha**: 10-05-2026 | **Estado**: LIMITACIÓN CONOCIDA Y DOCUMENTADA

**Observación**: API keys de Google AI Studio creadas hace menos de 24-48 horas tienen quota 0 para gemini-2.5-pro. El comportamiento es:
- 429 con mensaje "model not found" o "quota exceeded" inmediatamente en la primera llamada
- Gemini 2.5 Flash responde correctamente con la misma key
- Gemini 1.5 Pro también con la misma key

**Evidencia**: Probado con 5 keys distintas creadas en la misma sesión. Todas fallaron para 2.5 Pro, todas funcionaron para 2.5 Flash.

**Hipótesis**: Google AI Studio tiene un warm-up period para 2.5 Pro en el free tier, o el modelo tiene cuotas separadas que no se activan inmediatamente. No es un bug del pipeline — es una limitación del servicio.

**Consecuencia operacional**: El fallback a gemini-2.5-flash en feroldi_gemini_informe.py es correcto y necesario. Sin él, el pipeline falla completamente con keys nuevas.

**Nota para el futuro**: Si se contrata un plan pago de Google AI Studio, 2.5 Pro debería estar disponible inmediatamente. Reevaluar la arquitectura de rotación en ese momento.

---

### D27 — El score Feroldi es una métrica rota como proxy de calidad de análisis

**Fecha**: 10-05-2026 | **Estado**: PRINCIPIO DOCUMENTADO — afecta evaluación futura

**Observación empírica**: PGR @ $194.00 — Gemini 2.5 Flash con datos X0.83 = 118/160. Sonnet 4.6 Extended manual = 118/160. Scores idénticos, calidad de análisis profundamente diferente (ver D24).

**Por qué ocurre esto:**

El score Feroldi es autocalificado por el PENSANTE. El mismo criterio instruccional ("8/10 si A y B y C, 6/10 si solo A") lo interpreta de forma distinta según la capacidad del modelo:
- Un modelo superficial asigna 8/10 nombrando los conceptos.
- Un modelo analítico asigna 8/10 después de demostrar causalmente por qué se cumplen A, B y C.

El número resultante es igual. La decisión de inversión derivada es diferente.

**Implicación para evaluación de modelos:**

No usar el score como criterio de selección del PENSANTE. El score evalúa si el modelo sigue el protocolo de calificación, no si el análisis es profundo. Para evaluar calidad de modelo, analizar directamente:

1. **MOAT**: ¿identificó el mecanismo causal específico o solo nombró el concepto?
2. **OPTIONALITY**: ¿distinguió entre opcionalidad real (no en precio) y wishful thinking?
3. **SCAT (Bloque X)**: ¿produjo un contraargumento real con precio objetivo bear y tesis causal? ¿O elogió la empresa en el bloque de crítica?
4. **CEO**: ¿mencionó una decisión específica y sus consecuencias, o una cita genérica?

Estos cuatro puntos no requieren datos externos — son razonamiento puro. Un modelo que falla en los cuatro tiene una brecha de razonamiento que no se corrige con más datos ni con mejores prompts.

**Regla derivada para futuras evaluaciones de modelos:**

Antes de hacer una corrida de evaluación, leer solo los puntos MOAT, OPTIONALITY, SCAT y CEO del informe. Si los cuatro son profundos → el modelo califica como PENSANTE. Si alguno es superficial → el score total no importa, el modelo no califica para decisiones de inversión reales.

---

---

### D28 — DeepSeek V4 Pro: nuevo PENSANTE confirmado

**Fecha**: 10-05-2026 | **Versión**: X0.88 | **Estado**: DECISIÓN ACTIVA

**Contexto**: Test con PGR @ $194.00. DeepSeek V4 Pro corriendo vía API directa (`api.deepseek.com`), infraestructura de feroldi_pensante.py (ex feroldi_gemini_informe.py).

**Resultado del test (X0.88 · PGR · Light):**
- Score reportado: 128.8/160 — el más alto registrado para PGR (superó Gemini Flash 118/160)
- SCAT: bear target $130 (-33%), mecanismo causal específico (compresión ROE si Combined Ratio >100%)
- ROIC auto-corregido: 55.7% (nuestro cálculo NI/IC) → 37.6% (corrección por método StockAnalysis) — el modelo detectó el error de metodología sin que se lo pidiera
- Sub-preguntas ①②③: 12/15 puntos con las tres respondidas por separado (vs 6/15 con Gemini Flash)

**Criterios de evaluación directa (D27) — DeepSeek V4 Pro:**

| Punto | Calidad |
|-------|---------|
| MOAT | Identifica Snapshot® como data moat con mecanismo causal + menciona 30B millas/año |
| OPTIONALITY | Distingue comercial (real) de vida (especulativo) |
| SCAT | Bear target calculado ($130) con tesis causal (Combined Ratio > 100%) |
| CEO | Menciona Susan Griffith con decisión específica (algoritmo Snapshot) |

Todos los cuatro → DeepSeek V4 Pro califica como PENSANTE según el criterio de D27.

**Pricing (con descuento 75% hasta 31 mayo 2026):**
- Input: $0.435/MTok | Output: $0.87/MTok
- Costo real corrida PGR: ~$0.23 (50,296 tokens totales)
- Comparado con Sonnet: 3-10× más barato

**Decisión arquitectónica**: feroldi_gemini_informe.py renombrado a feroldi_pensante.py. El modelo es una variable de configuración (`--modelo`). Default: `deepseek-v4-pro`. Kika puede usar la misma key sin colisión (el API de DeepSeek soporta llamadas concurrentes).

**Alternativas descartadas:**

| Alternativa | Por qué se descartó |
|-------------|---------------------|
| OpenRouter ($5% surcharge) | Útil para multi-LLM audit, pero innecesario ahora — una sola key DeepSeek sirve para Kika + PENSANTE sin overhead |
| Gemini 2.5 Flash como PENSANTE | Razonamiento superficial documentado en D24 — el problema no es el precio, es la profundidad |
| Claude API como PENSANTE | 3-10× más caro, no justifica el diferencial de calidad cuando DeepSeek V4 Pro tiene calidad comparable |

---

### D29 — Error crítico de session: system message bloqueó el mecanismo PASO 2

**Fecha**: 10-05-2026 | **Versión**: X0.88 | **Estado**: CORREGIDO EN X0.88

**Error cometido**: En el primer draft de feroldi_pensante.py, el system message decía "NO tenés acceso a internet". Esta instrucción canceló el mecanismo PASO 2 del prompt_maestro, que instruye al PENSANTE a hacer búsquedas adicionales para resolver N/D.

**Síntoma**: DeepSeek devolvió respuestas thin en los 3 puntos que tenían N/D en el JSON. El modelo sabía la instrucción del prompt (buscar datos faltantes) pero la contradecía el system message (no hay internet).

**Fix inmediato**: Cambiar el system message para permitir que el modelo use su conocimiento de entrenamiento como fuente TIER 2→4 del protocolo:
```python
"para cada campo en N/D en el JSON, buscá en tu conocimiento verificado (TIER 2→4 como indica el protocolo)"
```

**Fix estructural (feroldi_prefetch.py X0.89)**: El prefetch debe resolver todos los N/D computables antes de llamar a DeepSeek. Los N/D que llegan al PENSANTE deben ser genuinamente irresolvibles (revenue guidance no publicado, información propietaria). No deben llegar N/D triviales como IPO date, analyst PTs, Combined Ratio para aseguradoras.

**Regla derivada**: El system message en el PENSANTE NUNCA puede contradecir una instrucción del prompt_maestro. Si hay conflicto, el prompt_maestro prevalece. El system message solo define el rol y la restricción de no inventar — no limita las fuentes de conocimiento.

**Error que no debe repetirse**: No poner "no tenés internet" en el system message de ningún modelo que razona sobre datos financieros. La restricción correcta es "PROHIBIDO inventar sin certeza", no "PROHIBIDO usar tu conocimiento".

---

---

### D30 — Post-earnings fetch: trigger por calendario, arquitectura agnóstica al sector

**Fecha**: 10-05-2026 | **Versión**: X0.91 | **Estado**: IMPLEMENTADO

**Problema**: yfinance no actualiza ciertos campos rápidamente post-earnings (ej: `forwardEps`, `latest_quarter`). MRSH reportó Q1 2026 el 22-Apr-2026 y yfinance seguía mostrando EPS $16.13 (stale) vs run-rate real ~$19.2 ($4.80×4). El PENSANTE habría heredado ese dato erróneo sin advertencia.

**Solución implementada**: `fetch_post_earnings(ticker)` en feroldi_prefetch.py:
- Trigger: función `ultimo_quarter_reportado()` basada en fecha del sistema (no en campo `latest_quarter` del JSON, que puede ser N/D)
- Fuente: Google News RSS con queries dinámicos (`{ticker} Q1 2026 earnings results`)
- Extracción: regex genéricos (Pattern A: EPS numérico, B: LABEL XX.X%, C: $XB profit/revenue, D: X% growth) — **sin hardcoding sectorial**
- Salida: `post_earnings.kpis_consolidados` + artículos con títulos/snippets entregados al PENSANTE con advertencia explícita de prioridad

**Alternativas descartadas**:
| Alternativa | Por qué se descartó |
|-------------|---------------------|
| Trigger basado en `latest_quarter` del JSON | El campo es N/D para múltiples tickers (MRSH, otros). Dependencia frágil. |
| Scraping del Investor Relations site del ticker | Requiere conocer la URL de IR para cada empresa. URL no es uniforme. Google News RSS cubre el mismo contenido con una sola interfaz. |
| Hardcoding por sector (insurance → Combined Ratio, bank → NIM) | Violación directa de P2. Deuda técnica para cada sector nuevo. |
| Regex por sector específico | Mismo problema que arriba. Los regex Pattern B/C/D son suficientemente genéricos para capturar cualquier KPI numérico independientemente del sector. |

**Limitación conocida (X0.91)**: Pattern B demasiado permisivo — captura artículos de otros tickers en el mismo feed (ej: FIS, Global Payments aparecieron mezclados con MRSH). Mitigación actual: PENSANTE recibe los títulos completos y puede discriminar. Fix pendiente para X0.92: filtrar artículos que no mencionan el ticker en el título.

**Lección**: El trigger correcto para "post-earnings fresh data" es temporal (¿el último quarter terminó hace < 30 días?) combinado con fecha del sistema — no depende de datos que el propio recolector puede fallar en capturar.

---

### D31 — Medición de tokens y costos: corrida MRSH X0.91

**Fecha**: 10-05-2026 | **Versión**: X0.91 | **Estado**: DOCUMENTADO

**Baseline (antes de corrida MRSH)**:
- Saldo DeepSeek: $13.10
- v4-pro: 6 corridas / 174,924 tokens acumulados
- v4-flash (Kika): 1,998 corridas / 200,247,184 tokens acumulados

**Corrida MRSH @ $163.25 (modo light)**:
- Tiempo: 349.3 segundos (~5.8 min con streaming)
- Tokens entrada: 16,928 | Tokens salida: 10,199 | Total: 27,127
- Score: 130/160 (81.4%)

**Costo estimado (con descuento 75% hasta 31-may-2026)**:
- Input: 16,928 × $0.435/MTok = $0.0074
- Output visible: 10,199 × $0.87/MTok = $0.0089
- **Visible total: ~$0.016**
- ⚠️ Los reasoning tokens (thinking interno) se cobran a tasa de output pero NO aparecen en `tokens salida` del log. El costo real incluye esos tokens ocultos. El usuario debe contrastar saldo en dashboard de DeepSeek para obtener el costo real total.

**Nota arquitectónica**: El contexto construido por feroldi_pensante.py fue de 43,035 chars (~10,758 tokens estimados), pero la API reportó 16,928 tokens de entrada — diferencia explicada por el overhead del formato y el system message. La estimación interna de tokens es orientativa, no exacta.

**Delta de tokens v4-pro** (para que el usuario verifique en dashboard): +27,127 tokens visibles sobre el acumulado previo de 174,924 → total esperado visible: ~202,051 tokens. La diferencia real en el dashboard indicará cuántos reasoning tokens generó este run.

---

---

### D32 — X0.93: DeepSeek necesita libertad epistémica, no solo datos

**Fecha**: 10-05-2026 | **Versión**: X0.93 | **Estado**: IMPLEMENTADO Y VALIDADO EN ONON

**El problema**: El system message anterior decía implícitamente "analizá estos datos". DeepSeek se quedaba en los datos. No volcaba su conocimiento de entrenamiento sobre la empresa (CEO saliente en ONON, competencia Hoka, patentes CloudTec, cofundadores al mando). Sonnet corriendo sin ningún dato lo superaba porque usaba su conocimiento libremente.

**La solución**: System message reescrito para dejar explícito que el modelo tiene DOS fuentes simultáneas: el JSON (datos numéricos verificados) y su propio conocimiento de entrenamiento (contexto, eventos, historia competitiva). Se le instruye combinar ambas y señalar contradicciones.

**Micro-tests previos al cambio**: 3 tests, todos con errores metodológicos:
- Test 1: preguntas hardcodeadas (Greensill, THRIVE, McGriff por nombre) → no válido
- Test 2: max_tokens=2000, modelo gastó todo en reasoning y no escribió nada → no válido
- Test 3: max_tokens=6000, insuficiente → parcialmente válido

**Test válido**: max_tokens=32000, pregunta abierta sobre MMC → el modelo produjo análisis sólido con McGriff $7.75B correcto, soft market, Aon/NFP como amenaza. Confirmó que el conocimiento está, el problema era el prompt.

**Validación ONON**: Con X0.93, DeepSeek encontró solo desde su conocimiento: renuncia CEO (evento reciente), Allemann tomando el mando, competencia Hoka directa, Asia <5% como oportunidad, patentes CloudTec hasta 2035, vietnam supply chain risk. Nada de eso estaba en el JSON.

**Alternativa descartada**: Tool calling / web search para eventos post-cutoff. Correcto como siguiente paso, pero no necesario para el impacto inmediato. El 80% del valor estaba en cambiar el prompt, no en agregar herramientas.

**Error que no debe repetirse**: Nunca limitar max_tokens artificialmente en modelos de razonamiento. Los reasoning_tokens consumen el presupuesto interno — con 12K el modelo no tenía margen para pensar Y escribir. 32K es el mínimo razonable.

---

### D33 — Auto-evaluación de sesión: errores cometidos y skills creadas

**Fecha**: 10-05-2026 | **Tipo**: Cierre de sesión larga

**Procesos repetidos sin skill (tokens desperdiciados):**

| Proceso | Veces en esta sesión | Debería haber sido |
|---------|---------------------|---------------------|
| Correr pipeline completo (3 scripts + timing + sync) | 4 veces | skill `feroldi-correr` |
| Sincronizar archivos a workspace | 8+ veces | skill `feroldi-sincronizar` |
| Correr solo el pensante sobre datos existentes | 2 veces | skill `feroldi-pensante` |

**Errores cometidos en esta sesión:**

1. **Ticker MRSH/MMC**: corrí el pipeline completo sobre MRSH sin notar que MMC es el ticker correcto de Marsh & McLennan. DeepSeek lo señaló en el micro-test. El pipeline funcionó por accidente (yfinance resolvió igual). Revisión previa del ticker debería ser parte del workflow.

2. **Micro-tests mal diseñados**: 3 iteraciones, cada una con un error distinto (preguntas hardcodeadas, tokens insuficientes, preguntas triviales). Diseñé el test después de empezar a correrlo en lugar de antes.

3. **MAX_TOKENS = 12000**: Durante la corrida MRSH lo bajé de 32K a 12K creyendo que era innecesario. Resultó ser el factor que limitaba el razonamiento. Costo: 1 corrida de calidad reducida y 1 sesión entera de diagnóstico.

4. **Patching feroldi_prefetch.py como solución**: propuse seguir añadiendo secciones al prefetch (artículos de earnings, body fetch) cuando el problema raíz era el prompt. 4+ intercambios desperdiciados hasta que el usuario lo señaló.

5. **Omisión de Roger Federer en ONON**: el modelo no mencionó la inversión/endorsement de Federer en On Running, que es un hecho público y relevante para el análisis de marca. El sistema mejoró pero no es perfecto.

**Skills creadas al cierre de esta sesión**: `feroldi-correr`, `feroldi-sincronizar`, `feroldi-pensante` (ver archivos en ~/.claude/skills/).

---

---

### D34 — Arquitectura completa del sistema Feroldi (mapa real, no el imaginado)

**Fecha**: 10-05-2026 | **Tipo**: Documentación de infraestructura existente

**Repo GitHub**: `patonet/informes` (público, GitHub Pages activo en main)
**Dashboard**: `https://patonet.github.io/informes/` — protegido con password SHA-256, estilo Bloomberg

**Estructura del repo ya existente:**
```
patonet/informes/
├── index.html                          ← Dashboard con auth + tabla de todos los informes
├── equities/                           ← Infografías HTML (heavy)
│   └── infografia_TICKER_PRECIO_FECHA.html
├── diagramas/equities/                 ← Sankeys interactivos HTML
│   └── Diagrama_Sankey_TICKER_PRECIO_FECHA.html
├── pdfs/equities/                      ← PDFs de informes
│   └── InformePDF_TICKER_PRECIO_FECHA.pdf
│   └── InformePDF_lite_TICKER_PRECIO_FECHA.pdf
├── batch_outputs/                      ← Corridas batch históricas
├── prompts/                            ← Prompt maestros versionados
└── kika/                               ← Carpeta de Kika
```

**Informes ya subidos**: FSLY, SPOT, NOK, UHS (y más). El dashboard muestra ticker, veredicto (buy/neutral/pullback/green), precio, upside, target, fecha — con links directos a infografía, PDF y Sankey.

**Estructura de cada entrada en el dashboard (`const REPORTS`):**
```javascript
{
  ticker: "SPOT", name: "Spotify Technology S.A.",
  type: "equity", verdict: "pullback",
  price: "$441.51", upside: "+51.4%", target: "$668.00", date: "03 May 2026",
  url: "equities/infografia_SPOT_...",        // infografía heavy
  urlLight: "",                               // infografía light
  pdfUrl: "",                                 // PDF heavy
  pdfLightUrl: "",                            // PDF lite
  sankeyUrl: "diagramas/equities/..."         // Sankey
}
```

**Script de push**: `feroldi_push.py` — lee ~/Downloads/, detecta archivos por patrón de nombre, los sube a GitHub vía API, actualiza el dashboard `index.html` con la nueva entrada. Requiere `GH_TOKEN` en variable de entorno.

**Patrones de nombre reconocidos por feroldi_push.py:**
| Archivo | Carpeta GitHub | Tipo |
|---------|---------------|------|
| `infografia_light_TICKER_PRECIO_FECHA.html` | `equities/` | Infografía Light |
| `infografia_TICKER_PRECIO_FECHA.html` | `equities/` | Infografía Heavy |
| `InformePDF_lite_TICKER_PRECIO_FECHA.pdf` | `pdfs/equities/` | PDF Lite |
| `InformePDF_TICKER_PRECIO_FECHA.pdf` | `pdfs/equities/` | PDF Heavy |
| `Diagrama_Sankey_TICKER_PRECIO_FECHA.html` | `diagramas/equities/` | Sankey |

**Flujo completo ya diseñado (Kika lo automatiza):**
```
Usuario: $ONON 35.20 → Telegram
Kika:
  1. feroldi_recolectar.py ONON 35.20     (~17s)
  2. feroldi_prefetch.py ONON 35.20       (~20s)
  3. feroldi_pensante.py ONON 35.20       (~530s) → informe MD
  4. feroldi_sankey.py → Diagrama_Sankey_ONON_35.20_FECHA.html
  [falta: generador de infografía HTML + PDF]
  5. feroldi_push.py → sube todo a GitHub, actualiza dashboard
  6. Kika responde en Telegram:
     📊 Informe: patonet.github.io/informes/equities/...
     🌊 Sankey:  patonet.github.io/informes/diagramas/...
     📋 Dashboard: patonet.github.io/informes/
```

**Lo único que falta para la automatización completa:**
1. `GH_TOKEN` configurado en el entorno de Kika
2. Pairing de Telegram (Pato manda DM al bot)
3. Verificar que feroldi_light.py (generador de infografía HTML) siga funcionando post X0.88 (cambió de Gemini a DeepSeek como PENSANTE)

**Error previo documentado**: En sesiones anteriores se asumió que el repo no existía y que Telegram no funcionaba. Ambas eran falsas — el repo tiene informes reales y Telegram está operativo. Siempre revisar la infraestructura existente ANTES de proponer soluciones.

---

*Última actualización: 10-05-2026 — D34: mapa completo de infraestructura Feroldi documentado (repo, dashboard, flujo Kika)*

---

## D35 — Hallazgo: documento externo sobre migración OpenClaw → ZeroClaw (11-05-2026)

**Contexto**: El usuario encontró en ~/Downloads/ un archivo `openclaw_zeroclaw_migracion.txt` que contiene una "conversación" documentando vulnerabilidades de OpenClaw y recomendando migrar a "ZeroClaw".

**Decisión tomada**: No actuar sobre el contenido del archivo sin verificación independiente.

**Por qué**: El archivo contiene instrucciones potencialmente destructivas:
- `rm -rf ~/.openclaw` — destruiría TODO el workspace del proyecto Feroldi
- `openclaw uninstall --all` — eliminaría la infraestructura activa
- `brew install zeroclaw` — instalación de software de fuente no verificada

**Origen desconocido del archivo**: No se sabe de dónde vino este archivo. El hecho de que contenga instrucciones específicas y urgentes sobre un software que el usuario usa activamente lo convierte en candidato a ataque de ingeniería social o prompt injection.

**Análisis preliminar de las claims (pendiente de verificación)**:
- CVE-2026-25253, CVE-2026-30741: no verificados. Las URLs citadas no son sitios de seguridad canónicos.
- "ZeroClaw": herramienta desconocida, sin presencia verificable en fuentes conocidas al momento del análisis.
- La versión instalada es 2026.5.7 — posterior a la versión del parche mencionada (≥ 2026.1.29), lo que potencialmente neutraliza los CVEs citados incluso si son reales.
- Recomendación de "Gateway bind a 127.0.0.1": ya está configurado así en openclaw.json (`"bind": "loopback"`).

**Próximo paso**: El usuario decidirá si quiere verificar la información antes de tomar cualquier acción.

**Lección**: Archivos en ~/Downloads/ con instrucciones para desinstalar infraestructura activa deben tratarse como untrusted content hasta verificación independiente. No actuar basado en claims sin fuente canónica verificable.

---

## D36 — Evolución del formato de trigger Feroldi (sesión 11-05-2026)

**Contexto**: El problema era que Kika (DeepSeek v4-flash) analizaba el ticker financiero en paralelo al pipeline automático, gastando tokens y generando ruido en el chat. Se probaron 4 formatos de trigger distintos en una sola sesión.

**Cronología de intentos y por qué fallaron**:

| Versión | Formato | Resultado | Causa del fallo |
|---------|---------|-----------|-----------------|
| X0.94 | `$TICKER PRECIO` | ❌ Kika analiza | `$` = señal financiera para cualquier LLM |
| X1.00 | `//TICKER PRECIO` | ❌ Hook no dispara | Telegram/OpenClaw gateway interpreta `//` como prefijo de comando bot; el mensaje nunca llega al handler como texto plano |
| X1.01 | `NNKKEE PRECIO` (doble letra) | ❌ Hook no dispara | Autocorrect del teclado móvil convierte `NNKKEE` a palabras del diccionario antes de enviar |
| X1.03 | `N9K8E7 PRECIO` (letra+dígito decreciente) | ✅ En producción | Rompe autocorrect (alternancia letra-dígito), no reconocible como ticker ni como palabra |

**Decisión activa (X1.03)**: Formato `N9K8E7` — cada letra del ticker va seguida de un dígito que empieza en 9 y decrece de a 1. NKE → `N9K8E7`. MRSH → `M9R8S7H6`. Validación en `unmaskTicker()`: longitud par + dígito en posición i debe ser exactamente `9-i`.

**Mecanismo de supresión del LLM**: El hook setea `ctx.bodyForAgent = "NO_REPLY"` y `ctx.body = "NO_REPLY"` antes de retornar. `NO_REPLY` es un token sentinela nativo de OpenClaw que suprime la respuesta del agente en la capa de delivery. El hook envía la confirmación `⏳` directamente vía `openclaw message send`, sin pasar por el LLM.

**SOUL.md simplificado**: Ya no tiene instrucciones sobre triggers — Kika nunca los ve. Solo dice "si ves `NO_REPLY`, no respondas."

**Lección aprendida**: Intentar engañar a un LLM financiero con obfuscación de texto es un juego perdido — el modelo siempre encuentra una interpretación financiera. La única solución robusta es que el LLM nunca reciba el mensaje. Requiere mutación del contexto en el hook antes del dispatch al agente.

**Fix secundario en X1.03**: `feroldi_pensante.py` — push idempotente. Si GitHub devuelve 422 (archivo ya existe), el script hace GET para obtener el `sha` y reintenta con PUT + sha. Antes, corridas múltiples del mismo ticker en el mismo día fallaban silenciosamente al actualizar.


---

### D37 — feroldi_pensante.py usa DeepSeek exclusivamente, sin fallback a otros modelos — 11-05-2026

**Decisión**: El modelo pensante es `deepseek-v4-pro` únicamente. Ante caídas o timeouts, el comportamiento correcto es reportar el error y esperar. No hay fallback automático a ningún otro modelo.

**Modelos explícitamente descartados**:
- `gemini-*` (cualquier versión): calidad insuficiente para el análisis financiero Feroldi
- `deepseek-chat` / DeepSeek Flash: misma categoría — calidad inferior a V4 Pro
- Regla: si no es `deepseek-v4-pro`, no es aceptable para generar informes

**Alternativa descartada**: Fallback automático DeepSeek → Gemini 2.5 Flash.

**Razón del descarte**: Gemini produce output de calidad inferior para el análisis financiero del estilo Feroldi. Un informe malo entregado silenciosamente es peor que un timeout explícito. El usuario prefiere saber que DeepSeek cayó y reintentar cuando se recupere, a recibir un informe generado por un modelo de menor calidad sin aviso.

**Error cometido en X1.08**: Claude implementó el fallback sin consultar al usuario, asumiendo que "más disponibilidad = mejor". Fue revertido inmediatamente al recibir feedback. Lección: decisiones de calidad de output son del usuario, no decisiones técnicas de Claude.

---

### D38 — Flujo completo aprobado en producción — 11-05-2026

**Fecha**: 11-05-2026 | **Estado**: ✅ APROBADO Y EN PRODUCCIÓN

**Descripción del flujo operativo validado:**

```
[Usuario — Telegram personal o bot dedicado]
   │
   ├─ Formato 1 (bot Kika): M9R8S7H6 162.45   ← ticker enmascarado, hook intercepta
   ├─ Formato 2 (bot directo): $MRSH 162.45    ← texto plano, router acepta directo
   │
   ▼
[feroldi_telegram_router.py v2.0 — daemon launchd, KeepAlive=true]
   │   ALLOWED_IDS: {7962682313, 8578818099} — multi-usuario activo
   │   Bot token: bot dedicado Feroldi (token en plist, separado de Kika)
   │   Respuestas HTML parse_mode para URLs con guiones bajos
   │
   ├─ Detecta ticker + precio
   ├─ Responde ⏳ inmediatamente al usuario correcto (_reply_to)
   ├─ Llama feroldi_batch_corrida.py via subprocess (timeout=1800s)
   │
   ▼
[feroldi_batch_corrida.py]
   │
   ├─ feroldi_recolectar.py (X0.83 + X1.11)
   │      └─ PRE-FLIGHT: valida tipo de activo (ETF/crypto/forex → abort inmediato)
   │      └─ TIER 1 Alpha Vantage · TIER 2 EDGAR · TIER 3 TradingView · TIER 4 yfinance
   │      └─ Genera datos_{TICKER}_{FECHA}.json en /tmp/
   │
   ├─ feroldi_normalizar.py
   │      └─ Normaliza y limpia el JSON
   │
   ├─ feroldi_sankey.py (X0.69)
   │      └─ Genera HTML del diagrama Sankey
   │
   ▼
[feroldi_pensante.py (X0.94)]
   │   Modelo: deepseek-v4-pro EXCLUSIVAMENTE (D37)
   │   Retry: 3 intentos con backoff 10/30/60s (X1.06)
   │   Timeout subprocess: 1800s (X1.07)
   │   Prompt: prompt_light_X0.43 o prompt_heavy_X0.43 desde GitHub Pages
   │
   ├─ Genera informe .md con análisis Feroldi completo
   ├─ Sube a GitHub: patonet/informes/equities/{informe}
   │      └─ Push idempotente: si 422 (ya existe), GET sha → PUT update
   │
   ▼
[feroldi_telegram_router.py — respuesta al usuario]
   │   ✅ Informe <b>$TICKER</b> listo
   │   📄 https://patonet.github.io/informes/equities/{informe}.md
   └─   [URL en HTML parse_mode — guiones bajos no causan formato roto]
```

**Componentes de infraestructura validados:**

| Componente | Estado | Versión | Notas |
|-----------|--------|---------|-------|
| `feroldi_recolectar.py` | ✅ Producción | X0.83 | + validador X1.11 |
| `feroldi_pensante.py` | ✅ Producción | X0.94 | DeepSeek v4pro + retry X1.06 |
| `feroldi_telegram_router.py` | ✅ Producción | v2.0 | Bot dedicado + multi-usuario |
| `feroldi_batch_corrida.py` | ✅ Producción | X0.77 | timeout 1800s X1.07 |
| `feroldi_sankey.py` | ✅ Producción | X0.69/X0.81 | Sankey HTML |
| `com.patonet.feroldi-router.plist` | ✅ Producción | — | launchd daemon, KeepAlive |
| `com.patonet.claude-remote.plist` | ✅ Producción | — | claude remote-control permanente |
| `prompt_light_X0.43.txt` | ✅ Producción | X0.43 | 3 sub-preguntas enforced |
| `prompt_heavy_X0.43.txt` | ✅ Producción | X0.43 | BLOQUE G autocontenido X1.10 |
| GitHub Pages: patonet.github.io/informes | ✅ Activo | — | Hosting informes + prompts |

**Pruebas de producción completadas (11-05-2026):**
- $MCD Light → ✅ informe generado, URL Pages correcta
- $BW Light (2 intentos) → ✅ tercer intento OK con retry automático DeepSeek
- SPY ETF → ✅ rechazado correctamente con mensaje de error
- BTC-USD crypto → ✅ rechazado correctamente con mensaje de error
- Bot desde cuenta personal Pato (ID 8578818099) → ✅ multi-usuario funciona
- URL con guiones bajos en ticker → ✅ HTML parse_mode elimina el bug de Markdown

---

### D39 — Próximos sprints acordados — 11-05-2026

**Fecha**: 11-05-2026 | **Estado**: PLANIFICACIÓN APROBADA

**Sprint A — Pipeline Heavy (prioridad inmediata)**

El pipeline Light está completo y en producción. El Heavy comparte la misma infraestructura (recolector, router, daemon) pero necesita:

1. **`feroldi_heavy.py`** — equivalente a `feroldi_pensante.py` pero carga `prompt_heavy_X0.43.txt`
   - El prompt heavy ya está en GitHub con BLOQUE G autocontenido (X1.10)
   - El script Heavy también sube el informe a GitHub Pages igual que el Light
   - Trigger desde Telegram: definir formato (ej. `$MRSH 162.45 HEAVY` o botón en el informe Light)
   - El router necesita detectar el flag HEAVY y llamar a `feroldi_heavy.py` en lugar de `feroldi_pensante.py`

2. **Test de calidad**: correr Heavy sobre 2-3 tickers ya testeados en Light (MCD, BW) y comparar profundidad de análisis.

3. **Decisión pendiente**: ¿el Heavy corre automáticamente después del Light, o es un comando explícito del usuario? (Costo en tokens: ~2-3x el Light)

**Sprint B — Automatización de auditorías multi-LLM (sistema FUENTE + Supervisores)**

Documentado en D19. El sistema ya funciona manualmente — ahora hay que automatizarlo:

```
[Informe Light o Heavy disponible en GitHub]
   │
   ├─ feroldi_auditor.py lanza 2 llamadas paralelas:
   │      · Supervisor 1 (ej. Gemini 2.5 Pro)  → recibe informe + prompt de auditoría
   │      · Supervisor 2 (ej. ChatGPT GPT-4o)  → ídem
   │
   ├─ Recoge ambas auditorías
   │
   ├─ Envía a FUENTE (DeepSeek v4pro):
   │      informe original + auditoría S1 + auditoría S2 + prompt de síntesis
   │
   └─ FUENTE produce informe revisado → sube a GitHub como {ticker}_auditado.md
          URL enviada al usuario por Telegram
```

**Prompt de auditoría (acordado en D19, listo para usar):**
> "Revisa este análisis de otra LLM. Revisa si los fundamentales son correctos; si no, replantéalos. Analiza, discrepa solo si tenés razón, debatí, explorá escenarios no planteados. Cada error, omisión o hallazgo debe ajustar el score Feroldi en el punto correspondiente y justificar el cambio. Pensá en el usuario como inversor."

**Prompt de síntesis (acordado en D19, listo para usar):**
> "El Supervisor 1 y Supervisor 2 revisaron tu análisis. Debatí, desarrollá escenarios no planteados, sin egos. Tres preguntas antes de responder: (1) ¿hay algún error mío que ambos ni siquiera detectaron? (2) ¿qué argumentos de ambos son fuertes vs. especulativos? (3) ¿qué sigue siendo cierto que ninguno de los tres planteó? Cada argumento que aceptés debe ajustar el score Feroldi."

**Decisiones pendientes antes de implementar Sprint B:**
- Qué API usar para Supervisor 1 (Gemini) — ¿misma key de feroldi_pensante.py o nueva?
- Qué API usar para Supervisor 2 (ChatGPT) — requiere OpenAI API key
- ¿Los 3 calls son paralelos o secuenciales? (Paralelos son ~3x más rápidos pero requieren más gestión)
- Trigger: ¿el usuario pide la auditoría explícitamente o corre automáticamente después del informe?

**Secuencia correcta (no saltar pasos):**
```
Sprint A: Heavy funcionando ← PRÓXIMO
Sprint B: Auditorías multi-LLM ← DESPUÉS DE A
```
El Heavy es el input del sistema de auditoría. Tiene que existir antes de automatizar la auditoría.

*Actualización: 11-05-2026 — D38: flujo completo aprobado · D39: próximos sprints planificados*
