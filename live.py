"""Conectores públicos de precios. Sin credenciales, sin proxies y sin eludir bloqueos."""
import asyncio
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlencode
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

FUENTES = {
    "Benavides": {
        "host": "benavides.com.mx",
        "buscar": "https://www.benavides.com.mx/catalogsearch/result/",
        "params": {"q": "{q}"}, "tipo": "magento",
    },
    "YZA": {
        "host": "yza.mx",
        "buscar": "https://www.yza.mx/on/demandware.store/Sites-YzaMexico-Site/es_MX/Search-UpdateGrid",
        "params": {"q": "{q}", "srule": "position", "start": "0", "sz": "18"}, "tipo": "sfcc",
    },
    "Guadalajara": {
        "host": "farmaciasguadalajara.com",
        "buscar": "https://www.farmaciasguadalajara.com/search",
        "params": {"q": "{q}"}, "tipo": "sfcc",
    },
    "Del Ahorro": {
        "host": "fahorro.com",
        "buscar": "https://www.fahorro.com/catalogsearch/result/",
        "params": {"q": "{q}"}, "tipo": "magento",
    },
}
# Este diccionario es una clasificación comercial REVISADA, no equivalencia médica.
COMPETIDORES_REVISADOS = {
    "novamil rice": ["Alula Gold Arroz", "Nutramigen LGG"],
    "alula gold arroz": ["Novamil Rice", "Nutramigen LGG"],
    "nutramigen lgg": ["Novamil Rice", "Alula Gold Arroz"],
}
# URLs oficiales conocidas; se vuelven a consultar, NO se reutiliza ningún precio almacenado.
FICHAS_CONOCIDAS = {
    "Benavides": {
        "novamil rice": "https://www.benavides.com.mx/novamil-rice-formula-no-lactea-especializada-a-partir-del-nacimiento-hasta-36-meses-400-g",
        "alula gold arroz": "https://www.benavides.com.mx/alula-gold-arroz-formula-no-lactea-para-lactantes-de-0-a-12-meses-400-g",
        "nutramigen lgg": "https://www.benavides.com.mx/nutramigen-formula-para-lactantes-a-partir-del-nacimiento-357-g",
    },
    "YZA": {
        "novamil rice": "https://www.yza.mx/novamil-rice-400g/MXYZ_7501318687332.html",
        "alula gold arroz": "https://www.yza.mx/alula-gold-arroz-premium-400gr/MXYZ_3551102354005.html",
        "nutramigen lgg": "https://www.yza.mx/nutramigen-a-partir-del-nacimiento-357-g/MXYZ_7506205804847.html",
    },
    "Guadalajara": {
        "novamil rice": "https://www.farmaciasguadalajara.com/bebes/especializadas/formula-infantil-novamil-rice-%28a-partir-del-nacimiento%29--400-gr.-1325884.html",
        "alula gold arroz": "https://www.farmaciasguadalajara.com/bebes/especializadas/formula-infantil-alula-gold-arroz-%28edad-0-a-12-meses%29--400-gr.-1388681.html",
        "nutramigen lgg": "https://www.farmaciasguadalajara.com/bebes/especializadas/formula-infantil-nutramigen-con-probiotico-lgg-%28a-partir-del-nacimiento%29--357-gr.-1178024.html",
    },
    "Del Ahorro": {
        "novamil rice": "https://www.fahorro.com/novamil-rice-lata-400-gr.html",
        "alula gold arroz": "https://www.fahorro.com/alula-gold-arroz-premium-formula-400g.html",
        "nutramigen lgg": "https://www.fahorro.com/nutramigen-premium-etapa-1-formula-infantil-especializada-para-lactantes-de-0-a-12-meses-lata-357-gr.html",
    },
}
CACHE = {}
ROBOTS_CACHE = {}
CACHE_SECONDS = 600
ROBOTS_SECONDS = 21600
USER_AGENT = "FarmaComparadorSinaloa/0.4 (demo academica; consultas espaciadas; solo paginas publicas)"
TIMEOUT = httpx.Timeout(connect=3.5, read=6.5, write=5, pool=3)
STOP = {"de", "del", "para", "en", "con", "la", "el", "los", "las", "un", "una", "a", "y", "formula", "infantil", "g", "gr", "gramos"}

def normalizar(t):
    t = "".join(c for c in unicodedata.normalize("NFKD", str(t).casefold()) if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", t))

def tokens(t):
    return {x for x in normalizar(t).split() if x not in STOP and len(x) > 1}

def coincidencia(texto, q):
    candidato = normalizar(texto).replace("expert pro", "expertpro")
    esperado = normalizar(q).replace("expert pro", "expertpro")
    found, wanted = tokens(candidato), tokens(esperado)
    if not wanted:
        return False
    if esperado == "nutramigen lgg" and "nutramigen" in found:
        return True  # Nombre comercial de ficha oficial, sin afirmar equivalencia.
    if len(wanted) <= 3:
        return wanted <= found
    return len(wanted & found) >= max(3, round(len(wanted) * .8))

def host_correcto(url, host):
    try:
        p = urlparse(url)
        return p.scheme == "https" and (p.hostname == host or p.hostname == "www." + host)
    except ValueError:
        return False

def dinero(valor):
    if valor is None:
        return None
    m = re.search(r"(?<!\d)(?:MXN\s*)?\$?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?!\d)", str(valor))
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
        return round(n, 2) if 1 <= n <= 100000 else None
    except ValueError:
        return None

def medida(titulo):
    # El tipo de unidad importa: nunca convertir ml o cápsulas en gramos.
    texto = "".join(c for c in unicodedata.normalize("NFKD", titulo.casefold()) if not unicodedata.combining(c))
    multi = re.search(r"(\d+)\s*(?:latas?|piezas|pzas?|paquetes?)\s*(?:de|x)\s*(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml)\b", texto)
    if multi:
        cantidad, unit = float(multi.group(1))*float(multi.group(2).replace(",",".")), multi.group(3)
        if unit == "kg": return cantidad*1000, "g"
        if unit in ("gr","g"): return cantidad, "g"
        return cantidad, "ml"
    m = re.search(r"(?<![0-9])(\d+(?:[.,]\d+)?)\s*(kg|gr(?:amos?)?|g|ml|l|capsulas?|tabletas?|tabs?|pzas?)\b", texto)
    if not m:
        return None, None
    valor = float(m.group(1).replace(",", "."))
    unidad = m.group(2)
    if unidad == "kg": return int(valor * 1000), "g"
    if unidad in ("gr", "gramo", "gramos", "g"): return valor, "g"
    if unidad == "l": return int(valor * 1000), "ml"
    if unidad == "ml": return valor, "ml"
    return valor, unidad

def extraer_precio(nodo, tipo):
    # Precio final de venta y nunca el precio tachado ni las mensualidades.
    for sel in (".special-price [data-price-amount]", ".price-box [data-price-type='finalPrice'] [data-price-amount]", "[data-price-type='finalPrice'] [data-price-amount]", ".sales .value", ".price-sales", ".special-price .price", ".price-wrapper[data-price-amount]", ".sales [content]", ".price .sales", ".price .value"):
        for el in nodo.select(sel):
            valor = el.get("data-price-amount") or el.get("content") or el.get_text(" ", strip=True)
            n = dinero(valor)
            if n is not None:
                return n
    for sel in ("[itemprop='price']", "meta[property='product:price:amount']", ".price .price-value", ".price-container .price", ".price-final_price .price"):
        for el in nodo.select(sel):
            val = el.get("content") or el.get("data-price-amount") or el.get_text(" ", strip=True)
            n = dinero(val)
            if n is not None:
                return n
    texto = nodo.get_text(" ", strip=True)
    # Último recurso limitado a un contenedor de producto, evita cuotas a meses.
    for pattern in (r"Precio (?:reducido de|oferta)\s*(?:MXN)?\s*\$\s*([\d,.]+)", r"(?:MXN)?\s*\$\s*([\d,.]+)", r"(?:precio|price)\s*:\s*([\d,.]+)"):
        match = re.search(pattern, texto, re.I)
        if match:
            n = dinero(match.group(1))
            if n is not None:
                return n
    return None

def json_ld(soup):
    for script in soup.select("script[type='application/ld+json']"):
        try:
            raw = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        pendientes = [raw]
        while pendientes:
            val = pendientes.pop()
            if isinstance(val, list):
                pendientes.extend(val)
            elif isinstance(val, dict):
                if val.get("@type") in ("Product", "IndividualProduct"):
                    yield val
                for campo in ("@graph", "mainEntity", "itemListElement"):
                    if campo in val:
                        pendientes.append(val[campo])

def extraer_ficha(html, url, host):
    if not host_correcto(url, host):
        return None
    soup = BeautifulSoup(html, "html.parser")
    titulo = (soup.select_one("h1") or soup.select_one("meta[property='og:title']"))
    titulo = ((titulo.get("content") if titulo.name == "meta" else titulo.get_text(" ", strip=True)) if titulo else "")
    precio = None
    for obj in json_ld(soup):
        if not titulo:
            titulo = obj.get("name", "")
        oferta = obj.get("offers", {})
        if isinstance(oferta, list): oferta = oferta[0] if oferta else {}
        if isinstance(oferta, dict):
            precio = dinero(oferta.get("price"))
            if precio is None and isinstance(oferta.get("priceSpecification"), dict):
                precio = dinero(oferta["priceSpecification"].get("price"))
        if precio is not None:
            break
    if precio is None:
        precio = extraer_precio(soup.select_one(".product-info-main") or soup.select_one(".product-detail") or soup.select_one(".product-detail-content") or soup, "ficha")
    return {"producto": titulo.strip()[:180], "precio_mxn": precio, "url_fuente": url} if titulo and precio is not None else None

def extraer_listado(html, url, host, tipo, buscado):
    soup = BeautifulSoup(html, "html.parser")
    nodos = []
    for sel in ("li.product-item", ".product-item", ".product-tile", ".product-tile-wrapper", ".product-grid .product", "article.product", "div.product-tile"):
        candidatos = soup.select(sel)
        if candidatos:
            nodos = candidatos
            break
    resultados = []
    for nodo in nodos[:40]:
        enlace = None
        for sel in (".product-item-link", ".pdp-link a[href]", ".product-name a[href]", ".product-tile__name a[href]", "a.link[href]", "a[href$='.html']", "a[href]"):
            enlace = nodo.select_one(sel)
            if enlace:
                break
        if not enlace:
            continue
        titulo = enlace.get_text(" ", strip=True) or enlace.get("title", "")
        destino = urljoin(url, enlace.get("href", ""))
        if not titulo or not host_correcto(destino, host) or not coincidencia(titulo, buscado):
            continue
        precio = extraer_precio(nodo, tipo)
        if precio is not None:
            resultados.append({"producto": titulo[:180], "precio_mxn": precio, "url_fuente": destino})
    # Algunos listados usan contenedores distintos; no extraer precios de toda la página.
    return resultados[:8]

async def permitido(client, host, destino):
    now = time.monotonic()
    cached = ROBOTS_CACHE.get(host)
    if cached and now - cached[0] < ROBOTS_SECONDS:
        reglas = cached[1]
    else:
        try:
            r = await client.get("https://www." + host + "/robots.txt", follow_redirects=True)
            if r.status_code == 200:
                reglas = RobotFileParser()
                reglas.parse(r.text.splitlines())
            elif r.status_code == 404:
                reglas = True
            else:
                return False, "robots_no_verificable"
            ROBOTS_CACHE[host] = (now, reglas)
        except (httpx.HTTPError, UnicodeError):
            return False, "robots_no_verificable"
    if reglas is True:
        return True, "ok"
    return reglas.can_fetch(USER_AGENT, destino), "ok" if reglas.can_fetch(USER_AGENT, destino) else "prohibido_robots"

async def get_publica(client, url, host):
    if not host_correcto(url, host):
        return None, "dominio_no_permitido", None
    ok, estado = await permitido(client, host, url)
    if not ok:
        return None, estado, None
    try:
        r = await client.get(url, follow_redirects=True)
        if not host_correcto(str(r.url), host):
            return None, "redireccion_externa", r.status_code
        if r.status_code in (401, 403, 429):
            return None, "acceso_restringido", r.status_code
        if r.status_code != 200:
            return None, "http_" + str(r.status_code), r.status_code
        if "html" not in r.headers.get("content-type", ""):
            return None, "respuesta_no_html", r.status_code
        if len(r.content) > 1_200_000:
            return None, "pagina_demasiado_grande", r.status_code
        return r.text, "ok", 200
    except httpx.TimeoutException:
        return None, "timeout", None
    except httpx.HTTPError:
        return None, "error_red", None

def fila(nombre_farmacia, item, consultado, principal, fecha):
    titulo = item["producto"]
    qty, unit = medida(titulo)
    # Presentaciones conocidas: solo si el título del vendedor no la explicita.
    if qty is None and normalizar(consultado) in {"novamil rice", "alula gold arroz", "nutramigen lgg"}:
        qty, unit = (357 if normalizar(consultado) == "nutramigen lgg" else 400), "g"
    precio = item["precio_mxn"]
    return {
        "producto": titulo, "producto_buscado": consultado, "farmacia": nombre_farmacia,
        "precio_mxn": precio, "presentacion_cantidad": qty, "presentacion_unidad": unit,
        "presentacion_g": qty if unit == "g" else None,
        "precio_por_100g_mxn": round(100 * precio / qty, 2) if unit == "g" and qty else None,
        "url_fuente": item["url_fuente"], "fecha_consulta_utc": fecha,
        "origen": "consulta_publica_en_linea", "verificacion_precio_en_vivo": True,
        "precio_sucursal_confirmado": False,
        "comparabilidad": "producto_consultado" if principal else "competidor_comercial_revisado_no_equivalente_clinico",
    }

async def una_busqueda(client, farmacia, consulta, principal, fecha):
    conf = FUENTES[farmacia]
    valores = {k: (consulta if v == "{q}" else v) for k, v in conf["params"].items()}
    url = conf["buscar"] + "?" + urlencode(valores)
    html, estado, http_status = await get_publica(client, url, conf["host"])
    productos = []
    if html:
        productos = extraer_listado(html, url, conf["host"], conf["tipo"], consulta)
    # Si hay ficha oficial conocida se consulta siempre: precios actuales, jamás los guardados.
    ficha_url = FICHAS_CONOCIDAS.get(farmacia, {}).get(normalizar(consulta))
    if ficha_url:
        ficha_html, ficha_estado, ficha_status = await get_publica(client, ficha_url, conf["host"])
        if ficha_html:
            item = extraer_ficha(ficha_html, ficha_url, conf["host"])
            if item and coincidencia(item["producto"], consulta):
                productos = [x for x in productos if x["url_fuente"] != ficha_url]
                productos.insert(0, item)
                estado = "ok"
        elif not productos:
            estado = ficha_estado if estado != "ok" else "sin_precio_verificable"
    dedup = {}
    for p in productos:
        if p.get("precio_mxn") is not None:
            dedup.setdefault(p["url_fuente"], p)
    filas = [fila(farmacia, p, consulta, principal, fecha) for p in list(dedup.values())[:5]]
    return filas, {"farmacia": farmacia, "producto_buscado": consulta,
                  "estado": "ok" if filas else ("sin_resultados_verificables" if estado == "ok" else estado),
                  "filas": len(filas), "url_busqueda": url, "http_status": http_status}

async def consultar(producto, ciudad, estado="Sinaloa", codigo_postal=None, incluir_competidores=True):
    fecha = datetime.now(timezone.utc).isoformat(timespec="seconds")
    consultas = [producto]
    if incluir_competidores:
        consultas += COMPETIDORES_REVISADOS.get(normalizar(producto), [])
    cache_key = (normalizar(producto), normalizar(ciudad), incluir_competidores)
    now = time.monotonic()
    hit = CACHE.get(cache_key)
    if hit and now - hit[0] < CACHE_SECONDS:
        data = dict(hit[1])
        data["cache"] = {"utilizado": True, "edad_segundos": int(now - hit[0]), "ttl_segundos": CACHE_SECONDS}
        return data
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "es-MX,es;q=0.9"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers, limits=httpx.Limits(max_connections=12)) as client:
        tareas = [una_busqueda(client, farmacia, q, q == producto, fecha)
                  for farmacia in FUENTES for q in consultas]
        resultados = await asyncio.gather(*tareas, return_exceptions=True)
    filas, estados = [], []
    for i, result in enumerate(resultados):
        if isinstance(result, BaseException):
            farmacia = list(FUENTES)[i // len(consultas)]
            estados.append({"farmacia": farmacia, "producto_buscado": consultas[i % len(consultas)],
                            "estado": "error_conector", "filas": 0})
        else:
            products, status = result
            filas.extend(products)
            estados.append(status)
    filas.sort(key=lambda r: (r["comparabilidad"] != "producto_consultado", r["producto_buscado"], r["precio_mxn"]))
    data = {
        "version": "0.4", "consulta": {"producto": producto, "ciudad": ciudad,
            "estado": estado, "codigo_postal": codigo_postal, "incluir_competidores": incluir_competidores},
        "modo": "actual", "fecha_consulta_utc": fecha, "total_filas": len(filas), "filas": filas,
        "fuentes": estados,
        "competidores_revisados": consultas[1:],
        "nota_competidores": ("Solo los competidores preclasificados tienen búsqueda ampliada; para otros productos se consulta el nombre exacto. "
             "No se infiere equivalencia clínica."),
        "cobertura_local": "no_verificada",
        "advertencias": [
            "Precios publicados online al momento de una consulta HTTP; no representan existencias ni precios de sucursales de Sinaloa.",
            "Si una farmacia rechaza la consulta o no ofrece precio verificable se informa en fuentes, sin inventar cifras.",
            "Los productos comparados comercialmente no son sustitutos clínicos.",
        ],
        "cache": {"utilizado": False, "ttl_segundos": CACHE_SECONDS},
    }
    if len(CACHE) > 80:
        CACHE.clear()
    CACHE[cache_key] = (now, data)
    return data
