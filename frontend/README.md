# ShopPilot AI frontend

Run `npm install` and `npm run build` to create the browser bundle at `js/app.js`.
The HTML files, `css/`, `js/`, `img/`, and `fixtures/` form a static export.

The frontend uses same-origin `/api` and `/media` paths by default. For another
deployment, set `window.SHOPPILOT_API_BASE_URL` in `js/runtime-config.js` to the
public API origin or path prefix before loading the bundle. Cross-origin use
requires the server to allow credentialed CORS. This setting is public: never
put a token or provider key in it. In Sites the same-origin proxy needs no setting.
