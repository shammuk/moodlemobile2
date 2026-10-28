# FarmaComparador Sinaloa v0.4

API REST con conectores públicos de búsqueda: Benavides, YZA, Farmacias Guadalajara y Farmacias del Ahorro. Consulta dinámica por producto, sin lista cerrada de productos. Cuatro orígenes configurados; precios y disponibilidad por sucursal NO comprobados.

## Rutas
- GET /health
- GET /api/v1/fuentes
- GET /api/v1/productos (catálogo precargado de competencia comercial)
- GET /api/v1/comparar?producto=Novamil%20Rice&ciudad=Los%20Mochis&estado=Sinaloa&modo=actual
- GET /api/v1/comparar?producto=Nan%20ExpertPro&ciudad=Culiacán&modo=actual
- GET /api/v1/comparar?producto=Novamil%20Rice&modo=demo
- GET /api/v1/comparar.csv?producto=Novamil%20Rice&modo=actual
- GET /openapi.json
- GET /docs

## Cómo interpretar
Modo actual intenta consultar resultados públicos mediante HTML de las cuatro farmacias y devuelve ESTADO POR FUENTE. 'sin_resultados_verificables', bloqueos, fallos o rechazos no se convierten en precios ficticios. Los precios que encuentre reflejan páginas online no validadas para una sucursal local. Caché de 10 minutos. Las búsquedas pueden fallar por robots, cambios de web, geolocalización, bloqueos y rate limits. No se eluden medidas antibot.

Modo demo: mantiene 9 precios históricos de 27/oct/2026 para Novamil Rice, Alula Gold Arroz y Nutramigen, solamente de las tres cadenas originales. Del Ahorro NO estaba en esa tabla.

Para Novamil Rice se incluyen competidores *preclasificados* Alula Gold Arroz y Nutramigen LGG, sin afirmar equivalencia clínica. Para otros términos no se inventan competidores; se muestran coincidencias de nombres. Una solución de inteligencia comercial universal requiere un catálogo de equivalencias y acuerdos o APIs autorizadas con farmacias. El resultado distingue revisiones de código, no confirma precio presencial ni stock.

La infraestructura Render plan free puede tardar en despertar tras inactividad.
