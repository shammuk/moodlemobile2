from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
import csv, io, unicodedata
from live import consultar, FUENTES, COMPETIDORES_REVISADOS, normalizar
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI(title="FarmaComparador Sinaloa", version="0.4", description="Demo con precios online históricos del 27/oct/2026. NO son precios en vivo ni verificados por sucursal.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app_data=[
("Novamil Rice",400,"Benavides",510.00,"https://www.benavides.com.mx/novamil-rice-formula-no-lactea-especializada-a-partir-del-nacimiento-hasta-36-meses-400-g"),
("Novamil Rice",400,"YZA",510.00,"https://www.yza.mx/novamil-rice-400g/MXYZ_7501318687332.html"),
("Novamil Rice",400,"Guadalajara",509.90,"https://www.farmaciasguadalajara.com/bebes/especializadas/formula-infantil-novamil-rice-%28a-partir-del-nacimiento%29--400-gr.-1325884.html"),
("Alula Gold Arroz",400,"Benavides",439.00,"https://www.benavides.com.mx/alula-gold-arroz-formula-no-lactea-para-lactantes-de-0-a-12-meses-400-g"),
("Alula Gold Arroz",400,"YZA",415.00,"https://www.yza.mx/alula-gold-arroz-premium-400gr/MXYZ_3551102354005.html"),
("Alula Gold Arroz",400,"Guadalajara",438.90,"https://www.farmaciasguadalajara.com/bebes/especializadas/formula-infantil-alula-gold-arroz-%28edad-0-a-12-meses%29--400-gr.-1388681.html"),
("Nutramigen LGG",357,"Benavides",527.00,"https://www.benavides.com.mx/nutramigen-formula-para-lactantes-a-partir-del-nacimiento-357-g"),
("Nutramigen LGG",357,"YZA",543.00,"https://www.yza.mx/nutramigen-a-partir-del-nacimiento-357-g/MXYZ_7506205804847.html"),
("Nutramigen LGG",357,"Guadalajara",558.00,"https://www.farmaciasguadalajara.com/bebes/especializadas/formula-infantil-nutramigen-con-probiotico-lgg-%28a-partir-del-nacimiento%29--357-gr.-1178024.html")]
def norm(t):
    return "".join(c for c in unicodedata.normalize("NFKD",t.casefold()) if not unicodedata.combining(c)).strip()
@app.get("/health")
def health():
    return {"status":"ok","version":"0.4","modos":["actual","demo"],"precio_sucursal_verificado":False}
@app.get("/api/v1/productos")
def productos():
    return {"productos":[{"nombre":"Novamil Rice","presentacion_g":400},{"nombre":"Alula Gold Arroz","presentacion_g":400},{"nombre":"Nutramigen LGG","presentacion_g":357}],"fecha_revision":"2026-10-27"}
def get_data(producto,ciudad,estado,codigo_postal):
    if norm(estado)!="sinaloa": raise HTTPException(422,"Esta demo solo cubre Sinaloa")
    if not ciudad.strip(): raise HTTPException(422,"Falta ciudad")
    if codigo_postal and (not codigo_postal.isdigit() or len(codigo_postal)!=5): raise HTTPException(422,"Codigo postal invalido")
    if norm(producto) not in [norm(x) for x in ("Novamil Rice","Alula Gold Arroz","Nutramigen LGG")]: raise HTTPException(404,"Producto no incluido en la demo")
    filas=[{"producto":p,"presentacion_g":g,"farmacia":f,"precio_mxn":precio,"precio_por_100g_mxn":round(precio*100/g,2),"url_fuente":url,"fecha_revision":"2026-10-27","precio_sucursal_confirmado":False,"verificacion_precio_en_vivo":False,"comparabilidad":"producto_consultado" if norm(p)==norm(producto) else "competidor_comercial_no_sustituto_clinico"} for p,g,f,precio,url in app_data]
    filas.sort(key=lambda x:(norm(x["producto"])!=norm(producto),x["producto"],x["precio_mxn"]))
    return {"consulta":{"producto":producto,"ciudad":ciudad,"estado":"Sinaloa","codigo_postal":codigo_postal},"total_filas":len(filas),"filas":filas,"fecha_revision":"2026-10-27","tipo_resultado":"historico_online_no_local","advertencias":["Precios historicos online NO verificados por sucursal o ciudad; NO en vivo.","Cambiar ciudad no afecta el precio en esta demo.","No hay garantia de equivalencia clinica entre formulas."]}

@app.get("/api/v1/fuentes", summary="Fuentes públicas de la búsqueda")
def fuentes():
    return {"version":"0.4","cadenas":list(FUENTES.keys()),"cantidad":len(FUENTES),
            "nota":"Fuentes consultables; la disponibilidad de datos depende de cada portal. Los precios NO son por sucursal."}

@app.get("/api/v1/comparar", summary="Buscar producto de manera dinámica en cuatro farmacias")
async def comparar(producto:str=Query(min_length=2,max_length=90),ciudad:str=Query(default="Los Mochis",max_length=70),
                   estado:str="Sinaloa",codigo_postal:str|None=Query(default=None, max_length=5),
                   modo:str=Query(default="actual",pattern="^(actual|demo)$"),
                   incluir_competidores:bool=True):
    if normalizar(estado) != "sinaloa":
        raise HTTPException(status_code=422, detail="Esta versión está destinada a Sinaloa")
    if not ciudad.strip():
        raise HTTPException(status_code=422, detail="Se requiere ciudad")
    if codigo_postal and (len(codigo_postal)!=5 or not codigo_postal.isdigit()):
        raise HTTPException(status_code=422,detail="Código postal no válido")
    if modo=="demo":
        d = get_data(producto,ciudad,estado,codigo_postal)
        for x in d["filas"]:
            x.update(origen="historico_manual",fecha_precio="2026-10-27",
                     verificacion_precio_en_vivo=False,precio_sucursal_confirmado=False)
        d.update(version="0.4",modo="demo",fuentes=[],cobertura_local="no_verificada",
                 cadenas=list(FUENTES.keys()),advertencias=[
                 "Datos históricos de demostración del 27/oct/2026: NO se consultaron precios actuales.",
                 "La farmacia Del Ahorro no formó parte de la tabla de precios históricos.",
                 "No son precios por sucursal. Los productos no son necesariamente sustitutos clínicos."])
        return d
    return await consultar(producto,ciudad,estado,codigo_postal,incluir_competidores)

@app.get("/api/v1/comparar.csv", summary="Exportar resultados actuales o históricos")
async def csv_export(producto:str=Query(min_length=2,max_length=90),ciudad:str="Los Mochis",
                    estado:str="Sinaloa",codigo_postal:str|None=None,
                    modo:str=Query(default="actual",pattern="^(actual|demo)$"),
                    incluir_competidores:bool=True):
    data=await comparar(producto,ciudad,estado,codigo_postal,modo,incluir_competidores)
    filas=data["filas"]
    columnas=["producto","producto_buscado","farmacia","precio_mxn","presentacion_g",
              "precio_por_100g_mxn","url_fuente","origen","fecha_consulta_utc",
              "fecha_precio","verificacion_precio_en_vivo","precio_sucursal_confirmado","comparabilidad"]
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=columnas,extrasaction="ignore")
    writer.writeheader()
    for x in filas:
        writer.writerow(x)
    return Response("\ufeff"+output.getvalue(),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":"attachment; filename=farmacomparador-v04.csv"})

@app.get("/",response_class=HTMLResponse,include_in_schema=False)
def inicio():
    return """<!doctype html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FarmaComparador Sinaloa v0.4</title>
<style>
:root{color-scheme:light}*{box-sizing:border-box}body{font:15px system-ui,sans-serif;background:#eef3f6;color:#18394a;margin:0}header{background:linear-gradient(105deg,#09384a,#126784);padding:28px 5%;color:white}header h1{font-size:26px;margin:0 0 4px}header p{margin:0;opacity:.86}main{max-width:1130px;margin:auto;padding:18px}section{background:white;padding:20px;margin:14px 0;border-radius:15px;box-shadow:0 1px 4px #144e5a19}h2{font-size:19px;margin:0 0 13px}.controls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}label{display:block;font-size:13px;color:#536974;font-weight:600;margin-bottom:5px}input,select{width:100%;padding:12px;font:inherit;color:#18394a;border:1px solid #b9cdd4;border-radius:8px}input[type=checkbox]{width:auto}button{background:#087ba6;color:white;padding:11px 17px;border:0;border-radius:8px;font-size:15px;cursor:pointer}button:disabled{opacity:.6}.check{display:flex;gap:10px;align-items:center;margin:13px 0}.note{background:#fff6df;border-left:4px solid #c59430;padding:12px;margin:12px 0;font-size:13px;line-height:1.5}a{color:#087ba6}a:focus{outline:2px solid #087ba6} .actions{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin:12px 0}.summary{font-size:14px;color:#445c6a}.table{overflow-x:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px}th,td{text-align:left;padding:11px;border-bottom:1px solid #e3e9ed}th{background:#f4f8fa}.badge{display:inline-block;background:#e5f4f1;color:#17775f;border-radius:6px;padding:4px 8px}.muted{color:#6a818b} .errors{margin-top:10px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px} .source{font-size:12px;color:#4d6570;padding:5px 7px;background:#f3f6f8;border-radius:5px}footer{text-align:center;color:#718991;font-size:12px;padding:20px}@media(max-width:660px){.controls{grid-template-columns:1fr}.errors{grid-template-columns:1fr}header h1{font-size:23px}}
</style></head>
<body><header><h1>FarmaComparador Sinaloa</h1><p>v0.4 · Búsqueda pública de precios online · Cuatro cadenas</p></header><main>
<section><h2>Buscar productos</h2><div class="controls"><div><label for="producto">Producto (nombre libre)</label><input id="producto" value="Novamil Rice" maxlength="90" placeholder="Ej. Nan ExpertPro"></div><div><label for="ciudad">Ciudad de referencia</label><select id="ciudad"><option>Los Mochis</option><option>Culiacán</option><option>Mazatlán</option><option>Guasave</option><option>Navolato</option><option>El Fuerte</option></select></div><div><label for="modo">Tipo de consulta</label><select id="modo"><option value="actual">Consultar sitios públicos</option><option value="demo">Demo histórica (3 productos)</option></select></div></div>
<div class="check"><input type="checkbox" id="competidores" checked><label for="competidores">Incluir competidores comerciales preclasificados (si existen)</label></div>
<div class="actions"><button id="buscar" onclick="buscar()">Consultar precios</button><a href="/docs">Documentación API</a><a href="/openapi.json">OpenAPI para el agente</a><a href="/api/v1/fuentes">Fuentes</a></div>
<div class="note"><b>Alcance:</b> los precios online no confirman precio o inventario de ninguna sucursal de Sinaloa. Las fuentes pueden rechazar consultas. Los productos comerciales comparados no son necesariamente sustitutos médicos. En modo demo se usan datos históricos del 27/oct/2026.</div>
</section>
<section><h2>Resultados</h2><p id="resumen" class="summary" role="status">Elige un producto y consulta.</p><div class="actions"><a id="json" target="_blank" rel="noopener">Ver JSON</a><a id="csv">Descargar CSV</a><button onclick="copiar()">Copiar dirección de API</button></div><div class="table"><table><thead><tr><th>Producto</th><th>Farmacia</th><th>Presentación</th><th>Precio MXN</th><th>Precio/100 g</th><th>Origen</th><th>Fuente</th></tr></thead><tbody id="filas"></tbody></table></div><h2 style="margin-top:20px">Estado de las fuentes</h2><div id="fuentes" class="errors"></div></section>
</main><footer>Proyecto de demostración. No se garantiza disponibilidad, exactitud ni validez clínica de sustituciones.</footer>
<script>
let ultima='';
function parametros(){return new URLSearchParams({producto:document.getElementById('producto').value.trim(),ciudad:document.getElementById('ciudad').value,estado:'Sinaloa',modo:document.getElementById('modo').value,incluir_competidores:document.getElementById('competidores').checked})}
function celda(tr,valor){let td=document.createElement('td');td.textContent=valor===null||valor===undefined?'—':String(valor);tr.appendChild(td);return td}
function copiar(){if(ultima&&navigator.clipboard){navigator.clipboard.writeText(ultima).then(()=>alert('Dirección copiada')).catch(()=>alert('Abre el enlace JSON para copiar la URL'))}}
async function buscar(){let p=parametros(),producto=document.getElementById('producto').value.trim();if(producto.length<2){document.getElementById('resumen').textContent='Escribe al menos dos caracteres';return}
const url='/api/v1/comparar?'+p;ultima=location.origin+url;document.getElementById('json').href=url;document.getElementById('csv').href='/api/v1/comparar.csv?'+p;let btn=document.getElementById('buscar');btn.disabled=true;document.getElementById('resumen').textContent='Consultando farmacias; algunas pueden tardar o bloquear solicitudes...';
try{let r=await fetch(url),d=await r.json();if(!r.ok)throw Error(d.detail||'Error HTTP '+r.status);let es=d.filas||[];document.getElementById('resumen').textContent=es.length+' precios documentados · '+(d.modo==='demo'?'históricos 27/oct/2026':'consulta pública '+(d.fecha_consulta_utc||'')+(d.cache&&d.cache.utilizado?' (caché)':''))+(es.length===0?' · No se obtuvieron precios verificables. Revisa el estado de las fuentes.':'');
let tb=document.getElementById('filas');tb.replaceChildren();es.forEach(x=>{let tr=document.createElement('tr');celda(tr,x.producto);celda(tr,x.farmacia);celda(tr,x.presentacion_g?x.presentacion_g+' g':x.presentacion_cantidad?x.presentacion_cantidad+' '+(x.presentacion_unidad||''):'—');celda(tr,x.precio_mxn==null?'—':'$'+Number(x.precio_mxn).toFixed(2));celda(tr,x.precio_por_100g_mxn==null?'—':'$'+Number(x.precio_por_100g_mxn).toFixed(2));celda(tr,x.origen==='historico_manual'?'Histórico':'Sitio consultado');let td=tr.insertCell(),a=document.createElement('a');a.href=x.url_fuente;a.target='_blank';a.rel='noopener';a.textContent='Ver farmacia';td.appendChild(a);tb.appendChild(tr)});
let s=document.getElementById('fuentes');s.replaceChildren();if(d.fuentes&&d.fuentes.length){d.fuentes.forEach(f=>{let e=document.createElement('div');e.className='source';e.textContent=f.farmacia+' · '+f.producto_buscado+' · '+f.estado+(f.http_status?' (HTTP '+f.http_status+')':'');s.appendChild(e)})}else{s.textContent=d.modo==='demo'?'Consulta de demostración: sin visitas a las farmacias.':'Sin información de fuentes.'}}
catch(e){document.getElementById('resumen').textContent='No se pudo consultar: '+e.message}finally{btn.disabled=false}}
document.getElementById('producto').addEventListener('keydown',e=>{if(e.key==='Enter')buscar()});buscar();
</script></body></html>"""
