// El front lo sirve el mismo uvicorn que la API, que cuelga de /api. Si algun
// dia el front se sirve aparte (nginx, Railway), aca va la URL del backend.
window.__APP_CONFIG__ = {
  apiUrl: '/api/'
};
