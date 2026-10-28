from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
import csv, io, unicodedata

app=FastAPI(title="FarmaComparador Sinaloa", version="0.3", description="Demo con precios online históricos del 27/oct/2026. NO son precios en vivo ni verificados por sucursal.")
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
    return {"status":"ok","modo":"datos_historicos_no_en_vivo","fecha_revision":"2026-10-27"}
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
@app.get("/api/v1/comparar")
def comparar(producto:str=Query(min_length=2),ciudad:str="Los Mochis",estado:str="Sinaloa",codigo_postal:str|None=None):
    return get_data(producto,ciudad,estado,codigo_postal)
@app.get("/api/v1/comparar.csv")
def csv_export(producto:str=Query(min_length=2),ciudad:str="Los Mochis",estado:str="Sinaloa",codigo_postal:str|None=None):
    filas=get_data(producto,ciudad,estado,codigo_postal)["filas"]
    output=io.StringIO(); w=csv.DictWriter(output,fieldnames=list(filas[0])); w.writeheader();w.writerows(filas)
    return Response("\ufeff"+output.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=farmacomparador.csv"})
@app.get("/",response_class=HTMLResponse,include_in_schema=False)
def inicio():
    return """<!doctype html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FarmaComparador Sinaloa</title><style>body{font:16px system-ui;background:#f0f5f7;color:#203b47;margin:0}header{padding:20px;background:#123e52;color:white}main{max-width:1100px;margin:20px auto;padding:0 16px}.card{background:white;border-radius:14px;padding:20px;margin:18px 0;border:1px solid #d8e4e8}label{display:block;margin:10px 0 5px}select,button{padding:12px;font:inherit;border-radius:8px;border:1px solid #ced9df;margin:0 8px 10px 0}button{background:#087ba6;color:white;border:0;cursor:pointer}.note{background:#fff2d5;border-left:4px solid #c99025;padding:12px}.table{overflow:auto}table{border-collapse:collapse;white-space:nowrap;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #e0e8eb}th{background:#f4f7f8}a{color:#087ba6}</style></head><body><header><h1>FarmaComparador Sinaloa</h1>Comparación DEMO de precios online históricos · 27/oct/2026</header><main><div class="card"><label>Producto de referencia</label><select id="producto"><option>Novamil Rice</option><option>Alula Gold Arroz</option><option>Nutramigen LGG</option></select><label>Ciudad</label><select id="ciudad"><option>Los Mochis</option><option>Culiacán</option><option>Mazatlán</option><option>Guasave</option></select><button onclick="buscar()">Comparar</button><p class="note"><b>Advertencia:</b> los precios NO son en vivo ni están verificados en sucursales de Sinaloa. La ciudad no modifica los precios. Comparables comerciales no implican sustitución clínica.</p><a href="/docs">Documentación API</a> · <a href="/openapi.json">OpenAPI para agentes</a> · <a href="/health">Estado</a></div><div class="card"><h2>Comparación</h2><p id="estado">Cargando...</p><a id="json">Ver JSON</a> · <a id="csv">Descargar CSV</a><div class="table"><table><thead><tr><th>Producto</th><th>Farmacia</th><th>Presentación</th><th>Precio MXN</th><th>Precio/100g</th><th>Fuente</th></tr></thead><tbody id="filas"></tbody></table></div></div></main><script>async function buscar(){const p=new URLSearchParams({producto:document.getElementById('producto').value,ciudad:document.getElementById('ciudad').value,estado:'Sinaloa'});document.getElementById('json').href='/api/v1/comparar?'+p;document.getElementById('csv').href='/api/v1/comparar.csv?'+p;try{const r=await fetch('/api/v1/comparar?'+p),d=await r.json();document.getElementById('estado').textContent=d.total_filas+' precios de ejemplo · fecha de revisión: '+d.fecha_revision;const tb=document.getElementById('filas');tb.replaceChildren();d.filas.forEach(x=>{const tr=document.createElement('tr');[x.producto,x.farmacia,x.presentacion_g+' g',x.precio_mxn.toFixed(2),x.precio_por_100g_mxn.toFixed(2)].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td)});const td=document.createElement('td'),a=document.createElement('a');a.href=x.url_fuente;a.textContent='Ver farmacia';a.target='_blank';a.rel='noopener';td.appendChild(a);tr.appendChild(td);tb.appendChild(tr)})}catch(e){document.getElementById('estado').textContent='Error al consultar datos: '+e.message}}buscar()</script></body></html>"""
